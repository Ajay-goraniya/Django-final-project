# Profit + small drawdown via COMBINATION - PRE-REGISTERED 09-30 01:4x UTC (before any look)

Owner 01:4x: "find the more profit + little drawdown". Single arms fail: calm FAV P/DD 0.74 on Zurich 6 days
(win +2..+5, loss -10 per $10 -> a 5-6 loss run erases days). No new gate, no threshold sweep, no sizing model.

Idea: arms whose losing stretches do not overlap. Split the SAME $10 per candle-slot across two arms ($5 each);
profit adds, drawdown grows slower if the arms' daily/hourly PnL are uncorrelated.

Candidates (fixed now, all frozen as registered): FAV, FAV_ref, FAV_mid, FAV_all, C_fixed15, F_z50, F25_z25, F75_z75, E3, S_fixed_top20.
Every PAIR at $5+$5, plus each single arm at $10 as the baseline. Report the WHOLE table, never the best row.

Per combo: fills, $ total, maxDD (on the per-candle cumulative curve), P/DD, days+/days-, H1$/H2$,
corr of hourly PnL between the two arms.
PASS only if ALL of:
 (a) $ > 0 on EVERY set: Zurich history 09-24..29, Zurich forward 09-29 01:20.., and V's independent 09-13..16
     where the arms exist there;
 (b) H1 > 0 and H2 > 0 on each set;
 (c) P/DD >= 2 on the pooled curve;
 (d) >= 60 fills per arm in the pooled sample;
 (e) beats both of its single arms on P/DD.
Paper first (Zurich shadow arm). Nothing reaches London or live without the owner.
