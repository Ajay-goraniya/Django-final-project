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

## Follow-up (a)(b)(c) — is S0=60 a plateau or a spike? `ef3_fine.py`

V, 14:1x: raw25 S0=60 is the first cell that looks like the owner's goal, so before anything else, does a
finer grid support it? The loader asserts it reproduces the published `raw25 S≥0 = +107.3 / DD 98.4`
before it prints a single new number.

```
  arm                               $tot    DD$   P/DD  f/day  fill%  days+  run|   per$1   win%
  raw25 S>=30                     +170.9   65.5   2.61   61.4  42.0%    3/5    5|  +0.133  46.5%
  raw25 S>=45                     +122.3   78.3   1.56   58.6  42.3%    3/5    6|  +0.099  45.2%
  raw25 S>=60                     +187.1   58.1   3.22   56.0  43.2%    4/5    5|  +0.155  47.9%
  raw25 S>=75                     +192.3   59.1   3.26   51.0  43.9%    3/5    5|  +0.172  49.1%
  raw25 S>=90                     +119.4   78.7   1.52   47.6  45.4%    2/5    6|  +0.111  46.3%
  raw25 S>=105                     +82.4   67.9   1.21   44.6  45.3%    2/5    6|  +0.082  45.5%
  raw25 S>=120                     +54.1  102.1   0.53   40.0  49.0%    3/5    8|  +0.057  43.9%
  fixed15 S>=30                    +49.9   96.3   0.52   38.0  42.6%    2/5    7|  +0.064  44.4%
  fixed15 S>=45                    +45.1  106.7   0.42   36.6  44.8%    2/5    7|  +0.057  43.9%
  fixed15 S>=60                    +85.5  100.6   0.85   35.4  44.1%    2/5    7|  +0.112  46.2%
  fixed15 S>=75                    +70.0  110.9   0.63   34.2  45.6%    2/5    6|  +0.092  46.2%
  fixed15 S>=90                    +31.2  110.9   0.28   32.8  43.9%    2/5    6|  +0.046  43.1%
  fixed15 S>=105                   +42.9  108.0   0.40   31.6  44.3%    2/5    6|  +0.064  45.7%
  fixed15 S>=120                   +75.5  111.6   0.68   29.0  44.8%    2/5    7|  +0.119  47.7%
```

**Neither answer is the clean one.** For raw25 it is not a flat plateau — 45 dips to +122 between 30
(+171) and 60 (+187) — but it is not an isolated spike either: **every cell from 30 to 75 is positive at
a ratio of 1.56–3.26, and the curve decays monotonically from 75 onward.** So the *regime* is real and
**60 is not the special number; 75 is marginally better.** For fixed15 there is no structure at all: the
band is +31 to +85 with no trend and 60 is a bump. Whatever the clock is doing, it does it to raw25 only.

Each cell holds ~120 fills, so a $70 swing between neighbours is well inside noise — which is exactly why
the neighbours, not the peak, are the thing to read.

### raw25 S0=60 in full, and the paired test that explains it

280 fires, 121 fills, 43.2% fill, 47.9% win, per $1 +0.155, mean ask 0.410, longest losing run 5,
opposite-ask flip p = 0.040, costs +1c +0.126 / +2c +0.099.
Per day: `09-24 +69.5 | 09-25 +109.8 | 09-26 +11.1 | 09-27 +14.8 | 09-28 −18.1`.

The paired test against `raw25 S0=0` is the informative part:

* 102 candles fire **and** fill under both rules. **88 of them are literally the same pass**, and the
  outcomes are **discordant in zero** of them. So within a candle, the start-second bar never picks a
  better trade — it picks the *same* trade.
* The entire difference is composition. The bar drops **36 fills at mean second 36, winning 33.3%, worth
  −$77.2** — which is essentially the whole of `+107.3 → +187.1`.

**So S0=60 is not an entry improvement, it is a veto on the first minute.** That is the owner's "no early
gambling", measured: fires before second ~36 win a third of the time and lose money. The rule is real;
the number 60 is not, and the mechanism says any bar somewhere in 30–75 does the same job.

`verify.py` on raw25 S0=60: **fails.** `sample` (no single day reaches 60 fills), **`both halves`
(H1 +0.314 / H2 −0.000 — a sign flip)**, `sweep shape` (jagged). Permutation gate inapplicable for the
same reason as §5. Passes grading, quote age, cost sensitivity, and `beats the null` (+0.155 vs +0.079).

