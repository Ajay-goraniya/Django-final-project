# M42 (V, 10-03 12:2x) owner: legging (M28 rule) on POLYMARKET, "specifically session wise". History only, nothing live.
RULE = M28 exactly (m28_legging.py): leg 1 at sec {30,60,120} on {fav, dog, UP}; leg 2 = other side, first second after leg 1 where
leg1_cost + ask2 + fee(ask2) <= 1 - m, m in {0.02,0.05,0.10,0.20}, until sec 295; never -> hold leg 1 alone. Taker both legs, fee 0.07p(1-p).
DATA: Zurich Polymarket 1 Hz bid+ask, every day available (09-11..16, 09-28..10-03). Labels = venues.outcome.
SESSIONS (fixed before running, by candle open UTC): ASIA 00-07, EUROPE 07-13, US 13-20, LATE 20-24.
REPORT: the FULL 36-cell grid in EACH session (+ all-day): candles, pair%, pair$, lone$, TOTAL$, per candle, green days, halves.
Never the best cell. A session "works" only if a cell there is > 0 with t >= 2, both halves > 0, >= 60% green days, n >= 60,
AND its grid neighbours (m +-1 step) are also > 0. Else FAIL for that session.
