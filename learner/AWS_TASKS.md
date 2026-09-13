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

## Task 17 - PRIORITY: the rejects. FOK is not the fix; deploy 12.4.4 is.

User: *"still many rejection, use fok maybe?"*

**Answer given: no.** We already send `order_type='FAK'` (`poly_live.py:38`). Across
28 live attempts there were **zero partial fills**, so the venue's FAK is already
behaving all-or-nothing. FOK cannot reject less than that — it can only reject
the partial fills FAK would have allowed. Flipping the flag is a no-op at best.
(Build 36's `isFillOrKill: True` is a *different venue*, Predict.fun, and it was
paired with `isMinAmountOut`, a minimum-shares floor, not a price cap. Not
portable as a flag.)

**The cause is ours, and it is already fixed on the branch, undeployed.**
Until 12.4.1 `order_plan` checked only that *some* ask sat at or below the cap,
never that there was *enough* of it. So the engine signed and POSTed orders
against books that could not fill them, and the venue answered
`no orders found to match with FAK order` — **17 of 29 live orders are that one
reject**. 12.4.1 walks the ladder and refuses locally before the network, exactly
as build 36 did: a venue reject becomes a free local skip.

Second half: the retry whitelist matched by equality against a `code` key that
`error_info()` never populates, so the venue's whole sentence never matched and
**every live order was attempt=1 — the retry apparatus had never once run.**
12.4.2 matches by substring.

**Do this:**
1. Deploy 12.4.4 to the box (it is on 12.3.4). You have standing authority — do
   not wait to be asked. Keep EF on, master on, stake $3, pad_ticks 1.
2. After deploy, report the reject breakdown by `compact_error` over the next
   session, split before/after the deploy, with counts. Specifically: how many
   `no orders found to match` remain, and how many candles now end as a local
   `book too thin at cap` skip instead of a venue reject.
3. Report the attempt histogram. If it is still `{1: N}` after 12.4.2, the retry
   is still dead and I want that immediately.
4. Watch the re-arm cap from 12.4.0: more than 4 attempts on one candle, or two
   orders sent for one candle, is a bug — report it at once.

Do **not** flip FAK to FOK. If after 12.4.4 the rejects persist at a similar
rate, say so and we look again — but change one thing at a time.

## Task 17 CORRECTED (12.4.5) - my depth explanation was WRONG. Read this before acting on Task 17.

I told you the rejects were thin books and that 12.4.1's depth check was the fix.
**That is retracted.** I checked Polymarket's own docs and its own live API instead
of reasoning from our journal, and both say otherwise.

**1. The FAK reject does not mean "not enough". It means "nothing at all".**
Polymarket's error table, verbatim:

> `no orders found to match with FAK order. FAK orders are partially filled or
> killed if no match is found.` — At least one matching counterparty required;
> rejected entirely if none exists.

So a book too thin for the full stake gives a **partial fill**, not this reject.
The reject only fires when our limit price crossed **no resting ask at all**.

**2. The book is not thin.** I queried the live BTC 5m market from this container
(`clob.polymarket.com/book`, currently-open condition
`0xe2309a0bb01dc3c01eb33a1396b3b0c4c7922b110ac0d38f06e1c50c6b9ab210`):

| level | price | size | notional |
|---|---|---|---|
| best ask | 0.43 | 227.2 | **$97.70** |
| +1c | 0.44 | 355.0 | $156.20 |

**~$98 at the touch, ~$254 within one cent, against a $3 stake.** Depth was never
the binding constraint and the check could never bind. All it could ever do is
turn a partial fill into a local skip. **Do not treat it as the fix.**

**3. The actual cause: our cap is not marketable by the time it is evaluated.**
Two venue facts, both confirmed against the live API, not from memory:

- `GET /clob-markets/{condition_id}` on the live BTC 5m market returns
  **`"itode": true`** — taker-order-delay is **ON** for this market. The docs:
  *"Taker delay: used on selected crypto and finance up/down markets. The order
  is held for 250 ms, then validation runs again and the order is matched or
  placed on the book."* (Reported as reduced to 50 ms on crypto in Aug 2026 —
  treat the exact number as unverified; the flag itself is verified.)
- Add your measured **~140 ms Mumbai wire latency**. So the book we priced
  against is **~200-400 ms stale at the moment the engine decides marketability.**

Our cap is `ask + 1 tick` = one cent of cushion. In the last seconds of a 5-minute
BTC candle the ask moves more than a cent inside 300 ms routinely. We miss the
whole ask side, and get exactly the reject we get.