**The caution that matters:** **+179.3 of the +187.1 is 09-24 and 09-25.** The three days since are
+11.1, +14.8, −18.1 — **+7.8 combined**, which is what H2 ≈ 0 is saying. This arm is pre-registered as B
in the forward shadow and I am not proposing a change to it; the forward days are the right instrument.

## Independent check of V's public-data late rule — `ef3_spot.py`

V's late rule looks strong on public data, but it prices with the **max taker print in the 3 s before the
decision** while the model sees Binance at the end of the second. Replayed here against the real own-side
ask at the pass with the +250 ms FAK simulator. Spot features only — `move_bps, ret5, ret30, ret60, rv60,
mv_x_sec` — walk-forward by day, refitted per 15 s bucket. 1015 candles, 822,331 passes.

Those features describe BTC, not a side: they are identical on the UP and DOWN rows of one pass. So the
fit is P(UP resolves) on one row per pass, with `p_side = p_up` for UP and `1 − p_up` for DOWN. Pooled
direction AUC **0.8121** — real skill, and still below the ask alone at 0.8611.

```
  cell                          $tot    DD$   P/DD  f/day  fill%  days+  run|   per$1   flipP
  S0=150 m=0.00/.02/.05/.10   -478.8 -455.1 -482.1 -544.4   (DD 587-669, ratio -0.75..-0.81, 0/4 days)
  S0=180 m=0.00/.02/.05/.10   -232.4 -243.6 -218.5 -213.2   (DD 417-467, ratio -0.49..-0.56)
  S0=200 m=0.00/.02/.05/.10   -219.8 -239.7 -204.3 -147.7   (DD 328-436, ratio -0.45..-0.55)
  S0=220 m=0.00               +215.7  237.0   0.91   70.0  82.5%    3/4    7|  +0.096   0.097
  S0=220 m=0.10               +223.0  232.4   0.96   58.5  80.8%    3/4    9|  +0.121   0.160
  S0=240 m=0.00/.02/.05/.10   -167.5 -165.8 -199.5 -218.2   (DD 268-287, ratio -0.62..-0.78)
```

**It does not replicate. 16 of 20 cells lose, most of them heavily.** The only positive band is S0=220,
and it sits between S0=200 at −$220 and S0=240 at −$168. One positive cell between two losers is the
overfit shape, not a regime. `m` barely moves anything because it rarely changes which side is taken.

### The decision-lag measurement — and it decomposes in an unexpected way

```
  S0=180 m=0.00 lag0s         -232.4  417.2  -0.56  106.8  78.9%    2/4    7|  -0.069   0.330
  S0=180 m=0.00 lag1s         -224.2  412.7  -0.54  108.2  79.4%    2/4    7|  -0.065   0.363
  S0=180 m=0.00 lag3s         -244.0  424.6  -0.57  109.8  78.1%    2/4    7|  -0.071   0.370
  S0=180 m=0.00 lag3s BOOKED +1447.4  299.9   4.83  109.8 100.0%    3/4    8|  +0.340   0.007
  S0=220 m=0.00 lag0s         +215.7  237.0   0.91   70.0  82.5%    3/4    7|  +0.096   0.097
  S0=220 m=0.00 lag3s         +231.3  206.9   1.12   75.2  80.7%    2/4    6|  +0.098   0.033
  S0=220 m=0.00 lag3s BOOKED +1552.9  154.7  10.04   75.2 100.0%    3/4    7|  +0.530   0.000
```

* **Deciding on a stale quote but paying the true forward price costs almost nothing** — S0=220 goes
  +215.7 → +231.3, inside noise. The selection effect that `quote_age` was written for is small *here*.
* **Booking at the stale quote is worth +$1,322 on that one cell** — 6.7× the real money, and it
  manufactures a **10.04 profit/drawdown with flip p = 0.000** out of a rule that truly makes +$231. At
  S0=180 it turns a −$232 loser into **+$1,447**.
* Look at the fill column: **BOOKED reads 100.0%**, because paying a price you saw 3 s ago also deletes
  every no-fill. That is half the illusion, and it is invisible in any table without a `fill%` column.

So the public-data result is fully consistent with **a rule that has no edge, plus a price you cannot
trade at.** The lesson generalises past this rule: the dangerous half of a stale price source is not that
it biases selection, it is that it lets the backtest transact at it.

## EF-4 — model the money after the fill, not P(win). `ef4.py`, `ef4_freeze.py`

