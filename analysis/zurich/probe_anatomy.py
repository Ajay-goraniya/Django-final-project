#!/usr/bin/env python3
"""Anatomy of the probe's live fills. READ-ONLY: probe db, public tape, bn_flow. Writes nothing.

A. Which SIM FILL RULE matches reality - did the tape print through our bid, only touch it, or
   neither, on orders that filled live vs orders that did not.
B. Would a STOP LOSS have cut the losers, priced on evidence that a bid existed.
C. What separates the 21 losers from the 75 winners at ENTRY.
"""
import math, sqlite3, sys
import datetime as dt

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
TAPE  = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
BN    = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
CHURN = 1790787600          # 09-30 17:00
LEVELS = (0.50, 0.40, 0.30, 0.20, 0.10)
FEE = lambda L: 0.07 * L * (1 - L)      # taker fee per share at the exit, V's formula
NO_EXIT_AFTER = 270        # a minimum printed at sec >= 270 is settlement, not an exit
BAR = 60
K = 1.4
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
FF_MAX_S = 10

p = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); p.row_factory = sqlite3.Row
t = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
g = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)
bn = sqlite3.connect(f'file:{BN}?mode=ro', uri=True)
EPS = 1e-9
L = []

# The tape has PRIMARY KEY(txh, asset, wallet, size, price) and no index on asset or epoch, so every
# per-order query was a full scan of 1.47M rows - ~280 scans for this study. One pass into memory
# instead, restricted to the epochs we actually need.
NEED = set(r[0] for r in p.execute('select distinct epoch from orders where dry=0')) | \
       set(r[0] for r in p.execute('select distinct epoch from fills'))
TP = {}
for ep_, ts_, asset_, px_, side_, tk_ in t.execute(
        'select epoch, ts, asset, price, side, is_taker from tape'):
    if ep_ not in NEED or px_ is None: continue
    TP.setdefault(str(asset_), []).append((int(ts_), float(px_), side_, int(tk_ or 0)))
for v in TP.values(): v.sort()

def prints(asset, lo_s, hi_s):
    return [r for r in TP.get(str(asset), ()) if lo_s <= r[0] <= hi_s]

_tok = {}
def toks(ep):
    if ep not in _tok:
        r = g.execute('select tok_up, tok_dn from mkt where epoch=?', (ep,)).fetchone()
        _tok[ep] = (str(r[0]), str(r[1])) if r and r[0] else (None, None)
    return _tok[ep]

_ser = {}
def series(ep):
    """1 s spot over [ep-305, ep+310], forward-filled up to FF_MAX_S, as FavBrain does."""
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
    """M19's fair price for UP at a given second. Same definition as the paper shadow, k frozen."""
    px = series(ep)
    w = [px[s] for s in range(ep - 300, ep) if s in px]
    if len(w) < 240: return None
    m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
    mu = sum(m) / len(m)
    sig = math.sqrt(sum((x - mu) ** 2 for x in m) / len(m))
    o = [px[s] for s in range(ep, min(at_s, ep + 60)) if s in px]
    S = px.get(at_s)
    tau = (ep + 300) - at_s
    if not o or S is None or tau <= 0 or sig <= 0: return None
    return Phi(math.log(S / (sum(o) / len(o))) / (K * sig * math.sqrt(tau)))

def cell(rows):
    w = sum(1 for x in rows if x['pnl'] > 0); l = sum(1 for x in rows if x['pnl'] < 0)
    dep = sum(x['spent'] for x in rows); pnl = sum(x['pnl'] for x in rows)
    return len(rows), w, l, dep, pnl, (pnl / dep if dep else 0.0)

def flag(n): return 'INSUFFICIENT (<60)' if n < BAR else ''

# =================================================================================================
# A. FILL-MODEL CALIBRATION
# =================================================================================================
L += ['A. FILL-MODEL CALIBRATION - what the public tape did while our order was live',
      '   Window: post_ts -> the fill, or the cancel, or the candle end if neither. Both legs of a',
      '   Polymarket trade are recorded (one row per token, prices summing to 1), so the MIRROR test',
      '   on the complement token at >= 1-p is included and verified below, not assumed redundant.', '']
