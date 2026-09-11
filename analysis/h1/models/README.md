# Frozen Task 11.2 direction model

**Frozen 2026-09-11 02:35 UTC (Task 17.1).** This artifact is immutable. Any retrain is a **new**
artifact with a new filename — never overwrite this one, or the forward test loses its meaning.

| | |
|---|---|
| model | `ef11_2_gbm_seed0.joblib` — `HistGradientBoostingClassifier`, 0.27 MB |
| params | `max_iter=200, learning_rate=0.06, max_depth=5, early_stopping=True, validation_fraction=0.15, random_state=0` |
| training rows | 505,365 from 72,207 candles |
| **training cutoff** | **`TRAINING_CUTOFF_MS = 1788887700000`** (venue-window start). Every training candle ends strictly before this. Nothing after it went in, and nothing ever will. |
| decision seconds | `SECS = [15, 20, 30, 45, 60, 90, 120]`, first clearing second wins, one fire per candle |
| EV margin | `EV_MARGIN = 0.15` |
| fee | `FEE = 0.02` (Predict.fun taker) |
| liquidity floor | notional ≥ $10 at the recorded ask |
| sklearn | **1.9.0** · joblib 1.6.0 · numpy 2.4.6 |

## Reproduction check (run at freeze time)

The frozen artifact, driven through `decide()`, reproduces the Task 11.2 replay exactly:

```
n=91  per-fire +0.263  halves +0.352 / +0.177  total +23.94
```

Feature parity between the training builder and `feats_at()` in the frozen module was asserted with
`np.allclose` before export. **One thing this check caught:** `TRAINING_CUTOFF_MS` was initially
written as the venue quote table's first timestamp, which is *earlier* than the first candle where
venue book, engine outcome and kline path all exist. The constant above is the real cutoff.

## Use

```python
import joblib
from ef11_2_predict import decide, trailing12, SECS
m = joblib.load('ef11_2_gbm_seed0.joblib')
t12 = trailing12(prev_12_candle_paths, candle_open)
for S in SECS:                      # first clearing second wins
    r = decide(m, path, S, t12, ask_up, ask_dn, size_up, size_dn)
    if r:
        side, ask, ev = r
        break
```

`path` is the candle's one-second closes so far; only `path[:S+1]` is read.

## Status

**Shadow candidate, not shippable.** The replay behind it is 648 candles over ~2.3 days in one
regime, on recorded quotes. A directly measured caution: that window's `<1 bps` bucket differs from
the 252-day set by **15 percentage points**, and 39% of this model's fires sit in that bucket.
Verdict at **≥100 forward fires**, sign holding on both halves, `verify.py` returning True.