V, 14:5x: every model so far learned P(side wins), but paper is positive and London-exec negative in every
cell, so the loss is in WHICH fires fill. Target changed to the realised return AS EXECUTED — `0` if the
+250 ms FAK does not fill, `per1(win, fill_price)` if it does — regressed on the 52 features with ridge
linear (primary) and a squared-loss stump booster (capacity check). Book age is **not** in the logged
features, so it is absent rather than approximated; given the hypothesis is about fill quality that is a
real limit on the test.

**The target does shift what the model reaches for**, which is the part that holds up:

```
  block               after-fill $      P(win)      (sum |coef|, standardised, same ridge, same features)
  the price                 0.1593      0.2297
  the engine p              0.1747      0.0817
  ask dynamics              0.0523      0.0086      <- 6x
  the clock                 0.0447      0.0006      <- 70x
```

P(win) is dominated by the price; the after-fill target moves mass onto ask dynamics and the clock. The
hypothesis behaves as intended.

**The headline did not survive, twice, for two different reasons.**

*First*, the linear model's best cell was +$417.1 / DD 76.2 / P/DD 5.47 / 4-of-4 days / flip p=0.000. The
coefficients gave it away: `ref_open −2.6881` and `bn_line_open +2.4082` — two **absolute BTC prices near
$84,000 correlated at +0.999886**. A large opposed pair on two copies of the same number is ridge
amplifying their numerical difference by ~10⁴ and using BTC's level as a per-day offset, i.e. fitting the
date. The tell was already visible in the walk-forward correlations: −0.046, +0.021, +0.043, +0.090, with
one test day *anti*-correlated, which cannot produce a genuine 4-of-4 arm. Dropping the six level columns
took it to **+$116.2 / DD 96.0 / P/DD 1.21**, 8 of 12 cells negative, and no cell beating C on both.

*Second*, the stumps largely survived that (they bin, so they cannot amplify a collinear pair): EF-4gb
t=0.00 S0=0 at **+$164.0 / DD $75.5 / P/DD 2.17 / 90.8% fill / 4-of-4 days / flip p=0.003**, against C at
+$16.3 / $85.3. Monotone in t, and unlike every other arm today the non-top-two days still summed
**positive** (+$26.0). Eight stump cells cleared C on both columns. My first qualification check missed
all of them — it only scanned the linear cells and printed "NONE" while the stump rows sat above it.

So the model was frozen as arm D and put in the shadow. **It does not reproduce.**

```
  D_ef4gb_t000   -138.1   DD 226.7   P/DD -0.61   416 fires   89.7% fill   1/5 days
     per day $:  09-24 -65.8   09-25 -7.9   09-26 -45.1   09-27 -38.1   09-28 +18.7
     (the four walk-forward days sum -72.4, where the grid said +164.0)
```

Checked before concluding: the shadow's scorer matches `ef4.gb_reg_pred` to 0.0, and the feature map drops
exactly the six level columns. Not a bug. **The cause is the threshold.** Predictions have sd 0.130 about
a base of −0.0996, so `pred ≥ 0` is a cut ~0.76 sd into the upper tail, and where that cut lands depends
on each fit's calibration offset. A model trained on 213k rows (walk-forward day 1) and one trained on
1.58M put it in different places. The grid's success was partly a per-day quantile accident, not a rule —
and a rule that only works when refitted nightly on a rolling window is not the rule that was tested.

**Arm D therefore stays in the shadow as a falsification check with a negative prior on record, NOT as a
qualifying candidate.** V's authorisation was conditional on beating C, and the frozen, forward-usable
form does not. It costs nothing to leave running (paper, no order path) and V can drop it at will.

The generalisable lesson, which is the third time today in a different costume: **an absolute threshold on
a model score is not a rule unless the score is calibrated.** EF-2 v0 used `p/be(ask) − 1 ≥ m`, which is
scale-free and survived freezing. EF-4 used `pred ≥ t` on an uncalibrated regression output, and did not.
A quantile cut ("fire on the top 20% of predictions") would have been the portable form.

## EF-5 — the causal quantile cut. Half my closing line was right. `ef5.py`

I claimed EF-4 died because `pred >= t` is an absolute cut on an uncalibrated score, and that a quantile
cut would be the portable form. V had me test it. **The quantile fixes the causality problem and does not
fix the portability problem**, which means the diagnosis was half right and the prescription was wrong.

Three readings, because two of them are easy to conflate and the gaps between them are the answer.
`IN-DAY` takes the threshold from the test day itself (not implementable — it needs the whole day before
it can fire on the first candle; it is the upper bound). `CAUSAL` takes it from day k−1 under the same
model. `FROZEN` is one model fitted on days < last, threshold still from day k−1 — what the shadow runs.

