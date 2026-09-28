# ARB_LEGGING_MS — how long the 15m/5m riskless pair actually lives

Zurich, 2026-09-28. READ-ONLY. Source: the dual-market ms probe, 02:15 → 06:45 UTC, **27,452,896** top-of-book
events and 81,222 trades on one WS carrying both BTC markets' tokens, top-two asks with sizes, stamped with
our receive time. Nothing live, master OFF.

## Answer up front

1. **The riskless interval is a millisecond phenomenon.** Median duration **43 ms**; **9 of 11 intervals
   (81.8%) are shorter than the 250 ms it takes to arrive**. Total riskless time is **0.252% of a window**.
2. **It is tiny.** Min touch size across the two legs, at the worst point of the interval: p50 **10 shares**,
   p90 19, max 23. Two of eleven intervals do not even clear the venue's 5-share minimum.
3. **It is rare, and it is not where you would look for it.** 2 of 18 scannable windows. Both are the
   **two smallest line gaps in the whole sample** ($7.35 and $9.21, against a median of $60.90) — the pair
   only goes riskless where the two lines are close, which is exactly where the sign of the gap, and
   therefore the choice of legs, is least reliable.
4. **Fire both and arrive 250 ms later and you leg it 45% of the time.** Both legs 54.5%, one leg only 9.1%,
   neither 36.4%. A pair that legs is not the trade that was measured.
5. So the structure is real (no 0-payoff anywhere, in this probe or in 763 windows of `arb_trades_check`) and
   the trade is not: the edge is a few cents, on ~10 shares, for ~43 ms, several times a day, and you have to
   hit two venues at once to collect it.

## Every window, so the denominator is visible

```
    09-28 02:15  gap  +119.59  scanned, 3413 + 7275 events
    09-28 02:30  gap  +201.32  scanned, 47490 + 218271 events
    09-28 02:45  gap   +59.07  scanned, 56628 + 158636 events
    09-28 03:00  gap   -60.90  scanned, 132465 + 178718 events
    09-28 03:15  gap   +36.94  scanned, 88828 + 201202 events
    09-28 03:30  gap  -106.24  scanned, 42014 + 165603 events
    09-28 03:45  gap   +59.37  scanned, 45327 + 101490 events
    09-28 04:00  gap    +9.78  scanned, 105678 + 131784 events
    09-28 04:15  gap   -74.17  scanned, 65509 + 206385 events
    09-28 04:30  gap    +9.21  scanned, 107466 + 126718 events   <- RISKLESS
    09-28 04:45  gap    +7.35  scanned, 100254 + 131130 events   <- RISKLESS
    09-28 05:00  gap  +144.50  scanned, 27982 + 146071 events
    09-28 05:15  gap  +209.38  scanned, 22478 + 227027 events
    09-28 05:30  gap  +307.28  scanned, 117263 + 79083 events
    09-28 05:45  gap   +17.72  scanned, 66388 + 79983 events
    09-28 06:00  gap   -43.89  scanned, 41148 + 110174 events
    09-28 06:15  gap  +145.49  scanned, 20468 + 160190 events
    09-28 06:30  gap   -38.43  scanned, 39070 + 86599 events
    09-28 06:45  gap        -  no btc5 market for the last 5m candle
    |gap| over the 18 scanned windows: min 7.35 median 60.90 max 307.28; the riskless ones are at 7.35, 9.21  - the pair only goes riskless where the two lines are CLOSE, which is also where the sign of the gap, and therefore the choice of legs, is least reliable

```

## The measurements

```
(1) HOW LONG BOTH LEGS STAY AT OR UNDER cost 1, on our receive clock
    riskless intervals 11 across 2 windows
    duration ms: min 0  p10 2  p50 43  p90 418  max 658  mean 137
    intervals shorter than the 250 ms it takes to arrive: 9/11 = 81.8%
    total riskless time per window: p50 755 ms of 300,000 ms = 0.252% of the window

(2) MIN TOUCH SIZE ACROSS THE TWO LEGS (the binding leg, worst point in the interval)
    shares: p10 2  p50 10  p90 19  max 23
    at the 5-share venue minimum, 9/11 intervals are even tradeable; 1 carry 20+ shares

(3) COUNT PER WINDOW
    window          legs         n  total ms  best cost    gap $  pay
    09-28 04:30     DOWN+UP      3        93     0.9932    +9.21    1
    09-28 04:45     DOWN+UP      8      1416     0.9882    +7.35    1

(4) WOULD A "FIRE BOTH, ARRIVE +250 ms" PAIR HAVE FILLED?  (FAK within one tick, ef_persist rule)
    both legs      6/11 =  54.5%   <- the only outcome that is actually riskless
    15m only       1/11 =   9.1%   outright long the 15m leg
    5m only        0/11 =   0.0%   outright long the 5m leg
    neither        4/11 =  36.4%
    per leg: 15m fills 63.6%, 5m fills 54.5%

(5) THE SINGLE-LEG OUTCOME - what the 15m leg alone is worth when the 5m leg misses
    n 1, 15m leg right 0.0%, mean cost 0.607, capital-weighted per $1 -1.000  *n<60, not a reading
    for reference, the 15m leg on EVERY riskless interval regardless of fill: n 11, right 0.0%, per $1 -1.000

    A pair that legs is not the trade that was measured. 9.1% of these intervals turn into an outright at +250 ms.
```

