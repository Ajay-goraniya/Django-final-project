# OBSERVATION ONLY - do not merge this code into v12

User decision, 09-11 14:15 UTC, verbatim:
> "that execution is fucked up it does not have our dashboard so for now keep it for just seeing how it
> does but don't include it's code into our new model v12 pollymarket one"

## What this means
- `btc_model_v12_polymarket.py` KEEPS RUNNING in paper as a scratch observation lane (port 8790,
  db scratchpad/v12/results/v12_poly_weekend.sqlite3, snapshot learner/live_backup/v12_poly_lane.sqlite3.gz).
  Watch its numbers, learn from its behaviour.
- Its CODE does NOT go into the real v12 Polymarket build. Do not import it, do not copy its executor,
  do not make it the basis of the lane. No session may merge it without the user saying so directly.

## Why - the substantive reason, not just a preference
This file is a standalone script whose only interface is a read-only JSON blob on `/`. It has no
dashboard, no `/api/controls`, no lane arm/disarm, no stake control, no order table, no manual override.
The live system is operated through build11's dashboard and control endpoints, and every operational
habit we have - arming lanes, the stake ladder, killing a lane, reading fills - depends on those. A
venue lane that cannot be driven from the dashboard cannot be operated, and on a 5-minute market the
ability to stop it NOW is not a nice-to-have.

## The design that follows from this
The Polymarket executor belongs INSIDE build11 as a venue backend behind the existing interfaces -
same dashboard, same /api/controls, same lane semantics, same ladder, same kill rules - with the venue
swapped underneath. Not a second process with its own private conventions. That also avoids two
codebases drifting apart on grading, fees and stake logic, which is exactly where this project has
already produced fake results.

## What is still worth taking from it (ideas, not code)
- Its trade schema is good and build11's Polymarket lane should record the same fields: quote_ask,
  quote_age_ms, attempts, order_ids, trade_ids, filled_shares, avg_fill_price, slippage, fee_rate_bps,
  pnl_per_dollar. That is what makes a live fill reconcilable against what the model saw.
- Its guard pattern is good: paper by default, live requiring an explicit CLI flag plus wallet env vars
  plus an eligibility confirmation, and an ambiguous submit disabling the lane instead of resubmitting.
Reimplement these in build11. Do not lift the file.
