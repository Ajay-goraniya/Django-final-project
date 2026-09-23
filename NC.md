# NC - New Changes (owner's list)

Findings the owner asked to record. Nothing here is deployed on London (eu-west-2) without the owner's
confirmation of that specific change (CLAUDE.md rule, 09-23).

## NC-1 - REVERSAL on Polymarket: trade only up to 240 s into the candle (09-23)

- **Why:** Polymarket settles on TWAP60 (average of the last 60 s vs the 60 s before the open), not on the plain
  candle close. A reversal that happens in the last minute only moves part of that average, so late REVERSAL
  bets stop paying. Predict.fun settles on the plain candle, so it is not affected the same way.
- **Result (8-day Polymarket replay, exact fee, graded on Polymarket's own outcome):**

  | window | trades | per $1 | w/o top 3 | all checks | losing days |
  |---|---|---|---|---|---|
  | 0-240 s | 394 | +0.215 | +0.144 | PASS (shuffle p=0.001, beats cheap-side null) | 1 of 9 |
  | 0-200 s | 323 | +0.144 | +0.063 | FAIL (shuffle, null) | 3 of 9 |
  | 200-240 s | 71 | +0.538 | +0.304 | PASS | 1 of 9 |
  | after 240 s | 65 | about -0.03 without one lucky 1c ticket | | | |

- **Meaning:** keep REVERSAL's trades up to 240 s; do not cut at 200 s (200-240 s is its best window);
  never trade it after 240 s. London's order engine already refuses orders after 240 s, so no code change is needed.
- **Limits:** the replay assumes every order fills (live, 40-60% of first tries are refused). Zurich's live
  shadow REVERSAL is weaker so far (32 trades, +0.034/$1) - confirm at 60 trades before any live use.
- **Status:** tested on replay, not deployed. REVERSAL stays OFF on London.
- **Full grid (every bucket, Polymarket replay, 459 graded REVERSAL):**

  | bucket | n | right | per $1 | w/o top 3 |
  |---|---|---|---|---|
  | 0-60 s | 36 (<60) | 66.7% | +0.098 | -0.016 |
  | 60-120 s | 123 | 62.6% | +0.077 | +0.001 |
  | 120-180 s | 119 | 65.5% | +0.202 | +0.014 |
  | 180-200 s | 45 (<60) | 64.4% | +0.213 | -0.056 |
  | 200-240 s | 71 | 83.1% | +0.538 | +0.304 |
  | 240-300 s | 65 | 49.2% | +1.769 (one 0.010 ticket) | -0.034 |

  0-240 s by day: 09-08 -0.153 | 09-09 +0.032 | 09-10 +0.176 | 09-11 +0.255 | 09-12 +0.846 | 09-13 +0.643 |
  09-14 +0.283 | 09-15 +0.067 | 09-16 +0.043. Costs: +1c +0.185, +2c +0.157, +5c +0.086.
  Predict.fun (Mumbai 8796): 43 trades, too few to compare.
- **Reproduce** (save as a .py next to `analysis/h1/verify.py`'s repo root; args `--rows lanes_twap60.csv --venues venues.sqlite3 --lo 0 --hi 240`):

```python
"""REVERSAL <240 s on the 8-day Polymarket replay, through analysis/h1/verify.py's gates (V, 09-23).
Input: lanes_twap60.csv (replay_lanes_1s.py --open twap60) + venues.sqlite3 (q = both asks at 1 Hz, outcome = Polymarket
resolution). Exact fee 0.07p(1-p) inside the stake; $1 per fire."""
import sys, csv, sqlite3, bisect, argparse, numpy as np, datetime as dt
sys.path.insert(0, 'analysis/h1'); import verify as V
ap = argparse.ArgumentParser(); ap.add_argument('--rows', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--lo', type=float, default=0); ap.add_argument('--hi', type=float, default=240); a = ap.parse_args()
vc = sqlite3.connect(a.venues); Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')]; QT = [q[0] for q in Q]
OUT = {int(e): x.upper() for e, x in vc.execute('select epoch,actual from outcome') if x}
def asks(ts):
    i = bisect.bisect_left(QT, ts - 5); best = None
    for j in range(i, min(len(Q), i + 11)):
        if abs(Q[j][0] - ts) <= 5 and Q[j][1] is not None and Q[j][2] is not None and (best is None or abs(Q[j][0] - ts) < abs(best[0] - ts)): best = Q[j]
    return (float(best[1]), float(best[2])) if best else None
R = []
for r in csv.DictReader(open(a.rows)):
    if r['kind'] != 'REVERSAL' or r['win'] in ('', 'None') or not (a.lo <= float(r['sec']) < a.hi): continue
    q = asks(int(r['ts']))
    if not q: continue
    R.append(dict(ep=int(r['epoch']), ts=int(r['ts']), side=r['side'], ask=float(r['ask']), up=q[0], dn=q[1], act=r['actual'].upper(), win=int(r['win'])))
R.sort(key=lambda r: r['ts'])
pay = lambda ask, win: (1 / (ask * (1 + 0.07 * (1 - ask))) - 1) if win else -1.0
per = np.array([pay(r['ask'], r['win']) for r in R]); n = len(R); h = n // 2
F = V.Finding(f'REVERSAL {a.lo:.0f}-{a.hi:.0f}s, Polymarket 8-day replay', per.mean(), n)
F.grading(replay_actual={r['ep']: r['act'] for r in R}, venues_outcome={r['ep']: OUT[r['ep']] for r in R if r['ep'] in OUT})
days = {}
for r, x in zip(R, per): days.setdefault(dt.datetime.utcfromtimestamp(r['ep']).strftime('%m-%d'), []).append(x)
F.sample({'all': n}); F.halves(per[:h].mean(), per[h:].mean())
y = np.array([1 if r['act'] == 'UP' else 0 for r in R]); pred = np.array([1.0 if r['side'] == 'UP' else 0.0 for r in R])
AU = np.array([r['up'] for r in R]); AD = np.array([r['dn'] for r in R])
def pnl(y_, p_, _):
    ask = np.where(p_ == 1, AU, AD); win = (p_ == y_)
    return float(np.mean(np.where(win, 1 / (ask * (1 + 0.07 * (1 - ask))) - 1, -1.0)))
F.permutation(y, pred, np.zeros(n), pnl, draws=1000)
F.costs({k: np.mean([pay(min(.999, r['ask'] + k), r['win']) for r in R]) for k in (0, .01, .02, .05)})
cheap = np.mean([pay(min(r['up'], r['dn']), (r['act'] == 'UP') == (r['up'] <= r['dn'])) for r in R])
F.null(per.mean(), cheap, 'buy the cheaper side at the same second')
opp = np.mean([pay(r['dn'] if r['side'] == 'UP' else r['up'], r['act'] != r['side']) for r in R])
F.null(per.mean(), opp, 'buy the OTHER side at the same second')
top = np.sort(per)[::-1]
print('concentration: all %+.3f | w/o top1 %+.3f | w/o top3 %+.3f | w/o top10 %+.3f' % (per.mean(), top[1:].mean(), top[3:].mean(), top[10:].mean()))
print('by day (n, per$1):', ' '.join(f'{d} {len(v)} {np.mean(v):+.3f}' for d, v in sorted(days.items())), '| losing days', sum(np.mean(v) < 0 for v in days.values()), '/', len(days))
F.verdict()
```

## NC-2 - TWAP settlement study (09-24) - verdict: the TWAP maths is right and needed, but on its own it is NOT an edge

Data: 2,274 candles 09-08..09-16. Polymarket's own `priceToBeat`/`finalPrice` per candle (gamma API, public after
the candle settles), Binance 1 s klines, Polymarket 1 Hz asks, `venues.outcome`.

- **A. Ground truth.** `finalPrice >= priceToBeat` matches Polymarket's resolution **2179/2179**. The price to beat of
  a candle = the previous candle's final TWAP (TWAP60 of Chainlink ending at the open). Polymarket does NOT publish it
  live - only after settlement - but it can be computed live from the Chainlink stream (London already does: `line_open`).
- **A. Which Binance proxy predicts the settlement.** Binance TWAP60 close vs TWAP60 open agrees with Polymarket
  **96.7%**; the plain Binance candle (close vs open) only **87.0%**. Every disagreement of the TWAP proxy is in a
  near-tie candle (|TWAP move| < 1 bp: 21% wrong, n=349); above 1 bp it is **0% wrong** (n=1,925).
  Chainlink sits about **$25 below Binance** (p10/p90 $-51/$-12) and that gap drifts only $2 (p50) / $6 (p90) within a candle.
- **B. Fair-probability maths (no fitted parameters, sigma = trailing Binance volatility, 4 windows 300-3600 s).**
  The TWAP-aware formula beats the plain close-vs-open formula at **every second of the candle, every window**
  (log loss e.g. 120 s 0.528 vs 0.557; 240 s 0.314 vs 0.446; 270 s 0.218 vs 0.953 - the plain formula collapses after
  240 s because it ignores the locked-in part of the average). **But Polymarket's own price beats both at every
  second** (120 s 0.495; 240 s 0.240; 270 s 0.124). The market already prices TWAP, and more.
- **C. Money: fire when the TWAP fair price beats Polymarket's ask** (15-239 s, first second EV >= bar, exact fee,
  1 s decision lag, graded on Polymarket). Full grid, 24 cells: TWAP model -0.066..+0.004 per $1 (best cell n=1390,
  +0.004, dies at +2c: -0.066); plain model -0.129..-0.036, worse in every cell. **No cell makes money.**
- **Verdict:** a pure TWAP fair-price model has no edge against Polymarket's price - do not build it as a signal.
  What TWAP is good for:
  1. **Labels:** anything trained or graded on the Binance candle (close >= open) is wrong on 13% of candles; the
     Binance TWAP60 proxy is wrong on 3.3%, all of them near-ties. Models should be trained on the TWAP label.
  2. **Timing:** after 240 s the average is part-locked - the reason late REVERSAL fails (NC-1).
  3. **Near-ties (< 1 bp)** are unreadable even with the right formula (21% proxy error) - that is where EF's
     losses concentrate (H1: near-tie candles -0.144/$1).
- **Next test (not done):** check which label EF's v10 model was trained on; if the Binance candle, retrain on the
  TWAP label and compare walk-forward. Not deployed anywhere; London unchanged.
