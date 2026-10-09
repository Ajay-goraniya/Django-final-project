# Can EF be made stable? Selectivity and hybrid staking on BTC EF

Owner (09-27 11:3x): *"work on staking or removing loss... stable version... fine with 5 winning trades a
day instead of 50 at 50% win rate... then I can use hybrid staking."*

**Read-only backtest. No config change, nothing live.** Kelly/dynamic staking going live still needs the
owner's **two separate confirmations** (CLAUDE.md); nothing here is a request to arm anything.

Script `analysis/zurich/stable_ef.py`. Fires rebuilt from the engine's own `diagnostics` pnl rows — the
source `raw_vs_fixed_london_exec.py` uses — so both profiles exist on the same candles:
**490 fires, 286 candles, 9 days** (RAW 266, FIXED 224).

Grading is the **venue's own resolution**, fetched from gamma for this window (332 fires), with engine
`results.actual` only where gamma has no row (158). Where both exist they **agree 0 disagreements in 30**.
The ask is the executor's own read at the deciding pass, so quotes are same-instant, not forward-filled.

Ranking statistic, fixed before looking: **edge = platt(p_raw) − ask·(1+0.07(1−ask))**, probability minus
break-even probability. Tiers keep the top X% **within each day**, so the bar adapts instead of being a
threshold fitted to the sample.

## 1. Selectivity — good on paper, and it fails its own controls

RAW (`*` = n<60, not a reading):

| tier | n | /day | win% | paper | **LONDON** | dayStd | worstDay | maxDD | pos days | H1 | H2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| top 5% | 15* | 1.7 | 53.3% | +0.136 | −0.037 | 15.0 | −20.0 | 20.3 | 56% | +0.331 | −0.033 |
| top 10% | 27* | 3.0 | 55.6% | +0.145 | −0.020 | 11.4 | −10.2 | 30.3 | 56% | +0.162 | +0.129 |
| **top 20%** | 54* | 6.0 | 59.3% | **+0.225** | **+0.060** | 30.4 | −23.6 | 39.3 | 44% | +0.273 | +0.177 |
| top 40% | 106 | 11.8 | 59.4% | +0.204 | +0.041 | 48.6 | −29.9 | 95.4 | 44% | +0.226 | +0.182 |
| all | 266 | 29.6 | 50.0% | +0.056 | −0.103 | 73.0 | −53.5 | 258.4 | 44% | +0.001 | +0.110 |

FIXED: **every tier is London-negative** (−0.159, −0.154, −0.035, −0.034, −0.059 for 5/10/20/40/100%), so
the selectivity idea only survives execution on RAW at all.

### verify.py on the arm I would have put forward — it is rejected

```
FINDING: EF RAW, top 20% by calibrated edge per day
  [PASS] grading provenance   gamma vs engine disagree on 0/30 (0.0%)
  [PASS] quote age            same-instant, executor read
  [FAIL] sample size          under the 60 bar: 54
  [PASS] both halves          h1 +0.273 / h2 +0.177
  [FAIL] permutation control  edge-ranked +0.225 vs SAME COUNT PER DAY chosen at RANDOM:
                              mean +0.059 (p95 +0.262), p=0.084 over 1000 draws
  [PASS] cost sensitivity     +0c:+0.225 +2c:+0.176 +5c:+0.111
  [PASS] beats the null       mine +0.225 vs buy the other side instead -0.284
  [FAIL] sweep shape          NON-monotone: [0.136 0.145 0.225 0.204 0.056], peaks at an interior point
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape
```

Two of those failures are the substance, not bookkeeping:

- **The edge ranking is not doing the work.** Picking the same number of fires per day *at random* averages
  +0.059, and its **p95 is +0.262 — above the real +0.225**. p=0.084 against a p≤0.01 bar. So "top 20% by
  edge" is not distinguishable from "6 fires a day, any 6".
- **The sweep peaks at the interior 20%** (+0.136, +0.145, **+0.225**, +0.204, +0.056). That is the exact
  shape CLAUDE.md names as fitting to noise, and 20% is the tier I would have chosen.

