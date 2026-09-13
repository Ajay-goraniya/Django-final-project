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

## Task 13 - the benchmark, now measured. Read this before comparing anything to it.

V runs the v12 paper lane in its own container, so I measured it rather than
guessing. 237 graded trades in `v12_poly_weekend.sqlite3`:

| | paper (8790) | live (your box) |
|---|---|---|
| graded trades | **237** | **11** |
| win rate | 53.2% | 63.6% |
| per $1 | **+0.1288** | **+0.3463** |

**The live edge per trade is not worse - on this sample it is better.** n=11 is
unreadable as PnL, so take the ratio: paper made **22x** as many trades. The gap
is entirely participation.

What paper assumes that live cannot have, straight from the table:
- 237 of 237 PAPER_FILLED - no venue rejection exists in that lane;
- 237 of 237 filled at exactly `quote_ask`, `avg_fill_price > quote_ask` in zero
  rows - slippage is structurally impossible;
- quotes average **680 ms** old, max **9,974 ms**; 27 of 237 exceed the 750 ms
  the live path requires, so a tenth of its trades are not legally attemptable
  live.

So +358.5 is an upper bound built on no rejection, no slippage and a stale quote.
**Do not report live as failing against it.** The comparison that means something
is per-$1 edge (live already matches) applied to trade count (live is at 1/22nd).

When you report pad 0: attempts, fills, rejects, fill rate, and per-$1 against
the same at pad 2. Both arms, with n. Under 60 graded fires it stays marked and
unread, including if it looks good.

## 12.3.8 on the branch - the audit you made necessary

I could not tell from here whether the user set pad 1 or whether it was the
silent revert, and that is the real problem. `Journal.set` was a bare
`INSERT OR REPLACE`, so a control changing value left nothing behind - which is
why the Tokyo flag reverts have been unreconstructable for two days.

Control writes now record **old value, new value and the calling frame** for
`master`, the three lane flags, `ev_settings`, `stake_settings`, `next_stake`,
`halt`, `sx_enabled`, `tp`, `sl`, `rules`. Same value written twice records
nothing, so the trace is changes only. Next time a flag moves on its own, the
diagnostics row names the code path.

Ruled out while looking, so you do not repeat the search: the `/api/controls/ev`
handler only assigns `pad_ticks` when `slippage_ticks` is in the request, so a
mode-only change cannot reset it; `renderEv()` fills the control from
`ev.slippage_ticks` rather than a default. Your fallback observation was the
right instinct though - `pad_ticks()` does return exactly 1 when the key is
absent, which is what made it look like a default being re-applied. The key was
present, so it was stored, not fallen back to.

Minor fix in the same build: the slippage control offered 0-3 while the endpoint
accepts 0-5, so two valid settings were unreachable from the dashboard.

## Standing correction: do NOT assume pad 0

The user's 03:25 decision was 0. It never applied. The engine ran pad 2 until
~03:41 and pad 1 since. **Tonight's execution numbers span three pad values with
changeover times known only to the minute** - treat them as three small unpooled
samples, not one series, and say so in any comparison you report.

When a deliberate pad value is finally set, note the exact timestamp in your
report so the samples can be cut cleanly.

## Task 14 - OPEN, once 12.3.8 is deployed: who writes the controls

With the audit in place, report every `control_write` row: key, old, new, and the
stack. In particular whether anything writes `ev_settings` or a lane flag that is
not a dashboard request. If nothing does over a full day, that is also an answer -
it puts the Tokyo fault outside this code path.

Your three `snapshot_age_s` rows: agreed, n=3 and the fill sits between the two
rejects, so it supports nothing either way. The 0.132 s reject remains the useful
one - it rules out staleness for that reject regardless of the ordering. Not
building on three rows.

## 12.4.0 on the branch - the two defects the user named

**1. EV now gates the decision instead of judging it afterwards.** The model
decided against the raw ask and the padded-price check ran later inside
`order_plan`, so a signal was drawn on the chart as fired and only then refused.
`decide_now()` now runs the same arithmetic at the price we would really pay and
returns `fire: False` with a reason when it cannot clear. It can only narrow a
fire, never widen one, and records `ev_gate`, `ev_gate_pad`, `ev_gate_ask`,
`ev_gate_cap`.

**Consequence for your reporting:** the fire count will drop and the SKIPPED
count will go to near zero, because refusals now happen before the signal rather
than after it. That is not a regression and it is not the engine trading less -
it is the same trades, honestly labelled. Any before/after across this build must
say so, and **do not compare fire counts across 12.4.0** without that caveat.

**2. A refused candle re-arms.** The reservation is PRIMARY KEY(epoch,kind), so
one refusal used to own all five minutes. `Journal.release()` now frees the
candle when nothing reached the venue (SKIPPED, DEADLINE, SIGNAL_CHANGED,
EV_CHANGED, PREPARE_FAILED); anything that did reach it (FILLED, REJECTED,
UNKNOWN, PENDING) still consumes it, so an order that may have landed can never
re-fire. Capped at 4 attempts per candle, counted in a new `candle_attempts`
table, each re-arm logged as `candle_rearmed`.

**Watch this one on deploy.** It is the only change tonight that can increase
order volume. If you see more than 4 attempts on any candle, or two orders sent
for one candle, that is a bug and I want it immediately.

## Task 15 - OPEN: read build 36's slippage rules

The user: *"still many orders are rejected as the build 36s slippage rules are
not applied"*. They are right that this build reinvented slippage instead of
porting what already worked.

Find build 36's slippage handling in the repo and report what it actually does -
not a summary, the rule. Then we port it rather than invent a third version. If
you cannot find it on that box, say so and I will locate it here.

## Task 16 - OPEN: what is missing from Trade Controls

The user: *"many things are not adjustable from trade control pannel"*. I have no
list. Enumerate what the engine reads from `meta` or from CLI flags that has no
control in the panel, and rank by what would actually be changed while running.

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
