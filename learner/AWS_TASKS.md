# AWS box tasks — from session V

Send findings to `V` with SendMessage. **Write nothing on your own user side** —
zero prose, no summaries, no sign-off. Nobody reads that session. Numbers and
findings in the messages to me, no preamble.

## Standing (user, 09-13)

- You may edit code, restart and redeploy that engine. No approval needed.
- **Stake $3 fixed.** Confirm after every restart.
- **EF stays enabled.** Never off, never master off, never paused "to be safe".
- MAIN and REVERSAL stay off.
- Off limits: the Tokyo host and its databases, and secret values.

## Task 6 - OPEN (do first): deploy 12.3.2

`git pull`. 12.3.2 is on the branch. It carries 12.3.1's two fixes (tick-grid
off-by-one, MAIN/REVERSAL seeding ON) plus the reject mechanism you found.

**The fix for the rejects.** You established there is no per-token sequence
number and that `price_change` applies deltas with no continuity check, so a
dropped delta is undetectable and leaves a phantom level until the next full
`book` snapshot. Since a gap cannot be detected it can only be aged out:

- each book carries a `snapshot` stamp refreshed **only** by a full `book`
  event, never by a delta;
- `quote()` reports `snapshot_age_s`;
- the executor refuses to price against a book running on deltas alone for more
  than `MAX_SNAPSHOT_AGE_S` (90 s), recording status `BOOK_UNSYNCED` plus a
  diagnostics row instead of sending an order it cannot trust.

Also: `dropped_stale` / `dropped_future` / `applied` and per-token snapshot ages
are now written to `diagnostics` once a housekeeping cycle, so this is
measurable at all.

Deploy on the same DB (migration is additive, history kept), same flags, $3, EF
on, master on. Then report in one short message: build reads 12.3.2, EF on,
master on, stake $3, main/reversal off, history intact.

**90 s is a guess, not a measurement.** Watch the `BOOK_UNSYNCED` rate. If it
refuses most candles the limit is too tight and I want your number instead —
you have the snapshot-interval data and I do not.

## Task 7 - OPEN: does the refusal actually reduce rejects?

The one that matters. After 12.3.2 has run a while, report:

- reject rate before vs after, on comparable samples;
- how many candles `BOOK_UNSYNCED` refused, and their `snapshot_age_s`;
- whether the fills that still happen have lower `snapshot_age_s` than the
  rejects that still happen — that is the direct test of the mechanism.

Under 60 graded attempts is insufficient and gets marked, not read.

## Task 8 - OPEN: two caps the code on disk cannot produce

Your finding, and I verified it here. 22:38:28 ask 0.45 cap 0.45, and 00:11:30
ask 0.40 cap 0.40. At tick 0.001 the **buggy** expression gives 0.451 and 0.401;
only the **str()-based** form gives 0.450 and 0.400 — and that form is my 12.3.1
fix, which the running process should not have had.

So either the deployed source differs from the branch, or something rewrites
`plan['cap']` after `order_plan`. Settle it: diff the deployed `poly_core.py`
against the branch at the commit that was live then, and check whether anything
between `order_plan` and `db.order` touches `cap`. If the deployed tree has
drifted from the branch, that matters more than the caps do.

## Settled

- **Task 1** (why the rejects): the pad never engaged — 11/11 fills at or better
  than the quoted ask. My slippage advice is retracted.
- **Task 2** (MAIN default): the seeding loop, not the `allowed()` fallback.
  Fixed.
- **Task 3** (tick size): 141/142 asks on the 0.01 grid. Tick is 0.01, the dial
  was ineffective rather than incoherent. Your retraction accepted and recorded
  — I had already written the incoherence into the 12.3.1 notes and have
  corrected it.
- **Task 4** (desync): 20.9% of the session with the feed unusable is real and
  worth fixing on its own, but gap proximity does not separate fills from
  rejects (73% vs 76%). The mechanism is the undetectable dropped delta, which
  12.3.2 ages out.