```
                        IN-DAY              CAUSAL              FROZEN
  q=0.70 S0=0       +276.2 / 104.9      +251.2 / 115.7       -64.2 / 223.0
  q=0.80 S0=0       +156.9 /  87.1      +169.1 / 105.6       -47.8 / 117.1
  q=0.90 S0=0        +29.0 /  66.4      +140.3 /  68.6       -98.5 / 133.6
  q=0.95 S0=0        +25.2 /  49.6       +91.5 /  68.6       +25.5 /  68.8
  C fixed15, same test days:  +16.3 / 85.3 / P/DD 0.19 / 43.6% fill / 1-of-4
```

**CAUSAL ≈ IN-DAY, and at q=0.90 causal is far better (+140.3 vs +29.0).** So the threshold was never
peeking: a quantile cut is causal-safe, and that part of the claim holds. Taking the threshold from
yesterday costs nothing.

**FROZEN collapses anyway.** `q=0.70 S0=0` goes +251.2 → −64.2. Six of eight frozen cells are negative.
So the thing that does not transfer is **the model**, not the threshold — refitting nightly on a growing
window is doing the work, and freezing removes it. EF-4's failure was over-attributed by me to the cut.

### The controlled comparison worth keeping

D and D2 use the **same frozen model**; only the decision rule differs. Absolute `pred ≥ 0` gives
**−$138.1 / DD 226.7**; the 0.95 quantile of the previous day gives **+$25.5 / DD 68.8**. So the quantile
cut is worth about **$164 and two thirds of the drawdown on an identical model** — a real effect,
cleanly isolated, and still not enough to make the model portable.

### D2 registered, with the objection on record

Exactly one frozen cell clears C on both columns: `q=0.95 S0=0`, +$25.5 vs C's +$16.3, DD $68.8 vs $85.3.
V pre-committed to registering that, so it is registered as **D2** rather than overruled after the fact —
declining a pre-agreed rule because the number came out small is the same error as accepting one because
it came out large. The objections, stated now and not after the forward days:

* it is an **isolated cell** — its neighbours are `q=0.90 S0=0` at −$98.5 and `q=0.95 S0=60` at −$48.0
* **flip p = 0.137**, which fails the p < 0.05 bar in V's own A/B/C decision rule
* the margin over C is **$9 across four days**, on 135 fills
* 09-24 is +0.0 by construction: no previous day exists, so no threshold, so no fires. Correct, not a bug.

On the evidence I would call it noise. It is in the shadow because the rule said so, with a negative
prior recorded, and the forward days will settle it.

## EF-6 — the trailing-window quantile. Rate-stability solved; the E3 bar not met. `ef6.py`

Arm E carries yesterday's quantile as a VALUE across a nightly refit that moves the prediction scale, so
the same q lands at a different rank each day — 4 fills one day, 188 the next. V's fix: at time t, take
the q-quantile of this model's predictions over the candidate rows in the last W hours. Only past rows,
so still causal; continuously re-anchored, so rate-stable. At the start of a day the window reaches back
into yesterday, scored under today's model.

The threshold is recomputed on a **60 s grid**, not per row — 1,440 updates a day rather than ~450,000,
which is also what an implementation would really do. Between updates the rule uses the older threshold,
which is the more conservative reading.

```
  cell             $tot    DD$   P/DD  f/day  fill%  days+  fmin  fmax    CV  per$1   flipP
  W=1h q=0.80    +179.4  117.4   1.53  161.8  93.5%   4/4     11   246  0.57  +0.030  0.127
  W=1h q=0.90    +222.1   72.6   3.06  126.2  93.1%   3/4      7   217  0.63  +0.048  0.037
  W=3h q=0.80    +267.4   99.7   2.68  147.2  93.0%   4/4     13   211  0.54  +0.049  0.007
  W=3h q=0.90    +213.4   92.8   2.30  115.5  91.1%   3/4      9   197  0.63  +0.051  0.000
  W=6h q=0.80    +161.2   85.8   1.88  129.0  92.1%   4/4     14   169  0.52  +0.035  0.027
  C fixed15       +16.3   85.3   0.19   37.2  43.6%   1/4      4    33  0.68  +0.028  0.527
```

**The rate-stability worked, and the headline CV column understates it.** 09-28 is a part day — 13 fills
against 156–211 on the full days — and it drags every CV up. On the three complete days:

