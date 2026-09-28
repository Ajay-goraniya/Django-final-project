# BTC 15m vs the last 5m candle inside it — is there a riskless pair?

Read-only. `analysis/zurich/arb_5m_15m.py`. Nothing traded, nothing live.

**The structure is real and it validates: 0 zero-payoffs in 725 graded cells.** Cost dips below 1 on
**25 of 81 scannable windows**, with a median best cost of **0.956**. But the sample is **22.8 h / 2
calendar days**, and the practical blocker is legging: the ms probe already showed a best-ask level lives
**~10 ms** with 67.9% of disappearances being cancellations, so filling *two* books at one instant is far
harder than my 1 Hz survival number suggests.

## The structure

Both markets settle on the same closing TWAP60 `X`, against different lines. With **one share of each leg**:

| | X ≥ far line | between the lines | X < near line |
|---|---|---|---|
| L15 < L5: 15m UP + 5m DOWN | 1 + 0 | **1 + 1** | 0 + 1 |
| L15 > L5: 15m DOWN + 5m UP | 0 + 1 | **1 + 1** | 1 + 0 |

Payoff is 1 or 2, never 0. So `cost = a15 + fee(a15) + a5 + fee(a5) < 1` is riskless, with
`fee(p) = 0.07·p·(1−p)` per share.

Sources: the recorder's 1 Hz `btc15` book (both tokens, with the 15m touch size), the engine's `tape1s`
BTC-5m asks **at the same second**, and the lines from `tape1s.ref_px` — the Chainlink reference the venue
settles on, TWAP60 over the 60 s before each open.

## Coverage — thin, and stated first

| | |
|---|---|
| 15m windows with book | **92**, 09-27 03:30 → 09-28 02:15 = **22.8 h, 2 calendar days** |
| windows usable (line + no tie) | 91 · graded on **both** markets 88 · lines equal 0 |
| scannable seconds in last-5m windows | 13,078 across **81** windows |

## Results

Pair cost across all 13,078 seconds: min **0.3873**, p05 0.9914, p50 1.3193, p95 1.7651, max 1.9441.

| | seconds | % | windows |
|---|---|---|---|
| **cost < 1.000 (riskless)** | 813 | 6.22% | **25 of 81** |
| cost < 1 + P(band) = 1.261 | 5,208 | 39.8% | 49 of 81 |

**Per window is the honest unit** — consecutive seconds are the same standing quote, so 813 seconds is not
813 opportunities. Best cost per window: p10 **0.7323**, p50 **0.9559**, p90 0.9897. So ~4.4c of edge per
share-pair at the median window, up to 27c at p10.

**The structural validation, and it is the most important line in this file:**
**0-payoff on 0 of 725 graded riskless cells** (1-payoff 711, 2-payoff 14). If the premise were wrong — a
different `X`, a different reference, a mis-derived line — zero-payoffs would appear. None did.

Where and why: the riskless seconds sit at **sec p50 191** of the last 5m candle (≈3 min in), with
a15 p50 **0.900** and a5 p50 **0.060**. And the 15m book at those moments is **tight**:
`up_ask + dn_ask − 1 = +1.0c` at p10, p50 and p90. So this is **not** a wide-book artifact — each market is
internally tight and they are simply not priced consistently with each other.

## V's "cost < 1 + P(band)" test — the data falsifies it

P(band) empirically is **23/88 = 0.261** unconditionally. But the cells that pass `cost < 1.261` realise a
mean payoff of only **1.065** against a median cost of **1.105** — that set is, on average, a **loss**.

The reason is selection: cost dips below 1.261 precisely when a5 is cheap, and a cheap a5 *is* the market's
estimate that the band will not happen. In the riskless set the realised band rate is **1.9%**, not 26.1%.
So an unconditional P(band) is the wrong bar; the market's own a5 already prices the conditional
probability. **Only the `cost < 1` test is sound**, because it needs no probability at all.

## Size, and what I could not measure

15m touch size on the riskless cells: p10 5, p50 **89**, p90 1,139 shares — about **$80** at the touch.

**The 5m leg's size is not measured.** `tape1s` carries no per-level ask size (only `ask5`/`ask20` depth
aggregates), so I can state the 15m leg's available size and not the pair's. That is a real gap: the pair is
capped by the *smaller* of the two, and I only have the larger-looking one.

## Legging risk — the actual blocker

Both legs' asks still ≤ their value **1 s later**: **605/790 = 76.6%** on riskless cells (68.5% on the
wider set). On its own that sounds survivable.

It is not, and the reason is elsewhere in this repo: `ASK_LIFETIME_MS.md` measured the BTC best-ask level's
life at **p50 68 ms** for the price level and **10 ms** for the specific shares, with **67.9%** of
disappearances being cancellations rather than trades, and 94.7% of share offerings gone before our ~230 ms
order path completes. A 1 Hz "survived one second" test cannot see any of that. Executing this pair needs
**two** books hit at effectively the same instant, on markets quoted by different makers — so the realistic
fill probability is well below 76.6%, and a single-leg fill converts a riskless pair into an outright
position.

## Verdict

1. **The arbitrage structure is sound and the data confirms it** — no zero-payoffs in 725 cells.
2. **It appears on 25 of 81 windows with ~4.4c median edge per share-pair**, concentrated ~3 minutes into
   the last 5m candle, on two internally-tight books that are inconsistent with each other.
3. **Too thin to size a claim**: 22.8 h and 2 calendar days. 678 of the 813 riskless seconds are on 09-27.
4. **Not actionable as measured**, for two concrete reasons: the 5m leg's size is unmeasured, and the
   legging requirement is far harsher than the 1 Hz test can show given a 10 ms quote life.
5. What would make this decidable: several more days of the 15m recorder, per-level sizes on **both** legs,
   and a ms-resolution capture of the two books simultaneously — the probe already does BTC 5m and could be
   pointed at both.
