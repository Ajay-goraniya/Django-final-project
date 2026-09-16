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

## (4b) MEASURED after V pushed a fresh `venues` snapshot — still does not ship

My `venues` copy was stale (ended 09-15 01:10); the branch snapshot reaches **09-15 23:00, 2,019
rows**. Coverage over the reject candles: **47 of 63 (75%)** — gaps are hours where V's container
was reclaimed and the collector died with it. Provenance: the Zurich journal's own `actual` agrees
with `venues.outcome` on **53 of 53** fills, independent files.

| | n | win% | pnl/$1 | total |
|---|---|---|---|---|
| current fills | 53 | 50.9% | +0.137 | +7.25 |
| **counterfactual — cap at the ask, on the 26 rejects priced below it** | **26** | 65.4% | **+0.170** | +4.42 |

**And pricing at the ask does not buy a fill either: of 59 orders priced at or above the ask, 42
filled — 71.2%.** Nearly a third still die to the round trip. At that rate the counterfactual
returns **+3.14**, not +4.42.

verify.py: **NOT A FINDING** — **sample size FAIL (n=26, under the 60 bar)** and **halves FAIL
(+0.566 / −0.226, sign flips)**. Costs and null pass; on 26 trades that is not evidence. The
fill-rate figure is n=59, itself one short of the bar, and is not read either.

**So part 4 is now measurable and the answer is: positive, unreadable, do not ship.** It needs
roughly 2.5x the reject sample before the cell clears the bar.

## Verdict

**No execution change is proposed for shipping.** One candidate is ruled out as already satisfied
(size), the other is mechanically supported but unmeasurable until reject candles carry outcomes.

**Superseded:** I asked V to record venue resolutions for every fired candle. V pointed out the
data already existed — my snapshot was simply stale. Measured above; the blocker was mine, not the
engine's. What it actually needs now is **more rejects**, not more instrumentation.

Token budget: R-14, ~25k.