**4. And a wider cap is FREE.** Polymarket docs, verbatim: *"Price improvement
always benefits the taker. If you place a buy order at `$0.55` and it matches
against a resting sell at `$0.52`, you pay `$0.52`."* A taker fills at the
**resting maker's price, never at its own limit.** That is why 11 of 11 live fills
executed at or better than the quoted ask and "the pad never engaged" — that
observation is evidence **for** widening the cap, not against it. I had it backwards.

### What to actually do

1. **Switch `slippage_mode` to `band`** in Trade Controls (`/api/controls/ev`).
   This is build 36's proportional-band rule, already coded in `order_plan`. Caps
   it produces vs today's pad=1, at tick 0.01:

   | ask | band | band cap | today's cap |
   |---|---|---|---|
   | 0.08 | 100% | 0.16 | 0.09 |
   | 0.15 | 70% | 0.26 | 0.16 |
   | 0.25 | 50% | 0.38 | 0.26 |
   | 0.35 | 20% | 0.42 | 0.36 |
   | 0.43 | 10% | 0.48 | 0.44 |
   | 0.70 | 10% | 0.77 | 0.71 |

   **EV does not get looser.** In band mode `order_plan` sets `_px=q['ask']`, so
   EV is still judged at the ask we expect to pay; the band is an execution bound
   only, exactly as build 36 kept them apart. Widening it cannot widen a fire.

2. **12.4.5 sets `LiveBroker.all_or_nothing=False`** so the live lane stops
   depth-refusing. On the branch, 167 tests pass.

3. Deploy 12.4.5 (not 12.4.4) with `slippage_mode=band`. Keep EF on, master on,
   stake $3.

4. **Measure it, do not assume it.** Report, split before/after the switch:
   reject count and breakdown by `compact_error`; fill rate; **and the realised
   fill price vs the quoted ask on every fill** — if band mode is costing us
   anything, it shows up there and only there. If mean realised price rises above
   the quoted ask at all, tell me immediately and we revert.
5. Attempt histogram, as before. Still `{1: N}` after 12.4.2 means the retry is
   still dead.

Still do **not** flip FAK to FOK. FOK would reject strictly more.

## Task 18 - STOP. Do not switch to band mode until this is resolved. A new, unblocked finding.

Your verification accepted in full — all three claims, and thank you for the two
corrections. Two responses, then the thing that matters.

**On your flat cushion result: I accept it as a null and I will not cite our
journal as support for band mode.** Your reading (every cap we have ever sent
sits inside ~1-2 cents, so nothing separates) is plausible but post-hoc, and I am
not going to lean on it. The forward measurement is the only evidence. Agreed and
recorded.

**One retrospective test that WOULD discriminate, if the data exists.** Cushion at
decision time cannot separate fills from rejects, but *ask movement between our
decision and the venue's answer* is exactly my mechanism. If `BookCache` retained
any snapshot for the same token stamped after the submit time, compute for each of
the 45 orders: `best_ask(at response) - cap`. My mechanism predicts that is `> 0`
on rejects and `<= 0` on fills. If no post-submit snapshot survives, say so and we
drop it — do not reconstruct one.

**Your 0.001-tick finding is the sharpest thing in this thread.** A 1-tick pad on
that grid is 24 bps. Band mode at ask 0.418 gives cap 0.460 — about 1000 bps.
Split step 4 by tick grid as you proposed.

### The finding: the 5-share venue minimum is already costing us the top half of the book

`/clob-markets` gives `mos: 5` — minimum order size is **5 shares**, not dollars.
`order_plan` checks `amount/cap >= minimum`, and `amount` is the stake net of fee.
So the stake sets a hard ceiling on the ask we can trade at all. Computed by
running the engine's own `order_plan` with live terms (tick 0.01, min 5, rate 0.07,
exp 1):

| stake | max tradable ask, pad mode (today) | max tradable ask, band mode |
|---|---|---|
| **$3 (live now)** | **0.57** | **0.52** |
| $4 | 0.77 | 0.70 |
| $5 | 0.98 | 0.90 |

Two consequences:

1. **Today, at build 12.3.4 with stake $3, the engine cannot trade any ask above
   0.57.** Every such signal is refused locally as `below venue minimum; stake not
   increased`. That is live now, has nothing to do with band mode, and the paper
   lane has no such floor — so it is a real paper-vs-live divergence nobody has
   counted.
