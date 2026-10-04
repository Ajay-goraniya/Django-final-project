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

IN-SAMPLE MECHANISM (09-11..16, logged before the forward read): of 638 FAV-wide trades, 281 are identical to base,
47 are extra (+0.15, nothing), and on 310 candles BOTH trade but FAV-wide buys EARLIER and CHEAPER (avg ask 0.596 vs 0.699):
wide +17.10 vs base -3.07. Paired on those 310: mean +0.065/share, t 2.52, sign-flip p 0.006, halves +14.45 / +5.73.
Reading: base waits for the favourite to climb to 0.65 and pays for the move; buying the same favourite at ~0.60 keeps it.
So the forward check that matters most is #3, the paired one.

RESULT (Zurich, M25_FAVWIDE.txt 4854391): FAIL on checks 1-3. Forward 09-29..10-02: wide -43.02 (halves +27.57/-70.59) vs base
+45.01; paired 158 discordant candles wide -83.46; the earlier-cheaper entry that GAINED +17 in sample LOST -103 forward.
Today: wide -72.68 vs base -64.97. RETRACTED. The band/timing knob flips sign between periods = noise; not tuned further.
Base calm-FAV stays the reference (forward +45.01 on 09-29..10-02 incl. today's -64.97).
