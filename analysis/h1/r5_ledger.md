# R-5 standing ledger — trained dynamic staking

One line per run. Re-run at every +100 graded live fires. Report to V only on a change of verdict.
Detail for each run is in `analysis/h1/task_r5_kelly_sizing.md` (rewritten in place each pass).

| run | date | paper n | live n scored | ship condition (same trades, more money) | ablation w/o `ask` | verify.py | verdict |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-15 02:4x | 1543 | 0 | **NO**, −381.51 vs fixed-3 | +0.073 → −0.146 | quote age FAIL, paired FAIL | DOES NOT SHIP |
| 1b | 2026-09-15 02:5x | **1872** | 0 | **NO**, −480.44 vs fixed-3; steelman also loses (−21.54) | −0.008 → **−0.138** | halves, null, quote age, paired all FAIL | **DOES NOT SHIP — stake stays fixed 3.0** |

**Run 1b supersedes run 1** and its row is kept rather than deleted. Run 1 used `v10_poly_long4`
(777); `poly_pnl` is a superset of it (all 777 rows, 125 fresher, to 2026-09-15 00:41), and adding
it plus `poly_acc` takes the sample to 1,872. The verdict got **stronger**: the per-$1 delta that
read +0.073 on the stale subset reads −0.008 on the full one, and the equal-capital steelman flips
from +168 to −21.54. A mildly positive number on the smaller sample was a small-sample artifact.

Blocking item carried forward, stated accurately (run 1's wording was wrong and V corrected it):
the v12 engine journals DO record `p`, `ev` and `rv60`, and this task reads exactly those for the
paper set. What is missing is a **Zurich live-journal snapshot on the branch** — `learner/live_backup`
holds 18 snapshots, none named zurich, and no `signals` or `diagnostics` table in any of them. The
only live-fill rows H1 can reach are `analysis/h1/r3_submissions.csv` (14 columns, no p/ev/rv60).
One pushed snapshot unblocks pass 2. Every number so far is paper at the quoted ask.
