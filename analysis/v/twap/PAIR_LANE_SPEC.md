# PAIR lane - the 5m/15m TWAP dominance pair (spec, V, 09-28 night). NOTHING BUILT OR DEPLOYED.

## Why it pays, in one line
The BTC 15m market and the LAST 5m candle inside it settle on the SAME closing TWAP60 (Chainlink, the window
[T+840, T+900) of the 15m window T). They only differ in the line: L15 = TWAP60 before T, L5 = TWAP60 before T+600.

| lines | buy | pays if X >= far line | between the lines | X < near line |
|---|---|---|---|---|
| L15 < L5 | 15m UP + 5m DOWN | 1 | **2** | 1 |
| L15 > L5 | 15m DOWN + 5m UP | 1 | **2** | 1 |

The pair can never pay 0. When the two asks plus both taker fees cost less than $1, the profit is locked in.

## Evidence so far
- Zurich's own books, 22.8 h: cost < 1 in **25 of 81** windows, median best cost **0.956** (4.4c per pair), p10 0.732;
  **0 zero-payoffs in 725 graded cells**; both books tight (+1c spread). analysis/zurich/ARB_5M_15M.md
- Public trade tape (independent): takers actually BOUGHT both legs within 3 s at cost < 1 in **19 of 91** windows;
  dominance-pair payoff on gamma across all 91 windows {1: 68, 2: 23}, never 0. analysis/v/twap/ARB_TRADES_CHECK.txt
- Running: the same public check over 09-20..27 (does it happen every day?), and a ms probe of both books on Zurich until
  06:45 UTC (does a simultaneous pair actually fill both legs?).

## What the lane would do
1. In the last 5m candle of each 15m window (5m sec 0..290), read both books (15m tokens + the 5m tokens London already has)
   and the lines from ref_px (the engine already computes the 5m line; L15 is the same TWAP60 at the 15m open).
2. Pick the dominance legs from sign(L5 - L15). If |L5 - L15| < $1, skip (the Chainlink/ref gap could flip the direction).
3. If a15 + fee(a15) + a5 + fee(a5) <= 1 - MARGIN (MARGIN about 1c), send BOTH legs as FAK at the same instant, each capped at
   its ask + 0 ticks (no chasing), size = min(both touch sizes, PAIR_STAKE / cost).
4. If only one leg fills: HOLD it. It is the leg the other market says is underpriced, so it is +EV on its own. Log it as a single leg.
   Never chase the second leg above the pair's break-even.
5. One pair per 15m window at first. Settle each leg on its own market's gamma resolution.

## What it needs (engine, owner's confirmation before any deploy)
- 15m market discovery (gamma events slug btc-updown-15m-T), a WS subscription to its 2 tokens, and L15 from ref_px.
- A two-leg FAK sender (both POSTs in flight together) and journal rows keyed by the 15m window (not the 5m epoch).
- Settlement and PnL for 15m positions; dashboard lines.
- Tests; then a Zurich shadow run (shadow fills in-process, so it cannot show legging - the ms probe does that).

## Test plan before real size
1. Morning: probe verdict on the simultaneous fill of both legs; the 7-day public frequency.
2. Owner yes -> build as a draft (OFF by default) + tests.
3. Owner yes -> live micro-test on London: PAIR_STAKE $5, one pair per window, 24 h. Measure both-legs fill %, single-leg %, realised $.
4. Only then size up. The stake stays fixed; no Kelly (two confirmations rule).

## Risks, stated plainly
- Legging: a book's best ask lives ~10 ms per share on BTC 5m (ASK_LIFETIME_MS). If the stale leg is the one that gets pulled, the
  other leg is left alone. Designed so the lone leg is still +EV, but it is not riskless.
- Depth: the 15m touch is ~89 shares at p50 (about $80); the 5m leg's size is not yet measured.
- Thin history: 2 days of books. The 7-day public check tells whether this is a standing feature or a bad weekend.
