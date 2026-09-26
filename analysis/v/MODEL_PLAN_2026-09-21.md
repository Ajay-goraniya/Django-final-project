# Plan before the next model — questions, answers, next questions (V, 2026-09-21)

Owner: "make a proper plan before making a model, how, why, everything... find questions and then
solutions and then again questions and then solutions... finalize this first."
Nothing here is built. Nothing here ships until the owner says so. Sessions stay stood down.

Status of every line: **KNOWN** = measured on this repo's data (source given); **OPEN** = must be
measured before building; **OWNER** = the owner's decision, not ours.

---
## 0. What we are actually trying to do (get this wrong and everything below is wasted)

**Q0.1 What is the objective?** OWNER's words: "good accuracy + pnl (more important) + adjustive
frequency + adaptive." Turned into numbers so it can be tested:
- Primary: **net PnL per $1 staked, after the venue's real fee and real fill price**, positive in
  BOTH halves of every test window (`halves()`), on ≥60 graded fills per cell.
- Secondary: fires per day inside a band the owner sets (OWNER: how many per day is "enough"?).
- Accuracy is reported but never optimised: R-10 proved a genuinely accurate mode is worth nothing.
**Q0.2 Whose result are we predicting?** KNOWN: Polymarket settles `btc-5m-twap-60` on the
**Chainlink BTC/USD 60 s TWAP at close vs the Chainlink value at open** (price to beat). Not Binance
close vs open. On 155 live fills the two disagreed 32 times (20.6%), 26 of them candles that closed
within 5 bps of open. Label = `venues.outcome`, always. The rule, not the exchange, is the target.
**Q0.3 Which venue?** OWNER said "we are moving to Predict". KNOWN: Predict fee 2% of shares,
winners only, ~99.5% fill; Polymarket 1.67% of shares win-or-lose ≈4.0% of stake, 41% fill at the
touch (R-18). KNOWN: Predict settles on **Binance close ≥ open** (`candles.actual`), a DIFFERENT
rule from Polymarket. => The model must be trained per venue rule. One model cannot serve both.
  -> Next Q: does the owner want Polymarket-rule or Predict-rule first? (OWNER). Everything in
  §2 onward is written for Polymarket's rule; the Predict version swaps the reference line for raw
  Binance open/close and the fee/fill model for Predict's, and needs the Predict credential the owner
  alone places.

---
## 1. Why the last one lost (so the new one does not repeat it)

| cause | status | evidence |
|---|---|---|
| Wrong ruler: features on Binance first-trade open, settlement on Chainlink TWAP line | KNOWN | §0.2; `btc_model_v10.py:83` default `first_trade`, `twap60` never selected |
| No refit: fit 08-29..09-06, live 09-16, decay already noted 09-09..09-15 | KNOWN | DEPLOYED.md:417 |
| Fill gap: paper fills at the quote, live fills 41% at the touch and pays +1c | KNOWN | R-18, R-3 |
| Fee: 4% of stake round trip on Polymarket | KNOWN | R-30b/31 |
| The model IS the venue price: v10 dir. acc 0.7494 vs venue price alone 0.7496, agree 92.1%, McNemar p=0.937; corr(p, p_venue)=0.98 | KNOWN | R-13 |
| Output-side patches (regime switch, adapt_ratio, venue shrink, freshness bar, gates) all lost | KNOWN | R-27/28/29/30, Task 116, CLOSED table |
| Streaks: at a 45% hit rate an 8-loss run is EXPECTED about once per 150 fills (150 × 0.55^8 ≈ 1.3). Live had 15, 11, 5. The 15 is not chance; the 8 by itself would be | KNOWN (arithmetic) | zurich_2/3 results |

**Q1.1 Given R-13, can ANY direction model beat the venue price?** OPEN and decisive. R-13 says the
v10 forecast adds nothing over the venue's own price. If that holds after fixing the ruler, the
edge is not in "who wins" but in **price paid vs settlement probability** (buy at 0.40 when the
true rate is 0.46 with fee covered) and in **execution**. The plan below tests this FIRST (§4, T1)
before a single feature is engineered. If T1 fails, §5 is the plan; if it passes, §3.

---
## 2. Data — what exists, what is missing

