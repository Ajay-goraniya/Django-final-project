# EF-3 — the owner's goal, judged on the owner's columns

Owner, 2026-09-28 13:4x, standing until met:

> an EF with good profit, SMALL max drawdown, good frequency and fill rate. fixed15 made money then
> gave it back. Judge every arm on THOSE columns first: $ total at $10, worst drawdown $,
> profit/drawdown ratio, fires/day, sim fill%, % days positive, longest losing run; then
> per$1/win%/halves/perm.

Every table below is in that order. Nothing here is deployed. Master is OFF, London is untouched.

## Headline

**No arm meets the goal.** The closest two, and why each falls short:

| | $tot @$10 | worst DD $ | P/DD | fires/day | fill% | days+ | run | per $1 |
|---|---|---|---|---|---|---|---|---|
| raw25 S≥60 (rule, 5 d) | +187.1 | 58.1 | 3.22 | 56.0 | 43.2% | 4/5 | 5 | +0.155 |
| EF-2 v0 m=0.02 S≥150 (model, 4 d) | +233.3 | 60.7 | 3.85 | 135.0 | 88.1% | 2/4 | 3 | +0.049 |
| fixed15 S≥0 — the live London rule (5 d) | +54.5 | 85.3 | 0.64 | 39.2 | 42.3% | 2/5 | 7 | +0.068 |

* **raw25 S≥60** is one day. On the 4 days where every arm exists it is +117.5, of which **+109.8 is
  09-25 alone**; the other three days are +11.1, +14.8, −18.1.
* **EF-2 v0 m=0.02 S≥150** has the best drawdown shape on the page. It now **passes** beats-the-null
  (see the correction below) and still fails verify.py on the **sweep shape**: its S-sweep is a jagged
  line with a spike at 150, not a plateau. Two of its three full days carry all the profit.

## Method

* All arms score on the same candles with the same per-pass FAK simulator: fire at ask+1 tick, fill iff
  the own-side ask on the first `decide_log` row at ≥ t+250 ms is within one tick, and fill AT that
  later ask. Unfilled fires cost nothing and earn nothing; they still count in `fires/day` and `fill%`.
* Two day sets, because EF-2 v0 is a walk-forward model (day *k* fitted on days < *k*, so the first day
  is unscorable): **5-day** = 09-24…09-28, 1015 candles, for the rule arms, which need no training;
  **4-day** = 09-25…09-28, 883 candles, for everything including v0. **The section-5 ranking runs on
  the 4-day set**, where every arm exists. 09-28 is a part day (8 fills for the v0 arms).
* Drawdown is peak-to-trough of the cumulative $ curve in fire order, at a flat $10 stake.
  `P/DD` is total ÷ worst drawdown. An arm that is never above water has `P/DD = −1.00` by construction.
* `*n<60` marks a cell with fewer than 60 **fills**.
* Files: `ef3.py` (the grid), `ef3_verify.py` (section 5).

## (1) Start-second curve — the arm may only fire from second S

5-day set. `$tot / DD$ / P/DD / fires-day / fill% / days+ / run`:

