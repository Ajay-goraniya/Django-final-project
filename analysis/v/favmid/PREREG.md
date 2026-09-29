# FAV_mid loss anatomy - PRE-REGISTERED 09-29 18:3x UTC (before any look)

Owner 18:2x: "Fav mid doing good so work on that and try to make it better, keep good trades and see what's in the losing ones".

Base rule (frozen, unchanged): FAV_mid = MID vol tercile, favourite (own ask > opp ask), ask 0.65-0.85, sec 60-180,
first qualifying second, once per candle, $10, arrival fill.

Features - all known AT the decision second, signed to OUR side. Buckets fixed now:
 F1 ask       [.65,.70) [.70,.75) [.75,.80) [.80,.85]
 F2 sec       60-90 | 90-120 | 120-180
 F3 z (TWAP-line distance in sd, our side)   <0 | 0-0.5 | 0.5-1 | >=1
 F4 mom15 our side   <0 | >=0
 F5 d_ask_30s (fav strengthening?)  <0 | 0 | >0
 F6 book size  own<opp | own>=opp
 F7 spread     <=0.01 | >0.01

Report EVERY bucket of EVERY feature (never the best cell): fills, win%, $@10, per-fill.
A change is a candidate only if ALL hold:
 (a) same sign on BOTH data sets (V: 09-13..16 independent; Zurich: 09-24..29 + forward);
 (b) same sign on both halves of each set;
 (c) the removed bucket has >= 60 fills in total, and paired()/McNemar on the discordant trades;
 (d) monotone across the buckets (no lone peak);
 (e) P/DD of the kept trades beats the base rule; frequency loss reported.
No new vol cut, no band sweep, no stake modifier. Paper only (Zurich shadow) - never London without the owner.
