# AWS-authored, ran ONCE on the AWS Mumbai box 01:02:49-01:03:22 UTC 2026-09-14 on the user's explicit
# instruction ("fresh journal (archive the old one)" + "arm master now"). Committed unedited by V from the
# AWS session's verbatim message. Its only writes to the live journal are the single Journal.set_many()
# at the end, through the deployed 12.8.8 module. Contains no secret values (env var NAMES only).
import os, signal, subprocess, sys, time, sqlite3, json, shutil, datetime
DEP='/home/ubuntu/polymarket_v12'; PY=os.path.join(DEP,'venv/bin/python')
DB=os.path.join(DEP,'polymarket_v12_live_8787.sqlite3')
NEED=['POLYMARKET_PRIVATE_KEY','POLYMARKET_WALLET_ADDRESS','RELAYER_API_KEY','RELAYER_API_KEY_ADDRESS','DASHBOARD_PASSWORD']
# settings to carry across; history//window keys deliberately NOT carried
KEEP=['ef_enabled','main_enabled','reversal_enabled','next_stake','stake_settings','ev_settings',
      'rules','sx_enabled','tp','sl']
pid=int(subprocess.run(['pgrep','-f','btc_model_v12_polymarket.py .*--live'],capture_output=True,text=True).stdout.split()[0])
env={}
for part in open(f'/proc/{pid}/environ','rb').read().split(b'\0'):
    if b'=' in part:
        k,_,v=part.partition(b'='); env[k.decode()]=v.decode('utf-8','surrogateescape')
argv=[a.decode() for a in open(f'/proc/{pid}/cmdline','rb').read().split(b'\0') if a]
assert os.readlink(f'/proc/{pid}/cwd')==DEP and '--live' in argv
if [n for n in NEED if not env.get(n)]: sys.exit('ABORT: credentials incomplete, engine NOT stopped')
print('pid',pid,'credentials 5/5 present')

c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
old=dict(c.execute('select k,v from meta'))
open_pos=c.execute("select count(*) from orders where status='FILLED' and epoch not in (select epoch from results)").fetchone()[0]
counts={t:c.execute(f'select count(*) from {t}').fetchone()[0] for t in ('orders','fills','results','signals','candles','diagnostics')}
c.close()
print('old journal counts:',counts,'| open positions:',open_pos)
if open_pos: sys.exit('ABORT: open position, journal NOT archived')
carry={k:json.loads(old[k]) for k in KEEP if k in old}
print('settings carried over:',{k:(v if k!='stake_settings' else 'fixed 3.0') for k,v in carry.items()})

ARCH='/home/ubuntu/polymarket_v12_journal_archive_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(ARCH)
os.kill(pid,signal.SIGTERM)
for _ in range(60):
    if not os.path.exists(f'/proc/{pid}'): break
    time.sleep(.5)
else: os.kill(pid,signal.SIGKILL); time.sleep(2)
print('stopped',datetime.datetime.now(datetime.UTC).strftime('%F %T'))
for suf in ('','-wal','-shm','.lock'):
    p=DB+suf
    if os.path.exists(p): shutil.move(p,os.path.join(ARCH,os.path.basename(p)))
print('journal archived ->',ARCH,'| live file present now:',os.path.exists(DB))

log=open(os.path.join(DEP,'engine.log'),'ab')
p=subprocess.Popen([PY]+argv[1:],cwd=DEP,env=env,stdout=log,stderr=log,start_new_session=True,close_fds=True)
time.sleep(30)
if p.poll() is not None:
    print('!! FAILED TO START, restoring old journal')
    for f in os.listdir(ARCH): shutil.move(os.path.join(ARCH,f),os.path.join(DEP,f))
    p=subprocess.Popen([PY]+argv[1:],cwd=DEP,env=env,stdout=log,stderr=log,start_new_session=True,close_fds=True)
    time.sleep(25); print('rollback alive:',p.poll() is None); sys.exit('FAILED, journal restored')
print('alive, new pid',p.pid,datetime.datetime.now(datetime.UTC).strftime('%F %T'))
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
fresh=dict(c.execute('select k,v from meta')); nc={t:c.execute(f'select count(*) from {t}').fetchone()[0] for t in ('orders','fills','results','signals','candles','diagnostics')}
c.close()
print('FRESH journal counts:',nc)
print('FRESH defaults:',{k:fresh.get(k) for k in ('build','lane','master','halt','ef_enabled','main_enabled','reversal_enabled','next_stake','ev_settings')})

sys.path.insert(0,DEP)
import poly_core
j=poly_core.Journal(DB,json.loads(fresh['lane']),json.loads(fresh['model_hash']))
updates=dict(carry); updates['master']=True
j.set_many(updates)
time.sleep(3)
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
after=dict(c.execute('select k,v from meta'))
print('AFTER ',{k:after.get(k) for k in ('build','lane','master','halt','ef_enabled','main_enabled','reversal_enabled','next_stake','ev_settings','stake_settings')})
print('audit rows:',[r[0][:220] for r in c.execute("select detail from diagnostics where detail like '%control_write%' order by rowid").fetchall()])
c.close()
print('DONE',datetime.datetime.now(datetime.UTC).strftime('%F %T'))
