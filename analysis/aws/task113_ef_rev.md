# Task 113 - EF + MAIN + REVERSAL together, PAPER lane D (port 8796, build 12.13.1)

Lane D ran `/home/ubuntu/pm_ef_rev/paper_ef_rev.sqlite3`, model_v10.json, capital 50, PAPER,
stake fixed 3.0, master true, ef_enabled true, main_enabled true, reversal_enabled true.
Closed 2026-09-16 when build 12.14.0 replaced it (Task 114 lane).

## Ledger, whole run

| kind | signals | orders | filled | stake $ | results n | W | pnl $ | pnl per $1 |
|---|---|---|---|---|---|---|---|---|
| EF | 1 | 1 | 1 | 2.99 | 1 | 0 | -2.99 | -1.00 |
| MAIN | 4 | 1 | 1 | 2.99 | (same candle) | - | - | - |
| REVERSAL | 0 | 0 | 0 | 0 | 0 | - | - | - |

Sample: 1 graded candle. Under the 60-fire bar this is **insufficient** for any pnl claim and
the pnl column is reported only so the grid is complete.

## The one structural fact the run does establish

**REVERSAL fired zero times, and could not have fired.** MAIN produced 4 signals and exactly 1
order; the other 3 MAIN calls never reached the venue. In 12.13.1 the REVERSAL trigger watches
the MAIN *order*, so 3 of the 4 candles where a MAIN view existed were invisible to it, and on
the 1 candle that did place, no reversal condition came up before settlement.

That is the defect 12.14.0 fixes: REVERSAL now watches the MAIN **call** (build11 parity), so a
MAIN view that is never placed still arms the hedge. Task 114 re-runs the same lane on 12.14.0
with main_enabled FALSE, which is the only configuration that tests the new trigger in isolation -
every REVERSAL there must carry the detail string "call only".

## Not touched

8787, 8793, 8794, 8795, both loggers, Zurich. Nothing live. Paper only.
