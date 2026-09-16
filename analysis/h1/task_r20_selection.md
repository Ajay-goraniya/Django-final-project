# R-20 — the fitted selector loses to the rule we already run, and makes the bad evening worse

The last untried route: don't improve the forecast or the price, choose *which candles to be in*.
Target = realized pnl per $1 at the paid price on `venues.outcome`. Inputs: fire-second observables
only (p_side, ask, ev, sec_left, rv60, move_bps, spread_bps, lv, imb5, imb20, micro_bps, ret60,
pos_in_range, ref_open_bps, ref_move_bps). Ridge, walk-forward by day, rank within each day, sweep
the top X%. Script `analysis/h1/task_r20_selection.py`.

1,033 fires over 9 days; **851 scored on 6 held-out days**; mean +0.150/$1 at 100%.

## The sweep — and the two columns that decide it

| keep | n | **model /$1** | model total | **EV /$1** | **random /$1** | win% |
|---|---|---|---|---|---|---|
| 100% | 851 | +0.150 | +127.41 | +0.150 | +0.150 | 53.5% |
| 90% | 767 | **+0.137** | +105.23 | +0.168 | +0.150 | 52.8% |
| 80% | 680 | **+0.143** | +97.03 | +0.185 | +0.148 | 52.6% |
| 70% | 596 | +0.170 | +101.28 | +0.171 | +0.149 | 53.9% |
| 60% | 511 | +0.162 | +82.87 | +0.227 | +0.150 | 53.6% |
| 50% | 425 | +0.173 | +73.68 | **+0.260** | +0.152 | 54.6% |
| 40% | 340 | +0.205 | +69.87 | **+0.301** | +0.152 | 55.6% |
| 30% | 255 | +0.227 | +57.90 | **+0.352** | +0.145 | 56.1% |
| 20% | 171 | +0.249 | +42.60 | **+0.420** | +0.154 | 56.1% |
| 10% | 84 | +0.235 | +19.78 | **+0.441** | +0.149 | 53.6% |

**The fitted model loses to the EV ranker at every single frequency**, and at 90% and 80% it is below
*random*. Subset control at top 50%: model +0.1734 against a random mean of +0.1449, **P(random ≥
model) = 0.218** — not significant. So the ranking carries essentially no information; what little the
per-$1 column gains as X falls is the arithmetic of firing less on a positive-mean, high-variance
series, which is exactly what the random column is there to expose.

verify.py, top 50% vs EV at the same count: **NOT A FINDING** — −0.086/fire, halves −0.064 / −0.114
(consistently behind, not noisy), and it loses the null by $37 (+73.68 vs +110.31).

## The evening test — it fails the user's actual complaint

Worst 3-hour window PnL and worst same-side loss run, per held-out day:

| arm | 09-10 | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 |
|---|---|---|---|---|---|---|
| current (all fires) | −3.6 r4 | **−9.8** r4 | −3.6 r3 | −5.5 r3 | −1.7 r4 | −4.1 r2 |
| model top 50% | −5.0 r3 | **−11.2** r3 | −2.7 r3 | −2.4 r4 | +0.8 r3 | −1.2 r2 |
| model top 30% | −2.0 r2 | **−14.3** r3 | −2.9 r2 | −0.7 r2 | −0.8 r2 | −1.0 r3 |
| EV top 50% | −4.0 r3 | −3.7 r2 | −1.3 r3 | −1.4 r3 | −2.7 r3 | −3.0 r2 |
| EV top 30% | −2.0 r3 | −3.7 r2 | −0.6 r3 | −3.3 r3 | +0.6 r2 | −2.0 r5 |

On 09-11 — the worst session in the set — the fitted selector takes the worst window from **−9.8 to
−11.2 at top 50% and −14.4 at top 30%**, while firing half and a third as often. **It concentrates
into the bad window instead of avoiding it.** That is the opposite of what was asked for.

## The trap in this table, stated so nobody walks into it

The EV column looks spectacular: +0.150 at 100% rising monotonically to +0.441 at 10%. **Do not read
"fire the top 30% by EV" off it.**

R-19 measured what that gradient is: across EV quartiles the **win rate is flat** (54.3 / 53.1 / 52.8 /
53.3) while the **ask falls 0.514 → 0.382**; `corr(ev, win) = −0.034`. EV ranks cheapness. And R-18
measured what happens to cheap asks in live execution on this same book: the orders that fill at a
better price win **40.7%**, the ones that do not fill win **99.1%**. So the high-EV tail is the part
most exposed to the selection that live fills impose, and its paper gradient is an upper bound that
live partially confiscates. Putting a hand-set threshold on it would be a gate on a score whose slope
is a known paper artifact — the standing rule and R-19 both say no.

## Verdict

**R-20 does not ship. No paper twin.** Selection from fire-second observables, fitted to realized PnL
and tested honestly, is worth nothing over the incumbent rule and is actively worse on the shape the
user cares about.

That closes the third and last of the routes this session opened: the direction forecast is the book
(R-13), paying under the touch costs more than it saves (R-18), and choosing among the fires carries
no information (here). The remaining honest statement is that on this data the engine's edge is the
half-spread it captures at the touch, it is small, and nothing tested in R-3 … R-20 enlarges it.
