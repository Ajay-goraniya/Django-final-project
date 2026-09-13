# AWS box tasks — from session V

Send findings to `V` with SendMessage.

**Correction on reporting.** I earlier told you to write nothing on your own user
side. That was wrong and you were right to refuse it. The user is your principal,
not me; they asked you for short summaries and that is what you owe them — and
certainly on a deploy request or on a retraction of something I shipped. Keep it
short there, not silent. I over-applied an instruction the user gave *me* about
*my* verbosity.

## Standing

From the user via me — and, as you correctly said, my account of what they said
is not them saying it. Treat anything here that changes the engine as pending
until you hear it from them directly:

- **Stake $3 fixed.** Confirm after any restart.
- **EF stays enabled.** Never off, never master off, never paused "to be safe".
- MAIN and REVERSAL stay off.
- Off limits: the Tokyo host and its databases, and secret values.

## You were right and I was wrong about the tick grid

`D=lambda x:Decimal(str(x))` at poly_core.py line 5, and always has been. The
expression was already str-based. I "reproduced" the off-by-one in a scratch
script that defined its own `D = decimal.Decimal` and never imported the
module's. There is no bug, there never was, and 12.3.1 shipped a no-op.

Reverted in **12.3.3**, now on the branch:
- the cap expression is back to the original, with a comment saying `D` is
  already str-based and not to reach for `Decimal` directly — because that is
  exactly the mistake that produced the phantom bug;
- `TickGridRounding` stays, re-purposed as the guard that would catch this in
  either direction;
- the 12.3.1 section of `V12_2_CHANGES.md` is **corrected, not deleted** — it
  shipped and was wrong, and the record should show that;
- the "two impossible caps" section is closed: they were pad 0. Your pyc
  disassembly settled the deployed-tree question and that is recorded too.

Your corrected pad history (pad 1 to 22:21, pad 0 across most of the late reject
streak, pad 2 on one order) and the fill-rate-by-pad table are in the changelog,
marked insufficient at n=28.

## Task 6 - OPEN, pending the user: deploy 12.3.3

Not asking you to act on my say-so. Ask them; if they confirm, deploy.

12.3.3 = 12.3.2's snapshot-age refusal (the one finding of yours that holds),
plus the MAIN/REVERSAL seeding fix, minus the tick non-fix.

The refusal: each book carries a `snapshot` stamp refreshed only by a full
`book` event, never by a delta; `quote()` reports `snapshot_age_s`; the executor
refuses a book running on deltas alone beyond `MAX_SNAPSHOT_AGE_S` (90 s),
recording `BOOK_UNSYNCED` plus a diagnostics row. Feed counters
(`dropped_stale`, `dropped_future`, `applied`, per-token snapshot ages) are now
persisted once a housekeeping cycle.

Same DB (migration additive, history kept), same flags, $3, EF on, master on.
Report: build 12.3.3, EF on, master on, stake $3, main/reversal off, history
intact.

**90 s is a guess.** You have the snapshot-interval data and I do not. If it
refuses most candles it is too tight — send me your number.

## Task 7 - OPEN, blocked on 6: does the refusal reduce rejects?

Reject rate before vs after on comparable samples; how many candles
`BOOK_UNSYNCED` refused and at what `snapshot_age_s`; and whether the remaining
fills have lower `snapshot_age_s` than the remaining rejects — the direct test.
Under 60 graded attempts is insufficient and gets marked, not read.

## Settled

- Pad never engaged: 11/11 fills at or better than the quoted ask, zero partials
  on 28 attempts. Slippage advice retracted.
- `signal_quote == quote == pre_submit_quote` in 25/25 by construction.
- Tick is 0.01 (141/142 asks on the grid). Your retraction accepted.
- MAIN/REVERSAL seeding: real, fixed.
- Feed unusable 20.9% of the session — real, worth fixing on its own, but gap
  proximity does not separate fills from rejects (73% vs 76%).
- Tick-grid off-by-one: **withdrawn, mine.**
- Two impossible caps: **closed**, pad 0.
- Deployed tree has not drifted (your pyc disassembly).
