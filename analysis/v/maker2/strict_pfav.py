#!/usr/bin/env python3
"""M5 STRICT passive FAV, calm only - see PREREG_STRICT.md (written before running). $100 start, fixed $10 per fill.
usage: strict_pfav.py --tape a.json.gz,b.json.gz,... --bn x.json,y.json,... [--book polybook.sqlite3] --out PREFIX"""
import sys, json, gzip, collections, argparse, sqlite3, datetime as dt
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('--tape'); ap.add_argument('--bn'); ap.add_argument('--book', default=None); ap.add_argument('--out')
A = ap.parse_args()
import os
LAG, TOUCH = 2.2, 14.0
S0, S1 = int(os.environ.get('PF_S0', 60)), int(os.environ.get('PF_S1', 180))      # defaults = M5 exactly
LO, HI = float(os.environ.get('PF_LO', 0.60)), float(os.environ.get('PF_HI', 0.80))
BUILD = (1790456400, 1790629200)            # 09-26..28 window M2 was designed on (in-sample)
CUT_FIT_DAYS = {'2026-09-22', '2026-09-23'}  # the fixed 0.304 cut was fitted on these
T = {}
import glob
for pat in A.tape.split(','):
    for f in sorted(glob.glob(pat)): T.update(json.load(gzip.open(f)))
for k, d in T.items():                       # lean format (fetch_tape_lean.py): normalise
    if 'p' in d: d['win'] = 'U' if d['up_won'] else 'D'; d['up'] = 'U'
BN = {}
for f in A.bn.split(','): BN.update({int(k): v for k, v in json.load(open(f)).items()})
day = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime('%Y-%m-%d')
def vol(e):
    r = [BN.get(t) for t in range(e - 300, e)]; r = [x for x in r if x]
    return float(np.std(np.diff(np.log(np.array(r)))) * 1e4) if len(r) >= 240 else None
eps = sorted(int(e) for e in T); V = {e: vol(e) for e in eps}
days = sorted({day(e) for e in eps})
# causal cut: 45th pct of the previous 3 days' candle vols
CC = {}
for i, d in enumerate(days):
    prev = [V[e] for e in eps if day(e) in days[max(0, i - 3):i] and V[e] is not None]
    CC[d] = float(np.percentile(prev, 45)) if i >= 3 and len(prev) > 300 else None
BOOK = collections.defaultdict(dict)
if A.book:
    for e, sec, bu, bd in sqlite3.connect(A.book).execute('select epoch, sec, bid_up, bid_dn from pb where bid_up is not null and bid_dn is not null'):
        BOOK[e][int(sec)] = (bu, bd)
def prints(d, e):
    if 'p' in d: return 'U', 'D', [(ts - LAG - e, 'U' if f else 'D', p, s) for ts, f, p, s in d['p']]
    toks = sorted({a for _, _, a, *_ in d['all']}); ref = d.get('up', toks[0])
    seen, out = set(), []
    for w, sd, a, s, p, ts, tx in d['all']:
        k = (tx, a, s, p)
        if k in seen: continue
        seen.add(k); out.append((ts - LAG - e, a, p, s))
    out.sort()
    return ref, [x for x in toks if x != ref][0] if len(toks) == 2 else None, out
def sim(e, mode):
    """mode: 'tape' (post one tick under the last traded favourite price) or 'book' (post at the real best bid). returns dict or None"""
    d = T[str(e)]; up, dn, P = prints(d, e)
    if dn is None: return None
    u = lambda a, p: p if a == up else 1 - p     # UP-equivalent price
    post = None
    if mode == 'book':
        B = BOOK.get(e)
        if not B: return None
        for s in range(S0, S1 + 1):
            if s in B:
                bu, bd = B[s]; side, b = (up, bu) if bu >= bd else (dn, bd)
                if LO <= b <= HI: post = (s + 1, side, round(b, 2)); break
    else:
        last, j = None, 0
        for s in range(S0, S1 + 1):
            while j < len(P) and P[j][0] <= s: last = u(P[j][1], P[j][2]); j += 1
            if last is None: continue
            side, fp = (up, last) if last >= 0.5 else (dn, 1 - last)
            if LO + 0.01 - 1e-9 <= fp <= HI + 0.01 + 1e-9: post = (s + 1, side, round(fp - 0.01, 2)); break
    if not post: return None
    t0, side, b = post
    q = lambda a, p: (u(a, p) if side == up else 1 - u(a, p))   # our side's equivalent price
    thru = touch = None; acc = collections.defaultdict(float)
    for sec, a, p, s in P:
        if sec <= t0 or sec > S1: continue
        x = q(a, p)
        if thru is None and x < b - 1e-9: thru = sec
        if x <= b + 1e-9:
            acc[int(sec)] += s
            if touch is None and acc[int(sec)] >= TOUCH: touch = sec
    return dict(e=e, side=side, b=b, win=(d['win'] == side), thru=thru is not None, touch=touch is not None, v=V[e])
def curve(rows, fillkey, slip):
    eq, peak, mdd, mddp, run, best, out, stopped = 100.0, 100.0, 0.0, 0.0, 0, 0, [], False
    for r in rows:
        if not r[fillkey]: continue
        if eq < 10: stopped = True; break
        c = r['b'] + slip; x = (10 / c - 10) if r['win'] else -10.0
        eq += x; peak = max(peak, eq); mdd = max(mdd, peak - eq); mddp = max(mddp, (peak - eq) / peak)
        run = run + 1 if x < 0 else 0; best = max(best, run); out.append((r['e'], eq, x))
    return out, mdd, mddp, best, stopped
