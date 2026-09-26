# Weekend vs weekday — MAIN, REVERSAL, EF on the Zurich shadow journals (09-26 UTC)

Owner's question via V: "do MAIN and REV do well on weekends (Sat/Sun)?"

## THE ANSWER IS THAT THIS BOX CANNOT ANSWER IT

| | |
|---|---|
| Sundays in the entire sample | **0** |
| Complete weekends (a Sat with its Sun) | **0** |
| Saturday graded rows, MAIN | **4** |
| Saturday graded rows, REVERSAL | **1** |
| Saturday graded rows, EF | 30, split across two different Saturdays |

Every weekend cell is below the 60-fire bar, most of them by more than an order of magnitude. There
is no weekend-vs-weekday comparison to make for MAIN or REVERSAL, and no amount of care with the
existing data changes that. It needs a Saturday and a Sunday actually traded.

## Two things to know before reading any number below

1. **Not graded on `venues.outcome`.** CLAUDE.md requires Polymarket trades to be graded on the oracle
   Polymarket settles on. `learner/live_backup/venues.sqlite3.gz` covers epochs 1788881100-1789578900
   (09-08 to 09-16). Every journal in this grid is 09-15 onward and `live4` is 09-22 onward, so the
   overlap is **zero**. These cells are graded on the engine's own `results.actual`, uncross-checked.
2. **All of it is shadow.** Master has been OFF throughout; every fill is a `PaperBroker` in-process
   fill. Fill behaviour is not represented here at all.

## The full grid, every cell, nothing selected

```
bucket                              MAIN                      REVERSAL                     EF
                        n   right%    per$1          n   right%    per$1          n   right%    per$1
Mon                     -      -        -            2   50.0%   -0.120 INSUF     67   44.8%   -0.018 INSUF
Tue                    45   75.6%   +0.009 INSUF    14   42.9%   -0.365 INSUF    173   51.4%   +0.163
Wed                    73   65.8%   -0.157          23   69.6%   +0.127 INSUF    150   49.3%   +0.181
Thu                    68   70.6%   -0.045          19   57.9%   +0.079 INSUF    162   50.6%   +0.187
Fri                    94   71.3%   -0.042          18   55.6%   -0.259 INSUF    182   48.4%   +0.195
Sat                     4   50.0%   -0.413 INSUF     1  100.0%   +0.344 INSUF     30   30.0%   -0.183 INSUF
Sun                     -      -        -            -      -        -            -      -        -
-----------------------------------------------------------------------------------------------------
WEEKEND Sat+Sun         4   50.0%   -0.413 INSUF     1  100.0%   +0.344 INSUF     30   30.0%   -0.183 INSUF
WEEKDAY Mon-Fri       280   70.4%   -0.067          76   57.9%   -0.065          734   49.5%   +0.168
```
`INSUF` = under 60 graded fires. `-` = no data. Mon/Tue MAIN and every REVERSAL day cell are thin too,
so the weekday columns are not a clean comparison either; only Wed/Thu/Fri MAIN and the EF weekday
cells clear the bar.

## Does the weekend sign hold on each weekend separately?
It cannot be asked. There are **two partial Saturdays and no Sundays**:

| date | MAIN | REVERSAL | EF |
|---|---|---|---|
| 2026-09-19 Sat | no data | no data | n 27, 25.9%, **-0.387** |
| 2026-09-26 Sat | n 4, 50.0%, -0.413 | n 1, 100.0%, +0.344 | n 3, 66.7%, **+0.890** |

EF's two Saturdays disagree in sign and by 1.3 per $1 — which is what n=27 and n=3 look like, not a
weekend effect. REVERSAL's entire weekend record is **one trade that won**.

## What would answer it
Sat and Sun traded for enough weekends to put 60+ graded fires per lane in the weekend bucket. At
MAIN's observed ~70 fires/day that is roughly one full weekend for MAIN, but REVERSAL runs ~19/day so
it needs about four weekends, and the weekday side needs to come from the same period to be comparable.
