#!/usr/bin/env python3
"""M21 out-of-sample evaluation of P1-P4 (PREREG_M21_PROBE_OOS.md). READ-ONLY.

usage: m21_oos.py            -> the real OOS run; REFUSES until the 200-candle mark is reached
       m21_oos.py --insample  -> plumbing check against V's published in-sample numbers

The refusal is the point. V's instruction is "do not read the OOS cells before then", and a script
that would happily print them on demand is one keystroke away from breaking the prereg. So the OOS
path is gated on the same latch file the watcher and its cron twin write, and the only thing that
runs before the mark is the in-sample reproduction, whose numbers are already public.
"""
import math, os, random, sqlite3, sys
import datetime as dt

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
TAPE  = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
BN    = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
FLAG  = '/home/ubuntu/maker_probe/.candles200.alerted'
CUT_MS = int(dt.datetime(2026, 10, 2, 10, 27, tzinfo=dt.UTC).timestamp() * 1000)
BAR, M21_BAR = 60, 200
K, FF_MAX_S, NO_EXIT_AFTER = 1.4, 10, 270
NPERM = 20000
EPS = 1e-9
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))

INSAMPLE = '--insample' in sys.argv
p = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); p.row_factory = sqlite3.Row
t = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
g = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)
bn = sqlite3.connect(f'file:{BN}?mode=ro', uri=True)

cand = p.execute('select count(distinct epoch) from fills where pnl is not null').fetchone()[0]
if not INSAMPLE and not (os.path.exists(FLAG) or cand >= M21_BAR):
    print(f'REFUSING: {cand} distinct graded candles, the M21 mark is {M21_BAR} and the latch '
          f'{FLAG} is absent.\nThe out-of-sample cells are not read before the mark '
          f'(PREREG_M21_PROBE_OOS.md). Run with --insample for the plumbing check.')
    sys.exit(0)

_tok = {}
def toks(ep):
    if ep not in _tok:
        r = g.execute('select tok_up, tok_dn from mkt where epoch=?', (ep,)).fetchone()
        _tok[ep] = (str(r[0]), str(r[1])) if r and r[0] else (None, None)
    return _tok[ep]

