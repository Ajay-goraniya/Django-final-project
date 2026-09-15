# R-5 standing ledger — trained dynamic staking

One line per run. Re-run at every +100 graded live fires. Report to V only on a change of verdict.
Detail for each run is in `analysis/h1/task_r5_kelly_sizing.md` (rewritten in place each pass).

| run | date | paper n | live n scored | ship condition (same trades, more money) | ablation w/o `ask` | verify.py | verdict |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-15 02:4x | 1543 | **0 — live journal records no p/ev/rv60** | **NO**, −381.51 vs fixed-3 | +0.073 → **−0.146** | quote age FAIL, paired FAIL | **DOES NOT SHIP — stake stays fixed 3.0** |

Blocking item carried forward: the live journal must record `p`, `ev` and `rv60` per fire before
any pass can be scored on real fills. Every number in run 1 is paper at the quoted ask.
