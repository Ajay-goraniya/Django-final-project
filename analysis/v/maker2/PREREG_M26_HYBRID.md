# M26 - HYBRID calm-FAV: rest at the bid first, take the ask only if not filled (V, 10-02 13:2x UTC). Frozen before any read.

Why (PROBE_VS_FAV.txt 74cf0dc, 09-30 17:00..10-02): on 70 candles both traded, the maker probe +0.085/$ vs FAV taker -0.093/$
(47 of 49 paired better; 4.2c a share cheaper). On the 89 FAV candles the probe MISSED, FAV +0.111/$ (72W/17L).
Execution helps where the maker fills; reach is lost where it does not. Hybrid keeps both - if the fallback is not too late.

RULE (frozen): calm (vol<0.304) candle. Phase 1, sec 60-120: the probe exactly as live (post-only BUY at best bid on the favourite,
band 0.60-0.80, its two cancels). If filled -> hold, done. Phase 2, sec 121-180: if NO maker fill in phase 1 and FAV's own
conditions hold (favourite ask in [0.65, 0.85]) -> TAKER buy at the ask (FAV's fill model), one per candle. Hold to settlement.
TEST A (Zurich, retro, 09-30 17:00..now): hybrid = real probe fills + FAV-taker at the first FAV-qualifying second >= 121
(real recorded ask, arrival +500 ms, exact fee). Compare per $1 AND $ vs FAV taker alone and vs probe alone; per day; halves.
 Caveat logged now: the probe ran 60-180 until 11:50 today, so retro phase 1 uses only its fills at sec <= 120.
TEST B (forward): same three as paper arms from now, judged at 150 calm candles with >= 60 hybrid trades.
PASS (both A and B): hybrid > FAV taker per $1 and in $; hybrid > 0 in both halves. Then proposed to the owner (his yes needed).

RESULT TEST A (Zurich M26_HYBRID.txt 5051426): FAIL. 202 calm candles 09-30 17:00..10-02: hybrid -0.0072/$ (-7.55), FAV taker
+0.0211/$ (+32.44), probe-only +0.1271/$ (+35.96, 76 trades). Fallback leg alone 79 trades -0.0565/$: it enters at sec 128 @0.764
vs FAV's sec 71 @0.721 (+0.0696/$) on the same candles - waiting costs 4.3c and flips the sign. Test B not built. RETRACTED.
Standing read: in calm-FAV the ENTRY TIME dominates; the passive probe is the best execution measured (+0.127/$, real fills).
