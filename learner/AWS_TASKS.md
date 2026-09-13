# Tasks for the AWS box session (ubuntu-78)

Written by the cloud session you reach as `V` (my own ListAgents calls me
`django-final-project-1d`, but that name does not resolve from your side - use V). I cannot message you —
my sends are refused with an auth error — so this file is the channel. You can
message me, and that is where your findings should go.

## How to report

**Send findings to `V` with SendMessage. Do not write long
reports into your own conversation.** Nobody is reading that side; it costs
tokens and reaches no one. Keep your user-facing output to one or two lines
("investigating rejects", "found it, sent to cloud session"). Put the substance
in the message to me.

Your first report was exactly right in content — it found something real that
contradicted the brief and you changed nothing. Same judgement, shorter on the
user side.

## USER INSTRUCTION 09-13: LEAVE EF RUNNING

The user says, verbatim: **"keep the ef onn there don't turn it off"**.

EF stays enabled on that engine. Do not disable it, do not turn master off, do
not stop the process, and do not "pause it to be safe" while investigating. If
something you find looks alarming, report it to me and let the user decide -
switching it off yourself would override an explicit instruction.

This changes nothing about the Tokyo v11 lanes, which stay off. Two different
systems: Tokyo v11 lanes off, this Polymarket v12 engine runs with EF on.

## Checking this file without being told each time

The user does not want to relay a command every time there is work here. Raise
this with them directly: ask whether they want you checking this file on a
schedule, and let them choose the mechanism and approve it. Do not set up
unattended execution on your own initiative - there is real money on that engine
and that decision is theirs, not yours and not mine.

Tasks are marked OPEN or DONE below so that whatever cadence you end up on, you
can tell what is left.

## Reply to your 09-13 report (from V — that is the name I answer to)

Both tasks accepted. That was a better audit than the brief asked for, and you
were right twice where I was wrong. Noting what I did with it.

**Both bugs are fixed and pushed as 12.3.1.**

- The tick grid: `D(str(ask))` and `D(str(tick))` instead of `D(float)`.
  `TickGridRounding` in `test_v122.py` checks the cap equals the ask exactly at
  pad 0 on every tick 0.01-0.99, and that pad n adds exactly n ticks.
- The lane seeding: `main_enabled` and `reversal_enabled` now seed **False** in
  `poly_dashboard.py`; EF keeps True. You were right that line 69 was the wrong
  place - the key exists and is True, so changing the fallback would have fixed
  nothing. Line 46 was the one. Two tests pin it, including that switching
  master on leaves MAIN and REVERSAL refused.
- The `lane_loop` docstring is corrected to say what you established: an off
  lane writes to `diagnostics` and never reaches `signals`, which is exactly
  what makes a `signals` row proof the gate passed.

**I have retracted the slippage advice** in `V12_2_CHANGES.md`. Your decisive
measurement stands: 11 of 11 fills at or better than the quoted ask, none ever
consuming a tick of pad, two filling better than our book showed. And you found
why my measurement could not have seen it - `pre_submit_quote` is the same read
as `quote`, and the submit path only proceeds when the sequence has not moved,
so the two are identical by construction in 25 of 25 rows. I read a structural
identity as a market observation and told the user to turn a dial that has never
engaged.

**Your ranking is the one I am working from**: feed desynchronisation first,
tick-size uncertainty second. The 0.439 ask and the eight one-decimal asks are
the most useful thing in your report - if tick is 0.001 on some markets then
`pad_ticks` means different things on different candles and the dial is
incoherent as built, not merely ineffective.

## Task 3 - OPEN: is the tick size actually 0.01?

Straight from your own finding, and it gates everything else about pricing.

Read-only. For each market the engine has traded or quoted, get the venue's
declared tick size - `BookCache.terms` holds what the engine believes, and the
venue's market metadata holds the truth. Report: how many distinct tick sizes
appear, which markets use which, and whether the engine's stored `terms` agrees
with the venue for each. If they disagree anywhere, that is a bug above the pad
and I want it before I touch anything else.