```
  fixed15 S>=0                     +54.5   85.3   0.64   39.2  42.3%    2/5    7|  +0.068  44.6%
  fixed15 S>=60                    +85.5  100.6   0.85   35.4  44.1%    2/5    7|  +0.112  46.2%
  fixed15 S>=120                   +75.5  111.6   0.68   29.0  44.8%    2/5    7|  +0.119  47.7%
  fixed15 S>=150                   -68.9  109.0  -0.63   23.8  41.2%    1/5    7|  -0.141  42.9%  *n<60
  fixed15 S>=180                    +1.4   67.6   0.02   17.0  49.4%    2/5    4|  +0.005  50.0%  *n<60
  fixed15 S>=200                   -27.8   67.3  -0.41   12.4  45.2%    1/5    5|  -0.099  46.4%  *n<60
  fixed15 S>=220                   -34.5   39.7  -0.87    7.0  51.4%    1/5    3|  -0.193  44.4%  *n<60
  fixed15 S>=230                   -24.5   30.0  -0.82    4.2  66.7%    1/4    3|  -0.175  42.9%  *n<60
  raw25   S>=0                    +107.3   98.4   1.09   65.2  42.3%    2/5    5|  +0.079  44.2%
  raw25   S>=60                   +187.1   58.1   3.22   56.0  43.2%    4/5    5|  +0.155  47.9%
  raw25   S>=120                   +54.1  102.1   0.53   40.0  49.0%    3/5    8|  +0.057  43.9%
  raw25   S>=150                   -45.8  100.4  -0.46   30.4  42.1%    2/5    5|  -0.071  40.6%
  raw25   S>=180                    -6.7   73.5  -0.09   22.2  47.7%    2/5    6|  -0.012  43.4%  *n<60
  raw25   S>=200                   -54.5   91.0  -0.60   17.0  49.4%    1/5    4|  -0.130  40.5%  *n<60
  raw25   S>=220                    +8.6   38.6   0.22   10.0  52.0%    2/5    3|  +0.033  46.2%  *n<60
  raw25   S>=230                   +14.5   39.9   0.36    6.2  64.5%    2/4    3|  +0.071  50.0%  *n<60
```

**The curve has a shape, and it is the opposite of the 220 s hypothesis.** Both rule arms make their
money **before 150 s** and give it back after. Delaying to 220–230 s does buy a genuinely better fill —
41% → 58% → 70% for fixed15 — and the drawdown does shrink, from $76 to $30. But the profit shrinks
faster than the drawdown does, and the sign turns negative. A smaller drawdown earned by taking fewer,
worse trades is not the small drawdown the goal asks for.

The reason the fill improves is mechanical: by second 220 the book has stopped moving, so an ask+1-tick
FAK is usually still there 250 ms later. The reason the profit dies is that by second 220 the price has
already absorbed the move, so the EV bar is only cleared when the quote is stale or wrong.

## (3) Skip-window — fire normally but never in 60–120 s

```
  fixed15 normal                   +54.5   85.3   0.64   39.2  42.3%    2/5    7|  +0.068  44.6%
  fixed15 skip 60-120              +51.3  107.3   0.48   33.4  43.1%    2/5    7|  +0.074  44.4%
  raw25   normal                  +107.3   98.4   1.09   65.2  42.3%    2/5    5|  +0.079  44.2%
  raw25   skip 60-120              +25.0  156.0   0.16   52.4  49.2%    2/5    8|  +0.021  41.9%
```

**No.** For fixed15 the total rises $7 and the drawdown rises $15 — the ratio gets *worse*, 0.90 vs 0.97.
For raw25 it is plainly harmful: −$82 of profit and +$58 of drawdown, the longest losing run goes 5 → 8.

The premise was that 60–120 s is London's real loss centre with 65% reversals, so pushing those candles
past 120 s gives them a second chance. What actually happens is that the deferred fire is a *different,
worse* trade: the 65% reversal rate is a property of the **candles** that qualify in that window, not of
the clock, and waiting does not make those candles behave. Removing the window removes some losses and
the winners attached to them, and it removes them unevenly, which is why the drawdown grows.

## (4) Drawdown-shaped rule — ask band × start second

```
  fixed15 ask0.30-0.70 S>=150      -42.1  105.4  -0.40   22.6  38.9%    1/5    7|  -0.095  43.2%  *n<60
  fixed15 ask0.30-0.70 S>=200      -30.8   67.3  -0.46   12.0  45.0%    1/5    5|  -0.113  44.4%  *n<60
  fixed15 ask0.40-0.70 S>=150      -92.9  122.9  -0.76   19.8  43.4%    0/5    6|  -0.217  41.9%  *n<60
  fixed15 ask0.40-0.70 S>=200      -20.8   51.8  -0.40   10.6  47.2%    2/5    4|  -0.081  48.0%  *n<60
  fixed15 ask0.50-0.80 S>=150     -137.7  137.7  -1.00   18.2  49.5%    0/5    4|  -0.307  42.2%  *n<60
  fixed15 ask0.50-0.80 S>=200      -62.8   85.5  -0.73    9.2  54.3%    1/5    4|  -0.251  44.0%  *n<60
  raw25   ask0.30-0.70 S>=150      -30.7  110.4  -0.28   30.0  42.7%    2/5    6|  -0.048  42.2%
  raw25   ask0.30-0.70 S>=200      -54.5   91.0  -0.60   17.0  49.4%    1/5    4|  -0.130  40.5%  *n<60
  raw25   ask0.40-0.70 S>=150      -77.8   92.8  -0.84   26.4  44.7%    0/5    4|  -0.132  42.4%  *n<60
  raw25   ask0.40-0.70 S>=200      -33.4   60.2  -0.55   14.4  52.8%    1/5    3|  -0.087  44.7%  *n<60
  raw25   ask0.50-0.80 S>=150     -159.1  159.1  -1.00   18.0  45.6%    0/5    6|  -0.389  34.1%  *n<60
  raw25   ask0.50-0.80 S>=200      -91.6  113.3  -0.81    9.0  55.6%    0/4    6|  -0.366  36.0%  *n<60
```

