# Dynamic staking grid — Zurich EF shadow journals (09-26). BACKTEST ONLY.

Spec: `analysis/v/staking/STAKING_GRID_SPEC.md` (8f763a0). Script: `analysis/zurich/staking_grid.py`.
**No engine was touched and nothing here is a recommendation to change a live stake.** CLAUDE.md
requires the owner's two separate confirmations before any live staking change; this is the back-test
that rule explicitly permits.

Sample: **765 graded EF fills**, 09-15 00:31 -> 09-26 00:52 UTC, pooled across all five Zurich shadow
journals. Split by **time** at the midpoint: first half 275 trades, second half 490. Parameters for
B and F fitted on the **first half only**, every arm scored on the second. Every arm takes **every**
trade (paired). Stake clipped to the engine's [3, 50] after normalisation.

No arm reads `p`, EV or any model score, per the spec. Arm G's sigma is the realised volatility of
the twelve 5-min BTC candles that close **before** the fire.

## Second half — scoring, per dollar actually deployed

| arm | deployed | PnL | PnL/$1 | maxDD | DD per $1k |
|---|---|---|---|---|---|
| **A fixed $5** | 2450 | +564.38 | **+0.2304** | 75.20 | **30.69** |
| B bankroll 15% (normalised) | 3732 | +861.30 | +0.2308 | 115.89 | 31.05 |
| B bankroll 15% (compounding) | 15380 | +3908.29 | +0.2541 | 494.36 | 32.14 |
| C fixed shares | 2422 | +526.03 | +0.2172 | 70.93 | 29.29 |
| D fixed win target | 2402 | +512.01 | +0.2132 | 68.44 | 28.50 |
| E cheap-entry tilt | 2472 | +597.32 | +0.2416 | 78.27 | 31.66 |
| **F de-risk below MA(40)** | 2639 | +650.51 | **+0.2465** | **49.10** | **18.60** |
| G vol scaled | 2394 | +543.39 | +0.2270 | 71.83 | 30.00 |

Beats A on **both** axes per dollar deployed: **F only.** B and E buy more PnL with more drawdown;
C, D and G buy less drawdown with less PnL. Every cell is n=490, above the 60 bar.

## Full period (for reference, not for scoring)

| arm | deployed | PnL | maxDD | P/DD | 1st half | 2nd half | worst day |
|---|---|---|---|---|---|---|---|
| A fixed $5 | 3825 | +510.60 | 213.14 | 2.40 | -53.77 | +564.38 | -63.81 |
| B 15% (norm) | 4580 | +825.02 | 135.85 | 6.07 | -36.28 | +861.30 | -38.29 |
| B 15% (compounding) | 18277 | +3838.25 | 592.76 | 6.48 | -70.04 | +3908.29 | -64.81 |
| C fixed shares | 3828 | +474.00 | 205.81 | 2.30 | -52.03 | +526.03 | -59.96 |
| D fixed win target | 3841 | +465.10 | 198.30 | 2.35 | -46.91 | +512.01 | -64.33 |
| E cheap-entry tilt | 3825 | +541.86 | 219.84 | 2.46 | -55.46 | +597.32 | -67.63 |
| F de-risk MA(40) | 3846 | +611.19 | 191.18 | 3.20 | -39.32 | +650.51 | -41.35 |
| G vol scaled | 3955 | +547.27 | 174.06 | 3.14 | +3.88 | +543.39 | -90.26 |

## Four things that must travel with these numbers

**1. The parameter fits are worthless as fits.** Both B and F were tuned on the first half, and the
first half was a **losing** period for EF, so every candidate scored negative:

```
B  pnl/maxDD by f:   2%:-0.35  4%:-0.35  6%:-0.29  8%:-0.24  10%:-0.20  15%:-0.13  -> chose 15%
F  pnl/maxDD by k:  10:-0.33  20:-0.35  40:-0.25                                    -> chose 40
```
B's sweep is monotone in f across a loss, so "pick the best" degenerates to "bet the most", and it
then scored on a winning half. That is not a validated parameter, it is a sign flip. F's sweep is at
least non-monotone (40 beats 20 beats 10 is not ordered), but it is still the least-bad of three
losers. **Neither fit earns the usual meaning of out-of-sample.**

**2. Equal capital does not hold inside the scoring half.** Normalisation was applied over the full
period, so within the second half B deploys 3732 against A's 2450 (+52%) and F deploys 2639 (+8%).
The headline "F makes +650 vs A's +564" is partly F betting more. Per dollar deployed the gap is
+0.2465 vs +0.2304 — real, but a third of the size the raw totals suggest. **That is why the scoring
table above is per dollar and the raw table is marked not-for-scoring.**

**3. The spec's win condition is not met, because I only have one venue.** An arm wins "on BOTH
London and Zurich". This is Zurich alone, and Zurich is shadow: paper fills at the quoted ask, no
refusal cost. London's live EF run just showed that fill behaviour is exactly where shadow lies —
event mode looked good here and lost money there. **F is a candidate, not a winner.**

**4. It is all riding on an EF edge that has never passed verification.** The standing ledger has the
raw EF arm failing the permutation control at every reading (p 0.065-0.280, bar 0.01), with the
"buy the cheap side at these moments" null taking 76-88% of the return. Every arm above is a way of
sizing that same unverified edge. If the edge is not real, the grid ranks ways of losing faster.
