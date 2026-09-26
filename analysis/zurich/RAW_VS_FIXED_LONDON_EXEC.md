# RAW vs FIXED under London execution — Zurich candles (09-26). READ-ONLY.

Model: `analysis/v/rawfixed/LONDON_EXEC_MODEL.md` (9b6d758). Script:
`analysis/zurich/raw_vs_fixed_london_exec.py`. Stake $10, 1000 Monte Carlo runs, fee
`0.07*shares*p*(1-p)`.

**357 candles** carrying both an EF decide row and a graded outcome, 09-15 02:25 -> 09-26 03:15 UTC.
Grading: `venues.outcome` on 51 candles, engine `results.actual` on 306; the two agree **84/84**
wherever the snapshot overlaps this journal set.

Both arms are recomputed from the **same** decide rows, so the comparison is paired by construction
and neither arm benefits from having been the live profile:
`ev = p/breakeven - 1`, `breakeven = ask*(1+0.07*(1-ask))`; RAW fires at the first pass with
`ev(p_raw) >= 0.25`, FIXED at the first pass with `ev(platt(p_raw)) >= 0.15`.

Fired: **RAW 336, FIXED 277, both 256, RAW-only 80, FIXED-only 21.**

## The answer: RAW does not beat FIXED — not under London execution, and not even on paper

| | RAW | FIXED |
|---|---|---|
| **London exec, all** | **-255.10** (-0.123/$1) | **-112.33** (-0.067/$1) |
| London exec, 2nd half | -20.43 (-0.017) | **+81.89 (+0.083)** |
| **No exec cost, all** | **+127.79** (+0.037/$1) | **+256.48** (+0.089/$1) |
| No exec cost, 2nd half | +307.25 (+0.153) | +421.83 (+0.248) |

Under London execution both arms lose, and **RAW loses about 2.3x what FIXED loses.** The only
positive cell anywhere in the execution runs is FIXED's second half.

**RAW does not lead on paper either, over the full sample.** +127.79 against FIXED's +256.48.

## Where RAW's apparent lead comes from, and why it does not survive

Paired on the 256 candles **both** arms fire:

| subset | RAW | FIXED |
|---|---|---|
| both-fire, no exec cost | **+346.30** (+0.130) | +259.84 (+0.098) |
| both-fire, London exec | -59.38 (-0.038) | -100.97 (-0.064) |
| RAW-only, 80 candles, no exec | **-218.51** (-0.263) | — |
| FIXED-only, 21 candles, no exec | — | -3.37 (-0.016) |

On the candles they share, RAW *does* beat FIXED on paper — it fires earlier and pays a better entry.
That is the whole of the owner's intuition and it is correct as far as it goes. But RAW also takes
**80 extra candles that FIXED declines, and those 80 lose -218.51 on paper at -0.263 per $1.** The
discordant trades give back more than the shared ones win. Calibration's value is not in the entries
it improves, it is in the fires it refuses.

Under execution the shared-candle lead reverses too: -59.38 vs -100.97 keeps RAW ahead there, but both
are negative and the 80 discordant candles sink the total.

## How much of the paper result survives execution

| arm | paper | London exec | lost to execution |
|---|---|---|---|
| RAW | +127.79 | -255.10 | **-382.89** |
| FIXED | +256.48 | -112.33 | **-368.81** |

**None of it survives for either arm.** Execution costs both roughly the same in absolute terms
(~370-383), so the ranking is set by where each started. The driver is adverse selection, not
slippage: winners fill at 54.1% and losers at 65.0%, so a rule with a real edge has that edge
filtered out of its fills before slippage is applied. Expected fills are 200 of 336 for RAW and
163 of 277 for FIXED — roughly 60% of intended trades in both cases.

The per-price-bucket sensitivity run changes nothing material: RAW -235.69, FIXED -129.06.

## The limitation that most affects this result
**A candle is only scorable if some lane actually traded it** — `results` rows exist only where a
filled order does (checked: 0 results rows without one, on live4 551 vs 552). On live4 alone, 1018
candles carry EF decide rows and only **544** are graded; **474 are invisible** because nothing traded
them. So this is not the population of candles the arms would face, it is the subset the live engine
happened to trade, and the live engine was running one profile at a time. That conditioning cannot be
removed from this data and it is the first thing I would want fixed before anyone acts on the ranking.

Second: the 5th/95th bands are wide and overlap heavily (RAW -409 to -99, FIXED -240 to +17), so the
gap between the arms under execution is directional, not a clean separation.