**All twelve cells are negative, both arms, and the highest band is the worst.** `0.50–0.80 S≥150` is
−$107.7 for fixed15 and −$159.1 for raw25 at a 34.1% win rate, and `P/DD = −1.00` on both means the
equity curve never goes above water at all — the drawdown *is* the whole loss.

The hypothesis was "high-price late fires win more and swing less". They do swing less: fill rises to
50–56% and the per-fire variance drops. They do not win more. This is the same survivorship error as the
220 s slice, one level down: when fixed15 *happened* to fire at 0.5–0.8 late in a candle, those fires
looked good, because the rest of the rule had already filtered the candle. **Forcing the band turns a
filter into a selector**, and what it selects is the expensive side of a move that has already happened.

## (2) EF-2 v0 × start second

4-day walk-forward set. v0 fires on **the model's own side** (`pw ≥ 0.5`) at the first row clearing
`pw / be(ask) − 1 ≥ m` — the definition in `ef2_v0b.py`.

```
  EF-2 m=0.00 S>=0                 +58.5  171.8   0.34  219.5  92.6%    2/4    5|  +0.007  65.2%
  EF-2 m=0.00 S>=120               -98.9  227.5  -0.43  179.5  92.9%    1/4    5|  -0.015  73.0%
  EF-2 m=0.00 S>=150              +206.5   88.4   2.33  155.2  91.0%    2/4    4|  +0.037  77.2%
  EF-2 m=0.00 S>=200                -4.2  111.5  -0.04  103.0  86.2%    1/4    6|  -0.001  74.6%
  EF-2 m=0.00 S>=230               +32.9   75.9   0.43   63.8  83.9%    3/4    4|  +0.015  76.6%
  EF-2 m=0.02 S>=0                +182.3  110.8   1.65  218.5  89.5%    4/4    5|  +0.023  66.5%
  EF-2 m=0.02 S>=120              +155.1   82.0   1.89  160.5  88.9%    3/4    4|  +0.027  73.6%
  EF-2 m=0.02 S>=150              +233.3   60.7   3.85  135.0  88.1%    2/4    3|  +0.049  75.8%
  EF-2 m=0.02 S>=180               +31.2   95.9   0.32  107.0  84.8%    3/4    3|  +0.008  73.6%
  EF-2 m=0.02 S>=200               -53.7  166.8  -0.32   85.8  85.7%    2/4    5|  -0.019  71.1%
  EF-2 m=0.02 S>=230               +85.6   54.0   1.58   47.8  80.6%    3/4    4|  +0.055  76.6%
  EF-2 m=0.05 S>=120              +162.0   71.2   2.28  123.0  81.7%    3/4    3|  +0.040  71.6%
  EF-2 m=0.05 S>=150               +37.4   85.4   0.44   95.5  79.6%    2/4    5|  +0.012  70.4%
  EF-2 m=0.05 S>=230               +83.4   45.0   1.85   25.2  76.2%    3/3    4|  +0.108  75.3%
```

**v0 does keep firing usefully late — it is the only family here that stays positive after 150 s.** It
also has by far the best fill rate on the page, 80–93% against the rule arms' 41–49%, and the smallest
drawdowns per dollar of profit.