| need | have | gap |
|---|---|---|
| Polymarket outcome per candle | `venues.outcome` 09-08 → 09-16; `ef_arch/polymarket/fiveday` markets json 08-29 → 09-06 (v10's label source) | 09-17 onward not collected (Zurich journal has its own `results.actual` to 09-17 12:30) |
| Chainlink settlement line (the ruler) | ref feed logged from 09-16 ~02:00 (`ref_stream`, 7.8 h in Task 98; engine features `ref_*` in zurich_2/3 signals, 69 live fires) | before 09-16 only the Binance TWAP60 proxy: matches Chainlink rule 71/72 (Task 108) — usable, must be flagged `ref_src=0` |
| Binance spot ticks | `week_data` 08-29 → 09-06 (8 GB L2 + trades), `book1s` 09-11 → 09-16 at 1 Hz, `data-api.binance.vision` for any range | continuous 1 s spot for 09-07..09-10 must be fetched (`fetch_rest_klines.py` style) |
| Venue price at decision time | `venues.q` 132k rows 09-08 → 09-16; `polybook` 441k rows 09-11 → 09-16; per-fire `ask_at_decision` in all journals | none before 09-08 => the venue-price feature has 9 days of history, the BTC features have years |
| Real fills | 158 LIVE rows (`all_trades.csv`) | tiny; PAPER/SHADOW 17k rows fill at the quote — must be corrected by the R-18 fill model, never used raw |

**Q2.1 Is 9 days of venue-price history enough to fit a p_venue coefficient?** OPEN. v10 fit it on
8 days and it dominated (R-13). Solution: fit the BTC-side model on the long history WITHOUT
p_venue, then combine with p_venue by a 1-parameter shrink fitted walk-forward on the 9 days
(R-29 tested one fixed shrink and lost; this fits it, does not guess it). -> Next Q: does the
combination beat p_venue alone on `paired()`? That is T1.
**Q2.2 Which candles are in the training set?** All of them, not only the fired ones. Training on
fired candles only (the export) learns v10's selection, not the market.
**Q2.3 Where is the line at the open?** KNOWN: `_ref_at` = feed value AT the open (12.11.1). For
history, TWAP60 of Binance ending at the open (proxy). Both must be built by the SAME code path the
engine serves (`open_reference="twap60"`), and Stage-A parity re-run as in R-12 (~1e-6 bps).

---
## 3. The model itself (only if T1 passes)

**Q3.1 What does it predict?** P(Chainlink TWAP at close > line at open) at second s of the candle,
for s in 15..240. Output calibrated (isotonic, fitted on the walk-forward fold, never on the test).
**Q3.2 Features?** The existing 30 v10 features re-measured from the settlement line (`twap60`),
plus `ref_open_bps` (Binance first trade vs line), `ref_move_bps`, `ref_gap_bps`, `ref_src`, plus
p_venue and its 15/30/60 s changes. NO new feature enters without `paired()` vs the model without
it (R-8 rule: parity first, then earn the place).
**Q3.3 Model class?** L2 logistic as now, or gradient boosting on the same inputs, chosen by
walk-forward Brier AND per-$1 — never by in-sample fit. R-12 showed 4.7M rows of history alone
scored WORSE (Brier 0.1952 vs 0.1654) than 8 recent days: recency dominates. So: rolling window,
OPEN length (test 3, 7, 14 days as a full grid, report all, pick by both halves).
**Q3.4 How does it stay adaptive?** In the inputs and the refit, never in a gate:
  - refit every N hours on the trailing window, automatically, with the previous model kept as the
    fallback if the new fold's Brier is worse (OPEN: N);
  - venue price and adapt_ratio-type vol scaling as INPUTS the fit sees, so their weight is learned;
  - regime is NOT a switch (R-30, "rain or sun" rule); if a bucket is unprofitable in all folds it is
    simply where p is ≤ breakeven and the EV rule refuses.
  -> Next Q: does a daily refit actually beat the frozen model on the same tape? T3 below.

---
## 4. The tests, in order. Each is a gate; failing one stops the build, it does not "get a
##    workaround".

Every test runs `analysis/h1/verify.py` `Finding` in full (grading, sample ≥60, halves, permutation
on PREDICTIONS, paired, sweep, costs, null, quote_age) and reports the whole grid, never the best
cell. Walk-forward only. Real data only.

- **T0 Ruler parity** — engine `twap60` path vs offline extractor on the 69 live fires with `ref_*`
  logged: differences ~1e-6 bps or the build stops.
- **T1 Can we beat the venue price at all?** On every logged candle 09-08 → 09-17, at each second
  bin: p_model(twap60 ruler) vs p_venue alone, graded on `venues.outcome`. `paired()` on discordant
  candles. PASS = model beats p_venue on PnL per $1 after fee, both halves, n≥60 discordant. R-13
  says the Binance-ruler model does not. If the settlement-ruler model does not either, GO TO §5.
- **T2 Cheap-side truth** (owner's own question: "how many times are we right at $0.40?") — grid of
  ask paid × second-in-candle × true settle rate, fee included, both halves. Breakeven at ask a on
  Polymarket: win rate > a/(1−fee_on_shares) ≈ a×1.017 + fee on the stake… computed exactly in the
  test, not by hand. This grid alone answers whether "right often enough at 0.40" exists.
- **T3 Frozen vs rolling** — same tape, same fills, frozen 8-day model vs daily-refit model.
  `paired()`. If rolling does not beat frozen, the refit schedule is dropped, not defended.
- **T4 Fill realism** — every PnL number re-run with the R-18 fill model (41% at touch, +1c pay-up
  else no fill) AND with the live 158 as the check. The number that goes to the owner is this one.
- **T5 Rain or sun** — per-day and per-6-hour-block PnL per $1, all blocks, both halves; any negative
  block is reported, not filtered.
- **T6 Paper, both venues' rule** — paper on Mumbai with the new json for ≥60 graded fills AND ≥2
  days, `halves()` green, before anyone says the word live.

---
## 5. If T1 fails (the model cannot beat the venue price on direction)

Then the direction model is not where the money is, and R-13 already said so. The candidates that
are NOT closed:
- **Price-paid model, not direction model**: predict P(settle) with the venue's own price as the
  baseline and learn only the RESIDUAL (where the venue is mispriced by second-in-candle and
  distance to the line). Passes/fails by T2's grid.
- **Execution**: R-3 measured the live cost (+0.004/$1 vs +0.038 quoted). Resting orders were
  tested (Tasks 101-103, closure notes) — do not re-open without reading them.
- **Venue choice**: Predict's 2%/winners-only fee and 99.5% fill changes T2's breakeven line by
  ~1/6 of the current hole (R-31). It does not create an edge; it stops one from being eaten.
Closed and NOT to be resurrected (STATE.md CLOSED table): direction model over the venue quote table
(12a), stacked brain (R-9), calibrated-p EV (R-6), Kelly/dynamic stake (R-4/5; and never live without
two owner confirmations), accuracy mode (R-10), gates of every kind, big-history retrain as-is (R-12).

---
## 6. Live-side rules that hold regardless of model

- Stake fixed; master and stake are the owner's; the only automatic stop is `ef_cash_floor`
  (OWNER: set it or leave unset — it is unset on zurich_3 today).
- Any new json: paper first (T6), then live with master OFF, then the owner arms.
- Expected streaks at the target hit rate are written into the deploy note BEFORE going live so a
  normal run is not mistaken for a broken model, and an abnormal one (15) is caught by a number, not
  by a screenshot.
- Every finding on the way: `verify.py` first, numbers only, ≤15 lines in chat, file on the branch.

---
## 7. Questions only the owner can answer (needed before §3 starts)

1. Venue rule first: Polymarket (Chainlink TWAP) or Predict (Binance close)? Both = two models.
2. Fires per day: what band counts as "adjustive frequency"?
3. Refit cadence you will accept in live (a model that changes every day vs every week)?
4. Capital and stake for the paper→live step, and whether `ef_cash_floor` gets set.
5. Do you want T1/T2 run now on existing data (no new collection needed, ~1 session-day), or
   collection restarted first (ref feed logger, venues.q) so the test window is longer?

Sizes: T0-T2 need no new data. T3 needs the 1 s spot for 09-07..09-10 fetched. T6 needs a Mumbai
paper lane, which is stood down until you say.
