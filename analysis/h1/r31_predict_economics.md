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
