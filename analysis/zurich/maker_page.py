#!/usr/bin/env python3
"""MAKER-ONLY page for the Zurich maker probe. STRICTLY READ-ONLY, SEPARATE PROCESS.

Owner, 10-01 12:40, on the :8787 screenshot: "Zurich is confusing, for a maker, new design needed".
He is right, and the reason is structural rather than cosmetic: :8787's EF card and this probe are
two disjoint populations that happen to sit on one wallet.

    :8787 EF card   29 CANDLES (not fills) of the ENGINE's own LIVE EF orders, 09-28 19:45 ->
                    09-30 07:40, graded on results.actual vs the SIGNAL's side. Frozen: the engine's
                    last live EF fill was 09-30 07:40 and master has been off since.
    this probe      fills over its own candles, 09-30 17:00 ->, graded on the VENUE's resolution.
    overlap         ZERO candles. The card has never shown the probe and structurally cannot - the
                    probe writes its own sqlite and the dashboard never reads it.

So this page exists to stop one instrument being read as the other. It shows the probe and nothing
else: no MAIN / REVERSAL / COMBINED shadow cards.

WHY A SEPARATE SERVER. V's brief says do not restart or touch the engine or the probe. Adding a
/maker route to poly_dashboard.py would need the engine restarted to load it, so that is out. This
binds its own port, opens every database read-only (mode=ro), and holds no handle to anything the
engine or the probe writes. It cannot place, cancel or modify an order: it imports no broker.
"""
import base64, hmac, json, os, sqlite3, subprocess, time, datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT   = int(os.environ.get('MAKER_PAGE_PORT', '8788'))
DB     = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
FLAG   = '/home/ubuntu/maker_probe/ENABLED'
PIDF   = '/home/ubuntu/maker_probe/watch.args'
REPO   = '/home/ubuntu/claude-work/repo'
BN_DB  = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
GAMMA  = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
PW     = os.environ.get('DASHBOARD_PASSWORD', '')
DAY_STOP, LIFE_STOP, BAR = -10.0, -20.0, 60
VOL_CUT = 0.304          # the frozen calm cut; same number poly_fav uses


def q(sql, args=(), db=DB, one=False):
    try:
        c = sqlite3.connect(f'file:{db}?mode=ro', uri=True); c.row_factory = sqlite3.Row
        r = c.execute(sql, args).fetchall(); c.close()
        return (dict(r[0]) if r else None) if one else [dict(x) for x in r]
    except Exception:
        return None if one else []


def probe_pid():
    try:
        with open(PIDF) as f: return int(f.read().split()[0])
    except Exception: return None


def alive(pid):
    if not pid: return False
    try: os.kill(pid, 0); return True
    except PermissionError: return True
    except OSError: return False


def build_hash():
    """The last commit that TOUCHED maker_probe.py - NOT repo HEAD.

    First version printed HEAD, which read "build 54ac2d7" while the probe was actually running
    f770acf: HEAD had moved on for an unrelated report commit. Labelling one thing with another
    thing's identifier is the exact confusion this page exists to end, so it reports the commit that
    owns the running code, and says so when the file on disk no longer matches it."""
    try:
        h = subprocess.run(['git', '-C', REPO, 'log', '-1', '--format=%h', '--',
                            'analysis/zurich/maker_probe.py'],
                           capture_output=True, text=True, timeout=5).stdout.strip()
        same = subprocess.run(['git', '-C', REPO, 'show', f'{h}:analysis/zurich/maker_probe.py'],
                              capture_output=True, timeout=5).stdout
        live = open('/home/ubuntu/pm_paper_zurich/maker_probe.py', 'rb').read()
        return (h or 'unknown') + ('' if same == live else ' (FILE ON DISK DIFFERS)')
    except Exception:
        return 'unknown'


