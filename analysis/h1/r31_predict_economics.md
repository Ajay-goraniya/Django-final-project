# R-31 — Predict.fun vs Polymarket: cheaper and it fills, **but it does not make the account profitable**

Script `analysis/h1/r31_predict_economics.py`. Sources: `learner/live_backup/tokyo_orders.json`
(1,184 rows, snapshot 09-13) and the live `zurich_2` journal (83 settled). Nothing assumed from
declarations — every rate below is measured from realised PnL and then checked against the declared
constant.

## 1. The fee, measured

**Both venues charge on SHARES, not on stake.** That is how the fee was identified, not assumed: on
the Polymarket rows `fee/shares` has sd **0.0010** against `fee/stake` sd **0.0053**. Since
shares = stake/price, the same share-rate costs more as a fraction of stake at a cheaper ask.

| venue | basis | winners | **losers** | n |
|---|---|---|---|---|
| Polymarket (live) | **1.67% of shares** | charged | **CHARGED** | 83 |
| Predict.fun (Tokyo) | **2.00% of shares** | charged | **ZERO** | 442 |

**Losers on Predict pay nothing beyond the stake**: `pnl == −stake` to 5e-5 on all 200 losing rows.
`fee_collateral` is 0.0 on every row; the fee is taken in shares (`fee_shares`), so a losing
position's fee is worthless shares. The declared `PREDICT_FEE_RATE=0.02` is confirmed exactly —
declared fee_shares total **10.253** equals the empirically-backed-out **10.253** on winners.

That asymmetry, not the headline rate, is the difference. Predict's rate is *higher* (2.00 vs 1.67);
it is cheaper only because it does not charge the ~46% of fires that lose.

## 2. The fill rate — the owner's ~98% is right, and understated

| | attempts | filled | rate |
|---|---|---|---|
| raw non-shadow rows | 857 | 442 | 51.6% |
| **excluding the manual-OFF pause** | **444** | **442** | **99.5%** |
| candle-level, same exclusion | 398 | 398 | **100.0%** |

403 of the 415 "unfilled" rows are `FORBIDDEN: EF/REVERSAL trading is manually OFF` — the user's own
pause since 09-11, not a venue failure. The only genuine failures are **2 × `noMarketMatch`**.
Against Polymarket live at 65% candle-level, this is a real and large advantage.

## 3. The same 1,762 graded EF fires, re-priced under both measured fees

Mean ask 0.456, win rate 54.1%.

| arm | per $1 | total | fee cost /$1 | fee as % of stake |
|---|---|---|---|---|
| gross (no fee) | +0.2054 | +361.96 | — | — |
| **Polymarket live** | +0.1667 | +293.80 | 0.0387 | **3.87%** |
| **Predict.fun** | **+0.1813** | **+319.49** | 0.0241 | **2.41%** |

**Predict − Polymarket = +0.0146 per $1, +25.68 over 1,762 fires. Predict is 38% cheaper on fees —
meaningfully, but not "way".** Because the fee scales with 1/ask it is not flat across prices:

| ask bucket | n | gross/$1 | Polymarket/$1 | Predict/$1 |
|---|---|---|---|---|
| 0.00–0.35 | 104 | +0.4999 | +0.4289 | +0.4699 |
| 0.35–0.45 | 683 | +0.2591 | +0.2171 | +0.2339 |
| 0.45–0.55 | 717 | +0.1586 | +0.1242 | +0.1354 |
| 0.55–1.00 | 258 | +0.0749 | +0.0460 | +0.0534 |

(0.00–0.35 is n=104, readable; reported whole, not as the best cell.)

## 4. THE NUMBER THAT ACTUALLY DECIDES IT — and it is not the fee

Put the paper record next to the live account on the same measure, **% of stake**:

| | gross | fee | net |
|---|---|---|---|
| paper, 1762 fires | **+20.5%** | 3.87% | +16.7% |
| **live Polymarket, 88 fires** | **−0.50%** | 4.01% | **−4.5%** |

**The gap between paper gross (+20.5%) and live gross (−0.50%) is 21 points and has nothing to do
with fees.** Fees are ~4 points of it. The other ~17 points are fill, slippage and selection — paper
fills every fire at the quoted ask with zero slippage, which this repo already records as an upper
bound that must never be compared like-for-like against a live fill.

So, plainly: **moving to Predict saves ~1.5% of stake per fire. The live gross edge is already
negative (−0.50%). A cheaper venue turns a −4.5% loss into roughly a −2.9% loss. It does not turn it
into a profit.** The venue switch is worth doing on its own merits — cheaper fee, 99.5% fill — but it
is not the fix, and it should not be sold as one.

## 5. The one way Predict could genuinely help beyond fees, untested