```
                  CV all 4   CV 3 full    best-day share (3 full)   $ (3 full)    DD
  W=3h q=0.80       0.54       0.13                53%                +252.5     99.7
  W=1h q=0.90       0.63       0.29                52%                +230.9     72.6
  W=3h q=0.90       0.63       0.31                53%                +228.9     92.8
  C fixed15         0.68       0.48               232%                 +35.4     85.3
  arm E causal q=0.90 (for comparison)  CV 3 full 0.94
```

**CV falls from 0.94 (arm E) to 0.13–0.31.** That is the problem V set out to fix, fixed, and it is better
than the incumbent control's 0.48 as well.

### No E3 — the bar was not met, and I am not rounding in my favour

`W=1h q=0.90` passes **$** (+222.1 vs +16.3), **DD** (72.6 vs 85.3) and **CV** (0.29 vs < 0.50). It fails
**best-day share: 52% against a bar of < 50%.** Two percentage points, on three days. It fails, so nothing
is registered; a bar that only binds when you round it is not a bar.

Two properties of that metric worth knowing before it is used again:

* **It is ill-behaved as a ratio when the total is small.** C scores **503%** on four days and 232% on
  three, because its total is +$16.3 while its best day is +$82.0. A denominator that can approach zero
  makes the statistic unbounded. Share of the *positive* days is the robust form; on that, C is 100%.
* **Its floor depends on the day count.** Uniform across three days is 33%, across four days 25%. So
  "< 50%" is a much tighter demand on a three-day sample than on a longer one, and the arms above are
  being judged on three complete days.

Both point the same way: the rule is closer to passing than 52% vs 50% suggests, and the right response is
more days rather than a softer bar.

## Priors recorded BEFORE the forward days arrive (09-28 15:1x)

Pre-registration only works if the prior is written down before the evidence. Two updates landed after
A/B/C were fixed and before any forward day exists, so they go here rather than into the eventual reading
of the result.

**Arm A's prior is now strongly against it.** London replayed `v0 m=0.02 S≥150` on its own 7 days. Out of
sample — 09-22 to 09-24, days the model never saw — it returns **−$214.6 with 0 of 3 days positive.** A's
entire positive record is 09-26 and 09-27, which were inside its walk-forward span. This does not change
the pre-registered definition of A and does not remove it from the shadow: changing an arm because a new
number arrived is precisely what pre-registration exists to prevent. It does mean that **if A comes back
positive on the forward days, two of three prior reads were negative**, and the honest reading of a
positive A will be "one window in three", not "confirmed".

**The data-api timestamp lag replicates independently.** V measured it on a different window (live, WS
`last_trade_price` vs data-api, `market=`, 146 matches on price *and* size) and got p10 +1.5 / p50 +2.2 /
p90 +3.0 s, 99% ≥ 1 s. Zurich's read on 09-27 05:30–07:30 with a different matching rule (unambiguous
pairs, no size available) gave p10 +1.42 / p50 +2.20 / p90 +3.00, 98.8% ≥ 1 s. Two windows, two matching
methods, the same median to 0.02 s. V's collectors were checked and all use `market=<conditionId>` with a
further `asset == token` filter, so the `asset=` defect I found does not affect their tape. The late spot
rule is closed on the lag plus Zurich's book replay.

## The 10-day read — `ef3_ten.py`. The start-second story does not survive it.

V, 14:4x: (c) showed the start-second bar is pure composition, so the 10 `stable_ef` days can be read the
same way and give B more history for free. They can, and the answer is negative on every count.

**One caveat first, because it cuts against every number here.** A slice can only DROP a fire; the rule
can also ADD one, firing at a later qualifying pass in a candle whose first qualifying pass was early. On
the 5 per-pass days the rule has **121 fills where the slice has 102**. So everything below is a lower
bound on the rule's activity. This is the same slice-vs-rule distinction the fires-after-220 test turned
on, pointing the other way.

These are the engine's own fires (one per candle, its own EV bar) at $10 — a different instrument from
the per-pass decide_log grids above, so cells are not comparable one-to-one across the two sections.