Two things stop this being good news:

1. **It wins by buying favourites.** Mean ask paid at `m=0.02 S≥150` is **0.713**. A 75.8% win rate at
   71c is only **+0.049 per $1** — barely more than fixed15's +0.050 on the same candles. The high fill
   rate is the same fact seen from the other side: a 70c favourite late in a quiet book is easy to buy
   precisely because nobody disagrees with you. High win%, high fill%, thin edge.
2. **The S-sweep is jagged, not monotone.** At m=0.02: `+0.023 +0.007 +0.027 +0.049 +0.008 −0.019
   −0.006 +0.055`. S=150 is a spike between two much smaller values, and S=230 is higher still. That is
   the shape of noise with a grid drawn through it.

### Diagnostic — what happens without the side restriction

My first run of this section dropped `pw ≥ 0.5`. The corrected numbers are above; the broken table is
kept because it is the clearest statement of a trap for any late-firing EF:

```
  no-side m=0.00 S>=0    +84.1   201.8   0.42  220.8  92.5%  2/4 | +0.010  65.2%   mean ask 0.628, 1.6% of fires on the pw<0.5 side
  no-side m=0.00 S>=120 -1596.6  1605.2  -0.99  220.2  94.7%  0/4 | -0.197  52.8%  mean ask 0.537, 27.3%
  no-side m=0.00 S>=230 -2024.3  2243.7  -0.90  143.0  92.5%  0/4 | -0.390  29.3%  mean ask 0.297, 64.5%
```

A 29.3% win rate looks like the model inverting late in the candle. It is not. After 150 s one side's
ask collapses toward 0.05, and `be(0.05) = 0.053`, so an EV bar **alone** is cleared by almost any long
shot: by S≥230 **64.5% of the fires are on the side the model rates below 0.5**. The rule had stopped
expressing the model and started buying whatever was cheap. An EV threshold is not a side rule, and the
later you fire the less it behaves like one.

## (5) Top 3 by profit/drawdown with n ≥ 60, through verify.py

All three are v0 arms — the rule arms with a good ratio (raw25 S≥60) have 99 fills but a worse ratio on
the 4-day set than any of these. Full output in `ef3_verify.py`.

| arm | $tot | DD | P/DD | fills | /day | days+ | 09-25 | 09-26 | 09-27 | 09-28 |
|---|---|---|---|---|---|---|---|---|---|---|
| v0 m=0.02 S≥150 | +233.3 | 60.7 | 3.85 | 476 | 135.0 | 2/4 | −8.9 | +116.5 | +129.0 | −3.2 |
| v0 m=0.00 S≥150 | +206.5 | 88.4 | 2.33 | 565 | 155.2 | 2/4 | −2.4 | +81.9 | +132.3 | −5.3 |
| v0 m=0.05 S≥120 | +162.0 | 71.2 | 2.28 | 402 | 123.0 | 3/4 | +58.1 | +28.3 | +88.7 | −13.1 |

**None passes** — but after the correction below the reason has narrowed to the sweep and the day count,
not the edge. Gate by gate:

* **grading** — PASS, all three. The two venue mirrors agree on 0/140 candles.
* **quote age** — PASS. `at-or-after`; the decision is made on the quoted ask.
* **sample size** — FAIL on the per-day cell for 09-28 (8 fills; it is a part day). The pooled cells pass.
* **both halves** — PASS, all three, same sign and both positive.
* **cost sensitivity** — PASS. All three survive a 2c haircut (+0.049 → +0.021).
* **permutation (verify.py)** — reported p = 1.000 on all three, and **this gate is inapplicable here,
  not failed on the merits.** `pnl_fn` selects on `pred ≥ 0.5`, but every already-selected fill has
  `pw ≥ 0.5` by construction, so shuffling `pw` among them cannot change the set or the statistic — the
  permuted mean equals the real value exactly (+0.049 vs +0.049, p95 +0.049), which is the signature of
  a statistic that never moved. The applicable control is V's: flip the sign and price it at the
  **opposite side's real ask**. That gives **p = 0.000 / 0.003 / 0.003**. I am not treating the 1.000 as
  evidence either way; I am recording that this harness needs a selection-aware permutation for arms
  whose fire rule is the same quantity being shuffled.
