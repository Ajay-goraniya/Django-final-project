#!/usr/bin/env python3
"""BTC 15m vs the last 5m candle inside it: is there a riskless pair? READ-ONLY.

Both markets settle on the SAME closing TWAP60 X, against different lines: L15 (the 15m opening line) and
L5 (the last 5m candle's opening line). So with ONE SHARE of each leg:

  L15 < L5:  buy 15m UP + 5m DOWN     X >= L5 -> 1+0 ;  L15 <= X < L5 -> 1+1 ;  X < L15 -> 0+1
  L15 > L5:  buy 15m DOWN + 5m UP     X >= L15 -> 0+1 ;  L5 <= X < L15 -> 1+1 ;  X < L5 -> 1+0

Payoff is 1 or 2 per share-pair, never 0. So any second where
    cost = a15 + fee(a15) + a5 + fee(a5)   <   1        (fee per share = 0.07*p*(1-p))
is a riskless profit, and any second where cost < 1 + P(band) is positive in expectation.

P(band) is estimated EMPIRICALLY from the realised gamma outcomes of these windows rather than from a vol
model - with ~90 windows the direct frequency is the better estimate and needs no distributional guess.

Sources: the recorder's 1 Hz btc15 book (both tokens, with sizes), the engine's tape1s BTC-5m asks at the
SAME second (past-only by construction - both are reads at that second), and the lines from tape1s.ref_px,
which is the Chainlink reference the venue settles on.
"""
import sqlite3, datetime as dt, collections, numpy as np

MULTI = '/home/ubuntu/pm_multi/multi_market.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
RATE = 0.07
fee = lambda p: RATE * p * (1 - p)

def outcomes5():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out