def vol_now(epoch):
    """1 s trailing-5-min log-return vol before the open, x1e4 - the frozen definition, read-only."""
    import math
    try:
        c = sqlite3.connect(f'file:{BN_DB}?mode=ro', uri=True)
        raw = {}
        for tms, px in c.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                                 "AND ts_ms>=? AND ts_ms<?", ((epoch - 400) * 1000, epoch * 1000)):
            raw[int(tms) // 1000] = float(px)
        c.close()
        w = [raw[t] for t in range(epoch - 300, epoch) if t in raw]
        if len(w) < 240: return None
        m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
        mu = sum(m) / len(m)
        return math.sqrt(sum((x - mu) ** 2 for x in m) / len(m)) * 1e4
    except Exception:
        return None


def hhmm(ts): return dt.datetime.fromtimestamp(ts, dt.UTC).strftime('%H:%M')
def hms(ts):  return dt.datetime.fromtimestamp(ts, dt.UTC).strftime('%m-%d %H:%M:%S')


def state():
    now = time.time(); ep = int(now // 300) * 300; sec = int(now - ep)
    pid = probe_pid(); on = os.path.exists(FLAG) and alive(pid)
    fills = q('SELECT * FROM fills ORDER BY fill_ts_ms DESC')
    today = time.strftime('%Y-%m-%d', time.gmtime(now))
    tp = sum(f['pnl'] or 0 for f in fills if f['utc_day'] == today)
    lp = sum(f['pnl'] or 0 for f in fills)
    w  = sum(1 for f in fills if (f['pnl'] or 0) > 0)
    l  = sum(1 for f in fills if (f['pnl'] or 0) < 0)
    pend = sum(1 for f in fills if f['pnl'] is None)
    # resting order: an OPEN live row in this candle with no cancel and no fill yet
    r = q("SELECT * FROM orders WHERE dry=0 AND epoch=? AND status='OPEN' AND cancel_ts_ms IS NULL "
          "ORDER BY id DESC", (ep,), one=True)
    # adverse share: ONLY fills with a venue-timed window (bn_after_bps present)
    adv = [f for f in fills if f['bn_after_bps'] is not None]
    adv_n = sum(1 for f in adv if (f['bn_after_bps'] or 0) >= 2.0)
    v = vol_now(ep)
    return dict(now=now, ep=ep, sec=sec, pid=pid, on=on, flag=os.path.exists(FLAG),
                alive=alive(pid), build=build_hash(), fills=fills, candles=len({f['epoch'] for f in fills}),
                today=tp, life=lp, w=w, l=l, pend=pend, resting=r, vol=v,
                calm=(None if v is None else v < VOL_CUT), adv=adv, adv_n=adv_n,
                rejects=len(q("SELECT 1 FROM orders WHERE dry=0 AND status='REJECTED'")))


CSS = """*{box-sizing:border-box}body{margin:0;padding:12px;background:#0f1115;color:#e6e6e6;
font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
h1{font-size:19px;margin:0 0 2px}.sub{color:#8b93a7;font-size:12px;margin-bottom:12px}
.card{background:#171a21;border:1px solid #242938;border-radius:10px;padding:12px;margin-bottom:10px}
.card h2{font-size:13px;margin:0 0 8px;color:#8b93a7;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
.row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px solid #1e2230}
.row:last-child{border-bottom:none}.k{color:#8b93a7}.v{font-weight:600;text-align:right}
.big{font-size:26px;font-weight:700}.on{color:#3ddc84}.off{color:#ff6b6b}.warn{color:#ffc857}
.mut{color:#8b93a7}table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:#8b93a7;font-weight:600;padding:5px 4px;border-bottom:1px solid #242938;font-size:11px;text-transform:uppercase}
td{padding:6px 4px;border-bottom:1px solid #1a1e29}tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{height:7px;background:#242938;border-radius:4px;overflow:hidden;margin-top:6px}
.bar>i{display:block;height:100%;background:#3ddc84}
.pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}
.pill.on{background:#113524;color:#3ddc84}.pill.off{background:#3a1b1b;color:#ff6b6b}
.note{color:#8b93a7;font-size:11px;margin-top:8px;line-height:1.4}"""


def money(x): return f'{x:+.2f}' if x is not None else '-'


def page(s):
    on = s['on']
    pill = f'<span class="pill {"on" if on else "off"}">{"RUNNING" if on else "STOPPED"}</span>'
    if s['resting']:
        age = int(s['now'] - s['resting']['post_ts_ms'] / 1000)
        rest = (f"{s['resting']['side']} @ {s['resting']['price']:.2f} &middot; {age}s old")
    else:
        rest = '<span class="mut">waiting</span>'
    calm = ('<span class="mut">vol unknown</span>' if s['calm'] is None else
            (f'<span class="on">calm</span> ({s["vol"]:.3f} &lt; {VOL_CUT})' if s['calm']
             else f'<span class="warn">not calm</span> ({s["vol"]:.3f} &ge; {VOL_CUT})'))
    graded = s['w'] + s['l']
    prog = min(100, 100 * graded / BAR)
    dayc = 'off' if s['today'] <= DAY_STOP else ('warn' if s['today'] < 0 else 'on')
    lifec = 'off' if s['life'] <= LIFE_STOP else ('warn' if s['life'] < 0 else 'on')
    rows = []
    for f in s['fills'][:40]:
        if f['pnl'] is None: res, cls = 'pending', 'mut'
        elif f['pnl'] > 0:   res, cls = 'WON', 'on'
        else:                res, cls = 'LOST', 'off'
        rows.append(f"<tr><td class=mut>{hhmm(f['epoch'])}</td><td>{f['side']}</td>"
                    f"<td class=num>{f['price']:.2f}</td><td class=num>{f['shares']:g}</td>"
                    f"<td class={cls}>{res}</td>"
                    f"<td class='num {cls}'>{money(f['pnl'])}</td></tr>")
    advtxt = (f"{s['adv_n']} of {len(s['adv'])}" if s['adv'] else 'no venue-timed fills yet')
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=20>
<title>Zurich maker probe</title><style>{CSS}</style></head><body>
<h1>Zurich maker probe</h1>
<div class=sub>read-only &middot; this page shows the MAKER PROBE only, not the v12 engine &middot; {hms(s['now'])} UTC</div>

<div class=card><h2>Status</h2>
<div class=row><span class=k>probe</span><span class=v>{pill}</span></div>
<div class=row><span class=k>pid</span><span class=v>{s['pid'] or '-'} {'' if s['alive'] else '<span class=off>(not running)</span>'}</span></div>
<div class=row><span class=k>enable flag</span><span class=v>{'present' if s['flag'] else '<span class=off>absent</span>'}</span></div>
<div class=row><span class=k>build</span><span class=v style="font-size:12px">{s['build']}</span></div></div>

<div class=card><h2>Right now</h2>
<div class=row><span class=k>candle</span><span class=v>{hhmm(s['ep'])} &middot; sec {s['sec']}</span></div>
<div class=row><span class=k>calm gate</span><span class=v>{calm}</span></div>
<div class=row><span class=k>resting order</span><span class=v>{rest}</span></div></div>

<div class=card><h2>Totals</h2>
<div class=row><span class=k>fills</span><span class=v>{len(s['fills'])} <span class=mut>over {s['candles']} candles</span></span></div>
<div class=row><span class=k>won / lost</span><span class=v>{s['w']} W / {s['l']} L{f' <span class=mut>&middot; {s["pend"]} pending</span>' if s['pend'] else ''}</span></div>
<div class=row><span class=k>today</span><span class="v {dayc}">{money(s['today'])} <span class=mut>of {DAY_STOP:.0f} stop</span></span></div>
<div class=row><span class=k>lifetime</span><span class="v {lifec}">{money(s['life'])} <span class=mut>of {LIFE_STOP:.0f} stop</span></span></div>
<div class=row><span class=k>progress to the bar</span><span class=v>{graded} / {BAR} graded fills</span></div>
<div class=bar><i style="width:{prog:.0f}%"></i></div></div>

<div class=card><h2>Adverse fills</h2>
<div class=row><span class=k>moved &ge;2bps against us within 1s</span><span class=v>{advtxt}</span></div>
<div class=note>Counts ONLY fills with a venue-timed window (the venue's own matched_at). Fills before
that fix fell back to the local clock and are excluded rather than shown as zero - which is why this
number is smaller than the fill count above. This is the figure M5/M10 died on.</div></div>

<div class=card><h2>Fills, newest first</h2>
<table><tr><th>candle</th><th>side</th><th class=num>price</th><th class=num>shares</th><th>result</th><th class=num>pnl</th></tr>
{''.join(rows) or '<tr><td colspan=6 class=mut>no fills yet</td></tr>'}</table>
<div class=note>Graded on the VENUE's own resolution. A maker buy pays its price and no taker fee, so
a win returns shares x (1 - price) and a loss costs shares x price - at 0.78 that is +1.10 against
-3.90, which is why entry price matters more than win rate here.</div></div>

<div class=card><h2>Why this page is not the :8787 EF card</h2>
<div class=note>The EF card on :8787 counts the ENGINE's own EF lane - 29 candles of live v10/fav_mid
orders from 09-28 19:45 to 09-30 07:40, graded on results.actual against the SIGNAL's side. It is
frozen: the engine's last live EF fill was 09-30 07:40 and master has been off since. It shares ZERO
candles with this probe, has never included it, and structurally cannot - the probe writes its own
database and the dashboard never reads it. Two instruments, one wallet. Read them separately.</div></div>
</body></html>"""


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a): pass
    def auth(self):
        if not PW: return True
        exp = 'Basic ' + base64.b64encode(('ajay:' + PW).encode()).decode()
        if hmac.compare_digest(self.headers.get('Authorization', ''), exp): return True
        self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="maker"')
        self.send_header('Content-Length', '0'); self.end_headers(); return False
    def do_GET(self):
        if not self.auth(): return
        p = self.path.split('?')[0].rstrip('/') or '/'
        if p not in ('/', '/maker', '/maker.json'):
            self.send_response(404); self.send_header('Content-Length','0'); self.end_headers(); return
        s = state()
        if p == '/maker.json':
            s.pop('fills'); s.pop('adv'); s.pop('resting', None)
            b = json.dumps(s, default=str).encode(); ct = 'application/json'
        else:
            b = page(s).encode(); ct = 'text/html; charset=utf-8'
        self.send_response(200); self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)


if __name__ == '__main__':
    if not PW:
        print('WARNING: DASHBOARD_PASSWORD not set - page will serve UNAUTHENTICATED', flush=True)
    print(f'maker page on :{PORT}  (read-only; /maker and /maker.json)', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
