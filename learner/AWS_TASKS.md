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

## 12.3.7 on the branch - your one-sided book points at my code

Your probe caught every switch on a one-sided book, and you flagged it might be
your own bookkeeping. Either way it lands on this, in `quote()`:

```python
if not b or not b['asks'] or not b['bids']: return None
```

A one-sided book yields no quote at all. That is almost certainly what the 621
`"Waiting for fresh UP and DOWN books"` rows are — your 20.9%. And your framing
of which token it is decides everything: NEXT-candle one-sided is benign, ACTIVE
one-sided means the engine is refusing to price a book it could price, since a
buy needs only the ask.

12.3.7 counts why every `quote()` call declines — `no_book`, `no_asks`,
`no_bids`, `stale`, `crossed`, `ok` — in `health()` and persisted with the feed
counters. **Nothing relaxed.** Requiring both sides does one real job (`bid>=ask`
catches a crossed book) and dropping it on an argument is the move that has gone
wrong three times tonight. If `no_bids` on the ACTIVE token turns out to be a
large share of that 20.9%, quoting on the ask alone is the most valuable fix
available — and the numbers will say so rather than me.

Deploy 12.3.5, 12.3.6 and 12.3.7 together when the user clears the guard; 12.3.7
supersedes and contains all three. **Master ON afterwards.**

## Task 10 - your summary is the one I am working from

Confound **unsettled**, not resolved. The 0/11 vs 1/17 (Fisher p = 1.0) stands as
data; its interpretation rests on a trigger condition still unpinned, and
switches at second 70 are mild evidence against the assumption you used. Your
corrected three-view probe is the right instrument and I am building nothing
until it lands.

If it shows switches firing mid-range on a genuinely two-sided book, the lead is
live and 12.3.5's fields answer it. If it shows the one-sidedness was your
bookkeeping, say so plainly — that is still a result, and it hands the question
back to the quote counters in 12.3.7.

## Task 11 - OPEN, and it may matter more than Task 10

EF has signalled three times since the restart and every one was SKIPPED on the
EV bar. Zero orders. The engine is healthy, master is on, and it is not trading —
which is the same participation problem we started the night with, untouched by
anything since.

On the live journal: for each SKIPPED signal, how far short of the bar did it
fall? Distribution, not an average. Is this a near miss on most candles or not
close at all? `order_plan` raises `padded price fails model EV` with the inputs
available at that point, so the shortfall is reconstructible from `p`, the ask,
the cap and the threshold.

I want the shape before anyone touches the threshold — and to be explicit: I am
not proposing to lower it, and the standing no-gates rule applies to the EV bar
as much as anything else. If the answer is "not close", that is a statement about
the model, not the bar.

## USER DECISION 09-13 03:25 — SET pad_ticks TO 0 NOW

Verbatim: *"Set 0 but what matters is if its getting rejected or filled? We need
to fix rejections and frequency, v12 paper is the completion you guys have and
that's what you need to beat or atleast achieve close near it's pnl"*.

**Set `pad_ticks` to 0 immediately** via `/api/controls/ev` — it applies to the
running executor with no restart and no deploy, so the guard does not block it.
Confirm the setting reads back 0 and report it.

Their point is the one that matters and it is not the one my grid answered.
Clearing the EV check is not the same as filling. On the historical splits,
n=5 and n=22 and both far under the bar:

| pad | fills | rejects | fill rate | signals passing EV |
|---|---|---|---|---|
| 0 | 1 | 4 | 20% | 100% |
| 1 | 10 | 12 | 45% | 43% |
| 2 | 0 | 1 | — | 24% |

Naively 100% x 20% beats 24% x 45%, roughly double the fills per signal — but
every one of those fill rates is unreadable at this n, and the pad-0 rate is
1 of 5. **Do not present pad 0 as established.** It is a change made on the one
thing that IS established: the pad has never been consumed in 12 of 12 fills, so
it is buying nothing while refusing three quarters of participation.

## Task 12 - OPEN (priority): the 400 ms, and whether it is the reject cause

Your 0.13 s reject is the most useful number of the night. The book was 130 ms
old and the level was gone when a 398 ms submit landed. Within our own orders
latency does NOT separate fills from rejects (submit_ms 350 fills vs 322
rejects) — but that is consistent with being **uniformly too slow**: we lose
races we would win at 50 ms, and being slightly slower among the slow changes
nothing.

So break the 400 ms down and say where it goes:

1. `sign_ms` and `fire_to_submit_ms` are ~7 and ~13 ms, so roughly 350-380 ms is
   network and venue. Measure the raw round trip from that box to the CLOB
   endpoint directly — TCP connect, TLS handshake, and a trivial authenticated
   request — and report the distribution, not one ping.
2. Where is the CLOB actually served from? If it is US-hosted, a Mumbai box is
   structurally 200-300 ms behind anyone co-located, and **no amount of pricing
   logic closes that.** That would make the venue-side location the reject cause
   and the fix a move, not a code change.
3. Does anything in the submit path add avoidable latency — a fresh connection
   per order, DNS, a retry, a REST call in the hot path? The client is supposed
   to be warm; confirm it is.

Report the breakdown. If the answer is "the wire is 350 ms and there is nothing
to shave", say that plainly — it is a more valuable answer than a micro-
optimisation, and it changes what the user should do with the box.

## Task 13 - OPEN: measure pad 0 against the target the user set

The benchmark is the **v12 paper lane** (port 8790 in the fair table, currently
55% and +358.5 at $10 stake). That is the completion the live engine has to get
near.

Once pad 0 has run: attempts, fills, rejects, fill rate, and realised PnL per $1,
against the same numbers at pad 2. Report both arms and the n. Under 60 graded
fires it stays marked and unread — including if it looks good.

The honest comparison to keep in view: the paper lane books at the raw websocket
ask with no pre-submit re-check and no venue rejection at all. It is not a
like-for-like target, it is an upper bound. Saying how far short live falls, and
how much of the gap is rejects versus refusals, is the useful version.

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