Two notes on reading the fill test. The +250 ms rule is `ef_persist.py`'s, unchanged: you price on the two
asks you can see and a leg fills only if its ask is still within one tick when you arrive. And the single-leg
row is n=1, so it is not a reading — it is there because the *rate* (9.1%) is the number that matters, not
the outcome of one trade.

## Cross-check: three independent instruments on the same two markets

`pair_bot.py` (V's, PAPER), my recorder + tape1s scan (`arb_windows.csv`, 15 s snapshot-age gate), and this
probe all watched the same hours with separate subscriptions.

```
(5) THE SAME HOURS IN MY OWN SCAN (arb_windows.csv, 15 s snapshot-age gate)
    pair_bot running period 09-28 02:45 -> 09-28 06:30 = 3.8 h = 16 15m windows; my scan flags 2 of them riskless
    BOTH 1: 09-28 04:45
      09-28 04:45  pair_bot DOWN+UP cost 0.9811 at sec 106  |  mine DOWN+UP cost 0.9996 best 0.9524 at sec 1, 7 riskless s, gap +7.35
    MINE ONLY 1: 09-28 04:00 (cost 0.9638, 1 s, gap +9.78)
    PAIR_BOT ONLY 0: 

    A window in one list and not the other is not a contradiction by itself: these costs sit within a cent of 1.000,
    so a single tick on either leg, or a few hundred ms of timing, moves a window across the line. What matters is
    whether the LEGS agree where both fire, and whether any settled payoff is 0.
```

- All three agree on **04:45**, and the legs agree (15m DOWN + 5m UP). Line gap +7.52 on pair_bot's own
  reference against +7.35 on mine — 0.17 apart on 83,470, or 0.02 bps.
- The probe also flags **04:30**; my 1 Hz scan does not. The probe's intervals there total **93 ms** across
  three bursts, so a 1 Hz observer will usually miss it entirely. That is not a disagreement, it is the
  sampling rate.
- My scan flags **04:00** with exactly **one** riskless second; pair_bot did not fire there. Same cause.

The three instruments disagree exactly where the theory says they must: these events are shorter than the
interval between looks.

## pair_bot's settled result — V's "0 would be a bug" check

```
(1) PAIRS PER WINDOW: 1 pairs across 1 distinct 15m windows (max 1 in any one window)
(2) COST: p10 0.9811  p50 0.9811  p90 0.9811  min 0.9811  max 0.9811
(3) SHARES: p10 20  p50 20  max 20; both legs PAPER_FILL on 1/1

(4) SETTLED PAYOFF - 0 per share-pair would mean the dominance structure is broken
    settled 1/1; payoff per share-pair {1: 1}   <- no zero, structure held
    spent 19.62, payout 20.00, pnl +0.3780, per $1 +0.0193  *n<60, not a reading
    09-28 04:45  sec 106  DOWN+UP  0.640+0.310 cost 0.9811 x20  settled UP/UP  payoff 1  pnl +0.3780  gap +7.52

```

**Payoff 1 per share-pair, not 0.** The 15m settled UP and the 5m settled UP, so with legs 15m DOWN + 5m UP
the 5m leg paid and the 15m did not — exactly the `L5 ≤ X` branch of the dominance table. The structure held.

## A verification that fell out of having two subscriptions

The probe overlapped the recorder both before and after this morning's resync fix, which turns "the snapshot
age is lower" into "the prices now agree with an independent subscription":

```
recorder btc15 book vs the independent probe
  pre-fix    n 22130   exact 56.4%   mean 2.48c   p90 3.00c   >=5c  7.3%   snap age p90 37.25s max 266.5s
  post-fix   n  6344   exact 67.3%   mean 0.60c   p90 2.00c   >=5c  1.7%   snap age p90  5.51s max  10.5s
```

0.60c mean error is better than the engine's own book against the same witness (0.79c). The 15 s gate in
`arb_windows_csv.py` stays on by default because everything before 05:47 still needs it.

## Files

- `arb_legging_ms.py` — the merged two-leg event walk and the +250 ms fill test
- `pair_bot_report.py` — pair_bot's paper record and the three-way comparison
- `arb_windows.csv` — 10 windows, gated
