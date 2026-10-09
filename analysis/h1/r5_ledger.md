# R-5 standing ledger — trained dynamic staking

One line per run. Re-run at every +100 graded live fires. Report to V only on a change of verdict.
Detail for each run is in `analysis/h1/task_r5_kelly_sizing.md` (rewritten in place each pass).

| run | date | paper n | live n scored | ship condition (same trades, more money) | ablation w/o `ask` | verify.py | verdict |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-15 02:4x | 1543 | 0 | **NO**, −381.51 vs fixed-3 | +0.073 → −0.146 | quote age FAIL, paired FAIL | DOES NOT SHIP |
| 1b | 2026-09-15 02:5x | **1872** | 0 | **NO**, −480.44 vs fixed-3; steelman also loses (−21.54) | −0.008 → **−0.138** | halves, null, quote age, paired all FAIL | **DOES NOT SHIP — stake stays fixed 3.0** |
| 2 | 2026-09-15 03:0x | 1872 | 0 (no `p` column live) | **NO** — shrunk Kelly +70.17 vs fixed-3 +505.53 | unchanged | `p` overconfident in **5 of 5** bins; Brier 0.2435 vs venue 0.2463 | **DOES NOT SHIP — stake stays fixed 3.0** |

**Run 2** adds V's amendment: reliability curve + shrunk Kelly from the measured error (Baker &
McHale 2013 principle; shrinkage = calibration slope fitted on the training half, 0.699, falling to
0.474 out of sample). It supplies the *reason* runs 1/1b could only infer: sizing on `p` fails not
because the Kelly fraction was mistuned — retuning it by the measured error leaves per-$1 at +0.177
— but because **`p` is overconfident in every bin** (gaps −0.051 / −0.039 / −0.102 / −0.119 /
−0.051, all n ≥ 266) and beats the venue's own price by only **0.0028 of Brier**. There is no
calibrated edge for a stake curve to amplify.

**Run 1b supersedes run 1** and its row is kept rather than deleted. Run 1 used `v10_poly_long4`
(777); `poly_pnl` is a superset of it (all 777 rows, 125 fresher, to 2026-09-15 00:41), and adding
it plus `poly_acc` takes the sample to 1,872. The verdict got **stronger**: the per-$1 delta that
read +0.073 on the stale subset reads −0.008 on the full one, and the equal-capital steelman flips
from +168 to −21.54. A mildly positive number on the smaller sample was a small-sample artifact.

**BLOCKER RESOLVED 09-15 02:3x** — V pushed `zurich_v1` and `zurich_2` at e64b5b7. The schema does
carry `p`/`ev`/`rv60`/`sec`/`ask` in `signals.decision`, so pass 2 needs no further plumbing. The
blocker is now **sample size**: **5 graded live fires against the threshold of 100.** Details,
plus an open question on Zurich's grading oracle and a correction to how R-3 applies to the live
1-tick pad, in `analysis/h1/task_r5_zurich_readiness.md`.

Historical (superseded by the line above), stated accurately after V corrected run 1's wording:
the v12 engine journals DO record `p`, `ev` and `rv60`, and this task reads exactly those for the
paper set. What is missing is a **Zurich live-journal snapshot on the branch** — `learner/live_backup`
holds 18 snapshots, none named zurich, and no `signals` or `diagnostics` table in any of them. The
only live-fill rows H1 can reach are `analysis/h1/r3_submissions.csv` (14 columns, no p/ev/rv60).
One pushed snapshot unblocks pass 2. Every number so far is paper at the quoted ask.
