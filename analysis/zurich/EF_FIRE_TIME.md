# EF_FIRE_TIME — when should EF fire?

Zurich, 2026-09-28. READ-ONLY on the research archive's `decide_log`. 5 days, **1,015** gamma-graded candles,
**785,924** passes, raw p and both side asks every ~250 ms. Master OFF, nothing live, nothing deployed.

Owner, 09-28 09:5x: *"EF acts like everyone else — fires late, after the price has moved. Predict.fun's v11
fired at ~20 s and earned early cheap entries. Same v10 model on both."*

Labels are the venue's own resolution. The fill simulator, the capital-weighted per $1 and the halves are
imported from `ef_persist.py`, so these sit on the same basis as EF_PERSIST.md and EF_TRIGGER_SOURCE.md. The
permutation is V's stricter one: a flipped draw is priced at the **opposite side's real ask**, both arms
through the identical FAK test, so the control answers "what if the model had picked the other side", fully
priced, rather than "what if the payout flipped".

## Answer in seven parts

**1. The owner is right that EF fires late.** Baseline fixed15 fire second: **p10 45, p50 126, p90 198**. Only
**5.1%** of fires happen at or before second 30; **55.4%** happen at second 120 or later.

**2. The owner is right that firing earlier is better — and it is not close.** Across the 28-cell grid, every
one of the **16 cells with S ≥ 45 is negative**, and **7 of the 12 cells with S ≤ 30 are positive**. The sign
pattern is the finding; no single cell is.

**3. But it is not "early cheap entries" — the early rule pays MORE, not less.** Mean ask at the fire is
**0.540** for S=15 P=0.55 against **0.430** for the baseline. The early rule's advantage is that it is right
more often (**win 58.3% vs 43.9%** of fills), not that it buys cheaper. The baseline buys cheap and wrong.