```
  cell             |    $tot    DD$   P/DD  f/day  days+  run      H1      H2 |  L $tot   L DD L P/DD  L days+
  RAW sec>=0       |  +142.3  258.4   0.55   29.9   5/10    7  +0.027  +0.070 |  -206.6  267.6  -0.77   2.8/10
  RAW sec>=30      |  +125.2  273.0   0.46   29.2   4/10    6  +0.019  +0.068 |  -210.1  272.2  -0.77   2.8/10
  RAW sec>=45      |  +155.6  243.0   0.64   27.8   5/10    6  +0.051  +0.066 |  -174.6  240.9  -0.72   3.1/10
  RAW sec>=60      |  +125.1  223.0   0.56   26.3   5/10    5  +0.044  +0.056 |  -179.3  239.7  -0.75   2.9/10
  RAW sec>=75      |   +76.1  193.6   0.39   23.5   5/10    6  +0.021  +0.053 |  -180.0  228.7  -0.79   2.7/10
  FIXED sec>=0     |  +233.7  233.4   1.00   25.2   6/10    7  +0.043  +0.121 |   -95.0  189.8  -0.50   3.7/10
  FIXED sec>=30    |  +233.7  233.4   1.00   25.2   6/10    7  +0.043  +0.121 |   -95.0  189.8  -0.50   3.7/10
  FIXED sec>=45    |  +215.4  227.4   0.95   24.6   6/10    7  +0.037  +0.118 |   -95.8  183.5  -0.52   3.7/10
  FIXED sec>=60    |  +229.4  207.4   1.11   23.8   6/10    6  +0.047  +0.124 |   -83.3  173.9  -0.48   3.8/10
  FIXED sec>=75    |  +177.8  187.9   0.95   22.1   6/10    5  +0.030  +0.118 |   -95.7  167.6  -0.57   3.8/10
```

**1. The start-second bar does nothing on 10 days.** RAW runs +142.3 → +125.2 → +155.6 → +125.1 → +76.1;
FIXED +233.7 → +233.7 → +215.4 → +229.4 → +177.8. Flat, with no trend in either direction. The 5-day
`+107.3 → +187.1` does not survive the longer history.

**2. The mechanism I reported is retracted as a general claim.** On the 5 per-pass days the dropped
`sec<60` set was 36 fills at a **33.3%** win rate worth **−$77.2**, which is why I called it a veto on bad
early fires. On these 10 days:

```
    RAW   dropped sec<30: n   7  win 57.1%  $  +17.1    dropped sec<60: n  36  win 47.2%  $  +17.2
    RAW   dropped sec<45: n  21  win 42.9%  $  -13.3    dropped sec<75: n  64  win 50.0%  $  +66.2
    FIXED dropped sec<45: n   6  win 66.7%  $  +18.3    dropped sec<60: n  14  win 50.0%  $   +4.3
    FIXED dropped sec<75: n  31  win 58.1%  $  +55.9
```

The dropped set is **mildly profitable**, not a pit of bad trades. So "early fires lose" is a fact about
one 5-day window, not a property of the clock, and I have **not** confirmed the owner's "no early
gambling" — I over-read a single window and said so to V rather than leaving it standing.

**3. The two-good-days pattern holds and hardens.**

```
  RAW sec>=60:   +125.1 over 10 days, 5/10 positive.  Best two (09-22 +123.7, 09-23 +74.6) = +198.4
                 = 159% of the total, so the other EIGHT days are -73.3 combined.
  FIXED sec>=60: +229.4 over 10 days, 6/10 positive.  Best two = +254.7 = 111% of the total, rest -25.2.
  RAW   per day: 09-15 -21.7  09-16 -48.1  09-21 -32.9  09-22 +123.7  09-23 +74.6
                 09-24 +58.9  09-25 +20.5  09-26 -40.1  09-27 +22.3   09-28 -32.3
  FIXED per day: 09-15 -52.9  09-16 -58.1  09-21 +38.0  09-22 +121.7  09-23 +132.9
                 09-24 +89.9  09-25 +18.1  09-26 -49.9  09-27 -34.9   09-28 +24.7
```

**4. Under the London execution model every cell of both arms loses.** RAW −$206.6 at `sec≥0` and −$179.3
at `sec≥60` (P/DD −0.77 / −0.75, 2.8 of 10 days positive); FIXED −$95.0 and −$83.3 (P/DD −0.50 / −0.48).
Paper positive and London negative in **every single cell**. That gap is the adverse fill, measured
directly, and it is the same thing the ledger section says with different arithmetic: these arms look
profitable exactly to the extent that the fill is assumed rather than simulated.

Drawdown here is taken **per simulation run and then averaged**, not computed on the averaged curve —
the average of many paths is smoother than any path, and a drawdown nobody could have lived through is
not a drawdown.

None of this changes the pre-registered B. It does mean the forward shadow is now the only evidence that
could support it, which is what it was set up to be.

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
