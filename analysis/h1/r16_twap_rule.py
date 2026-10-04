"""R-16 -- test Mumbai's settlement rule (btc-5m-twap-60) against the venue outcomes.

Rule per gamma: outcome = Chainlink 60 s TWAP at candle END vs the same 60 s TWAP at eventStartTime.
Chainlink is not Binance, but a LEVEL offset cancels in a TWAP-minus-TWAP comparison, so Binance 1 s
spot is a usable proxy for the SIGN. Testing the sign is the whole point: if TWAP60-vs-TWAP60 on
Binance matches venues.outcome materially better than close-vs-open does, the rule is confirmed and
the engine has been measuring its distance from the wrong line.
"""
import os, sys, numpy as np, sqlite3, datetime as dt
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import r12_parity as P
from r12_extract import to_sec

CACHE = '/tmp/claude-0/r16_px.npz'
days = ['2026-09-%02d' % d for d in range(7, 16)]
if os.path.exists(CACHE):
    z = np.load(CACHE); LO, PX = int(z['lo']), z['px']
else:
    arrs = []
    for d in days:
        try:
            a = P.daily(d)
        except Exception as e:
            print('  no daily %s (%s)' % (d, e)); continue
        a = a.copy(); a[:, 0] = to_sec(a[:, 0])
        arrs.append(a[:, :2])
    a = np.vstack(arrs)
    sec = a[:, 0].astype(np.int64)
    LO, HI = int(sec[0]), int(sec[-1])
    n = HI - LO + 1
    PX = np.full(n, np.nan)
    PX[sec - LO] = a[:, 1]
    m = np.isnan(PX)
    good = np.where(~m)[0]
    PX[:good[0]] = PX[good[0]]
    PX = PX[np.maximum.accumulate(np.where(m, 0, np.arange(n)))]
    np.savez_compressed(CACHE, lo=LO, px=PX)
print('1s grid: %s .. %s (%d s)' % (dt.datetime.utcfromtimestamp(LO),
      dt.datetime.utcfromtimestamp(LO + len(PX) - 1), len(PX)))

v = sqlite3.connect('/tmp/claude-0/db/venues.sqlite3')
rows = [(int(e), str(a).upper()) for e, a in v.execute('select epoch,actual from outcome')]
res = []
for e, act in rows:
    i = e - LO
    if i - 60 < 0 or i + 300 > len(PX):
        continue
    twap_o = PX[i - 60:i].mean()
    twap_e = PX[i + 240:i + 300].mean()
    op, cl = PX[i], PX[i + 299]
    res.append((e, act, twap_e - twap_o, cl - op, op))
print('candles tested:', len(res))
tw = np.array([r[2] for r in res]); co = np.array([r[3] for r in res])
op = np.array([r[4] for r in res]); act = np.array([r[1] for r in res])
for nm, x in (('close >= open (current)', co), ('TWAP60(end) >= TWAP60(open)', tw)):
    pred = np.where(x >= 0, 'UP', 'DOWN')
    print('  %-30s agrees with venues.outcome %6.2f%%  (%d of %d)'
          % (nm, 100 * (pred == act).mean(), int((pred == act).sum()), len(act)))
# where they differ from each other
d = (np.where(co >= 0, 'UP', 'DOWN') != np.where(tw >= 0, 'UP', 'DOWN'))
print('\n  the two rules disagree with EACH OTHER on %d of %d candles (%.1f%%)'
      % (d.sum(), len(d), 100 * d.mean()))
if d.sum() >= 60:
    a1 = (np.where(co >= 0, 'UP', 'DOWN')[d] == act[d]).mean()
    a2 = (np.where(tw >= 0, 'UP', 'DOWN')[d] == act[d]).mean()
    print('  on those, close-vs-open is right %.1f%%, TWAP-vs-TWAP is right %.1f%%'
          % (100 * a1, 100 * a2))
    from math import comb
    b = int((np.where(tw >= 0, 'UP', 'DOWN')[d] == act[d]).sum()); n = int(d.sum())
    print('  exact binomial p (TWAP better than coin on the discordant set) = %.3g'
          % min(1.0, 2 * sum(comb(n, k) * .5 ** n for k in range(0, min(b, n - b) + 1))))
np.savez_compressed('/tmp/claude-0/r16_twap_vals.npz',
                    ep=np.array([r[0] for r in res]), tw=tw, co=co, op=op, act=act)
