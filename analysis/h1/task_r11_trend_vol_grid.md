# R-11 — trend × vol × side grid

**Verdict: "selling into a selloff at high vol" is NOT established as a rain-or-sun loser.**
Cell `ret60 down / rv>0.75 / DOWN`: n=77, hit 44.2%, **−0.092/$1**, halves **−0.272 / +0.083** —
the sign flips, so verify.py returns NOT A FINDING. Days positive 2 of 6, and **every day is thin**
(n = 3–28). Negative pooled, not reproducible daily. Today is variance-shaped, not a proven regime.

**V's premise reconciles exactly** on the live lane: 09-15 from 13:00 UTC = **36 results, 13 wins
(36.1%), −0.165/$1**, rv60 median 0.712; before 13:00, 34 results, +0.499/$1. But the whole of
today pooled is **+0.175/$1 (n=77)**, *better* than all other days (+0.122), so the day is not a
losing day — an afternoon inside it is.

Full 18-cell grid in the script output; **8 of 18 cells are readable (n≥60)**, the rest marked
insufficient and not read. Buckets fixed before any outcome: ret60 terciles (−0.481 / +0.949 bps),
rv60 cuts 0.35 / 0.75 as the brief specified, side UP/DOWN. 1,942 graded fires — 1,872 paper
(quoted ask, upper bound) + **70 live Zurich rows** (real fills).

**One thing worth keeping:** the live rows are graded on the Zurich journal's own `actual`, not on
`venues.outcome`, because my `venues` snapshot ends 09-15 01:10 and requiring it silently dropped
68 of the 70 live rows — including every row that prompted this task. That journal field *is* the
venue's resolution (verified from `grade_loop`, STATE.md CLOSED 09-15 02:37), so this is the right
oracle rather than a convenient one.

Script: `analysis/h1/task_r11_trend_vol_grid.py`.
