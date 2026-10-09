# Is Raw's edge TIMING? And what does London execution actually cost?

Read-only. `analysis/zurich/timing_test.py` and `analysis/zurich/exec_cost_split.py`. No deploy, no
config change. Zurich stayed 13.1.2, master OFF, `decide_mode` poll, profile `raw_v10_live25`.

Raw arm: **339** graded EF fires, win rate 52.5%, fire second p50 **99**. Graded on
`results.actual` - the venues snapshot on the branch ends 09-16 and covers **0 of 339** of these
epochs, so no oracle cross-check exists here and none is claimed.

## 1. The control as specified does not measure timing. It has lookahead.

| arm (tape1s, px<=0.61, 1000 draws) | per$1 | p05 | p95 | p(>= own second) |
|---|---|---|---|---|
| Raw's side at Raw's **own** second (baseline) | **+0.0777** | - | - | - |
| Raw's side at a **random** second 15-240 s | +0.5035 | +0.3166 | +0.7241 | **1.000** |
| cheap side at a random second | +0.3535 | +0.1617 | +0.5692 | 0.995 |
| cheap side, random candle + random second | +0.1362 | -0.0857 | +0.3784 | 0.651 |
| coin-flip side, random candle + random second | +0.0981 | -0.1431 | +0.3933 | 0.519 |

A random second beats Raw's own second on 1000 of 1000 draws. That is not skill going the other way,
it is the control cheating: Raw names its side at a median second 99, and a draw at second 20 buys
**that side** at second 20's ask - a price from before the signal existed. Nobody at second 20 knew
which side Raw would name.

The mechanism is in the prices. A loss costs the stake whatever was paid, so only WINNER prices move
per$1, and the payout is `5/px`:

| | mean px at own second | mean px at a random second | shares per $5 |
|---|---|---|---|
| WINNERS (n 178) | 0.4591 | 0.3720 | 11.23 -> 17.62 |
| LOSERS (n 161) | 0.4468 | 0.2915 | 11.58 -> 32.01 |

Early in a candle the book has not converged, so a side that ends up winning is often cheap. Buying it
then requires knowing which side wins.

## 2. The implementable question is delay, and it answers the opposite way

Random second **at or after** Raw's own second: mean **-0.0873** vs Raw's +0.0777,
p(random >= own) = **0.023**. Paired candle by candle, no price cap so neither arm is censored:

| delay | n | own second | delayed | own better | sign-test p | half 1 | half 2 |
|---|---|---|---|---|---|---|---|
| +15 s | 323 | +0.0372 | -0.0231 | 192/315 (61%) | 6.0e-05 | +0.103 vs +0.023 | -0.050 vs -0.083 |
| +30 s | 321 | +0.0567 | -0.0263 | 219/314 (70%) | 1.0e-12 | +0.123 vs +0.003 | -0.029 vs -0.064 |
| +60 s | 306 | +0.0509 | -0.1640 | 228/303 (75%) | 2.1e-19 | +0.104 vs -0.104 | -0.016 vs -0.239 |
| +120 s | 279 | +0.0470 | -0.1209 | 197/275 (72%) | 2.4e-13 | +0.106 vs -0.106 | -0.039 vs -0.142 |

**Raw's moment beats every later moment, in both halves, monotone in the delay.** So there is timing
value, but it is "do not wait", not "it picks the moment". Against an EARLIER moment the arm cannot be
tested at all - the signal did not exist yet.

Caveat that cuts against this: the arm's own level is +0.135 in half 1 and -0.0005 in half 2 on
tape1s pricing, so **the arm is not both-halves profitable**; only the delay penalty is.

## Pricing: tape1s is not the fill price, and the two are never mixed

`tape1s` is a 1 Hz snapshot; the real fills are the executor's book read. At the fire second tape1s
sits **+0.050 (median), +0.082 (mean)** above the price actually filled, and it reads above the 0.61
cap on **50** candles Raw won **68%** of - so a cap applied to a tape-priced arm censors winners. Every
number above is tape-to-tape: the baseline is Raw's own second priced from tape1s too. The fill-price
figure (+0.2653/$1) is context only, and the paired tables use no cap at all.

## 3. Splitting RAW's London-execution loss, per $1

`exec_cost_split.py`, stake $10, 1000 Monte Carlo passes, 340 RAW fires.

| arm | fills | deployed | totPnL | per$1 |
|---|---|---|---|---|
| paper: fill all, no slippage | 340 | 3530 | +133.37 | +0.0378 |
| + symmetric fill 58.9% only | 200 | 2081 | +83.12 | +0.0400 |
| + London's asymmetric fill only | 203 | 2105 | -119.97 | -0.0570 |
| + slippage only, fill all | 340 | 3521 | -117.47 | -0.0334 |
| full London execution | 203 | 2099 | -261.07 | -0.1244 |

Attribution of the -0.1622/$1 fall:

| component | per$1 |
|---|---|
| fewer trades at random (symmetric fill) | **+0.0022** - capital, not edge |
| **missed fills on winners** (the 54.1% vs 65.0% asymmetry) | **-0.0970** |
| **slippage** alone, on every fire | **-0.0711** |
| interaction (slippage paid only on fills) | +0.0038 |

Missed fills on winners is the larger half; either component alone flips the arm negative. Random
subsampling costs nothing per $1, which is the check that the decomposition is sound - it should be
zero, and it is.

FIXED splits the same way: -0.0891 missed fills, -0.0711 slippage, from +0.0888 to -0.0663.

Total here is **-261.07** against the **-255.10** reported earlier for the same model: same fires, same
parameters, different Monte Carlo seed stream (2000+ here, 1000+ there). Within run-to-run noise, not a
changed result.
