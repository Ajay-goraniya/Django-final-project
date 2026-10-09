# R-22 — the TWAP line holds on every venue-settled candle we have. But it is 7.7 days, not 8 weeks.

User: *"test that new twap 60 stream with our 8 weeks of data."*

## 1. Coverage first, because the premise needs correcting

| source | table | n | span (UTC) |
|---|---|---|---|
| **`venues.outcome`** — the Polymarket settlement oracle | outcome | **2,132** | 09-08 15:25 → 09-16 08:25 |
| poly_pnl | trades | 1,036 | 09-08 17:35 → 09-16 04:30 |
| v10_poly_long4 | trades | 777 | 09-08 17:35 → 09-14 00:25 |
| v12_poly_lane | trades | 596 | 09-11 13:55 → 09-16 04:30 |
| v12_poly_weekend | trades | 303 | 09-11 13:55 → 09-13 18:40 |
| zurich_2 — **live money** | results | 76 | 09-15 02:25 → 09-16 00:45 |

**2,132 venue-settled candles over 9 UTC days = 7.7 days.** That is the whole span, and it is the
span since Polymarket logging started.

The "8 weeks" we hold is **Binance klines** — I have nine years of those. A Binance candle is not a
settlement. Grading a venue claim on Binance-only candles is the cross-venue error this project has
already paid for twice, in both directions, so the wider history cannot be stretched into a statement
about the settlement line. **R-22 widens R-16 from 1,797 to 2,132 candles — 19% more, not 7× more.**

## 2. The two rules over the full span — the advantage holds

n = **2,132**, every settled candle, 100% price coverage.

| rule | agrees with `venues.outcome` |
|---|---|
| `close ≥ open` | **87.05%** (1856 / 2132) |
| `TWAP60(end) ≥ TWAP60(open)` | **96.67%** (2061 / 2132) |

**Discordant 249 (11.7%): the close rule is right 8.8%, TWAP is right 91.2%. Binomial p = 3.1e-38.**

Per UTC day — every day, never the best one:

| day | n | close | twap | gain |
|---|---|---|---|---|
| 09-08 | 103 | 88.35% | 97.09% | +8.74 |
| 09-09 | 288 | 90.62% | 98.61% | +7.99 |
| 09-10 | 283 | 89.40% | 98.59% | +9.19 |
| 09-11 | 288 | 86.81% | 97.57% | +10.76 |
| 09-12 | 288 | 79.17% | 91.32% | +12.15 |
| 09-13 | 279 | 83.87% | 94.27% | +10.39 |
| 09-14 | 268 | 90.67% | 99.63% | +8.96 |
| 09-15 | 233 | 89.70% | 97.00% | +7.30 |
| 09-16 | 102 | 85.29% | 96.08% | +10.78 |

**Positive on 9 of 9 days, range +7.30 to +12.15.** Halves +10.04 / +9.19.

**Verdict on V's question: yes, the ~+9.9 point advantage holds wider.** R-16 measured 86.81 → 96.66
(+9.85) on 1,797; the full span gives 87.05 → 96.67 (**+9.62**) on 2,132, with no day below +7.3.
Nothing about the line changes. This is the grading line, and it is right.

## 3. The proxy error cannot be measured — the file is not here

`learner/live_backup/ref_stream.sqlite3.gz` is **not on the branch**, so
|Binance TWAP60 proxy − Chainlink value| in bps at open and close, and how often the two disagree on
the settlement direction, cannot be computed. **That measurement is the error budget on every R-16
and R-22 number**, and until it exists the honest bound is the one the data already gives: the
Binance TWAP proxy disagrees with the venue on **3.3% of candles**, which is an upper bound on the
proxy error *plus* whatever the venue does that neither rule captures.

**Requested: Mumbai pushes `ref_stream.sqlite3.gz`.** V offered; this is the ask.

## 4. What follows

No model change, as the brief says — and R-16's retrain already showed why none would help (the book
was pricing the TWAP rule all along). What this settles is narrower and worth having: **the engine's
`candles.actual` column, `close ≥ open`, is wrong about Polymarket settlement on 12.95% of candles,
consistently, every day.** It is the right grading line for Predict.fun and the wrong one for
Polymarket, and anything reading it for a Polymarket number is off by that much.