* **sweep shape** — FAIL on S for all three (jagged, spikes at the chosen cell). The m-sweep is monotone
  for `m=0.05 S≥120` only.
* **beats the null** — **PASS on all three, after the correction below.** fixed15 on the same candles
  earns **+0.028 per $1**; the arms earn +0.049, +0.037, +0.040. Before the fix the null read +0.050 and
  all three failed this gate. That claim was wrong and is retracted.
* **paired (McNemar)** — PASS for the two S≥150 arms (p = 0.031 and 0.004) but on only 41 and 43 shared
  candles; FAIL for `m=0.05 S≥120` (p = 1.000).

### The honest tension in that verdict

`beats the null` compares **per $1**, which is not the owner's first column. On the owner's columns v0
m=0.02 S≥150 is much better than fixed15 on the same four days: **+$233 vs +$26**, drawdown **$60.7 vs
$75.8**, ratio **3.85 vs 0.35**, fill **88% vs 42%**, longest losing run **3 vs 6**. Both statements are
true and they are not in conflict: v0 has **no better edge per dollar**, it applies the *same* edge
across six times as many fills, which is what shrinks the drawdown relative to the profit.

That is a real and useful property — but it is a reason to keep testing v0, not to run it. Turning a
+0.05/\$1 edge into +$233 only works if the edge is real, and after four days with two of them carrying
the entire profit, a jagged sweep, and an inapplicable permutation gate, I cannot say that it is. What I
can say is that **v0-late is the first arm in EF-1/2/3 whose failure is about evidence rather than about
the edge being absent**, and that it is worth a shadow run with a pre-registered (m, S) chosen now
rather than after seeing more tables.

## What this means for the goal

* **fixed15's shape is confirmed, and the clock does not fix it.** It earns before 150 s and gives it
  back after. None of S, the skip-window or the ask band changes that; each one trades profit for a
  smaller drawdown at a worse ratio.
* **The 220 s idea is dead as a rule**, in both its forms. The slice looked good; the rule loses.
* **Every "shape the drawdown" edit failed the same way**, and for one reason: fixed15's losses are not
  concentrated in a *clock window* or a *price band* that can be cut out. They are spread across the
  same candles that produce its wins. Cutting by time or by price removes both.
* **The one thing that changes the drawdown shape is firing more often on a thinner edge** — which is
  what v0 does — and that requires the thin edge to be real.

## Correction — a free extra tick on the fixed15 arm (found 09-28 14:1x, after the first push)

**Every `fixed15` number in this document was wrong on its first publication, by about one tick.** raw25
and every EF-2 v0 number were unaffected. The corrected tables are the ones above; the first-push values
are listed at the end of this section so the change is auditable.

### What happened

`fixed15` judges EV at **ask + 1 tick**, and that pad is computed on the tick grid with `Decimal`:

```python
px = float((Dc(a) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
```

`Dc` is `Decimal(str(x))`, and that is deliberate — `poly_core.order_plan` uses the same idiom and says
why in a comment that turns out to describe this incident in advance:

> Do NOT "fix" this by reaching for `Decimal` directly: `Decimal(0.28)/Decimal(0.01)` is `28.000...2` and
> `ROUND_CEILING` turns that into 29. I shipped exactly that non-fix as 12.3.1 after reproducing the
> "bug" in a scratch script that defined its own `D` and never imported this one.

The guard works because the venue's ask arrives as a float64 whose `str()` is `'0.34'`. **`ef2_rows.npz`
stores features as float32.** Round-tripped, `0.34` becomes `0.3400000035762787`, `str()` preserves the
noise, `0.34 / 0.01` evaluates to `34.0000003`, `ROUND_CEILING` returns **35**, and the fire price becomes
`0.36` instead of `0.35`. A free extra tick, on **44.8% of rows** — i.e. on every ask that lands exactly
on the cent grid, which is all of them. It only bites the padded profile, so `raw25` and EF-2 v0, which
use `be()` (plain float, no ceiling), are bit-identical before and after.

