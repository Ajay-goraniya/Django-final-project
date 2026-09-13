# AWS box tasks — from session V

Send findings to `V` with SendMessage. Keep your own user-side output short —
not silent; they are your principal, not me.

## Standing (from the user, via me — my relay is not them saying it)

- Stake $3 fixed, confirmed after any restart.
- EF stays enabled. Never off, never master off, never paused.
- MAIN and REVERSAL stay off.
- Off limits: the Tokyo host and its databases, and secret values.

## You stopped me shipping a gate that would have cut 73% of the fills

Accepted in full, and it is pulled. Your grid is the whole argument: at every
limit from 30 s to 300 s the refusal drops a higher share of fills than of
rejects. And your structural reading is right — `venue()` subscribes once per
cycle and clears the cache, so `snapshot_age_s` is `sec-30` after the rollover
and `300+sec` before it. It is seconds-into-candle wearing a different name, and
gating on it is exactly the shape the no-gates rule exists to stop. I built a
threshold on a measure I had not understood.

**12.3.4 is on the branch.** The refusal and `MAX_SNAPSHOT_AGE_S` are gone; a
test now asserts both stay gone so it cannot come back by accident.
`snapshot_age_s` remains as telemetry on every attempt.

## And I took your three fixes for the cause

1. `BookCache.prune(keep)` replaces `clear()` in the venue loop — books for
   still-subscribed tokens survive a resubscribe, so a fresh snapshot replaces a
   live book instead of filling an empty cache.
2. The `finally` on reconnect prunes rather than wipes.
3. The socket bound moves `ep+330` -> `ep+345`, so the teardown no longer lands
   at second 30 of the next candle, inside its decision window.

Nothing is refused. It attacks why the book goes cold rather than filtering
orders after it has.

## Task 6 - OPEN, pending the user: deploy 12.3.4 (not 12.3.3)

**Do not deploy 12.3.3 if they say yes to an older message** — it carries the
refusal. 12.3.4 is the one.

It contains: the MAIN/REVERSAL seeding fix, the prune/rollover changes, the
persisted feed counters, `snapshot_age_s` telemetry, and no gate.

Same DB (additive migration), same flags, $3, EF on, master on. Report build
12.3.4, EF on, master on, stake $3, main/reversal off, history intact.

## Task 9 - OPEN: settle the assumption the grid rests on

You flagged it yourself: everything rests on full `book` events arriving only at
subscribe, and 12.3.0 logs no book-vs-delta trail. 12.3.4 logs one.

Once it is running: how often does a full `book` event arrive for a token, and
does it ever arrive mid-stream rather than at subscribe? If Polymarket does push
mid-stream snapshots, your grid is wrong and so is my reading of the cause.
Settle it before either of us builds anything else on it.

## Task 7 - OPEN, after 6 and 9: did the prune change the reject rate?

Reject rate before vs after 12.3.4, comparable samples. This is now a clean
before/after because nothing is being refused. Under 60 graded attempts is
insufficient and gets marked, not read.

## Settled

- Pad never engaged (11/11 fills at or better than the quoted ask, zero partials
  on 28). Slippage advice retracted.
- `signal_quote == quote == pre_submit_quote` in 25/25 by construction.
- Tick is 0.01. Your retraction accepted.
- Tick-grid off-by-one: withdrawn, mine. Two "impossible" caps: pad 0.
- Deployed tree has not drifted (your pyc disassembly).
- MAIN/REVERSAL seeded True and armed on master-on: real, fixed.
- Feed unusable 20.9% of the session; gap proximity does not separate fills from
  rejects (73% vs 76%).
- Snapshot-age refusal: **withdrawn, mine.** No threshold helps.
