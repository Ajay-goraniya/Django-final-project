#!/usr/bin/env python3
"""M53-NC grader. READ-ONLY except the nc table. Settlement = the venue's own resolution
(Chainlink-settled venues.outcome, else gamma). Filled rows pay shares*1.00 on a win; the cost was
already deducted at fill time, so pnl = (shares if win else 0) - spent, and cash_after is corrected
to include the settlement credit so the bankroll path is right."""
import sqlite3, time
UP = {}
for ep, a in sqlite3.connect('file:/home/ubuntu/m29/venues.sqlite3?mode=ro', uri=True)\
        .execute('select epoch,actual from outcome where actual is not null'): UP[int(ep)] = (a == 'UP')
for ep, o in sqlite3.connect('file:/home/ubuntu/pm_ef3/gamma_zurich.sqlite3?mode=ro', uri=True)\
        .execute("select epoch,outcome from mkt where outcome is not null and asset='btc'"): UP[int(ep)] = (o == 'UP')
d = sqlite3.connect('/home/ubuntu/m53/m53.sqlite3', timeout=30)
n = 0
for ep, side, sh, sp, st in d.execute(
        "select epoch,side,shares,spent,status from nc where graded_ts is null and status in ('full','partial')").fetchall():
    if int(ep) not in UP: continue
    win = 1 if ((side == 'UP') == UP[int(ep)]) else 0
    pnl = (sh if win else 0.0) - sp
    # cash_after is NOT mutated any more: the bankroll is derived from the ledger (see cash_now in
    # m53nc_paper.py), so there is no chained value to keep in step.
    d.execute('update nc set win=?,pnl=?,graded_ts=? where epoch=?',
              (win, pnl, int(time.time()), ep)); n += 1
d.commit()
print(f'graded {n}', flush=True)