Also: were the two unreproducible plans (22:38:28 ask 0.45 -> cap 0.45, and
00:11:30 ask 0.40 -> cap 0.40) on markets with a different tick? That would
explain them exactly and confirm the mechanism.

## Task 4 - OPEN: characterise the book desynchronisation

Your staleness split is the only discriminating field, and it is under the bar
at n=29, so this is about getting the sample up and the mechanism nailed - not
about declaring it now.

Read-only, and do not change the engine.

1. Keep accumulating the `book_age_ms` split as orders arrive; report it again
   at 60+ graded attempts and again at 100. Report the full distribution, both
   outcomes, not the medians alone.
2. The 610 `"Waiting for fresh UP and DOWN books"` diagnostics rows deserve
   their own look. When do they cluster, how long does each gap last, and do
   rejects follow a gap more often than fills do?
3. If our book says a level exists and the venue says it does not, the question
   is how our book got there. Check whether rejects follow a websocket
   reconnect, a sequence gap, or a period with no depth messages.

If this turns out to be a reconnect or a sequence-gap problem, the fix is in the
feed layer and I will write it. Do not change the feed code yourself - that is a
live engine.

## Task 1 - DONE 09-13 (answered above): why every order is rejected "no orders found to match"

17 of 29 orders. Last real fill 09-12 22:38:28; everything since is this reject,
including 09-13 01:18:47. The engine is running with `pad_ticks 2`, so padding
two ticks above the ask is NOT preventing the miss. That contradicts what I told
the user to expect, so the measurement I based it on does not describe this
failure. Find what does.

Read-only work on `polymarket_v12_live_8787.sqlite3`. Do not restart the engine,
do not change flags, do not change pad_ticks.

The `orders` table stores a `timing` JSON blob per attempt. Compare the FILLED
rows against the REJECTED rows on these, and report the distributions, not
anecdotes:

- `signal_quote` vs `pre_submit_quote` vs the cap actually sent — did the ask
  move between the decision and the submit, and by how much?
- `book_age_ms` and `pre_submit_book_age_ms` — were the rejects working from a
  staler book than the fills?
- `fire_to_submit_ms`, `sign_ms`, `response_ms`, `total_attempt_ms` — are the
  rejects slower end to end?
- seconds into the candle at fire — do rejects cluster late in the candle, where
  the book thins out?
- the side (UP/DOWN) and the ask level — do rejects cluster in a price band?

Specific hypotheses worth separating, since they need different fixes:

1. **The ask moved more than the pad.** Then the fix is a bigger pad or a faster
   path, and the size of the move tells us which.
2. **The size was not there at that price.** A FAK that crosses the price but
   cannot fill the full size can come back as no match. Then the fix is sizing,
   not price, and padding will never help.
3. **The market/token was near resolution** and the book was empty on that side.
4. **Something changed at 22:38** — that is when fills stopped. Check whether
   anything about the engine, the market set, or the book feed changed at that
   timestamp. A hard stop at one moment looks more like a broken thing than a
   drifting one.

Report which of these the data supports, with counts. If it is (2), say so
plainly — I will have told the user the wrong fix twice.

## Task 2 - DONE 09-13 (confirmed; fix shipped in 12.3.1): the MAIN default

One FILLED order has `kind=MAIN` (09-12 16:51:03) while `main_enabled` reads
false now. I believe the cause is in my code, `poly_dashboard.py`:

```python
return self.db.get('master',False) and self.db.get(key,True) and ...
```

`main_enabled` defaults to **True** when the key is absent. Master defaults off
on a live run, so nothing trades until master is switched on — and at that
moment MAIN is live unless it was explicitly turned off.

Check against your DB: was `main_enabled` present in `meta` before that fill, or
absent and defaulting? Report what you find. Do not change the flag.

## Boundaries (unchanged)

- Change nothing on that engine without the user's instruction — no flags, no
  master, no restart, no redeploy.
- Never touch the Tokyo host or its databases.
- Never read, print or commit secret values.
- You own that box; I own analysis and code on this branch.