res = {}
for mode in (['tape'] + (['book'] if A.book else [])):
    rows = [r for r in (sim(e, mode) for e in eps) if r]
    for cutname in ('fixed0.304', 'causal'):
        def calm(r):
            if r['v'] is None: return False
            c = 0.304 if cutname == 'fixed0.304' else CC.get(day(r['e']))
            return c is not None and r['v'] < c
        sel = [r for r in rows if calm(r)]
        for fk in ('thru', 'touch'):
            for slip in (0.0, 0.01):
                res[(mode, cutname, fk, slip)] = (sel, curve(sel, fk, slip))
L = []
def P(s=''): L.append(s); print(s)
P(f'M5 strict passive FAV calm. candles {len(eps)} {days[0]}..{days[-1]}; $100 start, $10/fill, rebates excluded. IN = 09-26..28 build set.')
P(f"{'post':5s} {'calm cut':11s} {'fill':6s} {'slip':>4s} {'posts':>5s} {'fills':>5s} {'fill%':>6s} {'win%':>5s} {'end $':>8s} {'maxDD$':>7s} {'maxDD%':>6s} {'loss run':>8s} {'days+':>6s} {'OUT-of-sample $':>15s} {'IN $':>7s}")
for k, (sel, (cv, mdd, mddp, run, stp)) in res.items():
    mode, cutname, fk, slip = k
    f = [r for r in sel if r[fk]]
    byd = collections.defaultdict(float)
    for e, _, x in cv: byd[day(e)] += x
    ins = sum(x for e, _, x in cv if BUILD[0] <= e < BUILD[1]); outs = sum(x for e, _, x in cv if not (BUILD[0] <= e < BUILD[1]))
    P(f"{mode:5s} {cutname:11s} {fk:6s} {slip:4.2f} {len(sel):5d} {len(f):5d} {100*len(f)/max(1,len(sel)):5.0f}% {100*np.mean([r['win'] for r in f]) if f else 0:5.1f} {cv[-1][1] if cv else 100:8.1f} {mdd:7.1f} {100*mddp:5.0f}% {run:8d} {sum(v>0 for v in byd.values()):3d}/{len(byd):<2d} {outs:+15.1f} {ins:+7.1f}{'  STOPPED (<$10)' if stp else ''}")
# per-day table for the headline config
HEAD = ('tape', 'causal', 'thru', 0.01)
sel, (cv, mdd, mddp, run, stp) = res[HEAD]
P(f'\nPER DAY - headline = strictest: tape post, causal calm cut, trade-through fills, +1c slippage')
byd = collections.defaultdict(lambda: [0, 0, 0.0]); endq = {}
for e, q, x in cv: b = byd[day(e)]; b[0] += 1; b[1] += x > 0; b[2] += x; endq[day(e)] = q
for d in days:
    b = byd.get(d)
    tag = (' IN(build)' if '2026-09-26' <= d <= '2026-09-28' else '') + (' cut-fit day' if d in CUT_FIT_DAYS else '')
    if b: P(f'  {d}  fills {b[0]:3d}  won {b[1]:3d}  day $ {b[2]:+7.2f}  equity {endq[d]:7.2f}{tag}')
    else: P(f'  {d}  no fills{tag}')
open(A.out + '.txt', 'w').write('\n'.join(L) + '\n')
json.dump({'|'.join(map(str, k)): [(e, q) for e, q, _ in v[1][0]] for k, v in res.items()}, open(A.out + '_curves.json', 'w'))
# chart: headline + the loosest, equity from $100, drawdown shaded
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as mdates
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
for key, lab, col in ((HEAD, 'STRICT: trade-through fill, +1c slip, causal calm', '#1f6feb'), (('tape', 'causal', 'touch', 0.0), 'looser: touch fill, no slip', '#9aa4b2')):
    cvk = res[key][1][0]
    if not cvk: continue
    t = [dt.datetime.fromtimestamp(e, dt.timezone.utc) for e, _, _ in cvk]; q = np.array([x for _, x, _ in cvk])
    ax[0].plot(t, q, color=col, lw=1.6 if key == HEAD else 1.0, label=lab)
    if key == HEAD:
        pk = np.maximum.accumulate(np.r_[100, q])[1:]; ax[0].fill_between(t, q, pk, color='#d1242f', alpha=0.25, label='drawdown from peak')
        ax[1].fill_between(t, 0, -(pk - q), color='#d1242f', alpha=0.6); ax[1].set_ylabel('drawdown $')
ax[0].axhline(100, color='k', lw=0.6, ls='--'); ax[0].set_ylabel('account $ (start 100, $10 per trade)')
ax[0].axvspan(dt.datetime.fromtimestamp(BUILD[0], dt.timezone.utc), dt.datetime.fromtimestamp(BUILD[1], dt.timezone.utc), color='#f2cc60', alpha=0.2, label='09-26..28 build set (in-sample)')
ax[0].legend(loc='upper left', fontsize=8); ax[0].set_title('Passive FAV, calm markets only - strict backtest (public Polymarket tape, venue settlement)')
ax[1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d')); fig.tight_layout(); fig.savefig(A.out + '.png', dpi=110)
print('chart', A.out + '.png')
