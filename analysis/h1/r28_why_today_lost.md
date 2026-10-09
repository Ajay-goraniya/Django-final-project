# Why 09-16 lost (H1, 20:4x) — and why the "fire after 30s" idea is worthless

Source: `poly_pnl.sqlite3` / `v12_poly_lane.sqlite3` (snapshot 18:43), live `zurich_2` (snapshot 08:20).
Polymarket arms graded on their own `actual`, which matches `venues.outcome`.

## 1. The engine's edge is win% minus what the price charges. Today it went negative.

| day | n | win% | avg ask | price implies | **gap** | rv60 med |
|---|---|---|---|---|---|---|
| 09-14 | 146 | 57.5% | 0.445 | 44.5% | **+13.0pp** | 0.36 |
| 09-15 | 93 | 60.2% | 0.452 | 45.2% | **+15.0pp** | 0.48 |
| 09-16 | 93 | 41.9% | 0.443 | 44.3% | **−2.4pp** | 0.45 |

Nothing in the engine's *selection* changed: it paid the same average ask (0.443 vs 0.445/0.452) in
the same volatility (0.45 vs 0.36/0.48). It was not buying worse, or in a different regime. The
direction calls were simply wrong today. Per R-13 the model's call ≈ the venue price, so the engine
is capturing spread; the spread was not there today.

Daily PnL: 09-13 +153, 09-14 +426, 09-15 +278, **09-16 −89** (poly_pnl); v12 lane −62.
Live `zurich_2`: 09-15 **+14.11** (n=72), 09-16 **−9.63** (n=11, only to 08:20).

## 2. The loss is NOT in the first 30 seconds.

09-16: `<30s` n=9 −10.86, **`≥30s` n=84 −77.77**. Same shape in the v12 lane (−19.85 / −41.99).
A "wait past 30s" rule would have avoided about an eighth of today's loss.

## 3. The engine already fires late, so R-27's late-entry result changes nothing.

Live fire-second on 83 graded Zurich fires: min 15, **p25 53, median 85**, p75 134, max 240.
Only **7 of 83** fired under 30 s. **RETRACTED:** my 20:3x suggestion that "fire after 30 s" is an
actionable change. It is already what the engine does. The R-27 late-entry cell is positive because
it is nearly the whole sample, not because it is a rule.

## 4. The honest reading of the three-day gap

+13.0 / +15.0 / −2.4 pp on n≈93–146/day. Three days is not a sample, and with R-13 saying the call
carries no information beyond the price, a gap that swings 17pp day to day is consistent with a true
edge near zero plus variance. The two good days are as much evidence about variance as today is.

## 5. Not established here

Whether 09-16 differs from 09-14/15 in anything the engine can *see before firing*. Same ask, same
rv60 is evidence it does not — but it is one day, and no bucket below 60 fires should be read.
Hourly detail in the table above is n=2–8 per cell and must not be read as a time-of-day rule.
