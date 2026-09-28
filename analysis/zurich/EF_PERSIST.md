# Does waiting for the ask dip to persist fix the fills? No — and the reason is the real finding

Read-only, Zurich `decide_log`, gamma-graded, 5 days (09-24..09-28), 1,015 candles, 785,924 passes.
`analysis/zurich/ef_persist.py`. Nothing live.

**Headline: persistence trades edge for fill rate and loses. Waiting to K=4 lifts the fill rate from 42% to
84% and takes raw25 from +0.071 to −0.064/$1. The reason is that THE FILL IS ADVERSELY SELECTED BY 10–29 pp
— we get filled on the trades that were going to lose.**

## (1) The fill simulator, and it does NOT validate

A FAK at ask+1 tick fills iff our side's ask on the first same-candle row at ≥ t+250 ms is ≤ ask_t + 0.01,
at that later ask. Achieved lag p50 **257 ms**, available on 784,909 of 785,924 passes.

| | simulated first-attempt fill | London REAL |
|---|---|---|
| raw25 first qualifying pass (n325) | **42.2%** | **31%** |
| fixed15 first qualifying pass (n195) | 42.1% | — |

**11.2 pp optimistic.** Every fill% and total-$ figure below is therefore optimistic by roughly a third, and
I am not going to pretend otherwise. The likely causes are that the simulator ignores size (it fills any
depth) and ignores the sub-250 ms cancellation that `ASK_LIFETIME_MS.md` measured at a 10 ms median share
life. Directional comparisons between K values are still valid — they share the same bias.

## (2) Persistence — full sweep, both profiles

raw25:

| arm | fires | fills | fill% | win% of fills | **per$1** | total $ | H1 | H2 | perm p |
|---|---|---|---|---|---|---|---|---|---|
| **K=1** | 325 | 137 | 42.2% | 43.8% | **+0.071** | +96.3 | +0.213 | −0.069 | 0.202 |
| K=2 | 224 | 151 | 67.4% | 37.1% | **−0.137** | −207.1 | −0.092 | −0.180 | 0.880 |
| K=3 | 181 | 137 | 75.7% | 41.6% | −0.052 | −72.0 | −0.042 | −0.063 | 0.566 |
| K=4 | 151 | 127 | **84.1%** | 41.7% | −0.064 | −81.0 | +0.003 | −0.129 | 0.626 |

fixed15:

| arm | fires | fills | fill% | win% of fills | **per$1** | total $ | H1 | H2 | perm p |
|---|---|---|---|---|---|---|---|---|---|
| **K=1** | 195 | 82 | 42.1% | 43.9% | **+0.061** | +47.8 | +0.190 | −0.068 | 0.458 |
| K=2 | 123 | 75 | 61.0% | 41.3% | −0.078 | −58.9 | −0.025 | −0.129 | 0.704 |
| K=3 | 103 | 82 | 79.6% | 47.6% | −0.016 | −13.2 | −0.003 | −0.030 | 0.392 |
| K=4 | 89 | 71 | 79.8% | 49.3% | +0.009 | +7.2 | +0.178 | −0.155 | 0.302 |

**Paired on the candles filled in BOTH** (the only ones carrying information — and every pair is at a
different pass, so all of them are discordant):

| | raw25 | fixed15 |
|---|---|---|
| K=2 vs K=1 | 91 candles: K=1 −0.081, K=2 −0.095 | 45*: K=1 −0.159, K=2 −0.115 |
| K=3 vs K=1 | 81 candles: K=1 **+0.024**, K=3 −0.059 | 45*: K=1 −0.137, K=3 −0.119 |
| K=4 vs K=1 | 69 candles: K=1 **−0.009**, K=4 −0.083 | 34*: K=1 −0.256, K=4 −0.214 |

On raw25 — the only profile with n≥60 pairs — **K=1 beats K=3 and K=4 on the shared candles.** Waiting is
worse where it can be compared directly.

Per day, K=1 is positive on 09-24 and 09-25 and negative on 09-26, 09-27, 09-28 for both profiles, so even
the best arm is 2 of 5 days.

## THE FINDING: the fill is adversely selected

| | fires win% | **FILLED win%** | **NOT filled win%** | selection |
|---|---|---|---|---|
| raw25 K=1 | 50.2% (n325) | **43.8%** (n137) | **54.8%** (n188) | **−11.0 pp** |
| raw25 K=2 | 46.4% | 37.1% (n151) | 65.8% (n73) | **−28.7 pp** |
| raw25 K=4 | 44.4% | 41.7% (n127) | 58.3% (n24) | −16.6 pp |
| fixed15 K=1 | 49.7% (n195) | 43.9% (n82) | 54.0% (n113) | −10.1 pp |
| fixed15 K=2 | 51.2% | 41.3% (n75) | 66.7% (n48) | −25.3 pp |
| fixed15 K=4 | 50.6% | 49.3% (n71) | 55.6% (n18) | −6.3 pp |

**The trades that fill lose; the trades that don't fill win.** That is NC-10 proven from the fill side
rather than inferred: the maker leaves the quote standing when they are content to sell us the loser and
pulls it when we are right. It also explains why persistence fails — waiting converts *unfilled winners*
into *filled losers*, which is exactly the wrong direction, and it is why the K=2 row has both the biggest
fill-rate gain and the worst per$1.

It also reframes London's own observation: if 60% never fill, those 60% are disproportionately the winners.

## (3) With the v1 veto on top

raw25: K=1 **+0.212** (130 fires, 56 fills*, win 50.0%, halves +0.318/+0.106, perm p 0.070) ·
K=2 −0.052* · K=3 +0.138* · K=4 +0.002*.
fixed15: K=1 +0.153* · K=2 +0.230* · K=3 +0.222* · K=4 **+0.297*** (28 fires, 22 fills).

The veto still helps — it lifts every K — but **every single veto cell has fewer than 60 fills**, and the
best raw25 cell's permutation is p=0.070 against a p≤0.01 bar. The fixed15 K=4 cell at +0.297 rests on
**22 fills**; I would not quote it as anything.

## Verdict

1. **Persistence does not work, on either profile, paired or unpaired.** It is a clean negative: more fills,
   less money, worse on the shared candles.
2. **The mechanism is fill adverse selection of 10–29 pp**, measured directly. That is the most useful thing
   in this file and it is bad news for every "improve the fill rate" idea: raising the fill rate on this
   book raises it on the losers.
3. **My fill simulator is 11 pp optimistic** against London's real 31%, so treat levels as upper bounds and
   trust only the K-to-K comparisons.
4. **K=1 remains the best fire rule** and the v1 veto remains the only thing that improves it, still on
   n<60 fills with perm p 0.070. Nothing here should move London.
