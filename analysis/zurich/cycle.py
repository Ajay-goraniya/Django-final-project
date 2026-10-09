"""ONE-STEP restart: clean boundary -> stop -> deploy -> start -> audited arm -> verify, in a single run.
Standing rule (Z-13): never end a tool call with a live engine restarted and master off.
Usage: cycle.py <staged_dir> <commit> [max_wait_s]
Reads ~/polymarket_v12/deploy.env into the child env and for the arm; nothing from it is printed.
"""
import os, sys, json, time, signal, sqlite3, hashlib, subprocess, urllib.request, base64, datetime as dt

LIVE = '/home/ubuntu/pm_paper_zurich'
REPO = '/home/ubuntu/claude-work/repo'
DB = 'polymarket_v12_live_zurich_2.sqlite3'
staged, commit = sys.argv[1], sys.argv[2]
max_wait = int(sys.argv[3]) if len(sys.argv) > 3 else 420
f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%H:%M:%S')
ro = lambda: sqlite3.connect(f'file:{LIVE}/{DB}?mode=ro', uri=True)

env = dict(os.environ)
for line in open('/home/ubuntu/polymarket_v12/deploy.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); env[k.strip()] = v.strip().strip('"').strip("'")

def pid_of():
    out = subprocess.run(['pgrep', '-f', f'btc_model_v12_polymarket.py --live'], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None

# 1. clean boundary
c = ro(); t0 = time.time()
while time.time() - t0 < max_wait:
    now = time.time(); into = now - int(now // 300) * 300
    fly = c.execute("select count(*) from orders where status in ('SUBMITTING','PENDING')").fetchone()[0]
    ung = c.execute("select count(*) from orders where status='FILLED' and epoch not in (select epoch from results)").fetchone()[0]
    vs = c.execute('select cash,open_value from venue_state order by ts desc limit 1').fetchone()
    if fly == 0 and ung == 0 and (vs[1] or 0) == 0 and into <= 60:
        print(f'CLEAN {f(now)} sec_into_candle {int(into)} equity {vs[0]+(vs[1] or 0):.2f}'); break
    time.sleep(5)
else:
    print(f'ABORT: no clean moment in {max_wait}s (fly {fly} ung {ung} open {vs[1]}); engine untouched'); sys.exit(1)
c.close()

# 2. stop
old = pid_of()
if old:
    os.kill(old, signal.SIGTERM)
    for _ in range(30):
        try: os.kill(old, 0); time.sleep(1)
        except ProcessLookupError: break
    print(f'STOPPED pid {old} at {f(time.time())}')

# 3. deploy files + verify hashes
names = [l.split()[1] for l in open(f'{staged}/SHA256SUMS.txt')]
for n in names + ['SHA256SUMS.txt']:
    subprocess.run(['cp', f'{staged}/{n}', f'{LIVE}/{n}'], check=True)
subprocess.run(['rm', '-rf', f'{LIVE}/__pycache__'], check=True)
ok = sum(1 for n in names
         if hashlib.sha256(open(f'{LIVE}/{n}', 'rb').read()).hexdigest() ==
            hashlib.sha256(subprocess.run(['git', '-C', REPO, 'show', f'{commit}:learner/v12_2/{n}'],
                                          capture_output=True, check=True).stdout).hexdigest())
print(f'DEPLOYED {ok}/{len(names)} files == git show {commit}')
if ok != len(names): print('ABORT: hash mismatch, not starting'); sys.exit(1)

# 4. start
argv = [f'{LIVE}/.venv/bin/python', '-u', 'btc_model_v12_polymarket.py', '--live', '--mode', 'pnl',
        '--capital', '50', '--host', '0.0.0.0', '--port', '8787', '--db', DB, '--quote-age-ms', '2000']
log = open(f'{LIVE}/live.log', 'ab')
p = subprocess.Popen(argv, cwd=LIVE, env=env, stdout=log, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
print(f'STARTED pid {p.pid} at {f(time.time())}')

# 5. audited arm, retried until the dashboard answers
auth = base64.b64encode(('ajay:' + env['DASHBOARD_PASSWORD']).encode()).decode()
body = json.dumps({'confirmed': True, 'system': {'manual_enabled': True}}).encode()
armed = False
for i in range(40):
    time.sleep(3)
    if p.poll() is not None: print(f'ABORT: engine exited rc={p.returncode}'); sys.exit(1)
    req = urllib.request.Request('http://127.0.0.1:8787/api/controls/apply', data=body,
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if json.loads(r.read()).get('ok'): armed = True; print(f'ARMED via /api/controls/apply at {f(time.time())} (attempt {i+1})'); break
    except Exception as e:
        if i in (9, 19, 29): print(f'  arm retry {i+1}: {type(e).__name__}')
print('ARM RESULT:', 'ok' if armed else '*** FAILED - MASTER STILL OFF, ACT NOW ***')

# 6. verify in the same output
c = ro(); m = dict(c.execute('select k,v from meta').fetchall())
vs = c.execute('select ts,cash,open_value from venue_state order by ts desc limit 1').fetchone()
print(f"VERIFY build {m.get('build')} master {m.get('master')} halt {m.get('halt')} "
      f"ef {m.get('ef_enabled')} ef_cash_floor {m.get('ef_cash_floor')} next_stake {m.get('next_stake')}")
if vs: print(f'VERIFY equity {vs[1]+(vs[2] or 0):.2f} (cash {vs[1]:.2f} + open {vs[2]:.2f}) @ {f(vs[0])}')
for ts, d in c.execute("select ts,detail from diagnostics where detail like '%control_write%' order by ts desc limit 10"):
    j = json.loads(d)
    if j.get('key') == 'master':
        print(f"VERIFY master audit {f(ts)} {j.get('old')} -> {j.get('new')} | {j['stack'][-1]}"); break
print('RESULT:', 'OK - restarted and armed in one step' if (armed and m.get('master') == 'true') else '*** NOT ARMED ***')
