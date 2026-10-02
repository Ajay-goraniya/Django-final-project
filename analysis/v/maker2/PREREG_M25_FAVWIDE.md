# M25 - FAV-wide: calm-FAV with the band widened to 0.55-0.90 (V, 10-02 ~13:10 UTC). Frozen BEFORE any forward read.

Found on 09-11..16 real 1 Hz asks (M25_GRID.txt, 27 cells all reported). Within the base window 60-180, band 0.55-0.90 was
+0.067 / +0.081 / +0.082 per $ at vol cuts 0.20 / 0.25 / 0.304 (monotone, not a lone peak) vs base FAV +0.034.
Windows 0-120 and 0-240 were worse for every band - the 60-180 window is kept. In-sample to this grid: treat as a hypothesis.

RULE (frozen): calm vol<0.304 (poly_fav definition), sec 60-180, favourite ask in [0.55, 0.90], one buy per candle,
same entry/fill model as Zurich's FAV arm. Only the band changes.

TEST: Zurich replays FAV-wide AND base FAV, identical fill model (arrival +500 ms, real recorded ask, exact fee, $10),
on (a) the forward shadow 09-29 00:00 .. now and (b) history 09-24..28. PASS needs, on the FORWARD period:
 1. FAV-wide pnl > 0, both forward halves > 0, fills >= 60;
 2. FAV-wide beats base FAV in $ AND per $1;
 3. paired: on candles where the two DISAGREE (trade only in one, or different entry), FAV-wide's extra/different trades
    have pnl > 0 on n >= 60, else INSUFFICIENT (and then 2 alone does not pass);
 4. per day reported, no day hidden.
FAIL -> base FAV stays the reference. PASS -> proposed to the owner as the FAV rule for paper/live (his yes needed).
