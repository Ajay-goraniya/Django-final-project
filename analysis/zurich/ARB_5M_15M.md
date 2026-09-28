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

---

# CORRECTION, 2026-09-28 05:3x — the riskless-second counts above are inflated by a stale 15m book

Found while exporting `arb_windows.csv` for V. **The numbers in the sections above should not be used.** The
structural conclusion (payoff is 1 or 2, never 0; only the `cost < 1` test is sound) stands; the *frequency*
does not.

## What was wrong

The scan read the recorder's btc15 top-of-book without checking `up_snap_age_s` / `dn_snap_age_s`, which the
recorder stores precisely so that this can be checked: a `price_change` delta does not resync the book, so
snapshot age is the only measure of drift. The minimum pair cost reported above, **0.3873**, is a single
frozen quote. Traced second by second (window 09-27 06:45):

```
 sec  a15(UP)  snap_age   a5(DOWN)    cost
  25    0.350       0.2      0.780   1.1579
  50    0.350      11.1      0.800   1.1771
 125    0.350      86.2      0.950   1.3193
 250    0.350     211.1      0.260   0.6394
 289    0.350     250.2      0.020   0.3873   <- 15m ask unchanged for 250 s while the 5m went 0.78 -> 0.02
```

The 15m UP ask never moved for the last four minutes of the candle. It was not a quote, it was a memory.

## How stale is stale — measured against an independent witness

The dual-market ms probe (`/home/ubuntu/pm_probe2`) holds its own WS subscription to the same btc15 tokens,
so it is an independent read of the same book. Over **20,205** shared seconds, recorder vs probe:

| recorder snap age | n | mean abs diff | >= 1c | >= 5c | p90 |
|---|---|---|---|---|---|
| <= 3 s | 13,569 | **0.71c** | 38.5% | 2.0% | 2c |
| 3–15 s | 3,974 | **0.79c** | 34.1% | 3.2% | 3c |
| 15–60 s | 971 | **8.81c** | 56.6% | 34.2% | 24c |
| > 60 s | 1,691 | **15.62c** | 57.1% | 37.5% | 53c |

Usable to ~15 s, unusable past it. And the recorder was routinely past 60 s in exactly the window this scan
uses — the last 5 minutes of the 15m candle. Mean btc15 snap age by candle minute:

```
min  0-10: 1.9 2.3 2.3 2.3 2.7 2.7 4.1 2.8 3.5 4.2 4.9 s
min 11-14: 15.3  41.2  76.1  125.5 s      <- the last-5m sub-window is minutes 10-15
```

**Cause, and it is a recorder bug of mine.** `resync_loop` refetched REST `/book` every 45 s for tokens of
"live" candles, but tested `ep >= now // 300 * 300` — a 5-minute boundary. A 15-minute candle stops passing
that test 5 minutes after it opens, so btc15 tokens were dropped from the resync for the whole second half of
every candle. Fixed in `recorder.py` to `ep + MARKETS[m]['step'] > now`; recorder restarted 05:31:01 by the
cron keep-alive. ETH and SOL were never affected (step 300, max snap age 52–62 s across the whole sample).

**The engine's 5m leg is NOT affected.** `tape1s.up_ask`/`dn_ask` against the same probe over 16,387 shared
second-sides: exact match 66.6%, mean **0.79c**, >= 5c on **3.0%**, and flat across candle minutes 0–3 (0.64,
0.67, 0.68, 0.72c). The engine's book is fine; only my recorder's 15m leg was stale.

## The corrected frequency

Same code, same data, 105 windows with a btc15 book, gate = 15 s snapshot age on the 15m leg:

| | windows | best cost in window |
|---|---|---|
| ungated (what the sections above did) | **27 of 105** | down to 0.3873 |
| snap age <= 15 s | **10 of 105** | best 0.8010, p50 0.9774 |
| and \|L15 − L5\| >= $5 | **5 of 105** | 0.9524 – 0.9934 |

732 individual riskless seconds were dropped as stale. So the gate removes **63%** of the windows and most of
the apparent size of the edge.

The second filter is from the 09-28 `arb_trades_check` result (`analysis/v/twap/`): the single 0-payoff window
in 763 had a line gap of $2.33, so the *sign* of L15 − L5 — which decides which two legs you buy — is not
reliable inside the reference's own resolution. Five of the ten fresh windows are inside that band.

What is left, per window: **1 to 9 riskless seconds** out of 300, costs 0.9638–0.9996 at first sight and
0.9524–0.9934 at the best second, 15m touch size 43–997 shares. Every graded one paid 1. That is a real but
**4c-or-less** edge on a handful of seconds a day, on one leg's touch size — before any legging risk, which
EF_PERSIST-style fill behaviour says is the binding constraint.

Cross-check with V's `pair_bot.py` running in paper on this box: its one detected pair, `T=1790570700 sec=106
15m DOWN @0.640 + 5m UP @0.310 cost 0.9811`, is window 04:45 in `arb_windows.csv` — same legs, same window,
and my scan has it riskless at sec 1 with best cost 0.9524. Two independent implementations agree.

Files: `arb_windows_csv.py` (gated exporter), `arb_windows.csv` (10 rows, with `age15` and `gap` columns).
