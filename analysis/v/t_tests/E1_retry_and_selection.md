# E1 — execution on Polymarket: retries, rejects, and which candles live fires on. 2026-09-21 (V)
Owner: "the platform will stay Polymarket, you need to improve execution, retry and most importantly right signal."
Data: 151 live EF fills + 214 live rejects (zurich_v1/2/3, 09-15 → 09-17), polybook 1 Hz tape, paper lanes on the
same days (poly_pnl / v12_poly_lane via the unified export). Graded on venues.outcome / results.actual (0/32 disagree).

## 1. Retry — the largest identifiable live leak. DIRECTIONAL (n=51 < 60), not yet a finding.
| filled on attempt | n | hit | per $1 | pnl $ |
|---|---|---|---|---|
| 1 | 100 | 47% | +0.081 | +27.42 |
| 2 | 40 | 30% | −0.436 | |
| 3 | 10 | 40% | −0.045 | |
| 4 | 1 | 0% | −1.031 | |
| ≥2 together | 51 | 31% | **−0.371** | **−67.26** |
Halves for ≥2: −0.273 / −0.494 (same sign). Retried fills paid +3.0c median (+4.4c mean) over the attempt-1 quote.
Live total −39.84 = attempt-1 fills +27.42 plus retried fills −67.26.
verify.py: grading PASS, halves PASS, sample FAIL (51), sweep non-monotone (attempt-3 cell is n=10), null check
not applicable in this direction. **Re-read when attempt≥2 fills pass 60. Do not ship on this alone; run the A/B.**
The engine already retries up to 4 times (`--max-attempts`, default 4). The candidate change is max_attempts=1,
or retry only when the ask is unchanged from the attempt-1 quote. Both arms must run on paper on one box first.

## 2. Rejects are not lost profit
| | n | hit | per $1 |
|---|---|---|---|
| fills as they were | 153 | 42% | −0.070 |
| rejects, if filled at their own quote | 119 | 37% | −0.164 |
| rejects re-quoted at +1 s / +2 s / +3 s ask | 62 | 42% | −0.177 / −0.177 / −0.215 (ask +3.0 / +4.0 / +4.5c) |
Re-quoting after a FAK kill pays up and buys the same losing candle. "Fill more" is the wrong goal; "fill the first
quote or nothing" is what the data supports.

## 3. Same candle, same call: live and paper agree. The gap is WHICH candles.
| | n | hit |
|---|---|---|
| candles both fired: same side 71/74; live | 74 | 45% |
| same candles, paper | 74 | 49% |
| live-only candles (paper did not fire) | 78 | 38% |
| paper-only candles (live did not fire) | 120 | 52% |
Live-only fills are heavier in retries (22/78 vs 29/74) and later (median 102 s vs 89 s). On the 120 paper-only
candles live did evaluate (0 with no decision log) but EV crossed on only 19; the rest is quote/feed timing between
the two boxes. The "waiting for fresh books" log appears on 97–99% of ALL candles, so it does not discriminate here;
Task 116's 0.75 s bar finding stands on its own tape and is a candidate arm, not a claim from this data.

## 4. Streaks
Retried fills are 51/151 of fills and 13/37 of streak losses — proportional. With attempt-1 fills only the longest
run is still 13. Retry removal cuts the size of the hole, not the streak. Streaks are a stake question.

## What follows (owner decides; sessions are stopped)
Paper A/B on Mumbai, one process, twin decisions on one feed (the owner's 12.17.1 idea, with the decide_now fix):
arm A max_attempts=4 (as live), arm B max_attempts=1, arm C retry only at unchanged quote. ≥60 retried-candle
outcomes per arm before reading. Optional arm D: freshness bar 0.75 s vs Task 116's setting. No signal change:
T1 showed no better direction exists; the "right signal" on Polymarket is the first quote, not a second one.
