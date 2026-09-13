# Build36 vs Build35 — EF replay over 2026-08-01 (288 candles)

Causal replay of the unmodified production path over the
`btc_replay_2026-08-01_24h` dataset. MASTER OFF (asserted, not assumed):
signals fire → are recorded → settled → counted, and no venue order is built.

Window: 2026-08-01 00:00:00 → 2026-08-02 00:00:00 UTC, 288 settled candles.
Events replayed: 4,557,410 (3,217,252 perp depth20 + 1,073,872 perp tick trades
+ 266,286 spot aggTrades). EF evaluation ticks: 3,344,103, of which
**99.33% ran on `micro_source = PERP`** — the real perp lane, not spot fallback.

## Headline

| | Build36 (adaptive learner) | Build35 (baseline) |
|---|---|---|
| EF fires (settled/total) | 19/19 | 24/24 |
| directional wins | 10 | 12 |
| **directional accuracy** | **52.63%** | **50.00%** |
| fires per 100 candles | 6.60 | 8.33 |
| fires per day | 19.0 | 24.0 |
| average fire second | 92.7 s | 117.8 s |
| sample status | DIRECTIONAL_ONLY_NO_REAL_PNL | DIRECTIONAL_ONLY_NO_REAL_PNL |

Build36 fires ~21% less often than Build35 and commits ~25 s earlier in the
candle. Neither build demonstrates a directional edge on this sample.

**Sample size caveat.** 10/19 and 12/24 are coin-flips. The 95% interval on
10/19 spans roughly 29%–76%. The 2.6-point gap between the builds is far inside
noise, and a single 24-hour sample cannot separate them. An interim read at 238
candles showed 69.2% / 64.7%; the final 50 candles pulled both to ~50%, which is
what a sample this small does.

## The Build36 learner

| metric | value |
|---|---|
| state versions (one per candle) | 288 |
| learning samples | 496 |
| **economic samples (`econ_examples`)** | **0** |
| regime transitions | 396 |
| final intercept | −0.2702 |
| frequency ratio | 0.12 (floor 0.55) |
| frequency guard active | 283/287 candles (98.6%) |

The learner **is** adapting: it took 496 samples from 287 candles even though EF
only fired 19 times, because it learns from *candidates*, not just fires.
Its intercept tightened monotonically from −0.012 to −0.282 by candle 180, then
eased back to −0.263 — it got progressively more conservative as losses landed,
then partially relaxed.

Largest learned weights (magnitude): `certainty −0.154`, `persistence −0.128`,
`pclose +0.120`, `phase −0.112`, `anti_fake −0.070`, `path −0.063`.

Regime bias: `EARLY_UNDEVELOPED +0.327` (most permissive), `EARLY +0.162`,
`WHIPSAW +0.056` … `LATE −0.126`, `MIXED −0.216` (most restrictive).

Regime occupancy: CLEAN_REVERSAL 100, MIXED 72, LATE 39, EARLY 38, WHIPSAW 17,
WICK_REVERSAL 10, EARLY_UNDEVELOPED 7, WICK_TRAP 4.

### The learner's own starvation diagnostic

```json
{"active": true, "frequency_ratio": 0.12, "observed": 50, "ratio_limit": 0.2,
 "reasons": ["quote economics poor/unavailable"]}
```

Build36 diagnoses its own limitation here: with no Predict.fun books,
`learn_batch` treats every candidate as *directional-only*, so `econ_examples`
stays at 0 for the whole day. **Build36's headline feature — economics-aware
adaptation — was never exercised.** Only the directional half of the learner ran.

## Why EF did not fire (decision-reason histogram)

| count | reason |
|---|---|
| 995,304 | HARD:CONTROL |
| 955,593 | CANCEL:FLOW_AGAINST |
| 428,526 | HARD:REACH |
| 347,325 | price is at candle open |
| 147,415 | HARD:OLD_SIDE_EXHAUSTION |
| 104,475 | CANCEL:FAKE_REVERSAL_RISE |
| 90,315 | HARD:SETTLEMENT |
| 57,360 | CANCEL:CONTROL_COLLAPSE |
| 21,858 | HARD:CHOP |
| 13,076 | HARD:QUALITY |

`CONTROL` is the single dominant gate, with `FLOW_AGAINST` cancellation close
behind. 16 of 19 fires were `STRUCTURE_CONFIRMED`, 3 `STRUCTURE_DEVELOPED`.

## Causality audit

| check | result |
|---|---|
| fires decided outside their own candle window | 0 |
| fires with fire_second outside [0,300) | 0 |
| derived-vs-official kline drift (close/high/low) | 0.0 / 0.0 / 0.0 |

**PASS** — intra-candle OHLC was rebuilt from spot trades ≤ T only, and
reproduced the official archived klines exactly; the closed bar is injected at
its own close time, never before.

## What this run does and does not establish

Establishes: EF fires at ~19–24 per day on this data; the perp lane drives
99.33% of evaluations; the decision path, settlement, MASTER-OFF shadow
accounting and directional learner all execute causally end to end.

Does **not** establish: any directional edge (n=19/24, ~50%), any PnL or
return-on-stake, or whether the economics-aware learner helps — that layer got
zero samples. Quote economics require Predict.fun book history.