Two of my own call errors were fixed before this was believed: I first passed a prose string to
`quote_age` (correctly refused — the literal is what makes the check work), and a `pnl_fn` that ignored the
shuffled predictions, so real and permuted were identical at p=1.000 — a control that could not fail.

## 2. Hybrid staking — second order to selectivity, and half-Kelly collapses

All arms normalised to deploy the same total as fixed $10, so per$1 and maxDD compare per dollar risked.
Terciles and the MA window use **prior days only**.

RAW, all fires (266): | arm | paper | LONDON | maxDD | ret/maxDD | worst 3 h | pos days |
|---|---|---|---|---|---|---|
| A fixed $10 | +0.056 | −0.103 | 258.4 | +0.59 | −86.35 | 44% |
| **B tiered 5/10/20 by edge tercile** | **+0.119** | **−0.040** | 231.3 | +1.42 | −95.26 | 44% |
| C half-Kelly, cap 3× | +0.053 | −0.105 | 261.7 | +0.55 | −89.61 | 33% |
| F de-risk below MA(10) | +0.066 | −0.092 | 205.5 | +0.89 | −57.46 | 33% |

RAW, top 20%/day (54): A +0.060 · B +0.055 · C +0.060 · F +0.065 London — **a spread of one point.**

So: **tiering is worth ~6 points of London per$1 when you trade everything, and nothing once you are
already selective.** Selectivity does the work; staking is second order.

**Half-Kelly is indistinguishable from fixed stake in almost every cell**, because the 3× cap plus the
equal-deployment normalisation binds — the calibrated p is rarely far enough from the ask for Kelly to ask
for less than the cap. Reporting it as a distinct arm would overstate what it does.

## 3. Ranked on stability, as ordered — positive days first, then return/maxDD

| arm | n | pos days | ret/DD | paper | LONDON | worst 3 h | maxDD |
|---|---|---|---|---|---|---|---|
| RAW top 20% / B tiered | 54* | **67%** | +2.95 | +0.213 | +0.055 | −30.86 | 40.4 |
| FIXED top 20% / A, C, F | 45* | 67% | +0.95 | +0.123 | −0.035 | −40.00 | 60.3 |
| RAW top 10% / A, B, C | 27* | 56% | +1.34 | +0.145 | −0.020 | −30.00 | 30.3 |
| FIXED all / A, C | 224 | 56% | +0.94 | +0.094 | −0.059 | −74.09 | 233.4 |
| RAW top 20% / F de-risk MA(10) | 54* | 44% | **+3.85** | +0.231 | **+0.065** | −32.40 | 33.7 |
| RAW all / B tiered | 266 | 44% | +1.42 | +0.119 | −0.040 | −95.26 | 231.3 |
| RAW all / A fixed $10 | 266 | 44% | +0.59 | +0.056 | −0.103 | −86.35 | 258.4 |

Note the tension the owner should see: the **best return/maxDD** (F, +3.85) has the **worst positive-day
share** (44%), and the best positive-day share (67%) has a third of the ratio. On 9 days these two
rankings disagree, and 9 days moves `pos%` in 11 pp steps — the column cannot separate 44% from 67% yet.

## What I would actually say to the owner

1. **Nothing here is deployable.** The one arm that looks like the answer fails its own permutation and
   sweep checks, and 9 days cannot support a stability claim whose headline metric moves in 11 pp steps.
2. **The reliable part of the picture is not the staking grid, it is two exclusions**, and both need more
   sample before they are readings:
   - **ask 0.25–0.35 loses hard in both profiles** — the same 12 fires, 16.7% win, paper −0.472, London
     **−0.617**, positive on 12% of days. If anything is worth testing next it is refusing that bucket.
   - **sec 180–240 is the best bucket in both profiles** — FIXED +0.250 paper / **+0.096 London** on 63%
     positive days; RAW +0.163 / −0.001 on 75%. sec 120–180 is the worst in both.
3. **"Five trades a day" is achievable**: top 20%/day is 6.0 fires/day on RAW and 5.0 on FIXED, so the
   shape the owner wants exists. What is missing is evidence that the five chosen are better than five
   taken at random — and right now the data says they are not.
4. The honest next step is more days at the current cadence, not a staking change. Re-running this at
   ~30 days would let the permutation control and the positive-day column actually decide.
