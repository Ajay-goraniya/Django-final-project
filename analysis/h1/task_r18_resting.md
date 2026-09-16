# R-18 — resting limit orders. The idea dies, and the stop condition V set is the one that fires.

V's brief set the test and the kill switch: *"if pnl/$1 at k≥1 is not positive after adverse
selection, say so and the idea dies."* It is not positive. It is not positive in **any** of the 25
cells. Script `analysis/h1/task_r18_resting.py`, full grid `/tmp/claude-0/r18.log`.

Data: 492 fires with a live 1 s Polymarket book tape (`polybook`, `status='live websocket'`), 5 days
(09-11 127, 09-12 14, 09-13 117, 09-14 146, 09-15 88). Graded on `venues.outcome`.
Fill model: a buy limit at `cap = ask − k·0.01` rests from the fire second and fills **at cap** the
first second the best ask on our side trades to `cap` or below, within the TTL.

**Baseline — what we send today (FAK taker at the touch): n=492, win 54.3%, +0.164/$1, +80.47.**

## The grid — every cell, never the best one

| k | TTL=15 | 30 | 60 | 120 | 299 |
|---|---|---|---|---|---|
| **1** | −0.139 (222) | −0.148 (275) | −0.136 (320) | −0.109 (361) | −0.118 (378) |
| **2** | −0.151 (188) | −0.153 (246) | −0.140 (299) | −0.123 (344) | −0.136 (368) |
| **3** | −0.174 (162) | −0.182 (230) | −0.145 (286) | −0.136 (333) | −0.142 (361) |
| **4** | −0.208 (142) | −0.212 (211) | −0.187 (269) | −0.148 (317) | −0.158 (351) |
| **5** | −0.185 (129) | −0.190 (195) | −0.196 (258) | −0.146 (308) | −0.163 (345) |

per $1 (fills). Every cell has ≥ 60 fills, so every cell is readable — and all 25 are negative against
a taker baseline of **+0.164**. Fill rates are healthy (45–77% at k=1), so this is not a
"never fills" result. The orders fill. They fill badly.

## Why, decomposed

| k | TTL | fills | win% resting | win% all signals | **selection** | price gain | **net** |
|---|---|---|---|---|---|---|---|
| 1 | 299 | 378 | 40.7% | 54.3% | **−0.135** | +0.019 | **−0.281** |
| 2 | 299 | 368 | 39.1% | 54.3% | **−0.151** | +0.038 | **−0.299** |
| 3 | 299 | 361 | 38.0% | 54.3% | **−0.163** | +0.056 | **−0.305** |
| 4 | 299 | 351 | 36.2% | 54.3% | **−0.181** | +0.074 | **−0.322** |
| 5 | 299 | 345 | 35.1% | 54.3% | **−0.192** | +0.092 | **−0.326** |

Resting one tick lower is worth **+0.019/$1** in price. The orders that fill win **40.7%** instead of
**54.3%**. **Adverse selection costs seven times what the better price earns**, and the ratio gets
worse with k, because a deeper limit only fills when the market has moved further against the side we
picked. Going deeper buys a bigger discount on a worse book of trades.

Rain or sun — resting loses to the taker on every readable day:

| arm | 09-11 | 09-13 | 09-14 | 09-15 |
|---|---|---|---|---|
| taker k=0 | −0.021 | +0.131 | +0.292 | +0.298 |
| rest k=1 | −0.239 | −0.311 | −0.026 | +0.165 |
| rest k=2 | −0.252 | −0.351 | −0.040 | +0.153 |
| rest k=3 | −0.250 | −0.337 | −0.084 | +0.173 |

(09-12 has 14 fires — insufficient, not read.)

verify.py on k=1/TTL=299 vs the taker: **NOT A FINDING** — halves −0.325 / −0.244 (consistently bad,
not noisy), and it loses the null by $125 (−44.45 vs +80.47).

## A fake pass I built and caught

My first adverse-selection table compared the filled orders' win rate against **those same orders**
taken at the touch. Identical row set, so the gap was **+0.000 in all 25 cells** — it agreed by
construction and proved nothing. Selection is a claim about *which* signals fill, so the comparison
has to be against **all** signals. Recorded here rather than quietly fixed, because this is the exact
failure the standing rule names and I walked into it anyway.

## What this closes, and what it means for R-14

**R-14's +65% counterfactual is refuted as a trading idea.** R-14 observed that rejected orders —
those whose cap sat under the ask — went on to win 65% against 51% for the fills. I flagged it then
as unreadable (n=26, halves +0.566/−0.226). R-18 explains it: those were orders that *did not fill*.
Conditioning on "did not fill" selects candles where the ask never came down, i.e. where our side was
strengthening — of course they won. The ones that **do** fill are the mirror image, and that is the
half you actually own. The 65% was survivorship, seen from the wrong side.

**No fill model, no paper lane.** V's brief gated those on k≥1 being positive; it is not, so they are
not built. The FAK taker at the touch is, on this evidence, the correct execution.

**Where this leaves the goal.** PnL-first with adaptive frequency now has both obvious routes closed:
the direction forecast equals the book (R-13, five independent confirmations) and paying less than
the touch costs more than it saves (here). What is left is not "a better model" or "a better price"
but *which candles to be in at all* — and that is a frequency question, which this session has not
tested, because every previous attempt at it was a gate on a weak score. A frequency rule learned as
part of the fit, not bolted on, is the one untried direction.
