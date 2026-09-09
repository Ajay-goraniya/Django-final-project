# v12 notes - live findings from the Build 11 (v11) run (started 2026-09-09 16:30 UTC)

Scope: what the v11 build (Polymarket signal, Predict.fun execution, 2% fee, EV scale 0.75, calibration off,
10-s signal hold, one-sided refusal) does live, versus the four v10 runs on the same candles. Live data only.
Old-version findings keep going to NOTES_v11.md.

## Baseline at launch (retro on 09-08 17:31 -> 09-09 16:22, 139 recorded fires)
- v10-as-run replay = live (+223 vs +225). v11 launch settings in-sample +422 on 163 trades (65%).
- Calibration table lost out of sample on both time splits -> shipped OFF. EV scale 0.75 held out of sample.

## Running log
### 16:30-18:00 UTC (first 90 min): 8/16, -5.0 at $10
- Same window: Predict.fun pnl v10 4/8 -7.3, Polymarket pnl v10 3/6 -7.6 -> v11 is not worse, it fires ~2x as often (16 of 17 candles vs 6-8) so the chop shows faster.
- The 8 fires that also pass the strict (x1.0) threshold: 3/8 -18; the 8 extra fires from x0.75: 5/8 +13.
- By confidence p<0.62 3/7, p>=0.62 5/9 (the losing streak 16:40-17:20 included p 0.73 and 0.63 fires). Timing: 13 of 16 fires inside 60 s (7/13), 60-180 s 1/3.
- Signal quality: every fire on the Polymarket signal; one-sided refusals only in the last 2 min of candles; 0 venue fallbacks; ~1 socket reconnect per candle (rotation) bridged by the 10-s hold. No errors, no relaunch.
- Verdict pending: needs 60-80 fires against the Polymarket v10 run before judging the v11 layer.

### 18:24 UTC (114 min): 9/20, -22.7 at $10
- Same window v10: Predict.fun pnl 4/10 -27.3, Polymarket pnl 3/9 -37.6, Predict.fun accuracy 15/21. v11 is losing less than either v10 pnl run on the same tape, with 2x the fires.
- Strict-threshold fires 3/9 -27.8 vs x0.75 extras 6/11 +5.1 (second check-in in a row the "extra" fires are the better half). p<0.62 4/9 -2.1, p>=0.62 5/11 -20.7. Timing <60 s 8/17, 60-180 s 1/3. Regime low 2/4, mid 4/10 -16, high 3/6.
- 18:05 and 18:15: all three (v11, both v10) fired UP and lost - same-signal losses, the model, not the layer. 18:00: v11 DOWN won where Polymarket v10 UP lost.
- Signal: polymarket 2011, held 37, one-sided 296, fallback 0; 27 reconnects bridged. No errors, no relaunch.
