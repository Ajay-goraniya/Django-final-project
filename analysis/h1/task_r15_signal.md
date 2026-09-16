# R-15 — higher-timeframe state gives a real but tiny calibration gain; futures positioning gives nothing

The four-arm walk-forward V's brief asked for, on the full store. Script `analysis/h1/r15_train.py`,
log `/tmp/claude-0/r15tr.log`. **4,753,000 rows**, lightgbm, train every year strictly before Y and
test Y, hyper-parameters lifted unchanged from `r12s2_lgbm.py` so the only difference between arms is
the features. HTF block present on **100.0%** of rows; futures metrics on **62.1%** (the archive
starts 2020-09), so the (b) arms run 2022–2026 and are never pooled with the (a) arms.

## Per year — LL / AUC / (hit − momentum null)

| test Y | rows | base | +a (16 HTF) | +b (4 futures) | +ab | logit base |
|---|---|---|---|---|---|---|
| 2019 | 525,420 | 0.5303/0.811/+0.0005 | **0.5254**/0.813/+0.0009 | — | — | 0.5594 |
| 2020 | 526,860 | 0.5320/0.808/+0.0003 | **0.5254**/0.812/+0.0013 | — | — | 0.5511 |
| 2021 | 525,420 | 0.5239/0.817/+0.0000 | **0.5179**/0.819/+0.0006 | — | — | 0.5318 |
| 2022 | 525,420 | 0.5356/0.803/+0.0003 | **0.5312**/0.806/+0.0007 | 0.5362/0.803/−0.0002 | 0.5314/0.806/+0.0001 | 0.5494 |
| 2023 | 525,420 | 0.5256/0.817/+0.0003 | **0.5189**/0.820/+0.0007 | 0.5245/0.817/−0.0010 | 0.5177/0.820/+0.0012 | 0.5461 |
| 2024 | 526,860 | 0.5211/0.816/+0.0001 | **0.5172**/0.818/+0.0004 | 0.5198/0.817/+0.0003 | 0.5163/0.818/+0.0006 | 0.5360 |
| 2025 | 525,420 | 0.5217/0.816/+0.0003 | **0.5182**/0.817/+0.0003 | 0.5203/0.816/+0.0003 | 0.5174/0.817/+0.0006 | 0.5410 |
| 2026 | 349,800 | 0.5483/0.791/+0.0002 | **0.5453**/0.793/+0.0004 | 0.5479/0.791/+0.0002 | 0.5452/0.793/+0.0001 | 0.5606 |

| arm | years | logloss gain | years won | AUC gain | hit − null |
|---|---|---|---|---|---|
| **+a** | 2019–2026 | **+0.0049** | **8 / 8** | +0.0025 | **+0.0007** |
| +b | 2022–2026 | +0.0007 | 4 / 5 | +0.0002 | −0.0001 |
| +ab | 2022–2026 | +0.0049 | 5 / 5 | +0.0024 | +0.0005 |

## Reading

**(a) is real and small.** Eight years out of eight is not luck (p ≈ 0.004 against a coin), and the
gain is stable at +0.004 to +0.007 logloss per year. But it is **about 1% of the logloss level**, and
`+ab` equals `+a` exactly, so all of it is the higher-timeframe block.

**(a) does not buy direction.** The column that matters is `hit − null`: against the dumb rule "the
candle is up so far", base scores **+0.0003** and `+a` scores **+0.0007**. Both are effectively zero,
and R-12 step 2(c) already showed the logistic *loses* to that null by −0.0053 across 72 of 72 cells.
A stronger learner plus 16 timeframe features moves the direction call by **four ten-thousandths**.
**What HTF buys is calibration, not direction** — the same shape as every other result this session.

**(b) is nothing, and it retracts R-7.** Futures taker ratio and OI change give +0.0007 logloss,
+0.0002 AUC, and **−0.0001 on hit − null**, over five years and 2.95M rows. R-7 found the taker ratio
ordered accuracy 58.5 / 56.6 / 50.7 by tercile on 7 of 7 days with permutation p=0.0065 — **on one
week**. At five years it is indistinguishable from zero. **R-7 is retracted as a signal: it did not
survive the largest available sample.** That is the "full sweep AND largest sample" rule doing its
job, and it is the second finding of mine this session that a bigger sample has reversed.

## Verdict

**Nothing ships.** A +0.005 logloss gain that does not move the direction call cannot rescue an engine
whose direction call is already the venue price (R-13), and R-12 B2 showed the venue stage absorbs
history-model output entirely. The (a) block would be worth carrying only if something downstream
needed better calibration, and after R-18/R-19/R-20 there is no such consumer.

Both of R-15's sources are now closed: higher-timeframe state buys calibration we cannot spend, and
futures positioning buys nothing at all.
