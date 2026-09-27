#!/usr/bin/env python3
"""How many seconds of lead does Binance have over the recorded Polymarket ask? READ-ONLY.

V's task 1. For every candle-second where the frozen Binance model's EV against the CURRENT recorded ask
is >= theta, take the ask at t, t+1, t+2, t+3 s and the size at best, and score the PnL of buying at each.
If the edge survives a 1-3 s delay there is real lead; if it decays to nothing by t+1 the paper number in
ETH_SOL_EF.md was the 4-6 s stale proxy and nothing else.

Everything is the recorder's own 1 Hz data (/home/ubuntu/pm_multi/multi_market.sqlite3): `books` for the
ask and its size, `k1s` for the Binance price, `resolutions` for the venue's own settlement. The model is
frozen from ETH_SOL_EF.md arm (iv) on 14 days and is not refitted.

Needs >= 12 h of recorded books to be worth reading; it prints what it has and marks cells under 60.
"""
import sqlite3, math, argparse, datetime as dt, numpy as np

ap = argparse.ArgumentParser(); ap.add_argument('--db', default='/home/ubuntu/pm_multi/multi_market.sqlite3')
ap.add_argument('--theta', type=float, default=0.25); ap.add_argument('--stake', type=float, default=5.0)
A = ap.parse_args()
FROZEN = {'eth': (-0.007173, 1.487533), 'sol': (-0.027489, 1.863596)}
RATE, SEC_LO, SEC_HI, DELAYS = 0.07, 15, 240, (0, 1, 2, 3)
cost = lambda x: 1 + RATE * (1 - x)
ev_of = lambda p, a: p / (a * cost(a)) - 1

c = sqlite3.connect(f'file:{A.db}?mode=ro', uri=True)
f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
bl, bh = c.execute('SELECT min(ts),max(ts) FROM books').fetchone()
print(f'recorded books {f(bl)} -> {f(bh)} = {(bh-bl)/3600:.2f} h'
      + ('' if (bh - bl) >= 12 * 3600 else '   *** UNDER 12 h: not a reading yet ***'))

for coin in ('eth', 'sol'):
    b0, b1 = FROZEN[coin]
    kl = dict(c.execute('SELECT ts,cl FROM k1s WHERE sym=?', (coin,)).fetchall())
    res = dict(c.execute('SELECT epoch,outcome FROM resolutions WHERE market=?', (coin,)).fetchall())
    bk = {}
    for ts, ua, uz, da, dz in c.execute(
            'SELECT ts,up_ask,up_ask_sz,dn_ask,dn_ask_sz FROM books WHERE market=?', (coin,)):
        bk[ts] = (ua, uz, da, dz)
    def close_at(t, limit=3600):
        for k in range(limit + 1):
            if (t - k) in kl: return kl[t - k]
        return None
    eps = sorted({t // 300 * 300 for t in bk} & set(res))
    rows = []
    for ep in eps:
        line_px = [close_at(ep - 60 + i, 60) for i in range(60)]
        if any(v is None for v in line_px): continue
        line = sum(line_px) / 60.0
        if line <= 0: continue
        fired = False
        for s in range(SEC_LO, SEC_HI + 1):
            if fired: break
            t = ep + s
            if t not in bk: continue
            seq = [close_at(t - 1 - 900 + i) for i in range(901)]
            if any(v is None for v in seq): continue
            lr = [math.log(seq[i+1]/seq[i]) for i in range(900)]
            m = sum(lr)/900.0; v = sum(x*x for x in lr)/900.0 - m*m
            sig = math.sqrt(max(v, 1e-12))
            zt = math.log(seq[-1]/line)/(sig*math.sqrt(max(240-s, 0)+20))
            p_up = 1/(1+math.exp(-max(-30, min(30, b0+b1*zt))))
            ua, uz, da, dz = bk[t]
            best = None
            for side, ps, a, sz in (('UP', p_up, ua, uz), ('DOWN', 1-p_up, da, dz)):
                if a is None or not (0.02 <= a <= 0.98): continue
                e = ev_of(ps, a)
                if best is None or e > best[0]: best = (e, side, ps, a, sz)
            if best is None or best[0] < A.theta: continue
            e, side, ps, a0, sz0 = best
            win = int(side == res[ep])
            later = {}
            for d in DELAYS:
                bb = bk.get(t + d)
                if not bb: later[d] = None; continue
                aa, ss = (bb[0], bb[1]) if side == 'UP' else (bb[2], bb[3])
                later[d] = (aa, ss) if (aa is not None and 0.02 <= aa <= 0.98) else None
            rows.append(dict(ep=ep, s=s, side=side, p=ps, ev=e, ask0=a0, sz0=sz0, win=win, later=later))
            fired = True
    print(f'\n{coin.upper()}: {len(eps)} graded candles with books, {len(rows)} fired at EV>={A.theta} '
          f'(one per candle, first qualifying second)')
    if not rows: continue
    print(f'  fire second p50 {int(np.median([r["s"] for r in rows]))}  ask p50 {np.median([r["ask0"] for r in rows]):.2f}  '
          f'hit {100*np.mean([r["win"] for r in rows]):.1f}%')
    print(f'  {"delay":>6}{"n":>6}{"ask p50":>9}{"ask move":>10}{"size p50":>10}{"$ at best":>11}{"per$1":>9}{"cum pnl $":>11}')
    for d in DELAYS:
        sub = [r for r in rows if r['later'][d]]
        if not sub: print(f'  {d:>5}s{0:>6}       (no rows)'); continue
        asks = np.array([r['later'][d][0] for r in sub]); szs = np.array([r['later'][d][1] for r in sub])
        base = np.array([r['ask0'] for r in sub]); wins = np.array([r['win'] for r in sub], float)
        # money: $stake at the ask, capped by the size actually at best; fee 0.07*sh*p*(1-p)
        cash = np.minimum(A.stake, asks * szs)
        sh = cash / asks
        fees = RATE * sh * asks * (1 - asks)
        pnl = np.where(wins > 0, sh, 0.0) - cash - fees
        tot = (cash + fees).sum()
        mark = '' if len(sub) >= 60 else '  INSUFFICIENT'
        print(f'  {d:>5}s{len(sub):>6}{np.median(asks):>9.3f}{100*np.mean(asks-base):>+9.2f}c'
              f'{np.median(szs):>10.0f}{np.median(asks*szs):>11.2f}{pnl.sum()/tot:>+9.3f}{pnl.sum():>+11.2f}{mark}')
    print('  ask move is in cents vs the ask at the decision second; "$ at best" is ask*size, i.e. what a')
    print('  taker could actually lift at the touch - the stake is capped by it, which is the size answer.')
