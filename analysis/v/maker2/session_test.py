#!/usr/bin/env python3
"""M11 (V, 09-30, owner: 'a time when the model wins? Asia / Europe / US session - pause it otherwise'). Buckets fixed BEFORE running:
UTC hour sessions Asia 00-07, Europe 07-13, US 13-20, Late 20-24; weekday vs weekend.
(A) London's REAL EF trades (london_ef_real.csv, 296 fills 09-23..30 01:25): $ and $/1 per session, first vs second half of the trades.
(B) 20-day public-tape taker FAV family (strict_taker_fav rules, +1c): per session per day; WALK-FORWARD: sessions chosen on 09-11..20
    (train $ > 0 and both train halves > 0), traded on 09-21..30 (sealed). Compared with trading every session.
usage: session_test.py <scratch dir>"""
import sys, csv, collections, datetime as dt, runpy, io, contextlib
import numpy as np
S = sys.argv[1]
sess = lambda h: 'Asia 00-07' if h < 7 else 'Europe 07-13' if h < 13 else 'US 13-20' if h < 20 else 'Late 20-24'
ORDER = ['Asia 00-07', 'Europe 07-13', 'US 13-20', 'Late 20-24']
print('(A) London REAL EF fills by session (pnl $, stake-weighted $/1, n, first-half $ / second-half $):')
R = [(int(r['candle_epoch']), float(r['pnl_usd']), float(r['stake_usd'])) for r in csv.DictReader(open('analysis/v/combo/london_ef_real.csv'))]
h = len(R) // 2
for s in ORDER:
    x = [(i, p, st) for i, (e, p, st) in enumerate(R) if sess(dt.datetime.fromtimestamp(e, dt.timezone.utc).hour) == s]
    a = sum(p for i, p, _ in x if i < h); b = sum(p for i, p, _ in x if i >= h)
    print(f'   {s:13s} n {len(x):3d}  $ {sum(p for _, p, _ in x):+7.2f}  $/1 {sum(p for _, p, _ in x)/max(1e-9, sum(st for *_, st in x)):+.3f}  halves {a:+7.2f} / {b:+7.2f}{"  *n<60" if len(x) < 60 else ""}')
sys.argv = ['x', S]
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path('analysis/v/maker2/strict_taker_fav.py')
rows, arms, day = g['rows'], g['arms'], g['day']
pn = lambda r: (lambda c: (10 / c - 10) if r['win'] else -10.0)(r['ask'] + 0.07 * r['ask'] * (1 - r['ask']) + 0.01)
print('\n(B) taker FAV family, strict (+1c), walk-forward session choice: train 09-11..20 -> sealed test 09-21..30')
for name in ('FAV calm<0.304', 'FAV_mid 0.304-0.466', 'FAV_all'):
    sel = [r for r in rows if arms[name](r)]
    cell = collections.defaultdict(list)
    for r in sel: cell[(sess(dt.datetime.fromtimestamp(r['e'], dt.timezone.utc).hour), day(r['e']) <= '2026-09-20')].append(r)
    keep = []
    line = []
    for s in ORDER:
        tr = sorted(cell[(s, True)], key=lambda r: r['e']); x = np.array([pn(r) for r in tr]); hh = len(x) // 2
        te = np.array([pn(r) for r in cell[(s, False)]])
        ok = len(x) >= 60 and x.sum() > 0 and x[:hh].sum() > 0 and x[hh:].sum() > 0
        if ok: keep.append(s)
        line.append(f'{s}: train {x.sum():+.0f} (n{len(x)}) test {te.sum():+.0f} (n{len(te)}){" KEEP" if ok else ""}')
    test_all = [r for r in sel if day(r['e']) >= '2026-09-21']
    tk = [r for r in test_all if sess(dt.datetime.fromtimestamp(r['e'], dt.timezone.utc).hour) in keep]
    byd = collections.defaultdict(float)
    for r in tk: byd[day(r['e'])] += pn(r)
    print(f'  {name}:\n     ' + '\n     '.join(line))
    print(f'     -> sessions kept {keep or "none"}; TEST with session filter: n {len(tk)} $ {sum(pn(r) for r in tk):+.1f}, days + {sum(v > 0 for v in byd.values())}/{len(byd)};'
          f' TEST trading all sessions: $ {sum(pn(r) for r in test_all):+.1f}')
