# D1 — where the Polymarket paper lane loses (Mumbai 8795 EF, fill level). 2026-09-22 (V). INTERIM: chunks 1–2 of 3.
Data: 505 EF fills of arm 8795 (EF-only, 12.15.5), 09-16 18:35 → 09-20 11:10 UTC, relayed by Mumbai in md5-verified
chunks (scratchpad mumbai_chunk{1,2}.csv). Graded on results.actual. 8796 rows carry EF+REV combined pnl and are not
used for per-fill economics. Chunk 3 (09-20 11:10 → 09-21) pending; every number below is re-run when it lands.

## The lane
n=505 · hit 54.9% · +$387.69 · +0.260/$1 · every day positive (09-16 +67, 09-17 +89, 09-18 +185, 09-19 +20, 09-20 +27).
Max drawdown −$55.71, 09-19 01:30 → 10:30 (42 fills, hit 26%). Longest loss streak 11, 09-19 07:55.

## Where it fails — full grids, H1|H2, * = under 60
| model p at fire | n | claimed→realised | per $1 | H1 \| H2 |
|---|---|---|---|---|
| 0.50–0.55 | 185 | 0.52→0.48 | +0.29 | +0.21 \| +0.36 |
| 0.55–0.60 | 109 | 0.58→0.50 | +0.17 | +0.46 \| −0.14 |
| 0.60–0.65 | 95 | 0.62→0.64 | +0.41 | +0.47 \| +0.34 |
| 0.65–0.70 | 85 | 0.68→0.61 | +0.13 | +0.35 \| −0.06 |
| 0.70+ | 31* | 0.74→0.68 | +0.27 | |
On Mumbai the low band is NOT the problem: p 0.50–0.55 realises 0.48 and earns +0.29 both halves because the ask is ~0.40.
On Zurich (paper 09-21 and live 09-15/17) the same band realised 0.31–0.32. Same model, different days. Chunk 3 covers the
09-21 candles both boxes traded; the paired read on those decides whether it is the day or the box.

| rv60 at fire | n | hit | per $1 | H1 \| H2 |
|---|---|---|---|---|
| <0.15 | 140 | 53% | +0.05 | +0.31 \| −0.09 |
| 0.15–0.30 | 84 | 49% | +0.06 | +0.09 \| +0.03 |
| 0.30–0.60 | 160 | 59% | +0.42 | +0.36 \| +0.51 |
| 0.60–1.0 | 82 | 50% | +0.26 | +0.18 \| +0.38 |
| ≥1.0 | 39* | 67% | +0.81 | |
The 09-19 drawdown sat in a dead market (rv60 median 0.16 vs 0.35 overall). But rv<0.3 flips sign between halves and the
sweep is not monotone → verify.py: NOT a finding. Low vol is where the drawdown happened, not a rule.

| model p − market p (our side) | n | hit | per $1 | H1 \| H2 |
|---|---|---|---|---|
| 0.10–0.15 | 194 | 49% | +0.03 | +0.18 \| −0.07 |
| 0.15–0.20 | 221 | 57% | +0.26 | +0.24 \| +0.28 |
| 0.20–0.30 | 77 | 64% | +0.67 | +0.62 \| +0.73 |
| ≥0.30 | 13* | 62% | +1.25 | |
gap ≥0.15: n=311, +0.40/$1, H1 +0.42 | H2 +0.38. gap <0.15: n=194, +0.03, H2 negative. Monotone across the three readable
cells (verify's sweep check only fails on the empty first cell). Holds INSIDE every ask band (ask<0.40: +0.61 vs +0.32;
0.40–0.50: +0.27 vs −0.07; ≥0.50: +0.25 vs −0.01) — it is disagreement with the market, not cheapness. corr(gap, EV)=0.84.

| engine's own EV threshold in force | n | hit | per $1 | H1 \| H2 |
|---|---|---|---|---|
| thr 0.25 | 339 | 56% | +0.355 | +0.36 \| +0.34 |
| thr 0.15 | 166 | 53% | +0.067 | +0.31 \| −0.07 |
| fires that exist only because thr dropped to 0.15 (EV<0.25) | 140 | 52% | +0.016 | +0.27 \| −0.13 |
Per day, the 0.15-only fires: 09-16 +6, 09-17 +17, 09-18 +27, **09-19 −17, 09-20 −27**. In the 09-19 drawdown window they
are 19 of 42 fills and −28 of the −53. The lane's own frequency lever (dropping to 0.15) buys the fires that carry the
drawdowns and earn nothing over the sample. This is the engine's existing rule measured, not a new gate.

## Reading
1. The lane makes its money when the model disagrees with the market by ≥15c (EV ≥ ~0.3). Below that it is flat on paper
   and negative live (fills). Drawdowns are runs of those flat fires in dead markets.
2. The 0.15 threshold mode is the frequency knob the owner asked for; on this sample it adds trades and no money.
3. Not yet answered: why Zurich's low band realises 0.31 where Mumbai's realises 0.48. Chunk 3 → paired same-candle read.
Scripts: scratchpad mumbai_analyze.py. Token budget D1 so far: ~60k (two chunks written verbatim).
