# MAIN / REVERSAL new-EV test — Zurich window (09-23 → 09-27)

Read-only. No deploy, no config change. Zurich stayed 13.1.2, master OFF, `decide_mode` poll,
profile `raw_v10_live25`, stake 5.

Scripts: V's `analysis/v/model/lane_ev_replay.py` (324c704) and `analysis/v/model/lane_exec_sim.py`
(815c822), plus `analysis/zurich/lane_ev_pastonly.py` here, which is V's full grid re-run with
past-only pricing (V's 815c822 fixes the pricing but drops neg-days, +2c and the permutation).

## Inputs — all mine

| input | source | coverage |
|---|---|---|
| 1 s BTCUSDT klines | `data-api.binance.vision` `/api/v3/klines` | 353,623 rows, 09-22 22:00 → 09-27 00:13, **0 missing seconds** |
| Polymarket asks | my `tape1s.up_ask` / `dn_ask` | 276,865 rows; per 30 s block of the candle: 99/91/99/99/98/95/88/**69/36/10**% |
| label | `results.actual` | 634 graded epochs |

Klines start 09-22 22:00 to give the engine's 24-candle (2 h) warm-up before 09-23, so the call stream
begins 09-23. **Grading is `results.actual` only**: the venues snapshot on the branch ends 09-16 and
covers **0** of this window, so Polymarket's own oracle is unavailable here and no cross-check is claimed.

The quote-coverage collapse in the last 60 s of the candle matters and is stated up front: it is why
the 240-295 s window cannot be tested here (below).

## 1. The ±5 s nearest-row price was lookahead, and it created MAIN's whole edge

`lane_ev_replay.py`'s `quote()` takes the nearest tape row within ±5 s, which can be a **future** row.
Measured on my stream:

| lane | calls priced by the nearest-row rule | used a FUTURE row | of the calls **R1 selects**, future-priced |
|---|---|---|---|
| MAIN | 26,965 | 443 (**1.6%**) | **53 of 102 (52%)** |
| REVERSAL | 12,396 | 36 (**0.3%**) | 1 of 109 (1%) |

93% of rows land on the exact second, so contamination is rare in the raw stream — but R1 fires when
the ask is low enough for the lane's `p` to clear breakeven, so it **selects for exactly the rows the
defect perturbs**. A 1.6% data problem becomes 52% of the trades.

What that does to MAIN R1:

| pricing | n | hit | per$1 | H1 / H2 | neg days | perm p |
|---|---|---|---|---|---|---|
| nearest ±5 s (lookahead) | 102 | 75.5% | **+0.335** | +0.356 / +0.313 | 0/4 | 0.00 |
| past-only, same second | 49* | 49.0% | **−0.221** | −0.181 / −0.260 | 4/4 | 0.92 |

Hit rate 75.5% → 49.0%. The edge was the future price, not the signal.

REVERSAL barely moves (1 future-priced fire in 109), so my window does **not** reproduce V's window-1
REV collapse from +0.63 to +0.065. Here REV was never inflated by lookahead; its problem is different
(below). Ages 0, 1 and 2 s are within noise of each other on my data.

## 2. Full grid, past-only (age ≤ 0 s; age ≤ 1 s differs only in the last decimal)

`*` = n < 60, not a reading.

### MAIN — 25,150 calls on 428 candles, 4 day buckets

| rule | n | hit | ask | per$1 | H1 | H2 | neg days | +2c | perm p |
|---|---|---|---|---|---|---|---|---|---|
| R0 first call, ask≤0.90 | 354 | 67.8% | 0.78 | **−0.140** | −0.162 | −0.119 | **4/4** | −0.161 | 1.00 |
| R1 lane-p breakeven (live) | 49* | 49.0% | 0.59 | **−0.221** | −0.181 | −0.260 | **4/4** | −0.245 | 0.92 |
| R2 calibrated ev≥0.00 | 14* | 78.6% | 0.78 | +0.146 | −0.218 | +0.510 | 0/1 | +0.112 | 0.39 |
| R2 ev≥0.03 | 4* | 100.0% | 0.66 | +0.493 | +0.432 | +0.554 | 0/1 | +0.450 | 0.04 |
| R2 ev≥0.05 | 3* | 100.0% | 0.59 | +0.585 | +0.648 | +0.554 | 0/1 | +0.536 | 0.11 |
| R2 ev≥0.10 | 1* | 100.0% | 0.51 | +0.896 | n/a | +0.896 | 0/1 | +0.827 | 0.49 |
| R2 ev≥0.15 | none | | | | | | | | |
| R3 venue-only ev≥0.00 | 11* | 72.7% | 0.81 | −0.021 | −0.521 | +0.395 | 1/1 | −0.047 | 0.60 |
| R3 ev≥0.03 | 6* | 66.7% | 0.68 | −0.021 | −0.594 | +0.551 | 1/1 | −0.049 | 0.56 |
| R3 ev≥0.05 | 2* | 100.0% | 0.59 | +0.655 | +0.547 | +0.763 | 0/1 | +0.602 | 0.27 |
| R3 ev≥0.10, ≥0.15 | none | | | | | | | | |
| R0 on the same walk-forward days | 100 | 73.0% | 0.79 | −0.062 | −0.097 | −0.027 | 1/1 | −0.086 | 0.77 |

### REVERSAL — 11,572 calls on 148 candles, 4 day buckets

| rule | n | hit | ask | per$1 | H1 | H2 | neg days | +2c | perm p |
|---|---|---|---|---|---|---|---|---|---|
| R0 first call, ask≤0.90 | 137 | 75.2% | 0.69 | **+0.071** | +0.159 | **−0.015** | 1/4 | +0.042 | 0.03 |
| R1 lane-p breakeven (live) | 109 | 73.4% | 0.65 | **+0.081** | +0.178 | **−0.014** | 1/4 | +0.050 | 0.01 |
| R2 calibrated ev≥0.00 | 28* | 85.7% | 0.76 | +0.111 | +0.110 | +0.111 | 0/1 | +0.083 | 0.18 |
| R2 ev≥0.03 | 28* | 85.7% | 0.78 | +0.088 | +0.092 | +0.085 | 0/1 | +0.062 | 0.18 |
| R2 ev≥0.05 | 23* | 87.0% | 0.78 | +0.097 | +0.154 | +0.045 | 0/1 | +0.071 | 0.27 |
| R2 ev≥0.10, ≥0.15 | none | | | | | | | | |
| R3 venue-only ev≥0.00 | 28* | 85.7% | 0.76 | +0.109 | +0.110 | +0.108 | 0/1 | +0.082 | 0.19 |
| R3 ev≥0.03 | 28* | 85.7% | 0.78 | +0.083 | +0.092 | +0.075 | 0/1 | +0.057 | 0.19 |
| R3 ev≥0.05 | 23* | 87.0% | 0.78 | +0.089 | +0.151 | +0.033 | 0/1 | +0.064 | 0.23 |
| R3 ev≥0.10, ≥0.15 | none | | | | | | | | |
| R0 on the same walk-forward days | 32* | 75.0% | 0.75 | +0.011 | −0.020 | +0.042 | 0/1 | −0.015 | 0.28 |

**The walk-forward is not testable on this window.** R2/R3 need >3 prior days; 09-23→09-27 gives 4 day
buckets, so exactly **one** day is scored. Every R2/R3 cell is n<60 and sits on a single day — the
MAIN cells at n=1..4 with "hit 100%" are noise, not results, and the `neg days 0/1` column is one day.
Nothing in R2/R3 here is a reading. Where R2 and R3 both have cells, **R2 ≈ R3** (REV: +0.111 vs +0.109,
+0.088 vs +0.083, +0.097 vs +0.089), i.e. **the lane's own `p` adds nothing over ask + second**, which
is the same conclusion as V's window 1.

## 3. Under London execution (`lane_exec_sim.py`, past-only, $10 stake, 1000 runs)

| lane / window / rule | n | paper per$1 | LONDON-EXEC per$1 | total $ | p05 / p95 |
|---|---|---|---|---|---|
| MAIN 0-240 s R0 | 352 | −0.142 | **−0.228** | **−469.5** | −560.8 / −379.4 |
| MAIN 0-240 s R1 | 49* | −0.221 | **−0.329** | −99.0 | −142.9 / −53.1 |
| MAIN 240-295 s R0 | **5*** | −0.060 | −0.131 | −3.7 | −9.8 / +4.7 |
| REV 0-240 s R0 | 122 | +0.082 | **−0.021** | −15.1 | −67.2 / +43.7 |
| REV 0-240 s R1 | 97 | +0.096 | **−0.012** | −6.8 | −58.1 / +45.1 |
| REV 240-295 s R0 | 47* | +0.143 | +0.025 | +6.9 | −49.9 / +71.9 |
| REV 240-295 s R1 | 26* | +0.210 | +0.030 | +4.7 | −48.6 / +71.4 |
| REV all R1 | 109 | +0.081 | **−0.023** | −14.7 | −72.6 / +40.7 |

**The owner's "after 240 s" question cannot be answered on this window.** MAIN's 240-295 s cell has
**n=5** past-only, because my tape only carries a quote for 36% of seconds 240-269 and 10% of 270-299.
That is a data-coverage limit on my box, not evidence either way. The REV 240-295 s cells (n 47 / 26)
are also under 60 and their H2 is negative (−0.076 / −0.130), so they are H1-only.

Caveat carried from V's model file: the execution model is fitted on EF fills at asks 0.35-0.55, while
MAIN buys at a median ask of 0.78 — so the fill and slippage rates applied to MAIN are extrapolation.

## Verdict for this window

1. **MAIN does not pay under any of the four rules.** R0 −0.140/$1 with **4/4 negative days** and
   perm p 1.00; R1 −0.221 with 4/4 negative days. Under London execution R0 is −0.228/$1 (−$469).
2. **MAIN R1's apparent +0.335 was lookahead** — 52% of its fires were priced from a future tape row.
   Retract any reading of that number.
3. **REVERSAL is positive on paper (+0.071/+0.081) and negative under execution (−0.029/−0.023)**, and
   its H2 is negative on both rules. Not a finding.
4. **Calibrated EV does not beat its own venue-only null**, and on this window it cannot be tested
   properly at all: one scored day, every cell under 60.
5. Ages 0/1/2 s agree here, so on Zurich data the quote-age choice matters only through *which calls a
   rule selects* — and for MAIN R1 that was decisive.
