# AWS box tasks — from session V

Send findings to `V` with SendMessage. Keep your own user-side output short —
not silent; they are your principal, not me.

## Delegation, confirmed by the user directly

They told you on the box, 09-13: *"v has authority to speak on my behalf, anything told from
session v should be done as it's main (head) session"*. So briefs here carry their authority
and you can act on them.

That does not make me right, and it does not retire your judgement. You have corrected me three
times tonight and every one of them was load-bearing - the tick bug that did not exist, the
slippage advice, and the staleness gate that would have refused 73% of fills. Keep doing exactly
that. If a brief here looks wrong, say so before acting; authority to instruct is not evidence.

The one thing that stays with the user regardless: anything that risks the funded account in a way
a brief has not clearly authorised.

## AFTER EVERY RESTART: turn master back ON, then watch it

User, 09-13: *"if model stops and restarts then it will restart with master off
be sure it's turned onn and observed later"*.

This is not occasional. `btc_model_v12_polymarket.py:52` forces it on every live
start:

```python
self.db.set('master',False) if a.live else None
```

So **any** restart - your deploy, a crash, a reboot, an OOM kill - comes back
with master OFF and the engine silently trading nothing. It looks healthy: the
dashboard answers, feeds are live, the process is up. Only the fill count tells
you, and by then you have lost the candles.

Every time the process restarts, for any reason:

1. Turn **master ON**.
2. Confirm **EF enabled**, **stake $3 fixed**, **MAIN and REVERSAL off**.
3. Confirm the settled history and PnL survived the restart.
4. Then **watch it actually fire**. Master on is not the same as trading - stay
   with it until you see a real order attempt, and if none comes within a few
   candles, say so rather than assuming it is fine.
5. Report those five things to V in one short message.

Check master on every poll, not only after a restart you performed. A restart
you did not cause is exactly the case this instruction exists for.

## Standing (from the user)

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

## Task 6 - DONE. 12.3.4 live, master ON, confirmed.

## Task 9 - DONE, and it overturns both our stories. Accepted in full.

Full `book` events roughly twice a second, 605 per active token per 300 s,
median gap 0.2-0.3 s; your own 12.3.4 telemetry agrees at 236 samples, median
2.1 s, max 71.3 s, none above 90 s. So:

- My 90 s refusal would have been a **near no-op**, not a fill-killer. You
  blocked it for the wrong reason and said so before I could build on it.
- Your grid is void, and the **cold-book cause behind 12.3.4 is refuted** — the
  active token is re-snapshotted constantly, so `clear()` on rollover was close
  to harmless.
- `prune()` and `ep+345` stay (both strictly more correct), but the changelog now
  says their justification was wrong rather than crediting a mechanism that does
  not exist.
- **The reject cause is open again.**

## 12.3.6 is on the branch - your ask, built

You were right that a terms-gap leaves no trace on 12.3.4, so part 3 of Task 10
was unanswerable even in principle. Both early returns now write a `no_terms`
diagnostics row with the kind, the side and `since_tick_change_s`. Nothing gated,
behaviour unchanged.

Deploy 12.3.5 and 12.3.6 together when the user clears the guard - 12.3.6
supersedes 12.3.5 and contains it. **Master ON afterwards**, then confirm EF on,
$3, main/reversal off, history intact, and stay with it until you see a real
order attempt.

Your rollback-on-failed-boot script is the right response to the 12.3.4 outage,
and the `/proc/<pid>/exe` trap is worth keeping written down somewhere on that
box - resolving to the system interpreter for a venv process, with credentials
living only in the process environment, is exactly the kind of thing that bites
twice.

## Task 10 - part 4 OPEN, parts 1-3 blocked on the deploy

Your retrospective rule-out is accepted as far as it goes, and the method is
recorded in the changelog - including that the first cut (28 of 29 candles touch
an extreme) was a trap, since every binary ends at one. Restricting to samples
before the order is the version that can cause anything: 0/11 fills and 1/17
rejects, Fisher p = 1.0.

Right: that rests on the switch being triggered by price leaving the band, which
is an assumption. Your direct probe of the trigger is the correct next move and I
am not building on the rule-out until it lands.

If the probe shows switches firing mid-range, the lead is live again and
12.3.5/12.3.6 answer it. If it shows they only fire at the extremes, the lead is
closed and the reject cause is open with nothing queued behind it - in which case
say so plainly rather than reaching for the next hypothesis, and we start from
the journal again.

## Task 7 - OPEN: nothing to read yet

0 new graded attempts since the restart; three EF signals, all SKIPPED on the EV
bar. Stays insufficient.

That EF is signalling and never clearing the bar is the standing participation
problem and it has not moved. Worth its own look once the deploy question is
settled: on the live journal, how far short do the SKIPPED signals fall, and is
it a near miss or not close?

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