**4. And the gain is the TIMING, not the model.** A placebo that keeps the model's *side* but drops its
*confidence bar* entirely (P = 0.00) pays **+0.045** at S=15 against **+0.042** for P=0.55 — the same or
better. Raising the bar makes it worse at every S: **P=0.70 is negative at all seven S values.** The model's
side call does carry the result (V's opposite-ask flip: p = 0.002–0.018 on the early cells), but its
confidence number earns nothing.

**5. And a spot-only model does not find what the crowd misses — the crowd is better (section 4).** A
walk-forward logistic on spot features with `lv` and `p_venue` removed loses to the venue's own mid at every
second tested, 0.687 vs 0.714 at second 20 widening to 0.703 vs 0.768 at second 60, and its disagreement
cells do not pay. The reason is structural: `move_bps` alone correlates **+0.717** with the venue mid, so with
these inputs there is very little the crowd is not already looking at.

**6. And flow is not the answer either — the venue is already watching it (section 5).** `ofi60` correlates
**0.64–0.69** with the venue mid, essentially where `move_bps` sits at 0.717. Flow-only loses to the mid at
every second, and mid+flow is *worse* than mid alone at all four. The Chainlink-minus-Binance divergence is
the one input tested that is genuinely independent of the price (|corr| 0.10–0.13) and it predicts nothing —
AUC 0.470–0.512 against the venue's own outcome.

**7. And the settlement reference is a lagged copy of Binance, which is why section 5's divergence was
noise (section 6).** Binance leads Chainlink by **2–3 s** at corr **0.81**; the reverse never exceeds 0.095,
and conditioning on Binance's own last 5 s collapses it from 0.074 to **0.007**. At the candle level the two
lines disagree on sign 6.5–7.0% of the time — the ceiling on any reference-based edge — but on those candles
the move is a median 0.09–0.18 bps against 1.66–2.34 bps overall, so the ceiling is lower still.

**Every cell that met the standing precondition was put through verify.py and every one came back
NOT A FINDING** — six from the grid, one from section 4, and section 5 produced no candidate at all. The
honest summary is that the *pattern* across 28 cells is strong and no individual cell survives its own gates.

## 1. Baseline — the rule live on London today

```
```

`revC` is the mean ask reversion between the fire and the +250 ms row, in cents — the EF_VETO_V2 mechanism.
`secFire` is the median fire second.

The bucket table is the owner's point in one line: the baseline puts **55%** of its fires into the 120 s+
region, where per $1 is +0.196 and −0.139 on 33 and 13 fills. Nothing in that table is a reading on its own —
every bucket is far under the 60-fill bar — which is exactly why the grid below exists.

## 2. The grid — all 28 cells, plus a placebo row

Rule: fire at the **first** pass with `sec >= S` **and** `raw p_side >= P` **and** own-side `ask <= 0.60`
(the engine's cap). One fire per candle.

```
```

Two facts checked before the grid was built, because they decide what it can mean:

- the engine logs the side the **model favours** on **100.0%** of passes (`p < 0.5` on 0.0% of 785,924), so
  `p_side >= P` can only ever mean the logged side and nothing is hidden on the unlogged one;
- the binding constraint is the **price**, not p: 64.7% of passes already clear p ≥ 0.70, but only **21.4%**
  have an own-side ask ≤ 0.60.

That second fact is why the placebo matters. Dropping the p bar does not open the floodgates — the ask cap is
still doing the work — so P=0.00 is a fair comparison rather than a different trade.

### Reading the grid

| | cells | positive | negative |
|---|---|---|---|
| **early**, S ≤ 30 | 12 | **7** | 5 (three of them the whole P=0.70 column) |
| **late**, S ≥ 45 | 16 | **0** | **16** |

Sixteen from sixteen is a strong pattern, but the cells share candles and are **not independent**, so it is
not a 2⁻¹⁶ p-value and must not be quoted as one. What makes it convincing is that it holds *at every P
level separately*, including the placebo column.

Down the P axis the model's confidence is **anti**-predictive: P=0.70 is negative at all seven S values, and
at S=15 the sequence P=0.00 → 0.55 → 0.60 → 0.65 → 0.70 runs +0.045, +0.042, +0.009, +0.008, −0.083.

`revC` also explains the fill rates: the early cells revert **+0.56 to +0.75c** and fill at **82–87%**, while
the baseline reverts **+7.23c** and fills at 42%. Early fires are not selected dips. That is the same
mechanism EF_TRIGGER_SOURCE and EF_PERSIST measured, seen from the other end.

**A caveat that limits all of it:** the fill simulator was validated against London's real 31% per attempt and
reproduces ~42% on the baseline. These early cells run at **82–87%**, far outside the range where the
simulator was checked. The direction of the result does not depend on the exact fill rate, but the per $1
magnitudes do, and they should be treated as optimistic until London measures a real early fire.

## 3. Does EF follow the crowd?

```
  n 195 fires with a move_bps feature
  corr(ask-0.50, move_bps signed toward OUR side) = +0.338   corr(ask-0.50, |move_bps|) = +0.415
  fires taken WITH the move already in place (sign(move) == our side): 83.6%
  ask-0.50 by |move_bps| bucket (if EF only buys what already moved, these rise together):
    |move|   0-2    n   101  mean ask-0.50 -0.096  mean ask 0.404
    |move|   2-5    n    70  mean ask-0.50 -0.067  mean ask 0.433
    |move|   5-10   n    20  mean ask-0.50 +0.019  mean ask 0.519
    |move|  10-20   n     4  mean ask-0.50 +0.097  mean ask 0.598

  per $1 by ASK-AT-FIRE x FIRE-SECOND (the two ways of asking "did we pay up for news"):
    ask bucket               sec 15-30           sec 30-60          sec 60-120         sec 120-180         sec 180-240
    0.00-0.45             +0.405 (2/4)       -0.104 (6/13)      +0.033 (12/35)      +0.405 (23/43)       +0.346 (6/21)
    0.45-0.55             +1.033 (2/4)        -1.000 (2/7)       +0.449 (8/17)       -0.169 (5/19)       -1.000 (4/12)
    0.55-1.00             -1.000 (1/2)             - (0/1)        -1.000 (3/4)       -0.411 (5/10)        +0.031 (3/3)
    cell format: per $1 (fills/fires). Anything under 60 fills is not a reading.

  What p and the ask were at sec 20 and sec 30, in the 195 candles fixed15 later fired on
  (ask is always OUR side - the side the fire eventually took - so it is the price we could have paid):
    sec 20: n 195  ask then 0.402 (p50 0.390)  ask at the fire 0.430 (p50 0.420)  ->  the price moved +2.86c against us on average, p50 +4.00c
             p then 0.662 (p50 0.664); the pass at sec 20 already favoured the SAME side we later bought on 27.2% of candles
             the sec-20 ask was CHEAPER than the fire ask on 64.1% of candles, the same on 2.6%, dearer on 33.3%
    sec 30: n 195  ask then 0.399 (p50 0.390)  ask at the fire 0.430 (p50 0.420)  ->  the price moved +3.15c against us on average, p50 +6.00c
             p then 0.667 (p50 0.678); the pass at sec 30 already favoured the SAME side we later bought on 27.2% of candles
             the sec-30 ask was CHEAPER than the fire ask on 61.0% of candles, the same on 3.6%, dearer on 35.4%
```

**Yes, clearly.** 83.6% of baseline fires are taken with the Binance move already pointing our way, and the
ask at the fire tracks the size of that move: correlation +0.415 with |move_bps|, and mean `ask − 0.50` rising
−0.096 → −0.067 → +0.019 → +0.097 across the move buckets. EF is largely buying what has already happened.

**Waiting costs 3–4c a share.** In the 195 candles fixed15 fired on, the ask for the side it eventually bought
was **+2.86c higher at the fire than at second 20** (p50 +4.00c), and was cheaper at second 20 on **64.1%** of
candles. That is the owner's "early cheap entries", measured.

**But the early price is for a different trade, and this is the important qualifier.** At second 20 the model
favoured the *same side* the fire eventually took on only **27.2%** of those candles. Firing at ~20 s is not
"buying the same thing earlier" — three times out of four it is buying the other side. So Predict.fun's v11
cannot be explained as the same trade entered sooner, and the grid's early cells do not work by anticipating
the late signal: they work by taking whatever the model favours *at that moment* and being right 58% of the
time.

The ask × second table is reported in full for completeness and **is not readable**: the largest cell has 23
fills against a 60-fill bar, and several are 2–6 fills. It is in the file so the grid is not selectively
quoted, not because it supports anything.

## 4. Can a SPOT-ONLY model see what the crowd does not?

V, 09-28: `model_v10.json`'s two largest inputs are `move_bps` **+1.663** and `lv` **+1.551** — `lv` being the
venue's own logit. The model half-copies the price, so it agrees with the crowd by construction. So: fit a
model that cannot see the price at all, and look only where it *disagrees* with the venue.

**Design.** Features `move_bps, mv_x_sec, imb20, ret5, ret30, ret60, rv60, basis_bps` — no `lv`, no
`p_venue`. Label is the venue's own resolution. The model predicts P(UP), so `p_side` is symmetric by
construction (p_DOWN = 1 − p_UP), unlike the engine's own p — which is what lets a disagreement cell pick
**either** side instead of inheriting the engine's choice. Walk-forward: day *k* is fitted on days < *k* only,
standardisation included and fitted on the training rows alone; the first day is never scored. One row per
candle per second — the first pass at exactly `sec == S`. Ridge logistic, Newton steps, intercept unpenalised.

`sec_left` is in the brief but is not usable: `ef_persist`'s loader drops it, and each model is fitted at one
fixed second where it is constant. Dropping a constant changes nothing.

### (a) AUC — the venue mid wins at every second, in both specifications

| S | AUC spot-only | AUC spot-only, no imb20 | AUC **venue mid alone** | gap (briefed − venue) |
|---|---|---|---|---|
| 20 s | 0.687 | 0.684 | **0.714** | −0.027 |
| 30 s | 0.691 | 0.695 | **0.732** | −0.040 |
| 45 s | 0.709 | 0.713 | **0.744** | −0.036 |
| 60 s | 0.703 | 0.703 | **0.768** | −0.065 |

Eight comparisons, eight losses. And the **gap widens with time**: the venue's price improves faster through
the candle (0.714 → 0.768) than the spot model does (0.687 → 0.703). By second 60 the crowd is a
quarter-of-an-AUC-point better and pulling away.

### A correction, and the structural reason this was always going to be hard

I flagged `imb20` in the script as a likely *venue* book feature rather than a spot one, and ran every row
twice because of it. **The data refutes that**: correlation with the venue mid is **+0.200** for `imb20`,
against **+0.448** for the explicitly-spot `spot_imb60` and **+0.981** for `lv`. `imb20` belongs in the
spot-only set. The no-imb20 rows below are therefore a second *specification*, not a principled correction —
which matters, because the only cell that qualifies for verify.py lives in that second specification.

The structural point is more important. **`move_bps` itself correlates +0.717 with the venue mid.** The crowd
is mostly pricing the move, so a "spot-only" model built on the move cannot be decorrelated from the crowd —
what it sees that the venue does not is a small residual *by construction*, and the AUC table is what that
residual is worth. Getting genuinely independent information means a feature the venue is not already
watching, not a re-weighting of the one it is.

### (b) The disagreement cells — full table, `*` marks under 60 fills

The rule: the spot model likes a side at `p_side >= P` while the venue prices that same side at `ask <= A`.

```
spot-only (as briefed)

  S=20s   scored rows 882 of 1014   train n by day {'09-25': 132, '09-26': 419, '09-27': 707, '09-28': 995}
    (a) AUC spot-only 0.687   vs   AUC venue mid alone 0.714   gap -0.027  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        28    26  92.9%  34.6%   -0.297  -0.233  -0.360  0.904  0.471  *n<60
        p>=0.65 & ask<=0.45      0      -      -      -        -       -       -      -      -

  S=30s   scored rows 881 of 1013   train n by day {'09-25': 132, '09-26': 419, '09-27': 706, '09-28': 994}
    (a) AUC spot-only 0.691   vs   AUC venue mid alone 0.732   gap -0.040  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        63    59  93.7%  44.1%   +0.024  +0.098  -0.048  0.312  0.411  *n<60
        p>=0.65 & ask<=0.45        18    18 100.0%  44.4%   +0.079  +0.081  +0.076  0.348  0.388  *n<60

  S=45s   scored rows 883 of 1015   train n by day {'09-25': 132, '09-26': 420, '09-27': 708, '09-28': 996}
    (a) AUC spot-only 0.709   vs   AUC venue mid alone 0.744   gap -0.036  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        50    50 100.0%  40.0%   -0.049  -0.092  -0.006  0.488  0.400  *n<60
        p>=0.65 & ask<=0.45        11    11 100.0%  27.3%   -0.158  -0.204  -0.120  0.658  0.327  *n<60

  S=60s   scored rows 882 of 1014   train n by day {'09-25': 132, '09-26': 420, '09-27': 707, '09-28': 995}
    (a) AUC spot-only 0.703   vs   AUC venue mid alone 0.768   gap -0.065  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50       105   100  95.2%  38.0%   -0.020  -0.173  +0.133  0.524  0.376
        p>=0.65 & ask<=0.45        46    41  89.1%  41.5%   +0.209  -0.041  +0.448  0.204  0.345  *n<60

spot-only WITHOUT imb20

  S=20s   scored rows 882 of 1014   train n by day {'09-25': 132, '09-26': 419, '09-27': 707, '09-28': 995}
    (a) AUC spot-only 0.684   vs   AUC venue mid alone 0.714   gap -0.030  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        19    19 100.0%  42.1%   -0.134  -0.067  -0.194  0.690  0.472  *n<60
        p>=0.65 & ask<=0.45         1     1 100.0%   0.0%   -1.000  +0.000  -1.000  1.000  0.450  *n<60

  S=30s   scored rows 881 of 1013   train n by day {'09-25': 132, '09-26': 419, '09-27': 706, '09-28': 994}
    (a) AUC spot-only 0.695   vs   AUC venue mid alone 0.732   gap -0.037  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        55    54  98.2%  46.3%   +0.040  +0.087  -0.007  0.236  0.427  *n<60
        p>=0.65 & ask<=0.45        13    13 100.0%  61.5%   +0.428  +0.191  +0.631  0.082  0.408  *n<60

  S=45s   scored rows 883 of 1015   train n by day {'09-25': 132, '09-26': 420, '09-27': 708, '09-28': 996}
    (a) AUC spot-only 0.713   vs   AUC venue mid alone 0.744   gap -0.031  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50        51    51 100.0%  49.0%   +0.179  +0.049  +0.303  0.100  0.407  *n<60
        p>=0.65 & ask<=0.45        13    13 100.0%  46.2%   +0.328  +0.176  +0.459  0.224  0.348  *n<60

  S=60s   scored rows 882 of 1014   train n by day {'09-25': 132, '09-26': 420, '09-27': 707, '09-28': 995}
    (a) AUC spot-only 0.703   vs   AUC venue mid alone 0.768   gap -0.065  -> the VENUE MID discriminates better
    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap
        rule                     n cand fills  fill%   win%    per$1      H1      H2  permP    ask
        p>=0.60 & ask<=0.50       104    99  95.2%  42.4%   +0.091  +0.061  +0.120  0.178  0.375
        p>=0.65 & ask<=0.45        43    38  88.4%  36.8%   -0.026  -0.305  +0.252  0.464  0.352  *n<60
```

**Of the 16 cells, exactly one clears 60 fills and is positive in both halves**: the no-imb20 specification at
S=60, `p>=0.60 & ask<=0.50` — 104 candidates, 99 fills, +0.091, H1 +0.061 / H2 +0.120. The **briefed**
version of that same cell is **−0.020 with a sign flip**. Every other cell is between 1 and 63 fills.

Two things visible in the table that are worth saying out loud:

- **Removing imb20 flips the sign of three cells** (S=45 `p>=0.60`: −0.049 → +0.179; S=60 `p>=0.60`: −0.020 →
  +0.091; S=30 `p>=0.65`: +0.079 → +0.428). A one-feature change moving results that much on 11–51 candidates
  is the signature of noise, not of a better feature set.
- **Simulated fill rates are 88–100%.** The simulator was validated near London's real 31% per attempt and
  reproduces ~42% on the fixed15 baseline. These cells are further outside its validated range than anything
  else in this document, because they select cheap asks that barely move. Treat every per $1 here as
  optimistic.

### verify.py on the one qualifying cell

```
cell: spot-only WITHOUT imb20, S=60, p>=0.6 & ask<=0.5  ->  104 candidates, 99 sim fills, per$1 +0.0907, win 42.4%
  V's control - sign flip priced at the OPPOSITE real ask: p = 0.178, flipped mean -0.000
  simulated fill rate 95.2% - the simulator was validated near London's REAL 31% per attempt and gives ~42% on the fixed15 baseline, so this is far outside where it was checked
  sweep over the p bar 0.55/0.60/0.65/0.70 -> +0.033 +0.091 -0.040 +0.471
==============================================================================
FINDING: spot-only (no imb20) S=60 disagreement p>=0.6 ask<=0.5   (+0.091/fire, n=99)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-25': 50, '09-26': 34, '09-27': 15}
  [PASS] both halves          h1 +0.061 / h2 +0.120
  [FAIL] permutation control  real +0.091 vs permuted mean +0.091 (p95 +0.091), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.033  0.091 -0.04   0.471]
  [PASS] cost sensitivity     +0c:+0.091 +0c:+0.076 +1c:+0.062 +2c:+0.034
  [PASS] beats the null       mine +0.091 vs the BRIEFED specification, imb20 included -0.020
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape

```

**NOT A FINDING**, and the provenance is the first thing to say about it: this cell exists in a specification
I ran on a hypothesis the data then refuted, while the briefed specification of the same cell is negative.
Beyond that, the p-bar sweep is wildly non-monotone (+0.033, +0.091, −0.040, **+0.471**, the last on a handful
of rows), the permutation is degenerate for the same reason as in section 2 — the bar re-selects the same set
— and the per-day counts **decay to nothing**: 50 fills on 09-25, 34 on 09-26, 15 on 09-27, **0 on 09-28**. A
cell whose candidates disappear over the sample is not a cell to build on.

### Answer to part 4

**No.** On five days of Zurich data a spot-only model is worse than the venue's own mid at every second
tested, by a margin that grows through the candle, and the cells where it disagrees with the venue do not pay
— the single positive one is a specification artefact that fails verification and is empty on the most recent
day.

That is not an argument that the owner's instinct is wrong; it is a measurement of *this* feature set. The
finding underneath it is the +0.717 correlation between `move_bps` and the venue mid: with these inputs there
is very little the crowd is not already looking at. Finding something the crowd does not see needs an input
the venue is not watching — an order-flow or cross-market signal — not a re-weighting of the move.

## 5. A FLOW-ONLY model, and the Chainlink reference

V, 09-28, agreeing with part 4: the input has to be something the venue is not watching. So: drop every price
and move feature and keep only order flow, book shape and the perp basis.

**Kept** (all that `decide_log` holds of the brief): `ofi5, ofi15, ofi60` (aggressor order-flow imbalance —
the engine carries 5/15/60 s, not the 5/30/60 in the brief), `spot_imb15, spot_imb60`, `imb5, imb20` (book
depth imbalance), `perp_n15`, `basis_bps`, `rv60`.
**Excluded**: `move_bps`, `mv_x_sec`, all `ret*`, `prev1/2_bps`, `range_bps`, `pos_in_range`, `dist_hi/lo_bps`,
`ref_move_bps`, `ref_open_bps` (price or move), `lv`, `lv_x_sec`, `p_venue` (the venue's own opinion),
`micro_bps` (a book-derived *price* — the venue's view under another name), `hod_sin/cos` (clock, not flow).

Same harness as part 4: walk-forward by day, scaler fitted on training rows only, first day never scored, one
row per candle at exactly `sec == S`, label is the venue's resolution, model predicts P(UP).

### (a) The premise does not survive the correlation table

| feature | \|corr\| with venue mid, S=20 → 60 |
|---|---|
| `perp_n15` | 0.022 · 0.070 · 0.068 · 0.016 |
| `rv60` | 0.053 · 0.063 · 0.082 · 0.068 |
| `imb20` | 0.332 · 0.306 · 0.265 · 0.246 |
| `imb5` | 0.345 · 0.332 · 0.288 · 0.278 |
| `basis_bps` | 0.321 · 0.292 · 0.322 · 0.297 |
| `ofi5` | 0.416 · 0.361 · 0.380 · 0.350 |
| `spot_imb15` | 0.422 · 0.442 · 0.419 · 0.346 |
| `ofi15` | 0.492 · 0.469 · 0.489 · 0.425 |
| `spot_imb60` | 0.647 · 0.642 · 0.650 · 0.563 |
| **`ofi60`** | **0.670 · 0.682 · 0.688 · 0.641** |
| *for scale:* `move_bps` | *0.717* |
| *for scale:* `lv` | *0.981* |

**`ofi60` sits at 0.64–0.69 — essentially where `move_bps` sits.** The venue is already watching order flow,
or flow and price move together tightly enough that there is no private information left in it. The two
features that *are* genuinely uncorrelated with the price, `perp_n15` and `rv60`, are non-directional — a
trade count and a volatility — so neither can pick a side on its own.

### (b) Flow does not add to the price. It subtracts.

| S | flow-only | venue mid alone | mid + flow | flow adds |
|---|---|---|---|---|
| 20 s | 0.641 | **0.714** | 0.695 | **−0.019** |
| 30 s | 0.671 | **0.732** | 0.718 | **−0.014** |
| 45 s | 0.687 | **0.744** | 0.738 | **−0.006** |
| 60 s | 0.698 | **0.768** | 0.754 | **−0.014** |

Flow-only loses to the mid at every second — that now makes **twelve comparisons across parts 4 and 5,
twelve losses**. And the third column is the sharper result: bolting flow onto the price makes the combined
model *worse* out-of-sample at all four seconds. The flow features are not adding a weak signal that a bigger
sample would sharpen; they are adding variance to something already better than they are.

### (c) Disagreement cells

```
--- S=20s ---
      rule                    n cand fills  fill%   win%    per$1      H1      H2  permP    ask
      p>=0.60 & ask<=0.50       94    90  95.7%  42.2%   -0.047  -0.025  -0.069  0.534  0.436
      p>=0.65 & ask<=0.45       30    29  96.7%  37.9%   +0.046  +0.163  -0.062  0.432  0.383  *n<60
--- S=30s ---
      rule                    n cand fills  fill%   win%    per$1      H1      H2  permP    ask
      p>=0.60 & ask<=0.50       80    78  97.5%  34.6%   -0.211  -0.171  -0.252  0.888  0.410
      p>=0.65 & ask<=0.45       31    31 100.0%  41.9%   +0.022  +0.008  +0.036  0.334  0.367  *n<60
--- S=45s ---
      rule                    n cand fills  fill%   win%    per$1      H1      H2  permP    ask
      p>=0.60 & ask<=0.50       76    74  97.4%  33.8%   -0.202  -0.021  -0.384  0.882  0.413
      p>=0.65 & ask<=0.45       22    22 100.0%  40.9%   +0.078  +0.439  -0.283  0.354  0.378  *n<60
--- S=60s ---
      rule                    n cand fills  fill%   win%    per$1      H1      H2  permP    ask
      p>=0.60 & ask<=0.50      137   130  94.9%  43.1%   +0.059  +0.154  -0.036  0.176  0.386
      p>=0.65 & ask<=0.45       71    65  91.5%  33.8%   -0.075  +0.205  -0.347  0.584  0.361
```

**No cell meets the standing precondition.** Exactly one is positive in both halves — S=30 `p>=0.65`, at
+0.022 with H1 +0.008 / H2 +0.036 — and it carries 31 fills against the 60-fill bar. So unlike part 4 there
was no verify.py candidate to run at all, which is a cleaner negative than having one and watching it fail.

Simulated fill rates are 91–100% here, for the same reason as section 4 — the cells select cheap asks that
barely move — and the same warning applies: the simulator was validated near London's real 31%.

### The Chainlink angle

`tape1s.ref_px` is the venue's own RTDS `crypto_prices_chainlink` topic (`poly_feeds.py:90-94`) — the
Chainlink BTC/USD the market settles on — and `tape1s.spot_px` is Binance, both at 1 Hz over **135.2 hours**
and **437,389** shared seconds.

```
  tape1s rows with BOTH the Chainlink RTDS reference and Binance spot: 437389 seconds = 135.2 h span
  divergence (chainlink - binance), bps: mean -2.215  p10 -3.47  p50 -2.18  p90 -1.01  sd 1.17
  the reference moves MORE often than the 1 s Binance tape: unchanged second-to-second on 23.0% of seconds vs 43.9% for Binance

  NOTE the raw divergence is a drifting OFFSET, not a centred signal: it is negative on more than 90% of
  seconds and its mean moved from -0.25 bps over the first 20k seconds to -2.21 bps over the whole span.
  Testing the raw level would mostly test that offset, so everything below is reported BOTH raw and de-meaned
  against the median divergence over the previous 600 s (past-only).

  corr(divergence at sec s, the NEXT 60 s Binance return) - one observation per candle, so the observations
  at a given s do not overlap:
      sec  n candles  corr raw  corr demean  rank demean  fwd60 bps sd  div_z bps sd
       20       1307    +0.011       +0.047       +0.033          4.98          0.77
       30       1329    -0.108       -0.095       +0.006          4.76          0.81
       45       1317    -0.029       +0.016       +0.073          4.80          0.77
       60       1368    -0.077       -0.055       +0.034          4.71          0.82

  and the question that actually matters - does the divergence predict the VENUE OUTCOME?
        sec      n  AUC div raw  AUC div demean   AUC mid   div_z |corr| mid
         20    900        0.494           0.470     0.715              0.127
         30    919        0.494           0.497     0.723              0.119
         45    906        0.503           0.512     0.747              0.101
         60    918        0.482           0.481     0.763              0.126
```

**The divergence is the one input tested in parts 4 and 5 that is genuinely independent of the crowd** —
de-meaned, it correlates only **0.101–0.127** with the venue mid, against 0.641 for `ofi60` and 0.717 for
`move_bps`. And it predicts nothing: correlation with the next 60 s of Binance return is +0.047 / −0.095 /
+0.016 / −0.055 with the sign flipping between seconds, rank correlation ≈ 0 throughout, and AUC against the
venue's own outcome is **0.470–0.512** — a coin.

I tested it raw and de-meaned because the raw divergence is a drifting *offset*, not a centred signal: it is
negative on more than 90% of seconds and its mean moved from −0.25 bps over the first 20k seconds to −2.21 bps
across the full span. De-meaning against the past-only 600 s median does not rescue it.

**One operational note that belongs with the arb work.** The settlement reference runs about **2 bps below**
Binance spot and that offset *drifts*. On a $110k BTC that is roughly **$22** — nearly ten times the **$2.33**
line gap that produced the single 0-payoff pair in `arb_trades_check`. That is the quantitative reason a
Binance-derived line proxy cannot be trusted at small gaps, and it is now measured rather than inferred.

### Answer to part 5

**No.** Flow is not something the venue is not watching: `ofi60` is as correlated with the price as the move
itself, flow-only loses to the mid at every second, and adding flow to the mid makes it worse. The Chainlink
divergence *is* independent of the price — and it is noise.

Put parts 4 and 5 together and there is a single sentence in them:

> **Every input tested that predicts the outcome is already in the price, and the one input that is not in the
> price does not predict the outcome.**

That is a much stronger statement than "the model needs better features", and it is the thing to decide on.
It does not say no such feature exists; it says none of the eighteen features this engine already computes is
one, and that the search should move to data the engine does not currently collect at all — the venue's own
trade prints being the obvious first candidate, since Zurich has 81,222 of them sitting unused in the ms probe
archive and they are the one thing measured on the venue's clock rather than Binance's.

## 6. LEAD-LAG: the Chainlink settlement reference against Binance spot

Both series from the engine's own 1 Hz tape: `ref_px` is the venue's RTDS `crypto_prices_chainlink` topic
(`poly_feeds.py:90-94`), `spot_px` is Binance. **438,395 shared seconds over 5.7 days** (89.9% of slots).

Two caveats that apply to every number here. **Overlap**: using every second makes the k-second windows
overlap almost completely, so correlations are unbiased but the effective sample is nearer n/k than n — no
p-values are quoted, and every figure is repeated on a **non-overlapping** subsample (every k-th second).
**Cadence**: the feeds do not tick alike — unchanged second-to-second on **23.0%** of seconds for Chainlink
and **43.9%** for Binance — and that many zeros attenuates any 1 s correlation toward zero, so small numbers
here are a floor, not a ceiling.

### (1) Binance leads. It is not close, and the lead is 2–3 seconds.

| k | BIN leads CL | (non-ovl) | CL leads BIN | (non-ovl) | diff |
|---|---|---|---|---|---|
| 1 s | 0.2038 | 0.2038 | 0.0584 | 0.0584 | +0.1454 |
| 2 s | 0.7803 | 0.7856 | 0.0852 | 0.0852 | **+0.6950** |
| **3 s** | **0.8123** | 0.8124 | 0.0948 | 0.0940 | **+0.7175** |
| 5 s | 0.5673 | 0.5582 | 0.0862 | 0.0870 | +0.4811 |
| 10 s | 0.3150 | 0.2955 | 0.0642 | 0.0533 | +0.2508 |
| 20 s | 0.1685 | 0.1743 | 0.0488 | 0.0396 | +0.1197 |

`BIN leads CL` = corr(Chainlink return over [t, t+k], Binance return over [t−k, t]). It peaks at **k=3 s with
0.8123** while the reverse direction never exceeds **0.095** at any horizon. The non-overlapping column is
identical to three decimals, so the precision is real rather than an artefact of overlap.

### (2) The relationship is one-way

| horizon | corr(BIN last-5 s, CL forward) | partial, given CL's own last-5 s | corr(CL last-5 s, BIN forward) | partial, given BIN's own last-5 s |
|---|---|---|---|---|
| 10 s | 0.4153 | **0.4238** | 0.0739 | **0.0074** |
| 30 s | 0.2401 | **0.2350** | 0.0536 | **0.0114** |

Binance's last 5 seconds predicts the reference's next 10 seconds at 0.42, and **conditioning on the
reference's own last 5 seconds does not reduce that at all** — it rises slightly, so the reference's recent
move carries no information about its own future that Binance does not already carry. The reverse collapses:
0.0739 → **0.0074**. Once you know what Binance just did, the reference tells you nothing about where Binance
goes next.

So the settlement reference is a *lagged, smoothed copy* of the exchange the model already watches. That is
the mechanism behind section 5's result that the Chainlink−Binance divergence predicts nothing: the
divergence is mostly the 2–3 second lag plus feed noise, and a lag is not information about the future.

### (3) The candle version — and the ceiling on any settlement-reference edge

Binance move = spot(ep+S) against the TWAP60 of spot over [ep−60, ep−1]; Chainlink move = ref(ep+S) against
the TWAP60 of **ref** — the line the venue actually pays on. A line needs ≥45 of its 60 seconds on both
feeds, the same rule `arb_5m_15m.py` and `ef_chainlink_div.py` already use.

| S | n | corr(moves) | **sign disagree** | median \|BIN\| bps | median \|CL\| bps | median \|BIN\| **on disagreements** |
|---|---|---|---|---|---|---|
| 20 s | 1375 | 0.9784 | **7.0%** | 1.66 | 1.61 | **0.10** |
| 30 s | 1386 | 0.9802 | **6.9%** | 1.95 | 1.89 | **0.09** |
| 45 s | 1378 | 0.9874 | **6.7%** | 2.13 | 2.10 | **0.15** |
| 60 s | 1398 | 0.9870 | **6.5%** | 2.34 | 2.35 | **0.18** |

**The ceiling is 6.5–7.0%, and the last column says it is worth even less than that.** The two lines point at
different sides on about one candle in fifteen — but on exactly those candles the Binance move is a median of
**0.09–0.18 bps**, against **1.66–2.34 bps** across all candles. Disagreement happens only where the move is
roughly fifteen times smaller than typical, i.e. where the market is on the line and neither side is
meaningfully favoured anyway.

That reconciles the 6.5–7.0% here with the ~3.3% outcome-level disagreement measured in MULTI_MARKET.md: a
sign difference at second S often has 240 seconds left to resolve itself, and the ones that survive to
settlement are fewer still.

### Answer to part 6

Binance leads the settlement reference by **2–3 seconds** with a correlation of 0.81, the reverse direction is
0.09, and conditioning kills the reverse entirely (0.074 → 0.007). The reference is a lagged copy, so there is
no reference-based edge to find — and the candle-level ceiling on one, 6.5–7.0%, sits almost entirely on
candles where the move is a tenth of a basis point.

The one genuinely useful consequence is operational rather than predictive, and it is the same one section 5
surfaced: because the reference lags by 2–3 s and runs ~2 bps below spot, a **Binance-derived line is
untrustworthy whenever the gap it is being asked to resolve is small** — which is precisely the regime the
5m/15m arb pairs live in.

## verify.py on the grid cells (section 2)

Standing rule: run verify.py on any cell positive in both halves with n ≥ 60. Six qualified — S ∈ {15, 20, 30}
at P=0.55, the S=15 and S=20 placebos, and the baseline with the ask cap.

```

### grid S=15 P=0.55   per$1 +0.0425 on 683 fills of 829 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.016, flipped mean -0.036
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=15 P=0.55   (+0.042/fire, n=683)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 11}
  [PASS] both halves          h1 +0.039 / h2 +0.046
  [FAIL] permutation control  real +0.042 vs permuted mean +0.042 (p95 +0.042), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [PASS] cost sensitivity     +0c:+0.042 +0c:+0.033 +1c:+0.024 +2c:+0.006
  [FAIL] beats the null       mine +0.042 vs PLACEBO S=15 with no p bar +0.045
  [FAIL] paired test          n=60, agree on 36, discordant 24 (14 vs 10), edge +0.067, exact McNemar p=0.541
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### grid S=20 P=0.55   per$1 +0.0346 on 663 fills of 798 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.018, flipped mean -0.046
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=20 P=0.55   (+0.035/fire, n=663)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 9}
  [PASS] both halves          h1 +0.028 / h2 +0.041
  [FAIL] permutation control  real +0.035 vs permuted mean +0.035 (p95 +0.035), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [FAIL] cost sensitivity     +0c:+0.035 +0c:+0.025 +1c:+0.016 +2c:-0.001  <- dies once you pay realistically
  [FAIL] beats the null       mine +0.035 vs PLACEBO S=20 with no p bar +0.038
  [FAIL] paired test          n=57, agree on 37, discordant 20 (11 vs 9), edge +0.035, exact McNemar p=0.824
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, cost sensitivity, beats the null, paired test


### grid S=30 P=0.55   per$1 +0.0413 on 609 fills of 757 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.006, flipped mean -0.056
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=30 P=0.55   (+0.041/fire, n=609)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 10}
  [PASS] both halves          h1 +0.048 / h2 +0.034
  [FAIL] permutation control  real +0.041 vs permuted mean +0.041 (p95 +0.041), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [PASS] cost sensitivity     +0c:+0.041 +0c:+0.032 +1c:+0.023 +2c:+0.005
  [PASS] beats the null       mine +0.041 vs PLACEBO S=30 with no p bar +0.009
  [FAIL] paired test          n=58, agree on 41, discordant 17 (9 vs 8), edge +0.017, exact McNemar p=1.000
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, paired test


### placebo S=15 P=0.00   per$1 +0.0446 on 732 fills of 853 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.002, flipped mean -0.044
    sweep over S 15:+0.045 20:+0.038 30:+0.009 45:-0.044 60:+0.008 90:-0.034 120:-0.030
==============================================================================
FINDING: placebo S=15 P=0.00   (+0.045/fire, n=732)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 12}
  [PASS] both halves          h1 +0.021 / h2 +0.068
  [FAIL] permutation control  real +0.045 vs permuted mean +0.045 (p95 +0.045), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.045  0.038  0.009 -0.044  0.008 -0.034 -0.03 ]
  [PASS] cost sensitivity     +0c:+0.045 +0c:+0.035 +1c:+0.026 +2c:+0.007
  [FAIL] beats the null       mine +0.045 vs fixed15 unfiltered +0.061
  [FAIL] paired test          n=73, agree on 50, discordant 23 (15 vs 8), edge +0.096, exact McNemar p=0.210
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### placebo S=20 P=0.00   per$1 +0.0384 on 713 fills of 821 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.002, flipped mean -0.050
    sweep over S 15:+0.045 20:+0.038 30:+0.009 45:-0.044 60:+0.008 90:-0.034 120:-0.030
==============================================================================
FINDING: placebo S=20 P=0.00   (+0.038/fire, n=713)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 11}
  [PASS] both halves          h1 +0.002 / h2 +0.075
  [FAIL] permutation control  real +0.038 vs permuted mean +0.038 (p95 +0.038), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.045  0.038  0.009 -0.044  0.008 -0.034 -0.03 ]
  [PASS] cost sensitivity     +0c:+0.038 +0c:+0.029 +1c:+0.020 +2c:+0.002
  [FAIL] beats the null       mine +0.038 vs fixed15 unfiltered +0.061
  [FAIL] paired test          n=68, agree on 44, discordant 24 (13 vs 11), edge +0.029, exact McNemar p=0.839
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### baseline fixed15 + ask cap   per$1 +0.1452 on 72 fills of 182 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.128, flipped mean +0.007
==============================================================================
FINDING: baseline fixed15 + ask cap   (+0.145/fire, n=72)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-24': 15, '09-25': 28, '09-26': 8, '09-27': 17, '09-28': 4}
  [PASS] both halves          h1 +0.274 / h2 +0.017
  [FAIL] permutation control  real +0.145 vs permuted mean +0.145 (p95 +0.145), p=1.000 over 500 draws
  [PASS] cost sensitivity     +0c:+0.145 +0c:+0.130 +1c:+0.114 +2c:+0.086
  [PASS] beats the null       mine +0.145 vs fixed15 unfiltered +0.061
  [FAIL] paired test          the two rules never disagree - no information
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, paired test

```

**All six: NOT A FINDING.** What the failures actually say:

- **The permutation reads p = 1.000 on every cell, and that is an artefact of the construction, not a
  result.** verify.py shuffles the model's predictions and re-applies the rule's own bar — but 90.7% of all
  passes already clear p ≥ 0.55, so a shuffled p re-selects almost exactly the same set and real == permuted
  by definition. I flagged this before running it. The control that carries weight here is V's opposite-ask
  sign flip, which reads **p = 0.002–0.018 on the early cells** and **p = 0.128 on the baseline** — that one
  says the side selection is real.
- **`beats the null` is the substantive failure.** S=15 and S=20 at P=0.55 both lose to their own placebo
  (+0.042 vs +0.045, +0.035 vs +0.038). The model's confidence bar does not pay for itself. S=30 is the one
  exception (+0.041 vs +0.009).
- **The S sweep is non-monotone** on both families — earlier is better in aggregate but not smoothly, with a
  dip at S=45 and a partial recovery at S=60.
- **Paired against the baseline the evidence is thin**: 57–73 shared candles, agreeing on about two thirds,
  McNemar p = 0.21 to 1.00. The early rules are a *different population* (829 fires against 195), so the
  paired test has little to work with — which is itself worth knowing before anyone calls this an upgrade.
- Per-day samples fail only on 09-28, which is a partial day (9–12 fills).

## What I would say to the owner

The diagnosis is confirmed and the prescription is not. EF does fire late, late firing is worse, and the
price does run 3–4c away while it waits. But the grid says the gain from firing early comes from **when**, not
from the model — a rule that ignores the confidence number entirely does as well — and the sec-20 lookback
says the early entry is not the same trade at a better price. So "fire at 20 s like v11" is a real direction
with a real mechanism behind it, and it is not yet a validated rule: nothing here passed, the fill simulator
is being run far outside where it was checked, and the strongest single number in the study is a *placebo*
matching the model.

On part 4 the answer is cleaner and more negative. Taking the price out of the model does not reveal
something the price was hiding — it just makes the model worse, at every second, by a margin that grows
through the candle. The useful number there is not the AUC, it is the **+0.717** correlation between
`move_bps` and the venue mid: the venue is already a move-follower, so a move-based model has almost no
private information to contribute, and re-weighting it cannot create any. If the owner wants something the
crowd does not see, it has to be an input the venue is not watching — order flow, or another market —
rather than a different treatment of the move. Part 5 then tested exactly that and came back negative too, so
the conclusion has hardened into one sentence: **every input tested that predicts the outcome is already in
the price, and the one input that is not in the price does not predict the outcome.** The search has to move
to data the engine does not currently collect — the venue's own trade prints being the obvious candidate,
since Zurich holds 81,222 of them unused in the ms probe archive and they are the only thing measured on the
venue's clock rather than Binance's.

The next thing worth doing, if the owner wants it, is the one measurement Zurich cannot make: London firing a
small number of real early orders and reporting the actual fill rate and slippage at second 15–30. Everything
in sections 2 and 4 turns on a simulated 82–100% fill that no live system has demonstrated.

## Files

- `ef_fire_time.py` — baseline, the 28-cell grid, the placebo row, the crowd measure
- `ef_fire_time_verify.py` — verify.py on all six qualifying grid cells
- `ef_spot_only.py` — section 4: the walk-forward spot-only model and the disagreement cells
- `ef_spot_only_verify.py` — verify.py on the one qualifying section-4 cell
- `ef_flow_only.py` — section 5: the flow-only model, mid+flow, and the Chainlink divergence
- `ef_leadlag_ref.py` — section 6: Chainlink vs Binance lead-lag, partials, and the candle-line disagreement
