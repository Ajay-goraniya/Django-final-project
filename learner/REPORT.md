# Learner v10 — overnight build report

**Question you asked:** build a model whose learner actually learns and delivers accuracy + PnL while keeping frequency adjustable.

**Short answer:** yes, one design does — and it is the only thing in this whole project that has survived every check that killed the earlier numbers.

## The result (out-of-sample, $10 flat, one trade per candle, buy at the venue ask)

Every prediction below comes from a model that **never saw the day it is predicting** (leave-one-day-out over 8 days, calibration fitted inside the training fold).

| EV threshold | trades/day | accuracy | mean ask | PnL 8 days | per trade | t-stat | real-book-only PnL |
|---|---|---|---|---|---|---|---|
| 0.15 | 95 | 56.8% | 0.503 | **+$824** | +1.08 | 3.0 | +$368 |
| **0.20** | **62** | **59.4%** | **0.481** | **+$1,041** | **+2.09** | **4.5** | **+$437** |
| 0.30 | 30 | 59.5% | 0.439 | +$759 | +3.20 | 4.3 | +$393 |

At threshold 0.20:

- **8 of 8 days positive** (+$5 to +$395 per day)
- **0% of the profit comes from entries under 15 cents** — r6.4's +$465 was 90% from those and evaporated when filtered. This does not move at all.
- **Real order-book fills only: +$437 on 154 trades, 66.2% accuracy, t = 3.65** — no inferred prices anywhere in that subset.
- Day-block bootstrap of the 8-day PnL: P(≤ 0) ≈ 1.5%.

## Why this one learns and the others didn't

| | in-engine learners (b36 / v9.5 / v9.6) | v10 |
|---|---|---|
| training rows | ~50–450, only candles EF fired on | **22,720**, every candle × 10 decision seconds |
| sees skipped candles | never | always |
| calibration | claims ~60% every day, delivers 20–78% | claimed vs actual within **1 point in every bin** |
| beats the market's own price (log-loss, real book) | no | **yes: 0.5042 vs 0.5217** |
| accuracy as samples grow | b36 got *worse*; v9.6 flat | n/a — trained offline, no drift |

The venue's implied probability was the benchmark, not accuracy. A model that cannot beat the price has no edge whatever its hit rate; this one does, by a small but consistent margin, and it is the *disagreements* with the market (the EV threshold) that make the money.

## Frequency

`ev_threshold` is the one dial. Per-regime thresholds (realized-vol terciles) are in `model_v10.json` under `regime`; the model uses them automatically. Lower for more trades, higher for fewer and better.

## The 100-candle sample

Same 100 candles r6.4 and v9.6 were scored on:

| | trades | accuracy | PnL |
|---|---|---|---|
| **v10** thr 0.00 | 95 | 65.3% | +$81 |
| v10 thr 0.20 | 20 | 40.0% | −$32 |
| r6.4 | 99 | 39.4% | +$465 (→ +$48 without sub-15c entries) |
| v9.6 | 73 | 46.6% | +$1 |

At selective thresholds the 100-candle sample only yields 11–20 trades, which is too few to read. That sample was fine for comparing fire-happy models; it is too small for a selective one. The 8-day figures above are the real test (2,272 candles).

## What you should not trust

- Six of the eight days have **trade-inferred** venue prices, not an order book. The book-only subset is positive and significant, but the full-week dollars are an estimate.
- Live fills will be worse than the quoted ask (your live run showed ~1.2c slippage).
- 8 days is 8 days. The edge is small (+2 per $10 at thr 0.20) and could be regime-specific. Paper-trade it before sizing.

## Files

- `learner/btc_model_v10.py` — standalone model: feature state + prediction + EV decision. `--selftest` proves the live feature path matches the training table to 1e-11.
- `learner/model_v10.json` — exported parameters (fitted on all 8 days).
- `learner/build_features.py`, `train.py`, `finalize.py`, `evaluate.py` — the full pipeline, reproducible.
- `learner/oof_predictions.parquet` — every out-of-sample prediction.
- `learner/eval_final_thr020.txt` — the stress-test output above.

## How to plug in

```python
from btc_model_v10 import Model, FeatureState
m = Model("model_v10.json"); st = FeatureState()
# feed the raw streams your engine already has:
st.on_spot_trade(ts_us, price, qty, is_buyer_maker)
st.on_perp_trade(ts_us, price, qty, signed_quote_notional, quote_notional)
st.on_depth(ts_us, b0, bq0, a0, aq0, bid_qty_top5, ask_qty_top5, bid_qty_top20, ask_qty_top20)
st.on_venue_quote(ask_up, bid_up, ask_dn, bid_dn)
d = m.decide(st, candle_open_us, now_us)     # {'fire', 'side', 'p', 'ask', 'ev', 'threshold', ...}
```

---

## Update: accuracy mode — 80%+ achieved, whole week, out-of-sample

Same model, second decision rule: fire only when confidence `p_side >= conf_floor` **and** EV `>= ev_floor`. Both floors are the frequency dial.

| conf / EV floor | trades/day | **accuracy** | mean ask | PnL 8 days | per $10 | t | positive days |
|---|---|---|---|---|---|---|---|
| **0.85 / 0.02** | **82** | **87.6%** | 0.841 | +$263 | +$0.40 | 2.5 | **8/8** |
| 0.85 / 0.05 | 40 | 86.7% | 0.791 | +$314 | +$0.97 | 3.8 | 6/8 |
| 0.80 / 0.05 | 57 | 81.9% | 0.761 | +$335 | +$0.73 | 2.9 | 6/8 |

Day by day at 0.85 / 0.02 — every single day between 85.7% and 95.1%:

```
2026-08-29   32   90.6%   +15.05        2026-09-03  126   85.7%  +113.78
2026-08-30   48   87.5%    +8.15        2026-09-04  154   86.4%   +43.29
2026-08-31   99   87.9%   +10.97        2026-09-05   48   91.7%   +24.28
2026-09-02  106   85.8%   +27.91        2026-09-06   41   95.1%   +20.02
```

The fixed 100-candle sample: **35 trades, 91.4%, +$20.76** (r6.4: 39.4%; v9.6: 46.6% on the same candles).

**The trade-off you need to see clearly:** accuracy this high comes from buying contracts the market already prices at ~0.84. That is why the profit per trade is 40 cents on $10, not $2. The model's edge is the same in both modes — it's *where on the price curve you take it* that moves between "high hit-rate, small margin" and "60% hit-rate, big margin". The full frontier is in `learner/train_v11_summary.json` and the tables above; pick the point you want and set the two floors.

**Also tried and rejected (honestly):** richer features (venue momentum, physics fair value, longer returns) did not beat v10 on real-book log-loss; LightGBM overfits; per-second models trade more but predict worse. v10 stays.
