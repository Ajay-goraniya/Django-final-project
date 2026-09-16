# R-14 — execution anatomy. **Two candidate changes tested; both fail, for different reasons.**

R-13 said the engine is spread capture, so this looks at where the spread is won or lost. Real data
only: the Zurich live journals (`orders.plan` carries cap / quote / max_shares / age_ms, `fills` the
price paid, `results` the venue's own resolution) joined to the 1 Hz polybook.
**138 live orders — 75 filled, 63 rejected, 61 FAK-killed.** Script alongside this file.

## (1) You pay the ask, or you do not trade

Median price against the venue mid on the side being bought:

| | n | vs mid | vs mid +1s | vs mid +5s | vs mid +60s |
|---|---|---|---|---|---|
| FILLED (price paid) | 75 | **+0.0050** | +0.0050 | +0.0050 | −0.0575 |
| REJECTED (cap) | 63 | **−0.0150** | −0.0150 | −0.0550 | −0.0725 |

The ask itself sits **+0.0050** above the mid — so **the fills pay exactly the half-spread, never
better**, and the rejects were the orders trying to buy *below* fair. **The cheap ask is not
available. It is the thing that gets killed.**

## (2) Size is NOT the binding constraint — which kills V's first candidate change

| order size / displayed size at signal | n | fill% | median ratio |
|---|---|---|---|
| **under 25%** | **81** | **54.3%** | **0.04** |
| 25–50% | 4 | 25.0% | 0.28 |
| 50–100% | 1 | 100% | 0.70 |
| 1–2× | 6 | 50.0% | 1.46 |
| over 2× | 1 | 100% | 2.22 |

**81 of 93 orders are already under a quarter of displayed size — median 4% — and still only 54%
fill.** `size ≤ displayed` is already true on **86 of 93 (92%)**, and on **40 of the 43** rejects
with a book sample. **Capping size at displayed would change at most 7 orders.**

So the "105 of 108 rejects killed for size" reading of the FAK error does not survive contact with
the book: the order is tiny against what is shown. What fails is the book moving inside the ~350 ms
round trip, not depth. **Candidate change "size ≤ displayed": ruled out — it is already the case.**

## (3) Fire-second × ask grid — **unreadable, and reported as such**

All 12 cells run n = 1 … 34, every one under the 60 bar. 138 orders cannot support a 12-cell grid.
The full grid is in the script output; **no cell is read, and none should be.**

## (4) The second candidate change, and why it also does not ship

Of the 43 rejects with a book sample, **26 (60%) had a cap BELOW the ask at signal, median gap
0.070** — priced to buy under fair, exactly as (1) says. The obvious change is *cap at the ask*.

**It cannot be evaluated on this data, and I will not ship a number for it.** Reject candles have no
recorded outcome — `results` has 70 rows for 70 fills and nothing for reject-only candles — and my
`venues` snapshot ends 09-15 01:10, before these orders. Grading them off Zurich's `candles` table
would be the **Binance** oracle, which disagrees with Polymarket on ~9% of candles and is the exact
cross-venue error this project has already paid for twice. So the honest statement is: **the
mechanism is established, the payoff is not measurable yet.**

The remaining **17 of 43 rejects had a cap AT or ABOVE the ask** and were killed anyway — those are
pure round-trip losses, and no cap change reaches them.

## Verdict

**No execution change is proposed for shipping.** One candidate is ruled out as already satisfied
(size), the other is mechanically supported but unmeasurable until reject candles carry outcomes.

**What would make this answerable — one line for V:** have the engine record the venue resolution
for *every* candle it fired on, not only the ones that filled. That single change turns 63 rejects
from unmeasurable into a gradeable counterfactual, and R-14 part 4 becomes a real grid.

Token budget: R-14, ~25k.
