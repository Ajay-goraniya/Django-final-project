# Build36 / Build35 EF replay databases — 2026-08-01

Produced by `ef_replay/replay_build36.py` replaying the
`btc_replay_2026-08-01_24h` dataset causally through the unmodified production
code, with **MASTER OFF** (asserted at startup): signals fire, are recorded,
settled and counted, and no venue order is ever built. No live venue was
contacted.

| file | build | EF fires | directional |
|---|---|---|---|
| `build36_replay_2026-08-01.sqlite3` | 9.3-build36-adaptive-ef-learner | 19 | 52.63% |
| `build35_replay_2026-08-01.sqlite3` | 9.3-build35-ef-actual-fire-master-off | 24 | 50.00% |

Window: 2026-08-01 00:00:00 → 2026-08-02 00:00:00 UTC, 288 settled candles.
Both are `PRAGMA integrity_check = ok`, WAL-checkpointed, VACUUMed, and carry
the `btc-model-v9.1.1-r6.6-selective-adaptive-ef` ownership marker.

## Read them back with the model itself

```bash
python3 btc_model_v9_3_BUILD36.py --db build36_replay_2026-08-01.sqlite3 --ef-report
python3 btc_model_v9_3_BUILD35.py --db build35_replay_2026-08-01.sqlite3 --ef-report
```

Work on a copy if you want to keep the originals pristine — the model claims a
run lock and may write on open.

## What is inside

| table | build36 | build35 | contents |
|---|---|---|---|
| `candles` | 288 | 288 | settled 5m candles |
| `ef_predictions` | 19 | 24 | EF signals: direction, actual, correct, features |
| `ef_candidates` | 496 | 494 | every candidate considered, fired or not |
| `ef_episodes` | 6904 | 6872 | candidate lifecycle with decision stamps |
| `ef_frequency_candles` | 288 | 288 | per-candle frequency controller state |
| `trades` | 231 | 236 | shadow trade rows (MASTER-OFF accounting) |
| `predictions` / `gated_predictions` | 212 / 160 | 212 / 160 | MAIN / gated lanes |
| `model_weights` | 160 | 160 | MAIN model weight history |
| `meta` | 4 | 4 | includes the learner state, see below |

### Learner state

`meta['ef_adaptive_gate_v9_3']` is the full Build36 learner as JSON:
`version` (288, one per candle), `samples` (496), `weights` (20 features),
`regime_bias`, `intercept` (−0.2702), `econ_examples` (**0**), trackers.

```bash
python3 -c "import sqlite3,json;print(json.dumps(json.loads(sqlite3.connect('build36_replay_2026-08-01.sqlite3').execute(\"select value from meta where key='ef_adaptive_gate_v9_3'\").fetchone()[0]),indent=2))"
```

## Caveats carried by this data

* `sample_status = DIRECTIONAL_ONLY_NO_REAL_PNL`. No Predict.fun book history,
  so every quote-economics column (`real_pnl`, `shadow_pnl`, `return_on_stake`,
  `average_fill_price`) is NULL/None by construction — not zero, absent.
* `econ_examples = 0`: `learn_batch` treated every candidate as directional-only,
  so Build36's economics-aware adaptation never ran. The learner's own
  starvation diagnostic reports `"quote economics poor/unavailable"`.
* 19 and 24 fires are far too few to establish a directional edge; both builds
  are statistically indistinguishable from a coin flip on this sample.
* EF ran on the real perpetual microstructure: 99.33% of 3,344,103 evaluation
  ticks had `micro_source = PERP`.