orders = [dict(r) for r in p.execute('select * from orders where dry=0 order by id')]
fills_by_row = {}
for r in p.execute('select * from fills'):
    fills_by_row.setdefault(r['order_row'], []).append(dict(r))

# verify the two-leg structure before relying on it
two = t.execute('select count(*) from (select txh, count(distinct asset) c from tape group by txh) '
                'where c >= 2').fetchone()[0]
tot = t.execute('select count(distinct txh) from tape').fetchone()[0]
L.append(f'   two-leg check: {two} of {tot} tape transactions carry >= 2 token legs '
         f'({100*two/max(tot,1):.1f}%), so the mirror is usually the same trade seen from the other side.')
L.append('')

def classify(tok, comp, pr, lo_s, hi_s):
    thru = touch = False
    for _ts, px, _sd, _tk in prints(tok, lo_s, hi_s):
        if px < pr - EPS: thru = True
        elif abs(px - pr) <= EPS: touch = True
    if comp:
        for _ts, px, _sd, _tk in prints(comp, lo_s, hi_s):
            if px > (1 - pr) + EPS: thru = True
            elif abs(px - (1 - pr)) <= EPS: touch = True
    return 'thru' if thru else ('touch-only' if touch else 'neither')

# HOW LONG WAS AN ORDER EVEN LIVE, and can the tape resolve that? This decides whether the table
# below means anything, so it comes first.
live_s, seen_self = [], 0
for o in orders:
    fl = fills_by_row.get(o['id'], [])
    end = (min(f['fill_ts_ms'] for f in fl) // 1000) if fl else (
        (o['cancel_ts_ms'] // 1000) if o['cancel_ts_ms'] else o['epoch'] + 300)
    live_s.append(max(0, end - o['post_ts_ms'] // 1000))
    if fl:
        up, dn = toks(o['epoch'])
        comp = dn if str(o['token']) == str(up) else up
        sh = sum(f['shares'] for f in fl); pr = float(o['price'])
        hit = any(abs(px - pr) <= EPS or abs(px - (1 - pr)) <= EPS
                  for _ts, px, _sd, _tk in prints(o['token'], o['epoch'], o['epoch'] + 300))
        hit = hit or any(abs(px - (1 - pr)) <= EPS or abs(px - pr) <= EPS
                         for _ts, px, _sd, _tk in prints(comp, o['epoch'], o['epoch'] + 300))
        seen_self += 1 if hit else 0
qs = sorted(live_s)
nf = sum(1 for o in orders if fills_by_row.get(o['id']))
L += ['   RESOLUTION FIRST - can the tape see the interval we are asking about?',
      f'     order lifetime post -> fill/cancel: p10 {qs[len(qs)//10]} s, p50 {qs[len(qs)//2]} s, '
      f'p90 {qs[9*len(qs)//10]} s, max {qs[-1]} s. Most orders live for SECONDS.',
      f'     of our {nf} live-filled orders, a tape print at our price or its complement exists '
      f'anywhere in the candle for {seen_self} ({100*seen_self/max(nf,1):.0f}%).',
      '     The tape is a 1-minute REST cron with per-second stamps, so a window of a few seconds is',
      '     at the edge of what it can resolve - and our OWN fill is missing from it for '
      f'{nf-seen_self} of {nf} filled orders.',
      '     Therefore the tight-window table is reported WITH a candle-wide table beside it, and the',
      '     tight one must not be read as proof that nothing traded through us.', '']

for wname, wfun in (('TIGHT: post -> fill/cancel', 'tight'), ('WIDE: post -> candle end', 'wide')):
    rows = {k: {'filled': [], 'not': []} for k in ('thru', 'touch-only', 'neither')}
    for o in orders:
        ep, pr, tok = o['epoch'], float(o['price']), str(o['token'])
        up, dn = toks(ep)
        comp = dn if tok == up else (up if tok == dn else None)
        start = o['post_ts_ms'] // 1000
        fl = fills_by_row.get(o['id'], [])
        if wfun == 'tight':
            end = (min(f['fill_ts_ms'] for f in fl) // 1000) if fl else (
                (o['cancel_ts_ms'] // 1000) if o['cancel_ts_ms'] else ep + 300)
        else:
            end = ep + 300
        rows[classify(tok, comp, pr, start, max(start, end))]['filled' if fl else 'not'].append(o)
    L.append(f'   {wname}')
    L.append(f'     {"tape did":12s} {"live FILLED":>12s} {"not filled":>11s} {"fill rate":>10s}   '
             f'{"win rate of the live fills":28s}')
    for key in ('thru', 'touch-only', 'neither'):
        f_, n_ = rows[key]['filled'], rows[key]['not']
        tot_ = len(f_) + len(n_)
        gr = [x for o in f_ for x in fills_by_row.get(o['id'], []) if x['pnl'] is not None]
        wr = (f'{100*sum(1 for x in gr if x["pnl"]>0)/len(gr):.1f}% of {len(gr)} graded'
              if gr else 'no graded fills')
        L.append(f'     {key:12s} {len(f_):12d} {len(n_):11d} '
                 f'{(100*len(f_)/tot_ if tot_ else 0):9.1f}%   {wr:28s}  {flag(tot_)}')
    L.append('')
L += ['   READ: the sim rules compared are STRICT_PFAV_CALM touch (+155/20d) and thru (-335/20d).',
      '   What this says is narrower than the question asked: at the few-second holding times the',
      '   probe actually has, the public tape cannot reliably adjudicate touch against thru, so a',
      '   20-day sim built on that tape is deciding the fill rule on data blind to our own fills.', '']

# =================================================================================================
# B. STOP-LOSS GRID
# =================================================================================================
graded = [dict(r) for r in p.execute('select * from fills where pnl is not null order by fill_ts_ms')]
for f in graded:
    ep = f['epoch']; fs = f['fill_ts_ms'] // 1000
    up, dn = toks(ep)
    f['tok'] = up if f['side'] == 'UP' else dn      # fills has no token column; gamma has the pair
    lo = None
    if f['tok']:
        for _ts, px, sd, tk in prints(f['tok'], fs + 1, ep + NO_EXIT_AFTER):
            if sd != 'BUY' or tk != 0: continue     # maker-BUY = a resting bid at that price was hit
            lo = px if lo is None else min(lo, px)
    f['bidmin'] = lo
L += ['B. STOP LOSS on the graded fills, exit priced where a BID is PROVEN to have existed',
      '   The probe keeps no book history, so there is no recorded bid path. What the public tape',
      '   does prove is a MAKER-BUY print (is_taker=0, side BUY): a resting bid at that price was',
      '   hit, so a bid existed there. That is the evidence used. It is an upper bound on how well we',
      '   could have exited - it ignores queue position and our own size - and it is NOT the same',
      f'   thing as a continuous bid path. Minima at sec >= {NO_EXIT_AFTER} are excluded as settlement.', '']
have = [f for f in graded if f['bidmin'] is not None]
L.append(f'   fills {len(graded)}, of which {len(have)} have any proven bid print after the fill; '
         f'the other {len(graded)-len(have)} are EXCLUDED, not assumed un-stoppable.')

def grid(pop, title):
    out = ['', f'   {title} (n {len(pop)})',
           f'     {"L":>5s} {"W stopped":>9s} {"cost":>9s} {"L saved":>8s} {"gain":>9s} '
           f'{"NET vs hold":>12s}  flag']
    for lev in LEVELS:
        ws = [f for f in pop if f['pnl'] > 0 and f['bidmin'] is not None and f['bidmin'] <= lev + EPS]
        ls = [f for f in pop if f['pnl'] < 0 and f['bidmin'] is not None and f['bidmin'] <= lev + EPS]
        cost = sum(f['shares'] * (1 - lev) + FEE(lev) * f['shares'] for f in ws)
        gain = sum(f['shares'] * lev - FEE(lev) * f['shares'] for f in ls)
        out.append(f'     {lev:5.2f} {len(ws):9d} {-cost:+9.2f} {len(ls):8d} {gain:+9.2f} '
                   f'{gain-cost:+12.2f}  {flag(len(pop))}')
    return out

L += grid(have, 'ALL graded fills with a proven bid path')
L += grid([f for f in have if f['epoch'] != CHURN], 'EXCLUDING the 09-30 17:00 candle')
L += ['', '   cost of a stop = shares*(1-L) given up on a winner, plus the taker fee; gain on a loser',
      '   = shares*L recovered minus the fee. Fee = 0.07*L*(1-L) per share.', '']

# =================================================================================================
# C. ENTRY SEPARATION
# =================================================================================================
for f in graded:
    ep = f['epoch']; fs = f['fill_ts_ms'] // 1000
    f['sec'] = fs - ep
    px = series(ep)
    p0, p1 = px.get(ep), px.get(fs)
    f['favbps'] = None
    if p0 and p1:
        sgn = 1.0 if f['side'] == 'UP' else -1.0
        f['favbps'] = sgn * (p1 - p0) / p0 * 1e4
    fu = fair_up(ep, fs)
    f['edge'] = None if fu is None else ((fu if f['side'] == 'UP' else 1 - fu) - f['price'])

L += ['C. ENTRY SEPARATION, losers vs winners, one-way, every level shown',
      f'   {len(graded)} graded fills: {sum(1 for f in graded if f["pnl"]>0)} W / '
      f'{sum(1 for f in graded if f["pnl"]<0)} L', '']

def oneway(name, key, buckets):
    out = [f'   {name}',
           f'     {"level":>14s} {"n":>4s} {"W/L":>7s} {"deployed":>9s} {"pnl":>9s} {"pnl/$1":>8s}  flag']
    known = [f for f in graded if f.get(key) is not None]
    for lbl, test in buckets:
        sel = [f for f in known if test(f[key])]
        if not sel:
            out.append(f'     {lbl:>14s} {0:4d} {"-":>7s} {"-":>9s} {"-":>9s} {"-":>8s}  no fills')
            continue
        n, w, l, dep, pnl, per = cell(sel)
        out.append(f'     {lbl:>14s} {n:4d} {f"{w}/{l}":>7s} {dep:9.2f} {pnl:+9.4f} {per:+8.4f}  {flag(n)}')
    miss = len(graded) - len(known)
    if miss: out.append(f'     {"unknown":>14s} {miss:4d}  EXCLUDED, not bucketed as zero')
    return out + ['']

L += oneway('fill second', 'sec', [('60-120', lambda v: 60 <= v < 120), ('120-180', lambda v: 120 <= v <= 180)])
L += oneway('price paid', 'price', [('0.60-0.65', lambda v: 0.60 - EPS <= v < 0.65),
                                    ('0.65-0.70', lambda v: 0.65 <= v < 0.70),
                                    ('0.70-0.75', lambda v: 0.70 <= v < 0.75),
                                    ('0.75-0.80', lambda v: 0.75 <= v <= 0.80 + EPS)])
L += oneway('side', 'side', [('UP', lambda v: v == 'UP'), ('DOWN', lambda v: v == 'DOWN')])
L += oneway('Binance distance from the candle OPEN at the fill, signed IN OUR FAVOUR (bps)', 'favbps',
            [('<0', lambda v: v < 0), ('0-2', lambda v: 0 <= v < 2),
             ('2-5', lambda v: 2 <= v < 5), ('>5', lambda v: v >= 5)])
L += oneway('M19 fair for our side at the fill second MINUS price paid', 'edge',
            [('<-0.10', lambda v: v < -0.10), ('-0.10..0', lambda v: -0.10 <= v < 0),
             ('0..0.10', lambda v: 0 <= v < 0.10), ('>0.10', lambda v: v >= 0.10)])
print('\n'.join(L))
