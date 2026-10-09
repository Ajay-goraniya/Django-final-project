#!/usr/bin/env python3
"""W27 (V, 09-30): how do the CONSISTENT maker wallets on BTC 5m make money, and with what drawdown?
Input: wallets_raw.json.gz (top_wallets.py cache: data-api both legs + taker legs, gamma winner) - 576 settled candles.
Per wallet, per candle: shares bought of UP and DOWN, avg price each, paired shares = min(up, dn), pair cost = avgUP+avgDN,
unpaired residual (shares, and did it win), candle PnL (fee on taker legs only; maker rebates NOT included, so makers are understated).
Wallet-level: candles, total PnL, PnL/volume, % candles positive, max drawdown on the per-candle curve, P/DD, worst candle,
PnL split into PAIRED part (min(up,dn) x (1 - pair cost)) and RESIDUAL part (the unhedged directional piece).
usage: maker_profile.py <wallets_raw.json.gz>"""
import sys, json, gzip, collections
import numpy as np
data = json.load(gzip.open(sys.argv[1]))
WAL = ['0x86b14772', '0x7743aea5', '0xc1b4bfdc', '0xcd30457c', '0xc387c2a4', '0x32ed2e54', '0x3048d653', '0x41e2e1cc', '0xc53375ff', '0x0cb03848', '0xcc0d715a', '0x4b01c8e0']
full = {}
for e, d in data.items():
    for w, *_ in d['all']:
        for p in WAL:
            if w.startswith(p): full[p] = w
per = {p: [] for p in WAL}
for e in sorted(data, key=int):
    d = data[e]; tk = set((w, tx, a, s) for w, sd, a, s, p, ts, tx in d['taker'])
    toks = sorted({a for _, _, a, *_ in d['all']})
    agg = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0.0]))  # wallet -> asset -> [sh_bought, cost, sh_sold_cash]
    fee = collections.defaultdict(float); sold = collections.defaultdict(float); mk = collections.defaultdict(lambda: [0, 0])
    for w, sd, a, s, p, ts, tx in d['all']:
        q = w[:10]
        if q not in per: continue
        t = (w, tx, a, s) in tk
        f = 0.07 * p * (1 - p) * s if t else 0.0; fee[q] += f; mk[q][0 if t else 1] += 1
        if sd == 'BUY': agg[q][a][0] += s; agg[q][a][1] += s * p
        else: agg[q][a][0] -= s; agg[q][a][1] -= s * p
    for q, A in agg.items():
        win = d['win']; assets = list(A)
        other = [a for a in assets if a != win]
        up_w = A.get(win, [0, 0, 0]); lo = A.get(other[0], [0, 0, 0]) if other else [0, 0, 0]
        pnl = up_w[0] - up_w[1] - lo[1] - fee[q]           # winner shares pay 1, all cost paid
        sw, sl = up_w[0], lo[0]; paired = max(0.0, min(sw, sl))
        cw = up_w[1] / sw if sw > 0 else 0; cl = lo[1] / sl if sl > 0 else 0
        pc = (cw + cl) if (sw > 0 and sl > 0) else float('nan')
        paired_pnl = paired * (1 - pc) if paired > 0 else 0.0
        per[q].append(dict(e=int(e), pnl=pnl, vol=up_w[1] + lo[1], paired=paired, sw=sw, sl=sl, pc=pc, ppnl=paired_pnl, rpnl=pnl - paired_pnl + fee[q] * 0, taker=mk[q][0], maker=mk[q][1]))
print(f'{len(data)} candles (48 h). PnL excludes maker rebates. per-candle curve.')
print('wallet      cands  pnl$    pnl/vol  cand+%  maxDD$  P/DD  worst$  paired%sh  med pair cost  paired$   residual$  maker%')
for q in WAL:
    r = per[q]
    if not r: continue
    p = np.array([x['pnl'] for x in r]); c = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    vol = sum(x['vol'] for x in r); sh = sum(x['sw'] + x['sl'] for x in r); pr = sum(2 * x['paired'] for x in r)
    pcs = [x['pc'] for x in r if x['pc'] == x['pc']]
    ppn = sum(x['ppnl'] for x in r); mkr = sum(x['maker'] for x in r) / max(1, sum(x['maker'] + x['taker'] for x in r))
    print(f'{q}  {len(r):5d} {c[-1]:+7.0f}  {c[-1]/vol:+.4f}  {100*np.mean(p>0):5.0f}  {dd:7.0f} {c[-1]/dd if dd else 0:5.1f} {p.min():+7.0f}  {100*pr/sh if sh else 0:6.0f}     {np.median(pcs) if pcs else float("nan"):.3f}      {ppn:+8.0f}  {c[-1]-ppn:+8.0f}   {100*mkr:4.0f}')
json.dump({q: per[q] for q in WAL}, gzip.open('/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/maker_percandle.json.gz', 'wt'))
