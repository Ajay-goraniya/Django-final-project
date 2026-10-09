#!/usr/bin/env python3
"""In-trade stop for calm FAV per STOP_PREREG.md on independent 09-13..16 (EF-8 rows). Entry = frozen calm FAV
(vol tercile-1 cut from 09-11/12, fav, ask .65-.85, sec 60-180, first second, once/candle, $10, EF-8 fill model).
Exit: first later second where our side's bid <= S -> sell all filled shares at that bid, taker fee 0.07*p*(1-p)
per share; else hold to the venue label. usage: fav_stop.py <scratch>"""
import sys, numpy as np, datetime as dt
Z = np.load(sys.argv[1] + '/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
cut = np.quantile(X[np.isin(day, ['09-11', '09-12']), c['vol']], [1/3, 2/3])
TEST = ['09-13', '09-14', '09-15', '09-16']; m = np.isin(day, TEST)
Y = X[m]; dy = day[m]; o = np.lexsort((Y[:, c['sec']], Y[:, c['side']], Y[:, c['ep']])); Y = Y[o]; dy = dy[o]
sel = (Y[:, c['sec']] >= 60) & (Y[:, c['sec']] <= 180) & (Y[:, c['own_ask']] > Y[:, c['opp_ask']]) & \
      (Y[:, c['own_ask']] >= .65) & (Y[:, c['own_ask']] <= .85) & (Y[:, c['vol']] < cut[0])
idx = np.where(sel)[0]
idx = idx[np.lexsort((Y[idx, c['sec']], Y[idx, c['ep']]))]
_, first = np.unique(Y[idx, c['ep']], return_index=True); f = idx[first]
# bid path per (ep, side): later seconds of the same candle and side
key = Y[:, c['ep']] * 10 + Y[:, c['side']]
fee = lambda p: 0.07 * p * (1 - p)
trades = []
for i in f:
    if Y[i, c['fill']] <= 0: continue
    paid = Y[i, c['paid']]; sh = 10 / (paid * (1 + 0.07 * (1 - paid)))       # $10 spend incl fee
    k = key[i]; j = np.where((key == k) & (Y[:, c['sec']] > Y[i, c['sec']]))[0]
    j = j[np.argsort(Y[j, c['sec']])]
    trades.append((Y[i, c['ep']], dy[i], sh, Y[j, c['own_bid']], Y[i, c['win']] > 0))
eps = np.array([t[0] for t in trades]); med = np.median(eps)
print(f'vol cut {cut[0]:.3f}  test {TEST}  calm-FAV fills {len(trades)}')
print('   S     fills  stopped  avg_stop$     $@10    maxDD   P/DD  days+  H1$     H2$     per day')
for S in (None, .55, .50, .45, .40, .35, .30, .25, .20):
    pn, ns, sl = [], 0, []
    for ep, d, sh, bids, w in trades:
        hit = np.where(bids <= S)[0] if S is not None else np.array([], int)
        if len(hit):
            b = bids[hit[0]]; v = sh * (b - fee(b)) - 10; ns += 1; sl.append(v)
        else:
            v = sh * (1.0 if w else 0.0) - 10
        pn.append(v)
    pn = np.array(pn); cum = np.cumsum(pn); dd = np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum])
    per = [pn[np.array([t[1] for t in trades]) == d].sum() for d in TEST]
    h1 = pn[eps < med].sum(); h2 = pn[eps >= med].sum()
    print(f'{"none" if S is None else f"{S:.2f}":>5} {len(pn):6d} {ns:7d} {np.mean(sl) if sl else 0:+9.2f} {pn.sum():+8.2f} {dd:8.2f} '
          f'{pn.sum()/dd if dd else 0:6.2f}  {sum(v>0 for v in per)}/4 {h1:+7.2f} {h2:+7.2f}  ' + ' '.join(f'{v:+.0f}' for v in per))