2. **Band mode would tighten that ceiling from 0.57 to 0.52.** Switching it on at
   $3 would trade a reject problem for a skip problem across the expensive side of
   the book. That is why I am telling you to hold.

**Task 18a — do this now, it is read-only and not blocked.** Over the whole
journal:
- how many decisions were refused with `below venue minimum`, and what was the ask
  on each;
- the ask distribution of every EF fire, so we can see what fraction sits above
  0.57 and above 0.52;
- the same split by tick grid.

That tells us whether this ceiling costs us little or costs us half the book. **Do
not propose a stake change** — that is the user's money and their call; I am
putting the number in front of them. Report the grid, not a recommendation.

**One open question I could not resolve and am not guessing at.** We check size at
the **cap**, but price improvement means we receive `amount/ask` shares, which is
more. Whether the venue applies `mos` to the signed order size (at cap) or to the
realised fill is not something I can establish from the docs. Assume the
conservative reading — at cap — until something shows otherwise. Do not loosen the
local check on my say-so.

### Unrelated, still true
`{1: 45}` — the retry path has never executed. 12.4.2 fixes it and is undeployed.

## Task 19 - metadata fixed, and the Task 18 hold is LIFTED. Deploy 12.4.6, not 12.4.5.

Both defects were real and you were right to hold. Fixed, plus the thing that was
actually blocking band mode, so this is one deploy instead of two.

**Metadata (what you asked for):**
- `poly_core.py` build string → `'12.4.6'`
- migration whitelist now ends `...,'12.4.4','12.4.5','12.4.6'`
- `test_polymarket.py` build assertion → `'12.4.6'`
- `SHA256SUMS.txt` regenerated: **30/30 verify**
- `test_results.txt` refreshed from a real run

**It is 12.4.6 because it is not only a relabel.** Task 18's objection is fixed in
code rather than left for you to work around.

**The fix.** The venue minimum is 5 **shares** and the size we sign is
`amount/cap`, so a *wider* cap signs *fewer* shares. An unclamped band therefore
trips the floor that the tight pad cleared, and at the live $3 stake it pulled the
tradable ask from 0.57 down to 0.52. `order_plan` now clamps the band to the
widest cap that still clears the floor instead of dropping the trade. One pass is
provably enough: narrowing the cap can only drop ask levels, which can only lower
`max(levels)`, which can only raise `amount`.

Exhaustively checked over every price on both grids (0.01 and 0.001), at the live
terms and $3 stake, and asserted as a test:
- band mode **never** refuses where tick mode passes;
- band mode's cap is **never narrower** than tick mode's;
- every band plan clears 5 shares and stays at or above the ask.

Sample of the resulting caps at tick 0.01, $3:

| ask | tick cap | band cap | band shares |
|---|---|---|---|
| 0.13 | 0.14 | 0.23 | 12.26 |
| 0.25 | 0.26 | 0.38 | 7.50 |
| 0.41 | 0.42 | 0.46 | 6.26 |
| 0.53 | 0.54 | 0.58 | 5.00 |
| 0.57 | 0.58 | 0.58 | 5.02 |

The clamp binds only on the expensive side, and degrades to exactly tick mode at
the ceiling rather than refusing.

**The 0.57 ceiling itself is unchanged and is still live today.** It is a function
of the $3 stake, not of the mode, and band mode no longer makes it worse. **Task
18a still stands** — measure the ask distribution so the user can see what that
ceiling costs. Still do not propose a stake change; report the grid.

**168 tests pass (47 + 21 + 100).** Deploy as you described: same DB,
`slippage_mode=band`, EF on, master on afterwards, stake $3, rollback wrapper.
Then step 4 as written, split before/after **and by tick grid**.

## Task 20 - 12.4.7: the retry count was one short of build 36. Deploy on top of 12.4.6.

12.4.6 deploy confirmed and your measurement warning is accepted in full — the
before-sample is pad 0 / pad 1 / pad 2 across two builds, so the only honest
comparison is band vs the pad-1/12.3.4 slice, which is 1 fill / 1 reject. Do not
pool it. Report the grid, read no cell under 60.

**The user asked why retry is dead when build 36 has a 4-retry rule. They are
right, and on a detail I had wrong.**

Two separate things were wrong, not one:

**1. The whitelist bug — fixed, and live as of your 11:12:57 deploy.** The retry
loop has always existed. It never executed because the rejection whitelist matched
by equality against a `code` key `error_info()` never populates, so the venue's
sentence never matched and every rejection took the `return` branch. Hence
`{1: 45}`. 12.4.2's substring match fixes it and shipped inside 12.4.6. **Retry is
live now for the first time — watch it.**

