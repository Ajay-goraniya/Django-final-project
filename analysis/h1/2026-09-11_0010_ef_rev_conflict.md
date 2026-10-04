# EF and REVERSAL taking opposite sides of the same candle
H1, 2026-09-11 00:10 UTC. Verification of a claim relayed by the user from a **third session**
whose push was denied, so its own write-up (`learner/H1_RESPONSE.md`) never reached the branch.

I re-derived it from the snapshots rather than take it on trust. **It replicates — its exact
numbers, and the sign holds on all four sources.** Per $1 per fire (twins stake $10, Tokyo $1–$2;
normalised, because a units mismatch already caused one false alarm on 09-10).

| source | both lanes | opposing n | EF /fire | REVERSAL /fire | **combined /fire** |
|---|---|---|---|---|---|
| predict_pnl | 68 | 28 | −0.475 (29% hit) | +0.255 (71%) | **−0.220** |
| build11 (twin A) | 54 | 22 | −0.542 (27%) | +0.188 (73%) | **−0.354** |
| twin_c_thr1 | 47 | 17 | −0.380 (35%) | +0.051 (65%) | **−0.329** |
| Tokyo real fills | 18 | 7 | −0.506 (29%) | −0.010 (71%) | **−0.516** |

And when the two lanes **agree**, the pair is strongly positive: +0.641 / +1.515 / +1.521 / +0.721
per fire, with both lanes hitting 65–84%.

## What this is, and what it is not

**It is a portfolio fact: the engine is trading against itself.** On roughly 40% of the candles
where both lanes fire, they take opposite sides — paying two spreads and two fees to hold a position
that is close to flat in direction and is a net loser in every source measured.

**It is not two independent pieces of evidence.** REVERSAL fires *because* it thinks the move
reverses. "REVERSAL opposes EF" and "EF is wrong" are largely the *same event* seen twice, so the
73% REVERSAL hit rate and the 27% EF hit rate in that group are not confirming each other. The
combined loss is simply REVERSAL's edge being smaller than EF's loss on those candles.

**No rule is proposed.** "Do not fire EF when REVERSAL disagrees" is exactly the kind of gate the
user banned, and it would also be unimplementable as stated — REVERSAL fires later than EF, so at
EF's fire second the disagreement does not exist yet.

## Why it is not a finding yet

**Every cell is under the 60-fire bar** (28 / 22 / 17 / 7 opposing). And the three twins are
different configurations of the same engine over overlapping candles, so they are **not four
independent samples** — really one twin family plus a thin slice of real fills. The consistent sign
across all of them is what makes it worth recording; the sample is what stops it being a finding.

Worth watching as the twins accumulate. Repro: `analysis/h1/ef_rev_conflict.py`.
