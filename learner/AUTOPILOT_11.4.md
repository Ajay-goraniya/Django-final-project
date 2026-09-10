# Build 11.4 "autopilot" - the engine manages itself (spec, 19:20 UTC 09-10)

Goal (user, 19:15): the model must run 24/7 with MAIN + REVERSAL + EF together and handle, on its own, what V has been
handling by hand today: arming after restarts, stake sizing, lane kill/resume, dial verdicts, loss streaks, regime shifts.
No human, no agent required for it to keep working. Everything below is engine-side, persisted, and testable.

## A. Startup
- `auto_arm` (Trade Controls, default OFF for safety; ON on Tokyo): after the preflight (auth + approvals + book live)
  passes, restore master and the per-lane switches to their last persisted state instead of "OFF - safe startup".
  Persisted v11 settings already reload; this closes the last manual step after a crash/reboot.

## B. Stake ladder (engine)
- New stake mode `ladder`: stake = f(equity): $1 below 30, $2 at >= 30, $3 at >= 40, +$1 per +10 above, capped by
  max_stake (20 hard cap, never raised by the engine); steps down when equity falls below a rung. Re-evaluated at every
  settlement; changes apply at the next fire (existing "parked until open positions settle" logic stays).

## C. Lane autopilot (engine evaluates after every settlement of that lane; all thresholds are settings)
- REVERSAL: OFF if first 6 live fills <= 1/5, or avg fill worse than quote by > 3c over 20 fills, or after >= 20 fills
  real PnL < 0 and > 3.0 (at $1) under the shadow record over the same fires. RESUME automatically when the shadow
  record for the lane over the next 30 candles is >= 60% right at asks <= rev_max_entry.
- MAIN: stays OFF until its own entry cap exists (H1 Task 9 decides the cap from the shadow record: 72-74% right but
  bought at ~0.75 = negative EV; the break-even ask at 74% with a 2% fee is 0.725). Same kill/resume rules as REVERSAL.
- EF: `ef_min_ask` floor (11.3) stays; loss handling = the existing State X (2 consecutive losses -> 15 min shadow)
  extended with a rolling rule: if the last 20 settled EF fires are <= 8 wins, shadow EF for 30 min, resume on 5 shadow
  wins of the next 8. No hard stop-loss (user rule), only shadow-and-resume.

## D. Dial self-verdicts (the ledger logic moves into the engine)
- For every price dial (EF floor, REVERSAL cap, MAIN cap) the engine already records the refused fires with their quote;
  outcomes are known at candle close. Every 100 refusals it computes the refused group's PnL at $1 on both halves:
  if positive on both halves the dial is loosened one notch (floor -0.02 / cap +0.05); if negative on both halves it is
  kept; otherwise unchanged. Bounded to [0.40, 0.55] for the floor and [0.50, 0.70] for the caps. Logged to notes table.
- EV scale: every 150 graded EF fires compare realised PnL per unit at the current scale with the paper decision at the
  neighbouring scales (0.75 / 1.0 / 1.25 are all computable from the stored decision log) and move one notch only if the
  neighbour is ahead on both halves. Bounded [0.75, 1.5].

## E. Regime handling
- Weekend/low-range regime (H1 252-day result: half the range, a third fewer crossings, same accuracy): scale
  `min_notional` and the EV threshold by realised range of the last 12 candles vs the trailing 24-h median so a 7 bps tape
  is not traded with 14 bps thresholds. Setting `regime_scale` default ON on Tokyo, OFF elsewhere until the twins confirm.

## F. Reporting
- `/api/autopilot` returns every rule's state, last decision, counters; every automatic change is written to the
  engine's notes table with reason and numbers so a human can audit it later without V.

## Tests
- Unit tests for each rule on synthetic control-row histories (no market data needed), plus the existing 5 in
  V112ReversalEntryCapTests. Paper twin "AP" runs the autopilot beside C for 24 h before Tokyo takes it (except A + B,
  which are pure safety/ops and go live at deploy).

## Split
- V: A, B, C, D, F and the tests, in that order, as builds 11.4.x.
- H1: Task 9 (MAIN cap from the shadow record), Task 10 (E: regime scaling premise on the 252-day klines and the fire
  data), and review of every rule's thresholds against the fire record before V ships them.

## E2. Regime switches ("rain or sun", user 20:35 UTC 09-10)
Every rule carries an optional regime condition evaluated at the fire second from live-observable state only
(trailing 12-candle realised range quartile, crossings of the open in the last 6 candles, Polymarket book width /
one-sidedness, weekday/weekend, 8-h block). A rule is ON only in the regimes where H1's Task 13 grid shows it positive on
both halves; elsewhere the engine falls back to the plain setting. The regime table is data in the engine (persisted,
editable via /api/controls/autopilot), every switch is logged, and the autopilot's dial self-verdict runs per regime cell
so a rule that stops working in a regime is turned off there automatically.

### E2 rows so far (from H1 Task 13 grids)
| rule | regime switch | evidence | status |
|---|---|---|---|
| EF2 (second entry t~120, ask <= 0.60) | none - ON unconditionally; log the trailing-12-candle-range Q4 (> 76.4 bps) cell separately; arm "EF2 OFF in Q4" only if that cell is still negative at >= 60 fires | 215 fires: positive both halves in 9/9 buckets with >= 30 fires; Q4 -0.233 on 24 (under-sampled); chop (4+ flips in 6) is the BEST bucket (+0.695) | watch cell Q4 |
| EF ask floor 0.48 | ON except when trailing-12-candle range > 76.4 bps OR flips in the last 6 candles >= 4 | skipped group profitable both halves in Q4 (n=42, +0.250) and 4+ flips (n=56, +0.296); negative elsewhere | v12 rule |
| REVERSAL cap | none (cap removed 21:25; capital not binding at $1) | skipped group 77% +0.134/fire both halves on 108 | closed |
| REVERSAL lane | none; watch the 08-16 UTC block | +0.429/fire both halves on 255; 08-16 block -0.002 mixed | unconditional |

Regime logging rule (H1, 21:26): the trailing-12-candle range Q4 (> 76.4 bps) cell is logged separately for EVERY rule at
every check-in and by the engine's per-cell self-verdict - fast tape is the one regime signal that has appeared twice today
from independent directions (J weakens there; the EF floor's skipped fires turn profitable there).