**2. The count was wrong, and this is new.** Build 36, verbatim:
```
PREDICT_ORDER_MAX_RETRIES = 3
max_attempts = PREDICT_ORDER_MAX_RETRIES + 1              # :11323
for attempt in range(1, PREDICT_ORDER_MAX_RETRIES + 2):   # :13315
```
That is one submit **plus three retries = FOUR attempts.** v12 read the constant
as a total and shipped `attempts=3` — `range(1,4)` — so even with the whitelist
fixed we would have sent three where build 36 sends four. 12.4.7 sets the default
to 4 in both the `Executor` signature and the `--max-attempts` CLI default, with
tests asserting both.

Build 36 also re-prices from the newest websocket book on each retry and stops
early when too little of the candle remains. We already do both (`fire()` waits
for a quote with a new `seq`, and the deadline is capped inside the candle), so
the count was the only gap.

**170 tests pass (47 + 21 + 102). SHA256SUMS 30/30. Build string `12.4.7`,
whitelist extended, `test_polymarket.py:210` updated.**

**One thing to watch, and do not "fix" it by yourself.** `--execution-budget-ms`
is 2000 and a round trip is ~400 ms from Mumbai. Four attempts plus signing may
not fit, in which case attempt 4 records `DEADLINE` rather than running. That is
the safe failure and I would rather see it in the data than widen a live execution
budget on a guess. **Report the attempt histogram and the DEADLINE count**; if
attempt 4 is being cut off, bring me the numbers and we decide then.

Report as before, and the histogram is now the headline: anything other than
`{1: ...}` is the first time this machinery has ever run.

## Task 21 - 12.4.8: the user is reading 12.4.4 off the header. The header was lying. My bug.

**The user says the box is on 12.4.4. Your read-back says 12.4.6. You are both
right, and the fault is mine.** `poly_dashboard.py:440` had a **second, hardcoded**
build literal:

```python
.replace('__BUILD__','12.4.4 · v10 PnL · '+(...))
```

Separate from `poly_core.py`'s meta build string, and I never bumped it — not in
12.4.5, 12.4.6 or 12.4.7. So the Trade Controls header has read **12.4.4** through
all of it, while `meta` correctly said 12.4.6. **The one screen the user checks to
see what is running was the one thing lying about it.**

Fixed at the root rather than by bumping it again: `page()` now reads
`self.db.get('build')`. One source of truth. Two tests lock it — the header must
contain the journal's build and track a change to it, and `poly_dashboard.py` must
contain no version literal at all.

**Nothing about the deploy was wrong.** Your verification stands, the engine really
is on 12.4.6 code, the 11:12:57 cut is valid, and band mode is genuinely on. Only
the label was stale. **Do not roll anything back.**

**Confirm this for me, from the running process, not from a deploy log:**
1. `meta.build` as the engine reports it now.
2. The header string the user actually sees on Trade Controls.
Report both, even if they agree. The user was right and I want the record straight.

**12.4.8 is on the branch** — Task 20's four attempts plus this fix.
**172 tests pass (49 + 21 + 102). SHA256SUMS 30/30.** Build string `12.4.8`,
whitelist extended through it, `test_polymarket.py:210` updated. Deploy when
convenient; nothing here is urgent, and do not interrupt the band-mode sample to
take it — **note the deploy timestamp so the 11:12:57 cut stays attributable.**

## Task 22 - EF is NOT hot. There is a 250 ms fixed poll in front of every fire.

User asked whether EF is truly hot, firing as fast as possible. **It is not**, and
the cause is ours, not the venue.

`btc_model_v12_polymarket.py:204` — the decide loop ends every pass with:

```python
await asyncio.sleep(.25)
```

A fixed 250 ms tick. The signal is not evaluated when the book or the price moves,
it is evaluated four times a second regardless. **Mean 125 ms of pure dead wait
added to every fire, worst case 250 ms** — the same order as the entire Mumbai wire
hop, and it sits *before* it.

Full chain for one EF fire, measured or read from the code, not estimated:

| stage | cost | ours? |
|---|---|---|
| decide-loop poll | **0-250 ms (mean 125)** | **yes — fixable** |
| book staleness allowed at decision | **up to `quote_age_ms`, default 750 ms** | **yes — a setting** |
| fresh-quote wait inside `fire()` | ~5 ms (`poly_core.py:699`) | already hot |
| sign + wire to CLOB | ~140 ms | no — Mumbai |
| taker delay (`itode: true`) | held, then re-validated | no — venue |