I did not reach for `Decimal` directly, so the comment's literal warning was satisfied. I defeated the
same guard from the other end, by feeding it a value that had already lost its decimal identity.

### How it was caught

Not by review — by a disagreement between two implementations. `ef3_shadow.py` reads asks straight from
sqlite as float64 and reported **196** fixed15 candles where `ef3.py`, reading the npz, reported **178**.
B (`raw25 S≥60`) matched to the cent, which localised it to the padded arm immediately. The shadow's
number was the correct one all along.

### Fix

Snap the ask back to the grid before the ceiling, in `pad_cost`, with a tolerance far below a tick and
far above float32 noise:

```python
a = float(Dc(a).quantize(Dc('0.000001')))   # 1e-6 vs a 1c tick vs float32 noise of ~2e-8
```

Applied to `ef3.py`, `ef2_v0b.py`, `ef2_report.py`, `ef2_second.py`, `ef2_recross.py`, `ef2_v0_detail.py`
and `ef2_compare.py`, each with an assert that `pad_cost(float32(a)) == pad_cost(a)` across the price
range. `ef_fixed220.py`, `ef_persist.py` and `ef_regime_grid.py` read their asks from sqlite as float64
and were never affected — **so the "fires only after 220 s" answer already given to the owner stands.**
The live engine reads the venue's float64 and is not affected either; this is an analysis-side defect
only, and nothing about it touches London or the master switch.

### What the correction changes

| | first push | corrected |
|---|---|---|
| fixed15 S≥0, $ total / DD / P/DD | +73.8 / 75.8 / 0.97 | **+54.5 / 85.3 / 0.64** |
| fixed15 S≥0, fires/day / per $1 | 35.6 / +0.104 | **39.2 / +0.068** |
| fixed15 S≥120, $ total / P/DD | +130.0 / 1.59 | **+75.5 / 0.68** |
| the null in §5, fixed15 per $1 (4 d) | +0.050 | **+0.028** |
| §5 `beats the null` verdict | FAIL ×3 | **PASS ×3** |

The direction is what the mechanism predicts: with the extra tick removed, fixed15 clears its EV bar more
often (39.2 fires/day, up from 35.6) and each fire is judged against a cheaper reference, so the marginal
fires it now takes are worse ones — more trades, less money, a larger drawdown.

**The conclusions of this document do not change.** Items (1), (3) and (4) all still fail, and (4) gets
slightly worse. What changes is §5: the three v0 arms now clear `beats the null`, so their remaining
failures are the **jagged sweep** and the **09-28 part day** — which is the "evidence, not edge" reading,
now with the per-dollar comparison on its side rather than against it. It also strengthens the argument
for V's pre-registered shadow: the arms are worth measuring forward.

**A retraction I owe explicitly:** I told V at 14:02 that all three arms failed on the per-$1 null and
that "fixed15 +0.050 vs v0 +0.037..0.049" was the decisive gate. That was wrong. The decisive gates are
the sweep shape and the sample.

### First-push values, for audit

fixed15 §1 5-day: S≥0 +73.8/75.8/0.97/35.6/41.0%/2of5/6; S≥60 +105.6/92.9/1.14/32.8/41.5%/2of5/6;
S≥120 +130.0/81.6/1.59/26.2/41.2%/3of5/5; S≥150 −54.3/89.0/−0.61; S≥180 +13.3/67.6/0.20;
S≥200 −43.7/67.3/−0.65; S≥220 −34.5/48.6/−0.71; S≥230 −24.5/30.0/−0.82.
§3 fixed15 normal +73.8/75.8/0.97, skip +81.0/90.3/0.90.
§4 fixed15: −27.6, −46.7, −62.9, −20.8, −107.7, −52.8 (all still negative, all still failing).

## What I did not do

* Nothing was deployed, enabled or armed. Master is OFF, Zurich is SHADOW, London is untouched.
* No best cell was picked for deployment. Every grid is reported whole, including the losing halves.
* I did not re-fit anything for EF-3; v0's walk-forward predictions are the cached `ef2_fits.npz`.
