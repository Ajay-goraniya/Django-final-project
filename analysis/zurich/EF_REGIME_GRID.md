# Is there a regime where fixed15 is robustly profitable under London execution?

Owner/V: London's Fixed EF made money 09-23..25 (weekdays) and lost 09-26..27 (weekend, quiet).

Read-only, Zurich data, London untouched, nothing live. `analysis/zurich/ef_regime_grid.py`.

**Answer: the weekday/weekend split is real and large, and it still does not clear the gates — the weekday
cell fails cost sensitivity, and the whole result rests on 16 weekend fires.**

## Setup

All BTC EF paper fires re-profiled to **fixed15**, and re-profiled the way the engine actually judges it:
`q = platt(p_raw)` (a=1.0677, b=−0.3208, `q=min(p,q)`) with EV taken at **ask + 1 tick**
(`poly_core.EV_REFERENCE_PAD`), not at the raw ask. Using the raw ask would have loosened the bar by ~0.02
and silently changed which fires exist.

**129 fires on 7 days (09-22..09-28)**, win 57.4%, ask p50 0.47, sec p50 143. Graded on the venue's own
gamma resolution. Priced with `LONDON_EXEC_MODEL.md`: P(fill|win) 0.541, P(fill|lose) 0.650, slippage
p10/p50/p90 −1/+2/+11c on top, $10, 1000 runs.

Buckets were fixed in V's brief before anything was looked at. (a) and (d) use only the 60 minutes **before**
the candle opens. Tercile cuts on all fires: vol 0.000442 / 0.000679 (1-minute realised sd), range
49.6 / 86.8 bps.

## Full grid — `*` = n<60, not a reading

| bucket | n | win% | paper | **LONDON** | H1 | H2 | pos days | total $ |
|---|---|---|---|---|---|---|---|---|
| **(a) vol LOW** | 43* | 55.8% | +0.129 | −0.032 | +0.409 | −0.421 | 3/6 | −8.4 |
| (a) vol MID | 43* | 55.8% | +0.109 | −0.045 | +0.192 | −0.274 | 2/5 | −11.8 |
| (a) vol HIGH | 43* | 60.5% | +0.179 | **+0.022** | −0.040 | +0.063 | 3/5 | +5.7 |
| **(b) weekday Mon–Fri** | **113** | **61.1%** | +0.225 | **+0.065** | **+0.108** | **+0.025** | 3/5 | **+44.2** |
| (b) weekend Sat–Sun | 16* | **31.2%** | −0.471 | **−0.555** | −0.796 | −0.295 | **0/2** | −56.6 |
| (c) 00–08 UTC | 42* | 52.4% | +0.088 | −0.074 | +0.088 | −0.236 | 3/7 | −19.0 |
| (c) 08–16 UTC | 53* | 52.8% | +0.009 | **−0.139** | −0.077 | −0.193 | 2/5 | −45.3 |
| (c) 16–24 UTC | 34* | **70.6%** | +0.406 | **+0.230** | +0.523 | −0.021 | 4/5 | +46.2 |
| (d) range LOW | 43* | 51.2% | +0.036 | −0.122 | +0.245 | −0.436 | 2/6 | −32.3 |
| (d) range MID | 43* | 67.4% | +0.323 | **+0.159** | +0.317 | −0.003 | 3/5 | +40.7 |
| (d) range HIGH | 43* | 53.5% | +0.059 | −0.091 | −0.125 | −0.070 | 3/5 | −23.8 |
| **all fires** | 129 | 57.4% | +0.139 | **−0.021** | +0.194 | −0.229 | 3/7 | −16.4 |

Note the reference row: **fixed15 across all fires is −0.021/$1 under London execution.** Whatever regime
story is told has to be told against that.

## The one cell that qualified for verify.py, and it fails

Only **weekday Mon–Fri** is positive in both halves with n≥60.

```
FINDING: fixed15 under London execution, weekday Mon-Fri   (+0.065/fire, n=113)
  [PASS] grading provenance   gamma vs engine disagree on 0/90 (0.0%)
  [PASS] quote age            same-instant, executor read
  [PASS] sample size          n 113 >= 60
  [PASS] both halves          h1 +0.108 / h2 +0.025
  [PASS] permutation control  +0.065 vs coin-flip sides at the OPPOSITE ask: mean -0.175 (p95 -0.041), p=0.000
  [FAIL] cost sensitivity     +0c:+0.065 +2c:+0.018 +5c:-0.036   <- dies once you pay realistically
  [PASS] beats the null       mine +0.065 vs buy the other side instead -0.398
  VERDICT: NOT A FINDING - failed: cost sensitivity
```

Six of seven gates pass, including permutation at **p=0.000**. It dies on cost: **+0.065 at 0c, +0.018 at
2c, −0.036 at 5c.** And that stress is *on top of* the London model's own −1/+2/+11c slippage, so the true
margin is thinner than the headline.

## The caveat that matters most

**The weekday cell is 113 of 129 fires — 88% of the sample.** Removing the 16 weekend fires is what moves
the whole set from **−0.021 to +0.065**. So "weekday fixed15 is profitable" is very nearly the statement
"all fires, minus the 16 worst", and the entire regime claim rests on **n=16** on **2 days**.

That is not nothing — those 16 fires won 31.2% and lost −0.555/$1, which is a big, coherent effect in the
direction the owner predicted. But two weekend days cannot establish a weekend rule, and one more quiet
weekday would test it just as well as a weekend does.

## What else the grid says, as context only (every cell n<60)

- **16–24 UTC is the strongest cell anywhere**: 70.6% win, London +0.230, 4/5 positive days (n34).
  **08–16 UTC is the worst session**: −0.139 (n53). If there is a real regime here it may be a *session*
  effect that the weekday/weekend cut is partly picking up — the weekend is 2 days, the sessions cut all 7.
  I have not combined buckets to chase that; doing so post hoc is the trap the brief warns against.
- **Vol does not separate cleanly**: LOW −0.032, MID −0.045, HIGH +0.022. Only the high tercile is positive
  and barely, and its halves are −0.040/+0.063 — the opposite sign pattern to the low tercile's
  +0.409/−0.421. That is noise, not a regime.
- **Range is non-monotone**: LOW −0.122, MID **+0.159**, HIGH −0.091. A middle-peaking bucket on n=43 cells
  is the classic overfit shape, so I would not act on it.

## Verdict

1. **No bucket is robustly profitable under London execution on this sample.** The only cell large enough
   and stable enough to test fails cost sensitivity.
2. **The owner's observation is directionally right and worth keeping**: weekend fires are much worse
   (31.2% win, −0.555/$1, 0/2 positive days). But the evidence is 16 fires on 2 days.
3. The honest next step is more days, and specifically more weekend days — one more weekend would roughly
   double the evidence for the only effect in this grid that looks real.
4. Nothing here should change London. The margin on the best testable cell is +0.065 and it is gone by 5c.
