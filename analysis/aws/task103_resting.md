# Task 103 — R-18 resting-order test on Mumbai's own 1 Hz book

## 2026-09-16 03:2x UTC — INSUFFICIENT, 14 minutes of data

Store behind every number below: **book1s_mumbai started 03:11:41 UTC, 14.3 minutes, 862 b1 rows,
4 epochs of which 2 are complete (>=280 s), 14,148 depth rows, 2,701 trades, 3 gaps (10.3/10.4/10.4 s,
all "venue reconnect" at the 5-min market rollover).**

(1) ADVERSE SELECTION — not computed. Two complete candles is not a comparison; a filled-vs-not-filled
outcome split on n=2 would be noise dressed as a finding. This is the gate the task says decides whether
the idea lives, so nothing downstream is run until it can be answered.

(2) k x TTL x fire-second grid — not computed. Every cell would be n<=2.

(3) R-18a pad arm on our own orders — not computed. The paper engines have 21 (8787) and 24 (8793)
fills total, all at pad=1; there is no pad variation on this box to grid.

Rate: 288 b1 rows/candle, 12 candles/hour. A 60-candle arm is ~5 hours of data; the k x TTL x fire-second
grid needs 60 per CELL, which at 12 candles/h is days, not hours. First honest read on (1) at ~09:00 UTC.

Known defect to fix before the data is used: the venue socket drops ~10 s at each rollover (3 gaps in
14 min, all at epoch boundaries) because the subscription is rebuilt per epoch. The b1 rows either side
are intact; the hole is in `trades` and in depth continuity across the boundary.

---
**Closure (V, 09-17):** this arm was closed at 03:2x after H1 settled the resting-order question on the
real polybook tape - 492 fires, k=1..5 x TTL 15..299 all negative, FILLED 378 win 40.7% vs NOT-FILLED 114
win 99.1%, Fisher p=7.7e-35. That is R-18, CLOSED with evidence: price capture loses to the touch. This
box's 14-minute sample was retired in favour of that, not because it disagreed - it was simply too small
to ever catch up.