def main():
    mc = sqlite3.connect(f'file:{MULTI}?mode=ro', uri=True)
    lc = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    res15 = dict(mc.execute("SELECT epoch,outcome FROM resolutions WHERE market='btc15'").fetchall())
    res5 = outcomes5()
    b15 = {}
    for ts, ep, ua, uz, da, dz in mc.execute(
            "SELECT ts,epoch,up_ask,up_ask_sz,dn_ask,dn_ask_sz FROM books WHERE market='btc15'"):
        b15[int(ts)] = (int(ep), ua, uz, da, dz)
    tape = {}
    ref = {}
    for ts, ua, da, rp in lc.execute(
            'SELECT ts,up_ask,dn_ask,ref_px FROM tape1s WHERE ts>=? ORDER BY ts',
            (min(b15) - 700,)):
        if ua is not None and da is not None: tape[int(ts)] = (ua, da)
        if rp is not None: ref[int(ts)] = float(rp)

    eps = sorted({v[0] for v in b15.values()})
    f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'btc15 windows with book: {len(eps)}, {f(eps[0])} -> {f(eps[-1])} '
          f'= {(eps[-1]-eps[0])/3600:.1f} h ({len({dt.datetime.fromtimestamp(e,dt.timezone.utc).strftime("%m-%d") for e in eps})} days)')

    def line(ep):
        v = [ref.get(ep - k) for k in range(1, 61)]
        v = [x for x in v if x is not None]
        return (sum(v) / len(v)) if len(v) >= 45 else None

    rows = []
    stats = collections.Counter()
    for ep15 in eps:
        ep5 = ep15 + 600
        L15, L5 = line(ep15), line(ep5)
        if L15 is None or L5 is None: stats['no_line'] += 1; continue
        if abs(L15 - L5) < 1e-9: stats['lines_equal'] += 1; continue
        leg15, leg5 = ('UP', 'DOWN') if L15 < L5 else ('DOWN', 'UP')
        o15, o5 = res15.get(ep15), res5.get(ep5)
        band = (o15 is not None and o5 is not None and o15 == leg15 and o5 == leg5)
        stats['windows'] += 1
        if o15 is not None and o5 is not None: stats['graded'] += 1
        if band: stats['band'] += 1
        for s in range(ep5, ep5 + 296):
            if s not in b15 or s not in tape: continue
            ep, ua, uz, da, dz = b15[s]
            if ep != ep15: continue
            a15, z15 = (ua, uz) if leg15 == 'UP' else (da, dz)
            t = tape[s]; a5 = t[0] if leg5 == 'UP' else t[1]
            if a15 is None or a5 is None: continue
            if not (0.01 < a15 < 0.99 and 0.01 < a5 < 0.99): continue
            cost = a15 + fee(a15) + a5 + fee(a5)
            nxt = None
            if (s + 1) in b15 and (s + 1) in tape:
                ep2, ua2, _, da2, _ = b15[s + 1]
                if ep2 == ep15:
                    a15b = ua2 if leg15 == 'UP' else da2
                    t2 = tape[s + 1]; a5b = t2[0] if leg5 == 'UP' else t2[1]
                    if a15b is not None and a5b is not None: nxt = (a15b, a5b)
            pay = (1 if (o15 == leg15) else 0) + (1 if (o5 == leg5) else 0) if (o15 and o5) else None
            rows.append(dict(ep15=ep15, s=s, sec=s - ep5, leg15=leg15, leg5=leg5, a15=a15, a5=a5,
                             sz15=z15, cost=cost, band=band, pay=pay, nxt=nxt,
                             day=dt.datetime.fromtimestamp(ep15, dt.timezone.utc).strftime('%m-%d')))
    print(f'  windows used {stats["windows"]}, graded on BOTH markets {stats["graded"]}, '
          f'lines equal {stats["lines_equal"]}, no line {stats["no_line"]}')
    if not rows: print('no scannable seconds'); return
    P_band = stats['band'] / max(stats['graded'], 1)
    print(f'  P(band) EMPIRICAL = {stats["band"]}/{stats["graded"]} = {P_band:.3f}  '
          f'(the 2-payoff case; fair cost of the pair is 1 + P(band) = {1+P_band:.3f})')
    c = np.array([r['cost'] for r in rows])
    print(f'\nscannable seconds: {len(rows)} across {len({r["ep15"] for r in rows})} windows')
    print(f'  pair cost: min {c.min():.4f}  p05 {np.percentile(c,5):.4f}  p50 {np.percentile(c,50):.4f}  '
          f'p95 {np.percentile(c,95):.4f}  max {c.max():.4f}')
    print(f'  cost < 1.000            : {int((c<1).sum())} seconds ({100*(c<1).mean():.3f}%) '
          f'on {len({r["ep15"] for r in rows if r["cost"]<1})} windows')
    print(f'  cost < 1 + P(band)      : {int((c<1+P_band).sum())} seconds ({100*(c<1+P_band).mean():.3f}%) '
          f'on {len({r["ep15"] for r in rows if r["cost"]<1+P_band})} windows')
    for thr, lab in ((1.0, 'riskless'), (1 + P_band, 'positive EV')):
        sel = [r for r in rows if r['cost'] < thr]
        if not sel: continue
        sz = np.array([r['sz15'] for r in sel if r['sz15'] is not None], float)
        graded = [r for r in sel if r['pay'] is not None]
        pays = np.array([r['pay'] for r in graded], float) if graded else np.array([])
        surv = [r for r in sel if r['nxt'] is not None]
        ok = sum(1 for r in surv if r['nxt'][0] <= r['a15'] + 1e-9 and r['nxt'][1] <= r['a5'] + 1e-9)
        print(f'\n  --- {lab} cells (cost < {thr:.3f}), n {len(sel)} ---')
        print(f'    cost p50 {np.median([r["cost"] for r in sel]):.4f}, best {min(r["cost"] for r in sel):.4f}; '
              f'a15 p50 {np.median([r["a15"] for r in sel]):.3f}, a5 p50 {np.median([r["a5"] for r in sel]):.3f}')
        if len(sz): print(f'    15m touch size: p10 {np.percentile(sz,10):.0f} p50 {np.percentile(sz,50):.0f} '
                          f'p90 {np.percentile(sz,90):.0f} shares  (= ${np.median(sz)*np.median([r["a15"] for r in sel]):.2f} at the touch)')
        if len(pays): print(f'    realised payoff on gamma: mean {pays.mean():.3f} per share-pair, '
                            f'2-payoff on {int((pays==2).sum())}/{len(pays)}, 1-payoff {int((pays==1).sum())}, '
                            f'0-payoff {int((pays==0).sum())}  <- 0 would break the structure')
        if surv: print(f'    LEGGING: both legs\' asks still <= their value 1 s later on {ok}/{len(surv)} '
                       f'({100*ok/len(surv):.1f}%)')
    print(f'\n  per-day count of riskless seconds:')
    byd = collections.Counter(r['day'] for r in rows if r['cost'] < 1)
    alld = collections.Counter(r['day'] for r in rows)
    for d in sorted(alld): print(f'    {d}: {byd.get(d,0)} of {alld[d]} scanned seconds')

if __name__ == '__main__':
    main()