Polymarket live fills 65% of candles; Predict fills ~100%. If the 35% Polymarket misses are
systematically the *better* fires, the higher fill rate raises gross, not just lowers cost. R-18
found the opposite shape for resting orders (filled 40.7% win vs non-filled 99.1%), which argues the
missed ones were good — but that was a different mechanism and does not transfer. **Untested, and it
is the only route by which this venue move improves the edge rather than the cost.** It needs live
Predict fires to measure and cannot be settled from these journals.

## Limits

Tokyo snapshot is 09-13 and its lanes were manually OFF for much of it. Zurich live is n=88 ending
09-16 08:20. The 1,762-fire re-pricing is paper fills, so its absolute level is an upper bound for
both venues equally — the *difference* between the two columns is the reliable part, the level is not.

---

# R-31b — Predict's price is systematically different. **`p_venue` must be re-fit before the port.**

Script `analysis/h1/r31b_predict_quote.py`. 95,963 two-venue tick rows over 2,053 candles from
`venues.q`. `p_venue` rebuilt exactly as the live engine builds it from asks
(`btc_model_v10.py:173-179`): `(ask_up + (1 − ask_dn))/2`, clamped, `lv = logit(p_venue)`.
Same formula both sides, so only the prices differ.

**Oracle agreement first:** `venues.outcome` vs `candles.actual` agree on **1792/2050 = 87.4%**.
The venues settle differently on 12.6% of candles, and every cross-venue comparison below carries
that noise.

## (a) The answer, and the average hides it

| Polymarket ask | n | **mean (Predict − Poly)** | median | \|diff\| > 2c |
|---|---|---|---|---|
| 0.001–0.090 | 9409 | **+0.1042** | +0.0600 | 83.7% |
| 0.090–0.200 | 9239 | +0.1009 | +0.0700 | 84.1% |
| 0.200–0.310 | 9936 | +0.0820 | +0.0600 | 84.9% |
| 0.310–0.410 | 9463 | +0.0592 | +0.0500 | 86.4% |
| 0.410–0.500 | 9185 | +0.0276 | +0.0300 | 83.5% |
| 0.500–0.590 | 9803 | −0.0105 | −0.0100 | 81.4% |
| 0.590–0.690 | 9903 | −0.0464 | −0.0400 | 87.5% |
| 0.690–0.800 | 9498 | −0.0763 | −0.0600 | 87.3% |
| 0.800–0.920 | 9588 | −0.0976 | −0.0700 | 86.3% |
| 0.920–0.999 | 9939 | **−0.1028** | −0.0600 | 86.2% |
| **ALL** | 95963 | **+0.0031** | +0.0000 | **85.2%** |

**Predict's price is Polymarket's price compressed toward 0.5** — up to ±10 cents at the tails,
monotone across all ten deciles, and **85% of ticks differ by more than 2 cents**.

**The overall mean is +0.0031 — essentially zero — because the two tails cancel.** Anyone checking
only the average would conclude the books agree. They do not. This is the cell-vs-average trap and
it is why the decile table was required.

## (b) Predict's price is the worse forecast, each graded on its own oracle

| venue | n | Brier | logloss | mean p | base rate |
|---|---|---|---|---|---|
| Polymarket (vs `venues.outcome`) | 441 | **0.1941** | **0.5717** | 0.4998 | 0.5238 |
| Predict.fun (vs `candles.actual`) | 442 | 0.2128 | 0.6129 | 0.5022 | 0.5249 |
| constant 0.5 null | — | 0.2500 | 0.6931 | — | — |

Both beat the null, but Predict is materially less calibrated: +0.019 Brier, +0.041 logloss.

## (c) The port refire — **n=51, INSUFFICIENT, not read**

Only 199 of 1,108 fires had a two-venue quote logged at their own fire second, and only 51 of those
still cleared the EV rule once Predict's `p_venue` was substituted. **51 < 60, so by the standing
rule this cell is marked insufficient and I am not reading it**, in either direction — the number it
printed was positive and that is exactly when the rule matters most. The drop from 199 to 51 is
itself informative and is the one thing worth taking: substituting Predict's compressed price makes
the frozen model fire **~74% less often**, because a price pulled toward 0.5 produces less extreme
`lv`, hence less confident `p`, hence less EV clearing the threshold.

## Verdict for the adapter

**Yes — v10 needs `p_venue`/`lv` re-fit for Predict before the port, and V should know that now.**
The coefficient on `lv` is v10's second largest (+1.5514) and it was trained on the *spread* of
Polymarket logits. Feeding it a book compressed toward 0.5 does not merely shift the score, it
shrinks it — the refire firing 74% less is that effect, measured.

Two things this does **not** say: it does not say the port loses money (n=51 cannot support that),
and it does not say Predict's book is worse to trade. A compressed book with a 2%-on-winners fee and
100% fill may well be the better venue. It says the model cannot be moved across unchanged.

**Cheapest next step:** refit the venue block on Predict's own quotes over these 2,053 candles and
re-run the fire count; if it restores fire frequency, the port is a re-fit, not a rebuild.