_ser = {}
def series(ep):
    if ep in _ser: return _ser[ep]
    raw = {}
    for tms, px in bn.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                              "AND ts_ms>=? AND ts_ms<=?", ((ep - 310) * 1000, (ep + 315) * 1000)):
        raw[int(tms) // 1000] = float(px)
    out, last, held = {}, None, 0
    if raw:
        for s in range(min(raw), max(raw) + 1):
            if s in raw: last, held = raw[s], 0
            else:
                held += 1
                if held > FF_MAX_S: continue
            if last is not None: out[s] = last
    _ser[ep] = out
    return out

def fair_up(ep, at_s):
    """M19's fair for UP, k frozen at 1.4 - the same definition the paper shadow quotes on."""
    px = series(ep)
    w = [px[s] for s in range(ep - 300, ep) if s in px]
    if len(w) < 240: return None
    m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
    mu = sum(m) / len(m)
    sig = math.sqrt(sum((x - mu) ** 2 for x in m) / len(m))
    o = [px[s] for s in range(ep, min(at_s, ep + 60)) if s in px]
    S = px.get(at_s); tau = (ep + 300) - at_s
    if not o or S is None or tau <= 0 or sig <= 0: return None
    return Phi(math.log(S / (sum(o) / len(o))) / (K * sig * math.sqrt(tau)))

rows = [dict(r) for r in p.execute('select * from fills where pnl is not null order by fill_ts_ms')]
if INSAMPLE: rows = [f for f in rows if f['fill_ts_ms'] <= CUT_MS]
else:        rows = [f for f in rows if f['fill_ts_ms'] > CUT_MS]

NEED = {f['epoch'] for f in rows}
TP = {}
for ep_, ts_, asset_, px_, side_, tk_ in t.execute(
        'select epoch, ts, asset, price, side, is_taker from tape'):
    if ep_ not in NEED or px_ is None: continue
    TP.setdefault(str(asset_), []).append((int(ts_), float(px_), side_, int(tk_ or 0)))

for f in rows:
    ep = f['epoch']; fs = f['fill_ts_ms'] // 1000
    f['sec'] = fs - ep
    fu = fair_up(ep, fs)
    f['edge'] = None if fu is None else ((fu if f['side'] == 'UP' else 1 - fu) - f['price'])
    up, dn = toks(ep)
    tok = up if f['side'] == 'UP' else dn
    lo = None
    for ts_, px_, sd_, tk_ in TP.get(str(tok), ()):
        if not (fs < ts_ <= ep + NO_EXIT_AFTER) or sd_ != 'BUY' or tk_ != 0: continue
        lo = px_ if lo is None else min(lo, px_)
    f['bidmin'] = lo

def per(sel):
    dep = sum(x['spent'] for x in sel)
    return (sum(x['pnl'] for x in sel) / dep) if dep else 0.0

def line(lbl, sel):
    w = sum(1 for x in sel if x['pnl'] > 0); l = sum(1 for x in sel if x['pnl'] < 0)
    dep = sum(x['spent'] for x in sel); pnl = sum(x['pnl'] for x in sel)
    return (f'    {lbl:>16s} {len(sel):4d} {f"{w}/{l}":>7s} {dep:9.2f} {pnl:+9.4f} '
            f'{per(sel):+8.4f}  {"INSUFFICIENT (<60)" if len(sel) < BAR else ""}')

def nullp(a, b):
    """Random-subset null: hold the pnl/deployed pairs fixed and reassign WHICH fills fall in the
    better level, keeping both group sizes. p = share of reassignments whose gap is >= the observed
    one. This permutes the bucket LABEL, never the outcome, so the market's own pricing is intact."""
    pool = a + b
    obs = per(a) - per(b)
    na = len(a)
    if na == 0 or len(b) == 0: return None, obs
    hits = 0
    for _ in range(NPERM):
        random.shuffle(pool)
        if per(pool[:na]) - per(pool[na:]) >= obs - 1e-12: hits += 1
    return hits / NPERM, obs

def halves(sel):
    s = sorted(sel, key=lambda x: x['fill_ts_ms'])
    k = (len(s) + 1) // 2
    return s[:k], s[k:]

random.seed(20261002)
label = 'IN-SAMPLE REPRODUCTION (to 10-02 10:27 UTC)' if INSAMPLE else \
        'OUT OF SAMPLE (fills AFTER 10-02 10:27 UTC only)'
L = [f'M21 - {label}. READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC',
     f'  {len(rows)} graded fills over {len({f["epoch"] for f in rows})} distinct candles; '
     f'probe lifetime mark {cand} of {M21_BAR}',
     f'  prereg: analysis/v/maker2/PREREG_M21_PROBE_OOS.md. Whole grid, never the best cell.', '']

TESTS = [
    ('P1', 'fill second', 'sec',
     [('60-120', lambda v: 60 <= v < 120), ('120-180', lambda v: 120 <= v <= 180)]),
    ('P2', 'price paid', 'price',
     [('0.60-0.70', lambda v: 0.60 - EPS <= v < 0.70), ('0.70-0.80', lambda v: 0.70 <= v <= 0.80 + EPS)]),
    ('P3', 'M19 fair minus price', 'edge',
     [('<= 0', lambda v: v <= 0), ('> 0', lambda v: v > 0)]),
]
verdicts = []
for tag, name, key, buckets in TESTS:
    L.append(f'{tag}: {name} - prediction: the FIRST level beats the second')
    L.append(f'    {"level":>16s} {"n":>4s} {"W/L":>7s} {"deployed":>9s} {"pnl":>9s} {"pnl/$1":>8s}  flag')
    known = [f for f in rows if f.get(key) is not None]
    sels = []
    for lbl, test in buckets:
        sel = [f for f in known if test(f[key])]
        sels.append(sel)
        L.append(line(lbl, sel))
    miss = len(rows) - len(known)
    if miss: L.append(f'    {"unknown":>16s} {miss:4d}  EXCLUDED, not bucketed')
    a, b = sels
    gap = per(a) - per(b)
    pv, _ = nullp(list(a), list(b))
    ha, hb = halves(a), halves(b)
    h1 = per(ha[0]) - per(hb[0]); h2 = per(ha[1]) - per(hb[1])
    ok_dir = gap > 0
    ok_n = len(a) >= BAR
    ok_h = (h1 > 0) == (h2 > 0) == ok_dir
    ok_p = (pv is not None and pv < 0.05)
    L += [f'    gap {gap:+.4f}/$1 | better-level n {len(a)} ({"ok" if ok_n else "UNDER 60"}) | '
          f'OOS halves {h1:+.4f} and {h2:+.4f} ({"same sign" if ok_h else "DISAGREE"}) | '
          f'null p {"n/a" if pv is None else f"{pv:.4f}"} ({"ok" if ok_p else "not < 0.05"})',
          f'    {tag} VERDICT: ' + ('PASS' if (ok_dir and ok_n and ok_h and ok_p) else 'FAIL')
          + ('' if INSAMPLE else '   (prereg gates: direction, n>=60, both halves, null p<0.05)'), '']
    verdicts.append((tag, ok_dir and ok_n and ok_h and ok_p))

wins = [f for f in rows if f['pnl'] > 0 and f['bidmin'] is not None]
stopped = [f for f in wins if f['bidmin'] <= 0.10 + EPS]
L += ['P4: stop at bid 0.10 - prediction: winners stopped stays 0',
      f'    winners with a proven bid path {len(wins)}; winners whose path touched 0.10: {len(stopped)}',
      f'    P4 VERDICT: ' + ('PASS (no winner touched 0.10)' if not stopped else
                             f'FAIL - {len(stopped)} winner(s) touched 0.10'), '']
verdicts.append(('P4', not stopped))

L.append('SIDE (reported, no prediction was made)')
L.append(f'    {"level":>16s} {"n":>4s} {"W/L":>7s} {"deployed":>9s} {"pnl":>9s} {"pnl/$1":>8s}  flag')
for s_ in ('UP', 'DOWN'):
    L.append(line(s_, [f for f in rows if f['side'] == s_]))
L += ['', 'SUMMARY: ' + ', '.join(f'{t}={"PASS" if ok else "FAIL"}' for t, ok in verdicts)]
if not INSAMPLE:
    L += ['Per the prereg, a PASS is a proposal to the owner through V, never a change made here;',
          'a FAIL leaves the probe exactly as it is. Nothing in this file changes anything.']
print('\n'.join(L))