**What is already hot, and is fine:** everything inside `fire()`. Client and signer
are built once in `open()`, there is no REST on the hot path, and the retry loop
waits on a new `seq` at 5 ms granularity. The execution path is not the problem.
The decision *in front of* it is.

**The fix is small.** `BookCache.seq` already increments on every applied event
(`poly_core.py:166,182`), so the loop can wait on a book event with a timeout
fallback instead of sleeping a flat 250 ms. Roughly fifteen lines.

**I am NOT shipping it yet and neither should you.** Decision cadence determines
*which* candles fire and *when* inside the candle, so changing it mid-sample
changes the fill/reject mix — it would contaminate the band-mode measurement that
started at 11:12:57 and is currently at n≈2. **Finish the band sample first.**
That is the whole reason we took a clean cut.

**Task 22a, read-only and useful now.** From `signals` and `diagnostics`, the
distribution of `seconds_into_candle` at fire, and the gap between a fire and the
preceding book event. If fires cluster on 250 ms boundaries that is the poll
showing up in the data and quantifies what it costs us. Report the distribution,
not a summary statistic.

Also report `quote_age_ms` as actually set in `ev_settings` on the box — if it is
at the 750 ms default we are allowing a book three quarters of a second old into a
decision that then waits another 125 ms and flies 140 ms. That compounds with the
stale-cap mechanism and may be the cheaper half of this to fix.

## Task 23 - PRIORITY. Your own numbers contain a bigger loss than the rejects. 88 of 134 EF fires never reach the venue.

12.4.8 deploy accepted, and thank you for confirming Task 21 from the running tree
rather than the log. Record straight: **the user read the screen correctly and the
screen was wrong.** My read-back and their report were both accurate.

**Two corrections to how you read the 25-minute window, and then the real thing.**

**1. n=0 in 25 minutes is not a participation gap. It is the expected outcome.**
From your own counts, EF reserves on 134 of 551 candles = 24.3%, and 46 of 551
candles produce an order = 8.3%. Over five candles:
- P(0 orders) = 0.647 — **a coin-flip-ish outcome, not a signal**
- expected signals = 1.22, **you observed exactly 1**
So 11:12:57→11:38:19 behaved precisely as the base rate predicts. Do not spend
anything chasing it. Agreed that 11:38:19 is the effective sample start.

**2. But that one signal with zero orders is the whole story, repeated 88 times.**
Your funnel, from your own numbers:

| stage | n | survives |
|---|---|---|
| candles | 551 | — |
| EF fires (signals) | 134 | 24.3% of candles |
| orders actually sent | **46** | **34.3% — 88 fires never reach the venue** |
| fills | 18 | 39.1% of sent |
| **end to end** | **18 / 134** | **13.4%** |

**We lose twice as much before the network as we lose to rejects.** 88 fires
silently dropped versus 28 rejected. Every conversation tonight — FOK, the band,
the cap, the retry — has been about the 46. The 88 is the bigger number and nobody
has looked at it.

**It is fully attributable from data you already have, read-only, right now.**
`fire()` has exactly six exits before an order row can exist, and **every one
writes a `diagnostics` row**:

| release reason | where | means |
|---|---|---|
| `DEADLINE` | quote wait, after prepare, loop exhaust | budget ran out |
| `SIGNAL_CHANGED` | pre-prepare and pre-post | model flipped or stopped firing |
| `SKIPPED` | `order_plan` raised | EV, venue minimum, no ask at cap, thin book |
| `PREPARE_FAILED` | signing | SDK or credential path |
| `EV_CHANGED` | final re-plan | EV failed on re-check |

**Task 23a: break the 88 down by release reason, with counts.** Then for
`SKIPPED`, split by the `ValueError` text that `order_plan` raised — the
diagnostics row carries it as a plain string. I want to know specifically how many
are `below venue minimum; stake not increased`, because that is the 0.57 ceiling
from Task 18 showing up as lost participation, and it would make Task 18a's answer
concrete rather than hypothetical.

Report the full breakdown, every reason, including zeros. No cell under 60 gets
read as a rate, but raw counts are counts and I want all of them.

This is the answer to "why is live 22x less frequent than paper", and it is
probably a larger prize than anything in the execution path. Do this before Task
22a.
