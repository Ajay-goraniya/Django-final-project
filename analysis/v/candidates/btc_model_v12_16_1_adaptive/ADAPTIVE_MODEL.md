# v12.16.1 adaptive EF candidate

## What changed

The frozen `model_v10.json` remains in the package unchanged as the benchmark.
The runtime default is now `model_v10_adaptive.json`, which contains the same
trained coefficients/scaler/isotonic calibrator plus a causal volatility-trust
overlay. No coefficient was retrained.

The shared `adaptive_state.py` measures robust one-second realized volatility on
a 3-minute fast window against a 1-hour slow window. It is continuous; there are
no LOW/MID/HIGH labels in the probability adjustment.

When the engaged fast/slow ratio is <= 1, EF is exactly frozen v10. When fast
volatility accelerates above slow volatility, only v10's log-odds deviation from
the Polymarket consensus is reduced:

    z_final = z_venue + (1 / adapt_ratio) * (z_v10 - z_venue)

Examples: ratio 1.0 -> 100% v10 correction; ratio 2.0 -> 50%; ratio 6.0 ->
16.7%. Quiet tape never amplifies v10 beyond the trained probability.

This changes probability/EV, not stake. It does not react to recent wins/losses,
does not add a PnL kill, and does not introduce a new on/off regime gate.

## 12.16.0 fixes included

* EF and MAIN/REVERSAL now share the same volatility-transition state.
* A >5 s spot gap resets the fast segment and cannot immediately re-engage from
  pre-gap returns (the 12.16.0 reset-overwritten-by-refresh bug).
* MAIN/REVERSAL seed the slow-vol prior from closed 5-minute OHLC history, so a
  restart needs ~60 s of fresh fast data rather than ~10 minutes to adapt.
* Diagnostics expose adaptive ratio, raw ratio, fast/slow volatility and trust.
* `python test_lanes.py` now actually defines/runs the adaptive tests because the
  `unittest.main()` block was moved to the end.

## Validation status

This archive does not contain the historical tick/book datasets required to
make an honest performance claim. Therefore v12.16.1 is a paper candidate, not
a claim that drawdown/profitability is fixed.

Acceptance should compare `model_v10_adaptive.json` against frozen
`model_v10.json` on identical forward/replay candles using outcome log loss,
Brier score, calibration, PnL after fees/slippage, and worst volatility-
transition slices. The live journal already logs `p_base`, `p`, `adaptive_ratio`
and `adaptive_trust`, so the delta is directly auditable.
