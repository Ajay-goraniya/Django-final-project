# Frozen window-1 calibrated-venue filter for REVERSAL — out of sample on window 2

Read-only. No deploy, no config change. Zurich stayed 13.1.2, master OFF, `decide_mode` poll, profile
`raw_v10_live25`, stake 5. Script: `analysis/zurich/rev_frozen_oos.py`.

Nothing was fitted. The coefficients are V's window-1 fit, hard-coded:
`p = sigmoid(0.4951 + 0.8907·logit(ask) − 0.5533·sec/300)`. Rule fixed before the run: window-2 REV
call stream, 0-240 s, past-only **age-0** quote, ask ≤ 0.90, first call per candle with
`p/(ask·(1+0.07(1−ask))) − 1 ≥ θ`; **θ = 0.03 is the decision**, the rest is context.

Sample: **7,099 calls on 122 candles.** The frozen p on this window runs p05 0.592 / p50 0.757 /
p95 0.876 and clears θ=0.03 on 22.9% of calls. Grading `results.actual` — the venues snapshot ends
09-16 and covers none of this window.

## The cell, and the sweep as context

| rule | n | hit | ask | paper per$1 | H1 | H2 | LONDON-EXEC | total $ | p05 / p95 | perm p |
|---|---|---|---|---|---|---|---|---|---|---|
| frozen ev≥0.00 | 82 | 68.3% | 0.64 | +0.038 | +0.106 | −0.031 | **−0.071** | −34.5 | −87.6 / +16.1 | 0.13 |
| **frozen ev≥0.03 — THE RULE** | **53*** | **66.0%** | 0.60 | **+0.062** | +0.209 | **−0.080** | **−0.060** | −18.9 | −61.7 / +23.4 | **0.12** |
| frozen ev≥0.05 | 43* | 62.8% | 0.59 | +0.058 | +0.254 | −0.128 | −0.068 | −17.5 | −61.1 / +26.6 | 0.23 |
| frozen ev≥0.10 | 8* | 12.5% | 0.54 | −0.787 | −0.574 | −1.000 | −0.825 | −43.8 | −64.6 / −23.3 | 1.00 |

`*` = n<60, not a reading — **including the decision cell at n=53.**

The sweep is not monotone: +0.038 → **+0.062** → +0.058 → −0.787. It peaks at the frozen value and then
collapses. θ=0.03 was frozen on window 1, not picked here, so this is not selection on window 2 — but a
sweep shaped like that carries no stable relationship, and the θ=0.10 cell (n 8, hit **12.5%**) is the
frozen model's most confident picks being wrong 7 times in 8.

## Paired against plain REV R1 on the same candles

| θ | rule | candles | R1 fires | **discordant** | rule paper | R1 paper | rule LON | R1 LON |
|---|---|---|---|---|---|---|---|---|
| 0.00 | n82 | 82 | 75 | 35 | +0.038 | +0.044 | −0.071 | −0.071 |
| **0.03** | n53 | 53 | 52 | **20** | **+0.062** | +0.031 | **−0.060** | −0.090 |
| 0.05 | n43 | 43 | 43 | 20 | +0.058 | −0.002 | −0.068 | −0.119 |
| 0.10 | n8 | 8 | 8 | 6 | −0.787 | −0.794 | −0.825 | −0.830 |

At θ=0.03 the filter's +0.031 paper advantage over R1 rests on **20 discordant candles** — the other 32
are the same trade at the same second. At θ=0.00 it is actually *behind* R1 (+0.038 vs +0.044). Under
execution both are negative at every θ.

## What did transfer: the probability, not the edge

| | n | mean predicted p | actual win | gap |
|---|---|---|---|---|
| every call | 7,099 | 0.754 | 0.794 | −4.1 pp |
| first call per candle | 122 | 0.713 | 0.754 | −4.1 pp |
| cell ev≥0.00 | 82 | 0.683 | 0.683 | **0.0 pp** |
| cell ev≥0.03 | 53 | 0.660 | 0.660 | **−0.0 pp** |
| cell ev≥0.05 | 43 | 0.645 | 0.628 | +1.7 pp |

**On the cells it actually trades the frozen model is calibrated to within 0.1 pp on a window it never
saw.** That is a real result and worth keeping: the venue ask is a well-calibrated probability, and a
window-1 logistic on it stays calibrated on window 2.

It still does not make money, and the reason is not calibration error. A rule that is right 66.0% of the
time at a mean ask of 0.660 is sitting exactly on break-even before costs; the +0.03 of modelled EV is
then less than what London execution takes out (winners fill 54.1% against losers' 65.0%, plus
slippage), which is why paper +0.062 becomes **−0.060/$1**.

Discrimination, candle level (n 122): frozen p **AUC 0.577**, raw ask **0.613**, lane p 0.534. The
frozen model is a monotone transform of the ask at fixed `sec`, so the only thing the window-1 fit
contributed is the `−0.5533·sec/300` term — and it **lowers** ranking power below the raw ask.

## Verdict

- **Not a finding.** The decision cell is n=53 (<60), H2 is negative (−0.080), perm p is 0.12, and
  London execution turns it negative (−0.060/$1, p05 −61.7).
- The lead is **closed on the trading question**: the filter does not beat plain R1 on anything but 20
  discordant candles, and loses executed at every θ.
- The lead is **positive on one narrower question**: the window-1 calibration transferred almost exactly
  out of sample. That says the venue ask is trustworthy as a probability — not that a rule built on it
  clears costs.
- The `sec` term is the only new thing in the model and it makes ranking worse (0.577 vs 0.613). If
  anything is worth carrying forward it is the ask alone, which is not a new model.
