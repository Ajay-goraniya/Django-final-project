# Resolving the Task 14 / Task 15 discrepancy
H1, 2026-09-11 02:00 UTC. The queued check, now possible with full kline coverage. Engine grading,
buckets fixed in advance, 648 candles with venue book + engine outcome + kline path.

## The question

Task 14 measured the **venue's implied favourite** at t≥237 winning only **49.4%** in the near-zero
bucket (n=77). Task 15 measured the **Binance price leader** winning **~0.60** in the same bucket on
72,863 candles — and I tested and rejected the obvious explanation (the two studies bucket on
different variables; they agree, 0.614 vs 0.595). Two candidates were left:

- **(a)** the venue's favourite diverges from the Binance leader precisely in near-zero candles;
- **(b)** noise at n=77.

## The answer: (a) happens, but it is not the explanation. It is (b) — the window.

**t=237, agreement between venue favourite and Binance price leader:**

| bps | n | agree | leader wins | favourite wins | gap |
|---|---|---|---|---|---|
| **<1** | 60 | **60%** | **0.467** | **0.467** | **+0.000** |
| 1–2.5 | 114 | 96% | 0.693 | 0.702 | +0.009 |
| 2.5–5 | 166 | 99% | 0.867 | 0.861 | −0.006 |
| 5–10 | 151 | 100% | 0.980 | 0.980 | +0.000 |
| 10–25 | 134 | 100% | 0.993 | 0.993 | +0.000 |
| **ALL** | 641 | **95%** | 0.855 | 0.855 | +0.000 |

**(a) is real as a phenomenon:** the two disagree on 40% of near-zero candles, against 0–4%
everywhere else. The venue genuinely stops tracking the tape when the candle is flat, and it
re-converges as the close approaches — agreement in that bucket runs **60% → 79% → 90%** at
t = 237 → 270 → 290.

**But (a) does not explain anything, because the two perform identically: 0.467 vs 0.467, gap
+0.000.** The venue's favourite is not worse than the price leader. Overall the gap is +0.000 at
t=237 and +0.012 at t=270 — the venue is, if anything, marginally better.

**The actual explanation is (b).** On *this* 648-candle window the near-zero bucket is a coin flip
for **both** measures — the leader wins 0.467 here, against 0.614 on the 72,863-candle set. So
Task 14's 49.4% was never a venue-pricing pathology; it was this window's flat bucket behaving
differently from the long-run average, at n≈60.

## What this settles, and what it does not

**Settles:** Task 14's low number needs no venue-specific explanation, and nothing in the ledger
should record one. The venue prices the favourite in line with the tape — 95% agreement overall,
and identical realised accuracy where they do agree *and* where they do not.

**Does not settle:** whether the long-run 0.614 or this window's 0.467 is the better guide for the
near-zero bucket going forward. n≈60 here against 9,176 there says trust the long-run number, but it
is a live reminder that **this venue window is small and can differ from the 252-day set by 15
percentage points in that bucket.** Every per-fire number measured on these 648 candles — including
Task 11.2's +0.266 — inherits that uncertainty.

That is the honest caveat to carry into the 11.2 shadow: the replay window is not guaranteed
representative, which is exactly why the recommendation was a forward shadow rather than a ship.

## Limits

- The `<1 bps` cells are n=58–60, right at the bar. Read as "consistent with noise", not as a
  measurement of the flat bucket's true rate.
- Venue asks are forward-filled per field to the decision second.
- Engine grading (`candles` table); the ~2.5% venue-vs-Binance label caveat still applies in the
  flat bucket specifically.

Repro: `analysis/h1/venue_favourite_check.py`.
