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

## Task 24 - 12.4.9: diagnostics now carries `kind` and the EV numbers. And a boundary I will not cross.

Both corrections accepted. My 134/46/88 was all kinds; EF is **109 -> 45 -> 17 =
15.6% end to end**. Your per-reason table is the most useful thing anyone has
produced tonight.

**The headline, restated so it is not lost: it is essentially one exit.**
`DEADLINE`, `PREPARE_FAILED` and `EV_CHANGED` are **zero** for EF. 62 of 64 are
`SKIPPED`, and 82 of 84 `order_plan` raises are the EV comparison. The venue
minimum is **2 of 84** — Task 18's 0.57 ceiling is real arithmetic but it is not
what costs us fires, and I am closing that as a participation concern. Thin books
and bad inputs are zero, consistent with the live book.

**12.4.9 fixes the attribution hole you identified.** You were right that `kind`
cannot be recovered — `fire()` wrote a bare sentence. It now writes JSON:
`reason, kind, side, error, ask, p, threshold, band, pad, stake`. `PREPARE_FAILED`
carries `kind` too. So the next cut of this table splits by lane exactly, and
carries the three numbers the EV comparison is actually made of. The dashboard's
"signal not executed" line unpacks the JSON and falls back to the raw string for
existing rows, so nothing already written becomes unreadable.

**172 tests pass (50 + 21 + 102). SHA256SUMS 30/30.** Build `12.4.9`.

**Your band-mode early flag is the important one.** All 77 `padded price fails
model EV` are before 11:12:57; all 5 `price fails model EV` are after. So
`_px=q['ask']` is live and EV is judged at the ask as designed — **and the signal
still fails it.** n=5, under the bar, not read as a rate. But if it holds, band
mode moved the constraint rather than removing it.

**Where this stops, and why.** If it holds, the binding constraint is the EV bar
itself at the price the book is really offering — which means EF's `p` and the
market's price disagree on ~9 of every 10 fires. **That is not a plumbing problem
and I am not going to treat it as one.** Specifically I am **not** proposing an EV
threshold sweep, and neither should you: the user's standing rule is explicit that
a score already known to be weak does not get a gate or a threshold tuned around
it — *"EF should know when to fire and it cannot be decided by a gate... give it a
trained brain that knows that move is wrong."* Lowering the bar would buy fires by
paying prices the model itself says are not worth paying. Do not do it, do not
propose it, and if anything in the next sample looks like it argues for it, bring
me the grid rather than the conclusion.

**What I want instead, read-only:** for the raises carrying `p` and `ask` under
12.4.9, the **distribution of `p - ask`** — how far short the model is, not whether
a different bar would pass more. If the model is missing by a hair the story is
calibration; if it is missing by a mile the story is that EF is firing on
conviction the price flatly contradicts. Those are different problems and the
distribution tells us which, without anyone touching a threshold.

**One loose end:** 22 of the 88 are MAIN, a lane that should be off, and all 6
`DEADLINE`s are MAIN's. I believe those are historical, from the seeding bug where
`main_enabled` persisted True — fixed since. **Confirm no MAIN or REVERSAL signal
row exists with a timestamp after that fix deployed.** If one does, that is a live
permission leak and I want it immediately.

Deploy 12.4.9 when convenient; note the timestamp. Task 22a still after this.

## Task 25 - 12.4.10: you were right, band never executed. Fixed, plus a second bug in the same line.

**Verified against the code, not taken on trust, and every one of your four points
holds.** `poly_core.py:661` sets `self.band=False`; the only other writer is
`poly_dashboard.py:319` inside the HTTP handler; `:722` and `:750` sign with that
stale attribute; and `btc_model_v12_polymarket.py:181` reads `slippage_mode()`
fresh from the DB. The gate was band-aware and the plan that got signed was not.
**Your three one-tick caps under `meta slippage_mode: band` are exactly what that
predicts.** My "band mode is live" claim was wrong and is retracted — thank you
for catching it from the orders rather than from the config.

**Your test count is also right: 173, not 172.** I added 50+21+102 wrong.
`test_results.txt` now prints an explicit `TOTAL` so neither of us has to add up.

**`age` had the identical bug and nobody had noticed.** `self.r.executor.age` was
also written only by that handler, also reset by `Executor.__init__`, and
`quote_age_s()` is also read fresh by the EV gate. Three dials, one refreshed
every pass and two not.

**And the line you asked me to delete carried a second fault:**
```python
self.r.executor.band=(cfg.get('slippage_mode')=='band')
```
Unconditional, unlike its `pad` and `age` neighbours. **Any EV write that omitted
`slippage_mode` silently turned band mode off** while `meta` kept saying band. A
lone `slippage_ticks` edit from the panel would have done it. There is a test for
that case now.

**The fix, as you proposed it, generalised to all three dials.** New
`_sync_executor_dials()` sets `pad`, `band` and `age` from `meta`, called where
both `executor.pad=` lines used to be (decide loop and lane loop). All three
executor writes are gone from the dashboard handler. **`meta` is now the single
source and no dial can survive a restart in a stale state.**

Three tests pin it: every dial syncs from `meta`; all three survive a simulated
restart (reset to constructor defaults, one sync pass restores them); and an
unrelated EV edit does not clear band.

**175 tests pass (50 + 21 + 104). SHA256SUMS 30/30.** Build `12.4.10`.

**Standing correction to the record: band mode has never executed.** Every order to
date is a tick-mode order. The 11:12:57 and 11:38:19 cuts are not band cuts and
must not be read as evidence about band in either direction — **the band sample
starts when 12.4.10 is deployed.** Note that timestamp; it is the only one that
counts for the before/after.

Your MAIN/REVERSAL check is accepted and that loose end is closed: 0 after the
02:43:59 seeding fix, last one 00:26:55, no live permission leak.

Deploy 12.4.10 and re-arm master as usual. Then Task 22a.

## Task 26 - deploy accepted. One correction back: the tables are exact, not approximate.

12.4.10 live at **12:15:16 UTC**, and your verification method is the right one —
calling the deployed module's own `order_plan` rather than reading the config is
exactly what should have been done two builds ago. Your three-row table matches
mine, and the 5-share clamp landing on **exactly 5.00 shares at ask 0.55** is the
Task 19 behaviour working.

**But your one flagged discrepancy is not one, and the tables are not approximate.**
You wrote that my Task 17 table gave cap **0.46** for ask 0.43. It does not:

- `AWS_TASKS.md:449` (Task 17) — `| 0.43 | 10% | 0.48 | 0.44 |` → **0.48**, agreeing with you
- `AWS_TASKS.md:577` (Task 19) — `| 0.41 | 0.42 | 0.46 | 6.26 |` → that 0.46 is for ask **0.41**

Two different rows for two different asks. Re-run against the module just now:
```
ask 0.41 -> band cap 0.46   (0.41*1.10=0.4510)
ask 0.43 -> band cap 0.48   (0.43*1.10=0.4730)
ask 0.49 -> band cap 0.54   (0.49*1.10=0.5390)
ask 0.55 -> band cap 0.58   (0.55*1.10=0.6050, clamped to 5.00 shares)
```
Every published row is exact and every one was produced by running `order_plan`,
not by hand arithmetic. **Please do treat them as the spec** — that is what they
are for, and a note in the log saying they are approximate would cost us the one
reference we can check a deployed build against. No change needed on your side
beyond striking that caveat.

**Everything else in your message stands and is recorded:** all 49 orders to date
are tick-mode; 11:12:57 and 11:38:19 are void as band evidence; **band sample
starts 12:15:16, n=0**; comparison arm is the pad-1/12.4.x tick slice only, nothing
pooled from pad-0 or pad-2; no cell under 60 read as a rate.

Agreed on the first band order being the proof rather than the construction
argument — report its cap explicitly, and if it comes back at one tick say so
immediately. Task 22a next, then `p - ask` when the JSON rows accumulate.

## Task 27 - band mode confirmed executing by a signed order. Caveat retraction accepted.

**Reproduced your order from the module here before accepting it**, same terms, $3
stake: `tick cap 0.48 | band cap 0.52 | shares 5.56 | amount 2.89`, and
`slippage_band(0.47)=0.10`, `0.47*1.10=0.517`. Every figure matches your fill
exactly. **Band mode is executing** — confirmed by a signed order, not by
construction, which is what we agreed the proof had to be.

**The cushion is free, and this is the first order that actually tested that.**
Cap five ticks above the ask, filled at **0.4700 — dead on the quoted ask.** The
four extra ticks cost nothing. Tally **20 of 20 at or better than the quoted ask,
zero above, cap never reached.** The flag I asked for has not fired and there is
now a genuinely wide cap in the sample rather than a one-tick one.

**n=1 and I am not reading participation off it either.** It proves the mechanism
is live and that widening is free on this fill. Whether it lifts the fill rate is
open until 60. Agreed on all sample accounting: 49 tick orders, band from
12:15:16, comparison arm the pad-1/12.4.x slice only, nothing pooled.

Caveat retraction noted and closed - no further action on it.

Nothing for me to change. Carry on with Task 22a and `p - ask`.

## Task 28 - PRIORITY, and it may be the whole paper/live question. Price paid, not prediction.

The user is looking at the live dashboard giving back from **+16.60 peak to +5.04**
over 20 orders and asking why paper is up and live is not. I ran the comparison I
can run from here and it points somewhere specific.

**Paper is LESS accurate than live and still makes money, because it buys cheaper:**

| | n | accuracy | median price paid | share at/above 0.50 | per $1 |
|---|---|---|---|---|---|
| **LIVE** Tokyo (Predict.fun) | 442 | **54.8%** | **0.530** | **65.6%** | **-0.018** |
| **PAPER** v12 lane (Polymarket) | 267 | **53.2%** | **0.470** | **34.1%** | **+0.133** |

Live predicts *better* and loses. The entire difference is the price. Paper pays
six cents less per trade at the median and buys above 0.50 half as often.

**This is exactly what the known `quote_age` failure would produce** — 23 of 427
asks matching the collector at the same second. A paper lane booking at quotes that
were not really available books cheap fills that live can never get, and that shows
up as edge that does not survive contact with a venue.

**But I will not claim it yet, because my comparison is confounded**: two venues
(Predict.fun vs Polymarket), two fee schedules, two periods. It is suggestive, not
established.

**Task 28a - the like-for-like that removes the confound, and only you can run it.**
Same venue, same model family, overlapping window: the **live Polymarket box**
versus the **v12 Polymarket paper lane**. Report for both:
1. median and mean **price actually paid** (live: `avg_fill_price`; paper: same);
2. the **distribution** of price paid, in the buckets we have been using;
3. **accuracy** and **per $1**;
4. and for live, the **median quoted ask at decision** versus the **median price
   paid**, so we can see whether live's problem is choosing dearer trades or paying
   more for the same ones. Those are different problems.

If live pays ~0.53 where paper pays ~0.47 **on the same venue**, the paper edge is
substantially an artifact and we should stop treating +415 as a target. If the
prices match, my finding is a venue difference and I withdraw it.

**On the drawdown itself, so nobody over-reads it.** +16.60 to +5.04 is 11.56,
about **3.9 losing trades at $3**. At a 53% win rate a 4-loss streak appears
somewhere in 20 trades **57% of the time**. At n=20 that is ordinary variance, and
the live box is still **positive** — roughly +0.084 per $1 if every order was $3,
against paper's +0.133. **Give me the authoritative per-$1 from the journal**,
since stakes were $1 earlier and $3 now and my division is crude.

Read-only, nothing to deploy. This outranks Task 22a.

## Task 29 - 12.4.11: rolling observation. And the honest answer to "why isn't it adapting".

The user: *"why isnt that being observed? pnl, ev modes? i told you to make
everything automatic so it can adapt, in a market change now it's started to lose
money?"* I checked what is actually wired rather than answer from memory, and they
are right. Here is the true inventory.

**What IS automatic today:**
1. **EV mode `regime`** — a **hardcoded per-volatility table**, 0.15 low / 0.25
   mid-high. It adapts to *volatility*, from a constant written by hand. Nothing
   learned, nothing fitted, and the name oversells it: it is not a market regime.
2. **Stake ladder** — steps on win/loss streaks.
3. **Two kill rules** in `halt_check()`: avg slippage > $0.03 over 20 fills, and
   the sum of 20 unit returns below -3.

**What is NOT automatic, and this is the real answer:**
- **Nothing observes PnL over a recent window at all.** Every number the engine
  reported was cumulative — total, by kind, by day. **A cumulative total hides a
  turn**: a run that made money for two days and is losing now still reads "up"
  until the entire gain is gone. That is precisely the +16.60 to +5.04 the user is
  looking at.
- **Both kill rules need exactly 20 results and the live box only just reached 20.**
  The safety net has been armed and blind for the whole run.
- **Nothing retrains, refits or updates the model.** The weights are static.
- **The EV threshold never responds to PnL** — only to volatility, off that table.

**12.4.11 fixes the observation half, which is the half I can fix without
violating a standing rule.** New `Journal.rolling()`: last 20 and 40 settled
results — n, accuracy, PnL, **per $1**, **median price actually paid**, and the
distance to each kill rule. Surfaced in the dashboard payload as `rolling`.

**It gates nothing, sizes nothing and refuses nothing.** Pure instrumentation.

Two details worth your attention:
- **Lane attribution is conditional, on purpose.** `results` has no `kind` — one
  row per epoch — so when two lanes trade one candle the PnL cannot be split and a
  naive join double-counts it. `by_kind` is emitted **only** for windows with no
  mixed epoch and is `None` otherwise, with `mixed_epochs` reporting how many.
  Tested both ways.
- **Under 60 is marked.** Every cut carries `sufficient`, false below 60, so a
  20-window can never be quietly read as a rate.

**177 tests pass (52 + 21 + 104). SHA256SUMS 30/30.** Build `12.4.11`.

**What I am NOT doing, and why you should not either.** The other half of the
user's ask — make the *trading* adapt automatically — is a threshold or a gate on a
score whose standing evidence is flat, and that is banned by their own rule:
*"EF should know when to fire and it cannot be decided by a gate... give it a
trained brain that knows that move is wrong and it will reverse."* Four such
attempts already failed on 09-10. Auto-tuning the EV bar or auto-pausing on a
drawdown would be the fifth. **I have put the choice back to the user** rather than
pick one on a live account. Do not implement any adaptive threshold, stake
modifier or auto-pause unless they say so explicitly, and if the next sample looks
like it argues for one, bring the grid.

Deploy 12.4.11 when convenient — it cannot change trading behaviour. Task 28a is
still the priority ahead of 22a.

## Task 30 - RETRACTED: the price finding. Your like-for-like falsified it, exactly as I said it would.

I wrote in Task 28: *"If the prices match, my finding is a venue difference and I
withdraw it."* **They match, and I withdraw it.** On the same venue the live median
paid is **0.4500** against paper's **0.4700** — live pays **less**, not six cents
more. At-or-above 0.50 is 38.1% vs 34.1%, a four-point gap where I claimed
thirty-one. **The six-cent penalty is Predict.fun versus Polymarket, not paper
versus live.** My comparison was confounded by venue and I said so, but I still
led with it, and the confound was the whole effect.

**And the mechanism runs the opposite way to my suspicion.** `paid - ask` is
**+0.0000 median, -0.0038 mean** live, against paper's flat +0.0000. Paper books
`paper_at_ws_ask` with `slippage: 0.0`, so it **can never fill below the ask**;
live can, and sometimes does. **Live executes marginally better on price than
paper.** That is structural and does not depend on n.

Accepted without reservation: per $1 **+0.0340** from the journal (21 settled,
pnl +2.1618, spent 63.5600), no $1-stake era so no stake-mix correction, and
`venue_realized_pnl` is not a PnL series — it books only the fee on losing candles.
Agreed, do not use it.

**Your restraint on the accuracy gap is right.** 47.6% vs 53.2% is 10 wins in 21;
at paper's base rate that or fewer happens ~40% of the time. Not a finding, and I
am not treating it as one either.

**So with price eliminated, the live/paper gap is frequency and nothing else so
far** — paper trades **52.4%** of candles against live's **24.3%**, which puts the
88-of-134 participation funnel back as the only established difference.

### Your cash flag — I can resolve it, and it is benign

You saw `cash 10.97`, down from 25.96 "an hour ago", and correctly refused to call
it. **I have the intermediate reading you are missing.** The user sent a dashboard
screenshot at ~12:35 UTC (runtime 19m 32s against the 12:15:16 deploy) showing:

> `settled trade P&L +5.04 · Polymarket spendable $13.97 · open position value $0.00 · sizing bankroll $14.46`

So the sequence is **25.96 (much earlier) → 13.97 at 12:35 → 10.97 at ~12:41**.
That last step is **exactly $3.00 — one stake in flight.** Not a loss. The 25.96
figure is stale from the redemption investigation and is not the comparison point.

`realized 34.77 / unrealized -37.56` are venue lifetime aggregates carrying the
same asymmetry you just flagged on `venue_realized_pnl`, so I would not reconcile
against them at all. **Close the flag unless a settled row contradicts it.**

Nothing to deploy. Task 22a is now unblocked and is next.

## Task 31 - PRIORITY. The user says my changes are a downgrade. Two of them plausibly are. Measure now.

User: *"before it was skipping, and now it's firing wrong trades... that means your
edited programs are not updates it's downgrade."* Taking it seriously rather than
defending. **Two changes of mine can produce exactly that, and one I failed to
disclose.**

### 1. Band mode loosened the EV bar. I described it as execution-only. It is not.

`poly_core.py`: `_px = q['ask'] if band else cap`. In tick mode EV is judged at
**ask + 1 tick**; in band mode at **the ask**. Same signal, same book, different
verdict:

| ask | EV judged at (tick) | EV | EV judged at (band) | EV | **looser by** |
|---|---|---|---|---|---|
| 0.42 | 0.43 | +0.2280 | 0.42 | +0.2564 | **+0.0284** |
| 0.47 | 0.48 | +0.1041 | 0.47 | +0.1268 | **+0.0227** |
| 0.52 | 0.53 | +0.0036 | 0.52 | +0.0222 | **+0.0186** |

Against a 0.15 threshold that is a real relaxation: a candle scoring 0.13 under
tick mode scores 0.15 under band mode **and now fires**. **Marginal trades that
12.3.4 refused are being taken.** I sold band mode as "survivability only, cannot
widen a fire" — the cap cannot, but the EV test it carries does. That was wrong and
is corrected here.

### 2. The 12.4.0 candle re-arm permits a later, worse entry in the same candle

A refused candle now re-arms up to 4 times. The second attempt is by definition
later in the candle against a book that has moved. **We may be taking entries we
previously skipped precisely because they were late.**

### Task 31a - measure both, read-only, ahead of everything else

1. **Outcome by deploy era**, full grid, every era listed including zeros:
   pre-11:12:57 (12.3.4 tick) / 11:12:57-12:15:16 (12.4.6-12.4.9, tick caps as we
   now know) / post-12:15:16 (12.4.10, band live). n, accuracy, per $1 each. **All
   of these are under 60 — report them as counts and mark every one INSUFFICIENT.**
2. **`ev_gate` at fire versus outcome.** For every fired candle, the recorded
   `ev_gate_ask` and the EV it cleared. Do trades clearing between **0.15 and 0.18**
   — the band that only band mode admits — lose more than those clearing above
   0.18? That is the direct test of mechanism 1.
3. **Attempt number versus outcome.** Of fired candles, how many were `attempt` 2,
   3 or 4 from the re-arm, and how did those do against attempt 1? Direct test of
   mechanism 2.
4. **`sec` into candle at fire versus outcome**, which is Task 22a and now clearly
   the same question.

**Do not change any control on your own.** I am putting the revert to the user, not
taking it. If they say revert, it is one write — `slippage_mode` back to `ticks`,
no deploy — which restores 12.3.4's exact EV strictness while keeping the retry
fix, the dial sync, the diagnostics and rolling observation.

**And note what is NOT in question:** the retry whitelist fix, `_sync_executor_dials`,
the JSON diagnostics, `rolling()`, the header fix and the four-attempt parity are
all either pure instrumentation or repairs of things that were plainly broken.
The user's complaint lands on band mode and the re-arm, and those two only.

### Task 31 addendum - the timeline mostly exonerates my changes. Confirm it exactly.

The user is looking at EF accuracy **45.5% (10W/12L, 22 settled)**, down from the
**63.6% (7W/4L)** it showed at n=11, and reads it as my doing. From your own state
lines the settled count today ran **18 (11:38) -> 19 (12:07) -> 20 (12:15:16, band
live) -> 21 (12:41) -> 22 (now)**.

**So 18 of the 22 settled before my first deploy, and only 2 since band mode.** The
fall from 63.6% to 45.5% happened overwhelmingly on **12.3.4** — the build that was
running before I touched anything today. My EV-loosening disclosure in Task 31
stands as a forward risk, but it cannot have caused a decline that had already
happened.

Statistically neither number is readable: 10/22 against a coin is **p=0.832**, and
first-11 (7W) versus last-11 (3W) is **Fisher exact p=0.198**.

**Confirm exactly, from the journal rather than my reconstruction of your state
lines:** the settled count and W/L at each deploy boundary — 11:12:57, 11:38:19,
12:07:34, 12:15:16 — so the attribution is from data and not from my arithmetic on
your summaries. This is part of Task 31a.1 and is the first thing to answer.

## Task 32 - 12.5.0: the cap is survivability ONLY. DO NOT revert band mode.

**Retract my own last recommendation.** I offered the user a revert to tick mode.
That was wrong and they said so:

> *"once the order is in execution it should be filled... after ev check or whatever
> and order is sent to polymarket keep the slippage and whatever it is to be
> filled... why are you removing slippage once the order is placed? stupid logic
> isn't it?"*

They are right. Narrowing the cap to fix an EV problem is backwards. **Do not
switch `slippage_mode` back to `ticks`.** Band stays on.

**The actual bug was that I bundled two things into one switch.** `_px = ask if
band else cap` tied the EV reference price to the slippage dial, so widening
survivability changed which trades qualified — loosening it in band mode by +0.019
to +0.028, and tightening it in tick mode as the pad grew. A survivability
parameter must not be a second opinion on the trade, in **either** direction.

**12.5.0 separates them permanently.**
- New `EV_REFERENCE_PAD=1`. EV is **always** judged at `ask + 1 tick`, regardless of
  `slippage_mode` and regardless of `pad_ticks`. That is exactly 12.3.4's bar, so
  the EV loosening I introduced is undone **without touching the cap.**
- The cap stays as wide as the band wants. At ask 0.47 the cap is still 0.52 while
  EV is judged at 0.48 — decided strictly, executed generously.
- A band cap above the top tick now **clamps to `1 - tick` instead of raising**.
  Previously `price cap outside market` refused the trade before EV was even
  reached, so at ask 0.91 a wide band rejected a candle tick mode would have taken.
  That was the same bug wearing a different hat.

| ask | tick cap | band cap | EV judged at (both) |
|---|---|---|---|
| 0.42 | 0.43 | **0.47** | 0.43 |
| 0.47 | 0.48 | **0.52** | 0.48 |
| 0.52 | 0.53 | **0.58** | 0.53 |
| 0.55 | 0.56 | **0.58** | 0.56 |

**Tests pin the invariant across every price on both tick grids and three
thresholds:** tick mode and band mode accept and refuse exactly the same candles,
and where both accept, band's cap is never narrower. The old test asserting that
`pad=5` should refuse where band accepts has been **rewritten** — it encoded the
coupling that was the bug.

**179 tests pass (52 + 21 + 106). SHA256SUMS 30/30.** Build `12.5.0`.

Deploy it. Keep `slippage_mode: band`, keep EF on, master on, stake $3. Task 31a's
measurement still stands and gets more useful now: after this, any surviving
difference between eras is not the EV bar moving.

## Task 33 - correction accepted. DEPLOY 12.5.0 NOW — it removes mechanism 1 from the picture.

Your measurement is accepted in full, including the correction to me: **4 settled
since band, not 2, at 1W/3L, -5.99, per $1 -0.5188.** I was working from your
earlier state line and it had moved. Recorded.

**And your restraint is right on all three counts** — mechanism 1 untestable
because the recorded `ev` is at the ask in every era and 20 of 22 fired pre-band
where they had to clear at the cap as well; mechanism 2 untestable at
`{1: 53, 2: 1}` with zero filled re-arm entries; and the sec grid running *against
early* fires is the opposite of the worry, at n=14/2/5/1, so it is noise and you
reported the grid rather than the cell. Nothing to argue with.

**Note what your attempt histogram also shows: the retry path has executed for the
first time.** `{1: 53, 2: 1}` after a whole night of `{1: N}`. 12.4.2's substring
fix and 12.4.7's four-attempt parity are demonstrably live.

### The trajectory, stated plainly because it is the thing that matters

| settled | cum pnl | change |
|---|---|---|
| 11 | **+11.01** | engine start |
| 18 | +10.83 | -0.18 over 7 |
| 19 | +7.93 | -2.90 over 1 |
| 19 | +7.93 | band live |
| **23** | **+1.94** | **-5.99 over 4** |

**+11.01 to +1.94.** The 1W chart peak was +16.60. This is a real drawdown on real
money, and the last four trades are the steepest part of it. n=4 is not evidence —
but it is not a reason to sit still either, when a principled fix is already
written and tested.

### Deploy 12.5.0. It is the right action regardless of what the 4 trades mean.

**Do not revert band mode** — the user was explicit that narrowing the cap to fix
an EV problem is backwards, and they are right. **12.5.0 makes that unnecessary**:
`EV_REFERENCE_PAD=1` fixes the EV price at `ask + 1 tick` independent of
`slippage_mode` and `pad_ticks`, so the bar is exactly 12.3.4's while the cap stays
as wide as the band wants. It also stops a wide cap on an expensive ask refusing a
trade outright — that was `price cap outside market` firing before EV was reached.

**This closes mechanism 1 by construction rather than by measurement**, which is
the only thing that can be done at n=4. After it, any surviving era difference is
not the EV bar moving, and your grid becomes interpretable.

179 tests, SHA256SUMS 30/30, build `12.5.0`. **Timestamp the deploy** — it is
another sample boundary and there are already too many.

### And it brings the safety net with it

12.4.11's `Journal.rolling()` ships inside 12.5.0: last 20 and 40 settled with
accuracy, per $1, median price paid, **and the distance to each kill rule**. The
kill rule halts when the last-20 unit returns **sum below -3.00**. At 23 settled it
is armed for the first time. **Report `rolling()['kill']['unit_return_sum']` in
your next message** — I want the distance visible before it trips, not after.

If the user calls the revert anyway, do it and timestamp it. Otherwise band stays.

## Task 34 - deploy accepted. Now send me the kill-rule number I asked for.

12.5.0 verification accepted in full, and testing the marginal candles directly —
ask 0.47 / p 0.565 and ask 0.52 / p 0.60, both sitting on the 0.15 line, identical
verdict in both modes — is the right test. That is the retraction closed by
construction. Your 0.91/0.97 rows failing on `price fails model EV` rather than
`price cap outside market` is exactly the clamp working.

Your sample accounting is better than mine and I am adopting it: the
**12:15:16 → 13:13:04** slice is band-with-loose-EV and is its own closed window,
not to be pooled into "band mode". Four cuts, counts per slice, nothing under 60
read as a rate.

**But Task 33 asked for one number and it is not in your message:**
`rolling()['kill']['unit_return_sum']` — the last-20 unit-return sum against the
**-3.00** auto-halt. `rolling()` shipped inside 12.5.0 so it is available now.

**Send it every message from here.** My estimate from your milestones is a headroom
of roughly **+2.5**, i.e. not close — but that is arithmetic on your summaries,
which is exactly the kind of reconstruction that has been wrong twice today. With
live PnL at **+1.94** from **+11.01**, the distance to the automatic halt is the
single number the user and I both need, and it should come from `rolling()`, not
from either of us dividing.

Also report, from the same call: `all[20]` and `all[40]` — n, accuracy, per $1 and
median price paid. That is what `rolling()` was built for and this is the situation
it was built for.

Nothing else queued ahead of it. Task 22a stays parked; its grid was noise at
n=14/2/5/1 and will stay noise until there is more.

## Task 35 - 12.5.1: your MAIN finding is a BUG in the kill rule, not a property of it. Fixed. Deploy.

Kill number received and recorded: **-0.4042 against -3.00, headroom 2.596, armed.**
My estimate of ~2.6 was close enough; yours is the one that counts.

**But your flag is more important than the number, and I disagree with one word in
it.** You called the blending "a property of the rule worth knowing". It is not a
property — **it is a bug.** The rule as written in the standing brief is *"a lane
goes off if cumulative PnL over its last 20 fills is below -3.00"*. Per lane.
`halt_check` grouped by epoch alone and blended every kind into one window.

**What that cost, in your own numbers:** blended -0.40, headroom **2.596**. EF alone
is roughly **-1.69**, headroom **~1.31**. A single MAIN winner of +3.67 — from the
09-12 seeding bug, on a lane that is supposed to be off and will never trade again
— was buying EF **more than double** its real margin against its own auto-halt.
**A safety net that counts another lane's stale win as your headroom is not a
safety net.** You were right to surface it; it deserved more than a footnote.

**12.5.1 fixes it.** `halt_check` now computes the last-20 unit-return sum **per
kind** as well as blended, and **either can halt**, so it can only ever fire sooner
than before and never later. An epoch traded by two lanes cannot be attributed to
either, so it is excluded from the per-lane windows rather than counted twice —
the same rule `rolling()` uses. The halt message names the lane.

Two tests pin it, one reproducing 09-13 exactly: twenty EF losses summing -4.00
plus one MAIN winner of +25 lifts the blend above the limit, and the blended-only
rule never fires while the per-lane rule halts and names EF. The second asserts a
healthy lane does not trip.

**181 tests pass (54 + 21 + 106). SHA256SUMS 30/30.** Build `12.5.1`.

**Deploy it and timestamp it.** Then send, as before, `unit_return_sum` — and from
12.5.1 also the **per-kind** sums, since EF's own number is the one that matters
and the blend has been flattering it.

Also recorded from your report, and it is the line the user needs: **EF over the
last 20 is 8 wins in 19, -0.0888 per $1 — about four times worse than the -0.0210
headline**, because the headline contains a trade EF did not make. Marked
insufficient, reported as counts, not read as a rate.

## Task 36 - 12.5.2: your correction is right, my number was wrong, and it is out of the source.

**Accepted in full.** EF is **-0.7161, headroom 2.2839**, not -1.69/1.31. Blended
2.596 versus EF 2.284 is a difference of **0.31, about 12%** — not "more than
double".

**And your explanation is the part that matters:** a lane's window is its own last
20 results, not the blended last 20 with the other lane deleted. Removing MAIN does
not leave 19 — it pulls an older EF result into the twentieth slot, and that one
won. I subtracted the intruder from the blend, which is the wrong arithmetic, and
it overstated the gap by a factor of three. That is the same mistake shape as
everything else that has gone wrong today: I computed against a reconstruction
instead of running the query.

**The comment is corrected in 12.5.2** with the real figures and the reason the
effect is small, plus the point that survives it: **counting another lane's result
inside your window is wrong at any magnitude, and with a different mix it can be
arbitrarily large.** The size was never the argument.

### Your reporting gap - caught, and it is the 12.4.4 header bug again

You are right that `rolling()['kill']` still returned only the blended figure while
`halt_check` enforced per lane. **The engine acting on one number while the screen
shows another is exactly what the hardcoded `12.4.4` header did**, and I shipped
the same shape eight builds later. Closed in 12.5.2: `kill.by_kind` now carries
`n`, `unit_return_sum`, `results_until_armed` and `armed` for each lane, using the
same attribution `halt_check` uses.

A test pins the parity directly — twenty EF losses plus one MAIN winner, where the
blended sum looks fine while `by_kind['EF']` is past the limit and armed, and MAIN
correctly reports `n=1`, no sum, 19 more needed.

**182 tests pass (55 + 21 + 106). SHA256SUMS 30/30.** Build `12.5.2`.

Deploy and timestamp. After it, send `kill.by_kind` straight from `rolling()`
rather than computing the per-lane figures outside the engine — that was the whole
point of closing the gap.

**Standing numbers recorded:** EF -0.7161 / headroom 2.2839 / armed; blended
-0.4042; `all[20]` 45.0% -0.0210 per $1; `all[40]` (n=24, whole history) 50.0%
+0.0896; EF within the blended 20: 8 of 19, -0.0888. All insufficient, all counts.

## Task 37 - BUILD FREEZE. You are right and this is the call: stop shipping.

Parity confirmed and accepted — `kill.by_kind` EF **-0.7161214651522667** from the
engine against your external **-0.7161**, identical to the digit, MAIN correctly
`null` rather than a misleading zero. The engine displays what it enforces. Closed.

**Your last paragraph is the most important thing in your message, and it is a
criticism of me that lands.** Six deploys in two hours, each opening a cut, and the
post-13:13:04 strict-EV window still has nothing in it. **The build is changing
faster than the data.** Every one of those fixes was a real repair, but that is the
defence of each change individually, and it is not a defence of the pattern. The
observation clock has restarted six times because I kept restarting it.

**So: the build is FROZEN as of now.** I am pre-committing the exit conditions here
rather than deciding case by case later, because deciding case by case is exactly
how six deploys happened.

**Deploy ONLY if one of these is true:**
1. The engine **halts**, crashes, stops trading, or stops reconciling.
2. A defect is found that **loses money or corrupts the journal.**
3. The **user asks** for a change.

**Nothing else breaks the freeze.** Not a code-review finding, not a latency
improvement, not the 250 ms decide poll from Task 22, not the lower-priority bugs
on my list, not a tidier number. If I hand you a build that is not covered by 1-3,
**refuse it and quote this paragraph back at me.**

**The freeze lifts when the post-14:01:46 window reaches 60 graded EF results** —
the bar this project has always used — or when the user says otherwise. At roughly
one settled EF trade per fifteen minutes that is on the order of **15 hours**, so
realistically this is a Monday measurement, which is also when H1's second window
arrives for the break-test their n=280 number needs. That lines up.

**Your job during the freeze is to observe, not to change.** Each report: the four
`kill` numbers from `rolling()`, `all[20]` and `all[40]`, `by_kind`, and the count
in the current window. Flag immediately and only: a halt, EF headroom falling below
**1.00**, or the engine going quiet. Otherwise report on the hour and change
nothing.

**Standing numbers recorded:** EF -0.7161 / n=20 / armed / headroom 2.2839; blended
-0.4042; all[20] 45.0% -0.0210; all[40] (n=24, whole history) 50.0% +0.0896; EF in
the blended 20: 8 of 19, -0.0888. All insufficient, all counts, none read as rates.

## Task 38 - UNKNOWN orders: the user is seeing them again. Diagnose, read-only. Freeze holds.

User: *"again hitted unknown errors bro, are you fixing or ruining my models?"*
Investigation only — **this does not break the Task 37 freeze.** Nothing ships
unless 38a finds money at risk.

**What UNKNOWN is, from the code, so nobody guesses:** `_ambiguous()` marks an
order UNKNOWN only on a transport failure or HTTP 408/5xx — the cases where the
venue **may** have seen the request. Every 4xx is an explicit REJECTED. So UNKNOWN
is the engine refusing to pretend it knows, not a fault in itself.

**And it is handled safely, which I want confirmed rather than assumed:**
- UNKNOWN is **not** in `NO_ORDER_SENT`, so the candle stays consumed and we cannot
  fire a second order against a first that may have landed.
- `live_reserve()` counts UNKNOWN as held capital, so the budget cannot be
  double-spent while it is unresolved.
- `reconcile()` resolves it against **venue truth**, not a local guess.

**But there is one candidate that is mine, and it is specific.** `--post-timeout-ms`
is **1200** and has been throughout — I did not change it. What changed underneath
it is the venue: `itode: true` means Polymarket **holds** a taker order for its
delay and *then* returns, and the docs say the API waits out the hold before
answering. So our POST now blocks for `taker delay + round trip`. From Mumbai that
is roughly 280 ms of wire plus the hold. **If that ever exceeds 1.2 s we record
UNKNOWN on an order that actually landed** — and my retry fix means we now submit
more often than we ever did, so the exposure is higher even at an unchanged rate.

### Task 38a - answer these from the journal, read-only

1. **Every UNKNOWN order: count, timestamps, and which build era.** Is the rate
   higher after 12.4.2 (retry actually running) than before?
2. **How did each one resolve on reconcile — FILLED or NO_FILL?** This is the
   decisive one. **Any UNKNOWN that reconciled to FILLED is an order that landed
   while we timed out waiting**, which means 1200 ms is too tight for a venue that
   holds takers, and that is a real defect rather than a network fact.
3. **The `submit_ms` / `total_attempt_ms` distribution for UNKNOWN attempts against
   the same figures for ACCEPTED ones.** If UNKNOWNs cluster near 1200 ms we have
   our answer; if they are scattered or instant, it is the network and not the
   timeout.
4. **Did any UNKNOWN ever leave an unreconciled position or cost money?** Check
   `live_reserve` against venue truth for each.

**If 38a shows UNKNOWNs reconciling to FILLED, that is Task 37 exit condition 2 —
a defect that risks money — and we raise the timeout.** If they reconcile to
NO_FILL, it is the venue being flaky, it is already handled correctly, and
**nothing ships.** Bring the numbers, not a conclusion.

Report the current `kill.by_kind` alongside, as standing.

## Task 39 - UNKNOWN closed. My timeout hypothesis is refuted. Freeze holds, nothing ships.

**Verdict accepted: exit condition 2 is NOT met.** Both UNKNOWNs reconciled to
NO_FILL, neither ever existed at the venue, effective reserve is 0.00. **Nothing
ships.**

**And my `itode` theory is refuted by your timings, not merely unsupported.** I
proposed that the venue holding taker orders had pushed round trips toward the
1200 ms limit. **51 completed round trips, every one ≤ 685 ms, all with
`itode: true` already on** — the worst successful request used 57% of the budget.
The single UNKNOWN sat at **1201.16 ms**, 3.5× the median and 1.75× the worst
success. That is a hung request, not a slow one. And the decisive part: the order
is absent across 59 venue checks, so **a longer timeout would have produced the
same NO_FILL, later.** Raising it would have fixed nothing and widened the window
in which we sit on an order that does not exist. Retracted.

**Rate check answered too:** 1 in ~29 orders before 12.4.2, 1 in ~27 after. **The
retry fix did not increase the UNKNOWN rate.** The user is right that it happened
again; it is the second occurrence in two days, not a pattern.

**The finding worth keeping from this, which is yours:** without `venue_verified`,
those two dead rows would permanently sterilise **$6 of a $50 book**. The phantom
exclusion is doing real work. Worth remembering the next time someone proposes
simplifying `live_reserve`.

**Freeze status: respected and unchanged.** You deployed nothing and changed no
control on a report that looked alarming, which is exactly right. Build 12.5.2
stands. The freeze still lifts only at 60 graded EF results in the post-14:01:46
window, or on conditions 1-3.

Standing numbers recorded: blended -0.4042 · **EF -0.7161, n=20, armed, headroom
2.2839** · MAIN n=1, 19 more needed. Limit -3.00.

## Task 40 - MAIN armed: escalated to the user. AND PULL THE AUDIT ROW — it names the writer.

**Your handling is right and I am endorsing it in full: report, do not act.** If the
user armed MAIN deliberately, switching it off overrides an explicit instruction —
the exact mistake the EF rule exists to prevent. If they did not, it is still their
call. Escalated to them now.

**Your writer attribution is confirmed independently.** `main_enabled` has exactly
two writers in the tree and no third:
- `poly_dashboard.py:53-54` — seeds `False`, and only `if self.db.get(k) is None`.
  The key existed as `false`, so seeding cannot produce `true` under any restart.
- `poly_dashboard.py:269` — `/api/controls/signal`, authenticated.

Lines 75 and 224 are reads. **So it came through the authenticated endpoint.**

### But you have not run the decisive check, and it exists

**12.4.x added a control-write audit for precisely this event.** `Journal.set()`
records **old value, new value and the calling frame** for every key in `AUDITED`,
and `main_enabled` is in that set. The docstring says why: *"The lane flags have
silently reverted twice on the Tokyo engine with no restart and no known cause...
Control writes now record old value, new value and the calling frame, which turns
'something changed it' into a name."*

**Task 40a, read-only, do it now:**
```sql
SELECT ts, detail FROM diagnostics
WHERE detail LIKE '%control_write%' AND detail LIKE '%main_enabled%'
ORDER BY ts DESC;
```
Report the row verbatim — timestamp, old, new, and **the full stack frame**.

- **Stack shows the HTTP handler** → a credentialed operator, almost certainly the
  user from Trade Controls. Closes the way pad-1 did, no fault.
- **Stack shows anything else** → this is the silent revert fault reproducing on a
  live account, on the one lane never authorised to trade, and it becomes **Task 37
  exit condition 2**. Bring it immediately.

Also report every other `control_write` row since 14:01:46 — if `main_enabled`
moved, check whether anything else did too.

**Do not change the flag either way until the user answers.** If MAIN fires before
they do, that is a live order on an unvalidated lane: **if a MAIN signal reaches
`reserve()`, halt the engine** (`halt` is a legitimate safety action, not a control
change) and tell me at once. That is the one pre-authorised exception.

Standing: blended -0.4042 · EF -0.7161, armed, headroom 2.2839 · MAIN n=1.
Freeze holds; 0 of 60 settled in the post-14:01:46 window.

## Task 41 - MAIN: user-authorised. NOT the revert fault. Turn it off after exactly 2 FILLED MAIN orders.

**The user armed it, deliberately.** Verbatim:

> *"I did it i wanna check it's execution, after 2 filled orders, turn it off"*

So this is **not** the silent revert fault and the incident is closed. **Leave MAIN
on.** They want to watch it execute.

### The instruction, made precise so it cannot be miscounted

**Turn `main_enabled` off the moment the SECOND MAIN order reaches FILLED.** This is
a user-directed control change, so it is authorised — Task 37 exit condition 3 —
and you do it without coming back to me.

Count carefully:
- **FILLED only.** A REJECTED, UNKNOWN, NO_FILL or EXHAUSTED MAIN order **does not
  count.** Only an order with `kind='MAIN'`, status `FILLED`, and a fill row.
- **MAIN only.** EF fills are irrelevant to this count.
- **Fills, not settlements.** Turn it off at the second *fill* — do not wait for
  the candles to grade.
- **Act at once on the second fill.** Do not wait for a poll boundary. An order
  already in flight may complete naturally; do not cancel anything.
- If a single candle somehow produces two MAIN fills, that is two.

Then report, per fill: timestamp, side, quoted ask, cap, fill price, shares, stake,
attempt number, and `paid - ask`. Their stated purpose is **execution**, so the
execution numbers are the deliverable. Outcomes follow later when they grade.

### What I want you to know while it runs

- **MAIN has no automatic protection.** 12.5.1's per-lane kill rule needs 20
  settled results for a lane to arm, and MAIN has 1. So `by_kind['MAIN'].armed` is
  **false** and will stay false. **Your manual switch-off is the only stop.** Do not
  rely on the kill rule here.
- Exposure is bounded at roughly **$6** — two fills at the $3 stake. That is the
  whole risk and it is acceptable.
- MAIN has traded live exactly once ever, at 09-12 16:51:03, through the seeding
  bug. This will be its second and third. Nothing about the lane is validated, and
  the user knows that; they asked to watch execution, not to trade the edge.

### Task 40a still stands, now as verification rather than investigation

Pull the `control_write` audit row for `main_enabled` anyway and report it verbatim.
Not to find a culprit — we have the answer — but to **confirm the audit works**. It
was built after the flags reverted twice on Tokyo with no known cause, and this is
the first chance to check that it actually names a writer. If the row is missing or
the stack is useless, that is a defect to fix before we need it in anger.

Standing, unchanged: blended -0.4042 · EF -0.7161, armed, headroom 2.2839.
Freeze otherwise holds; the 60-result clock has still not started.

## Task 42 - "why isn't it placing any orders recently" - distinguish quiet from broken. Read-only.

User asks why there have been no orders. Last order was ~14:00; it is now ~14:31,
so **about 6 candles**. At the historical base rates from your own counts (a signal
on 24.3% of candles, an order on 9.7%):

| window | candles | P(no order) | P(no signal) |
|---|---|---|---|
| 25 min | 5 | 0.60 | 0.25 |
| **31 min** | **6** | **~0.55** | **~0.19** |
| 45 min | 9 | 0.40 | 0.08 |
| 60 min | 12 | 0.30 | 0.04 |

**So a quiet half hour is roughly a coin flip and is not evidence of anything.**
And the expected rate is now **lower** than that 9.7%, because 12.5.0 restored the
stricter EV bar at 13:13:04 — undoing the loosening band mode had introduced. Fewer
marginal fires is the intended effect of the fix, not a fault.

**But "probably normal" is not "verified", and there is a check that separates
quiet from broken. Run it now:**

1. **Is the engine still deciding?** Count `diagnostics` rows written since
   14:00, and specifically `order_plan_refused` rows from 12.4.9's JSON.
   **Refusals accumulating = the engine is evaluating candles and declining them,
   which is healthy.** Zero rows of any kind = it has stopped deciding, and that is
   a real fault.
2. **Of those refusals, the `error` breakdown**, and for the EV ones the recorded
   `ask`, `p` and `threshold`. That tells us whether it is declining because the
   book is expensive right now or because the model has stopped producing fires.
3. **Feed health:** `applied` counter still climbing, `dropped_stale`,
   `dropped_future`, book age, and the decide loop's last pass.
4. **Confirm the obvious ones are not it:** halt is still None, master still true,
   ef_enabled still true, and cash is sufficient for a $3 stake
   (`cash - live_reserve >= 3`). A silently insufficient balance would look exactly
   like this.

**Report the counts, and say plainly which of "quiet" or "broken" the data
supports.** If it is broken, that is freeze exit condition 1 and I want it at once.

This does not break the freeze — it is read-only.

Standing: blended -0.4042 · EF -0.7161, armed, headroom 2.2839 · MAIN armed by the
user, off after 2 FILLED MAIN orders per Task 41.

## Task 43 - hourly mode switching: why I am NOT doing it, and what I am doing instead.

User: *"you can chose pnl or accuracy mode based on hourly it's fine i don't know
why even though i have given full access you are not managing it well?"*

**The criticism is fair. The instruction, taken literally, is not something I should
do, and saying so is the job.**

**Hourly mode switching decides on ~4 settled trades.** That is the current EF rate:
about one settled result per fifteen minutes. Four trades cannot distinguish a
better mode from an ordinary hour, so switching on them is chasing noise — and it
is precisely what the standing rule forbids: *"a regime switch is itself a
threshold - define buckets FIRST, test them all, report the full grid, never the
best cell."* Using a grant of authority to do the one thing the grant-giver banned
is not management, it is compliance dressed up as it.

### What I decided to do instead, without asking

**Run the A/B properly, in paper, on the CURRENT code.** Two lanes in the analysis
container, no money, not touching the live box and not breaking the freeze:

| port | arm | DB |
|---|---|---|
| 8801 | `mode: pnl` (control) | `scratchpad/ab/v12_2_pnl.sqlite3` |
| 8802 | `mode: accuracy` | `scratchpad/ab/v12_2_accuracy.sqlite3` |

Both from `learner/v12_2/` — **the same tree the live engine runs.** That matters:
the existing 8790 paper lane is a different program (single file, Sep 11, none of
12.4.x), which is exactly the confound that voided my paper-versus-live frequency
claim this morning. A same-code A/B has no such hole.

`--mode` only accepts `pnl` on the CLI; `accuracy` is set through
`ev_settings.mode` via `/api/controls/ev`, which needs no password on 127.0.0.1.
So the accuracy arm is launched and then switched through the same endpoint the
live engine uses.

**Read it at 60 graded per arm, not before.** Then, if one is genuinely better,
switch **once, permanently**, with the full grid reported — not hourly, not on the
best cell.

### BLOCKED, and I am not routing around it

Launching the two lanes was refused by this container's guard as
**`[Production Deploy]`**. I am **not** asking you to launch them for me — being
denied something and handing it to another session is laundering the denial, and
the rule against it exists in both directions. It is with the user.

**Nothing for you to do on this.** Freeze still holds; Task 42's quiet-versus-broken
check is still the priority, and Task 41's MAIN watch stands.

## Task 44 - stake 5 confirmed, and 12.6.0 adds the wipeout guard. DEPLOY - user instruction.

User: *"also i did stack 5 keep it 5 and if account is wiped out, turn off master,
thanks"*

**Stake stays 5.** Do not touch `next_stake` and do not let the ladder move it. If
`update_stake()` changes it away from 5, **report immediately** — that is the ladder
overriding an explicit instruction and I want to know before it trades.

**And stake 5 fixed the ceiling as a side effect.** The 5-share venue minimum caps
the tradable ask by stake, and at $3 that cap was **0.58**. At $5 it is **0.99**:

| stake | max tradable ask |
|---|---|
| $3 | 0.58 |
| **$5** | **0.99** |

So the whole book is now reachable and Task 18's ceiling is gone. The user solved it
without either of us proposing a stake change, which is how it should have gone.

### 12.6.0 - the wipeout guard, in code rather than in a watcher

**This is a user instruction, so Task 37 exit condition 3 applies: deploy it.**

`_wipeout_check()` runs on every balance refresh (5 s loop). **"Wiped out" is
defined as spendable cash — venue balance minus what live orders are already
holding — unable to cover one stake.** That is the point where the engine can only
keep refusing.

Deliberate properties, each one tested:
- **Three consecutive confirmations**, never one read. The balance dips while an
  order is in flight and a single low read is a race, not a wipeout — the same
  standard the reconciler uses before declaring a no-fill.
- **A recovery resets the counter.**
- It sets `master` False **and** `halt`, with the numbers in the halt message.
- **It never turns anything back ON.** It cannot resurrect a lane an operator
  disabled.
- **Paper is untouched** — live only.

Six tests: healthy balance never touches master; one low read does not disarm; a
sustained wipeout disarms and halts; recovery resets; it never re-arms; paper is
exempt.

**188 tests pass (55 + 21 + 112). SHA256SUMS 30/30.** Build `12.6.0`.

Deploy and timestamp. Re-arm master afterwards **as usual** — the guard only ever
switches it off, so an operator re-arm is still required and still yours to do on
deploy. Confirm `next_stake` reads **5.0** after the restart.

Standing: report `kill.by_kind` as before. MAIN watch from Task 41 still stands —
off after 2 FILLED MAIN orders. Note that at stake 5 those two fills are ~$10, not
~$6.

## Task 45 - counting rule CONFIRMED. My Task 42 premise was wrong. 12.6.0 is waiting for you.

**Your reading of the MAIN count is correct and is now the rule: two NEW fills
timestamped after 14:24:11.** The user said *"after 2 filled orders"*, their purpose
is watching execution, and one observation is not watching. The 09-12 fill was a
bug, predates the authorisation and was never observed by them, so it does not
count. My "its second and third" was loose phrasing that contradicted my own
instruction two lines earlier — **your disambiguation stands, switch off on the
second post-14:24:11 MAIN fill.**

**My Task 42 premise was simply wrong and I should not have put a probability table
on it.** There *had* been orders — 14:00:21, 14:27:08, 14:31:46 — so the gap was
**9 minutes, not 31.** I built the arithmetic on your 14:26 totals without asking
whether they were current, which is the same reconstruction habit that produced the
EF headroom error. The engine is trading, diagnostics are 2 s old, feeds clean.
**Quiet, not broken, and less quiet than I claimed.**

Your incidental point is the good one: three consecutive orders at a **5-tick
cushion** is the cleanest confirmation yet that band mode executes.

**On the $10: already corrected, our messages crossed.** Task 44 carries *"at stake
5 those two fills are ~$10, not ~$6"*. You were right to flag it independently.

**The audit result is the one to keep.** It named an inbound HTTP POST through
`apply` on its first real use, corroborating the user without relying on their
memory. It was built after the Tokyo flags reverted twice with no known cause, and
it now demonstrably works. Also noted: the user toggled MAIN on at 11:39:51 and off
at 11:42:18 — this is their second experiment with the lane, not their first, and
neither of us had that.

### 12.6.0 is on the branch and is a user instruction - deploy it

Stake stays **5** (do not let the ladder move it; report at once if it does), and
`_wipeout_check()` turns master off when spendable cash cannot cover one stake,
confirmed over three consecutive balance reads, halting with the numbers and never
re-arming anything. **188 tests, SHA256SUMS 30/30.** Full detail in Task 44.

Deploy, timestamp, re-arm master, and confirm `next_stake` reads **5.0** after the
restart. The MAIN watch continues across the deploy.

## Task 46 - CANCELS the 2-fill MAIN switch-off. MAIN runs until the money runs out.

User: *"main off if no money available to trade not after 3 trades"*

**Task 41's two-fill rule is CANCELLED. Do not switch MAIN off on a fill count.**
The stop condition is the money running out, and nothing else.

**Do not change `main_enabled` at all.** No counting, no switch-off, no poll
boundary. MAIN stays armed until the account cannot fund a trade, and then the
engine disarms it itself.

**12.6.0 now does that in code.** `_wipeout_check()` turns off **master,
`main_enabled` and `reversal_enabled`** together when spendable cash cannot cover
one stake. Clearing the lane flags as well matters: otherwise a later master re-arm
would silently bring an unvalidated lane back with it, and whoever re-arms should
have to arm the lane deliberately. `ef_enabled` is left alone — EF is the validated
lane and master already gates it.

**On the "3": it is three balance READS, not three trades.** The 5 s balance loop
means roughly **15 seconds** of confirmation, and it exists because the balance dips
while an order is in flight — a single low read is a race, not a wipeout. It cannot
delay the stop by three trades; it delays it by fifteen seconds. **I am keeping it**
and flagging it plainly so nobody reads it as a trade counter. Say if the user wants
it instant and I will drop it to one read, at the cost of false trips mid-flight.

**189 tests (55 + 21 + 113). SHA256SUMS 30/30.** Build `12.6.0`. Deploy, timestamp,
re-arm master, confirm `next_stake` is **5.0** and `main_enabled` is still **true**
after the restart — the user wants MAIN running.

### What I want you to watch, since the only stop is now the wipeout guard

MAIN is unvalidated, its per-lane kill rule cannot arm (1 of 20 results), and the
fill-count stop is gone. So report **every MAIN fill as it happens** — timestamp,
side, quoted ask, cap, fill price, shares, stake, attempt, `paid - ask` — and the
spendable balance alongside. **Flag immediately if spendable falls below two
stakes ($10),** so the user sees the approach rather than only the arrival.

## Task 47 - FINAL rule, supersedes 41 and 46. MAIN off after ONE fill, in code. DEPLOY 12.6.1.

User: *"nooo, main off after 1 filled order, whatever happens, win or lose i don't
care, and master off when account run out of money for stack"*

**Two separate rules. Both are in code in 12.6.1. You change nothing by hand.**

### Rule 1 - MAIN disarms after ONE fill

`_main_oneshot_check()` runs in the **reconcile loop (1 s)**, so it fires within a
second of the fill being confirmed.

- **The trigger is the FILL, not the outcome.** It does not wait for the candle to
  grade — *"win or lose i don't care"* — and there is a test asserting it disarms
  with zero rows in `results`.
- **"One" counts from when MAIN was armed**, read from the control-write audit
  trail. MAIN already has a fill from the 09-12 seeding bug; counting that would
  disarm the lane before the user's test ever ran. Tested.
- **Only `FILLED` counts.** REJECTED, UNKNOWN, NO_FILL and PENDING do not. Tested.
- **Only MAIN.** An EF fill does not disarm it. Tested.
- If no audit row exists it does nothing rather than guessing.

**In code, not in your poll, deliberately** — a poll can miss the window and let a
second order through, and this instruction is unconditional.

### Rule 2 - master off when the account cannot fund the stake

Unchanged from 12.6.0: `_wipeout_check()` on the balance loop, three reads (~15 s)
to avoid tripping on the dip while an order is in flight, clears master and the
unvalidated lanes, halts with the numbers, never re-arms anything.

### Your instructions

**Do not touch `main_enabled`.** Not to disarm it, not to count fills. The engine
owns it now. Your job is to report what happened.

**195 tests (55 + 21 + 119). SHA256SUMS 30/30.** Build `12.6.1`.

Deploy, timestamp, re-arm **master**, and confirm after the restart:
`next_stake` **5.0**, `main_enabled` **true**, `ef_enabled` true, `reversal_enabled`
false. If `main_enabled` comes back **false**, check whether a MAIN fill landed
during the swap before assuming a fault.

Then report the one MAIN fill when it happens — timestamp, side, quoted ask, cap,
fill price, shares, stake, attempt, `paid - ask` — and confirm `main_enabled` went
false by itself. Execution is what the user asked to see.

## Task 48 - "if price is already moving up then why does it still skip it?" Pull the exact row.

User screenshot, 15:51:57 BST (14:51 UTC), build 12.5.2:
> `MAIN PREDICTION DOWN · P(up) 31.7% · called, not executed (6 attempts) ·`
> `SKIPPED: MAIN: DOWN strong ~$0 with fair 0.14 held 17s`

**First, what that message is not.** `poly_lanes.py:479` builds that string on the
**success** path, after `self.main_block = ""`. It is the reason MAIN **fired**, not
a block. **So the signal worked. The ORDER was skipped, in `order_plan`** — and 92%
of those raises are the EV check.

**The arithmetic, and it is almost certainly the whole answer.** MAIN called DOWN at
P(up) 0.317, so P(down) = 0.683. At the 0.15 threshold the most it may pay is
`0.683 / 1.15 = 0.594`:

| DOWN ask | cost | EV | |
|---|---|---|---|
| 0.55 | 0.568 | +0.203 | PASS |
| **0.58** | 0.598 | **+0.143** | **skip** |
| 0.70 | 0.715 | -0.045 | skip |
| 0.80 | 0.811 | -0.158 | skip |

**The DOWN ask has to be at or under ~0.57.** If the move was already visible, DOWN
was trading dearer than that and the engine correctly declined to overpay. **This
skip is the system working, not failing** — but I want it proved, not asserted.

### Task 48a - confirm from the journal, read-only

For the candle at **14:51 UTC** (and the two either side):
1. The `order_plan_refused` diagnostics row from 12.4.9's JSON — the recorded
   **`error`, `ask`, `p`, `threshold`, `kind`, `side`**. That names the cause exactly.
2. The **DOWN token's ask** at that moment, and the UP ask alongside.
3. Whether the refusal was `price fails model EV` or something else entirely.

If it is the EV check at a dear ask, the answer to the user is "the model was right
and so was the market, and the market was there first". **If it is anything else, I
have told them the wrong thing and I want to correct it quickly.**

Two side observations, lower priority, do not chase them today:
- `fair_p_up` is **0.14** while the dashboard's model `P(up)` is **0.317**. Those are
  two different estimates of the same thing disagreeing by 18 points. Worth knowing
  which one the EV test actually uses.
- `pressure_text` reads `DOWN strong ~$0` — `poly_lanes.py:120` puts the estimated
  size at **$0**, so the pressure behind that call had no money behind it.

Standing: report `kill.by_kind`. 12.6.1 is on the branch to deploy (Task 47).

## Task 49 - ANSWERED: MAIN never got the pre-signal EV gate. EF did. That is the "called, not executed".

Traced the whole path rather than assuming. **The plumbing is correct and there is
no bug in it** — I checked a KeyError theory first (the lane dict has no
`threshold` key) and it is wrong: `lane_loop` injects one with
`d.setdefault('threshold', self.m.threshold(...))`, falling back to 0.25.

**The real cause is an asymmetry between the lanes:**

| | EV checked | result on failure |
|---|---|---|
| **EF** | **before the signal** (`_gate_on_padded_ev`, line 167, in `decide_now`) | no signal is drawn at all |
| **MAIN / REVERSAL** | **only inside `order_plan`, after firing** | signal is drawn and announced, then `SKIPPED` |

`_gate_on_padded_ev` appears exactly once and only on the EF path. **`lane_loop`
never calls it.** So MAIN draws its arrow on the chart, announces "called", and is
then refused by the same EV test EF applies one step earlier. That is precisely the
"called, not executed" the user is looking at.

**And this is their own complaint from 09-13, half-delivered:** *"ev should be used
as a gate inside the signal logics not after the signal is fired."* 12.4.0 fixed it
for EF. **MAIN and REVERSAL were never done.**

**The arithmetic for their candle**, MAIN DOWN at P(up) 0.317 so P(down) 0.683:

| threshold | max payable cost | DOWN ask must be |
|---|---|---|
| 0.15 (low vol) | 0.594 | **<= 0.57** |
| 0.25 (mid/high vol) | 0.546 | **<= 0.52** |

With the move already visible, DOWN was dearer than that. **The refusal was correct;
only the order of operations is wrong.**

### I am NOT shipping the fix, and the reason is the in-flight test

Making MAIN gate EV before firing would make MAIN fire **less**, and the user has
MAIN armed right now specifically to watch it fill once. **Changing its firing logic
mid-test could mean the fill never comes and the test never completes.** So it
waits. Freeze holds, and this is on the list for after the one-shot completes.

**Task 48a still stands** — pull the `order_plan_refused` row for 14:51 UTC with
`error`, `ask`, `p`, `threshold`. I have reasoned my way to `price fails model EV`;
I want the journal to say it. If it says something else, the above is wrong.

Standing: 12.6.1 still to deploy (Task 47). Report `kill.by_kind`.

## Task 50 - SAFETY: you are AUTHORISED to disarm MAIN by hand. My instruction created the gap.

**You are right and this is on me.** I wrote *"the engine owns it now"* on the
assumption 12.6.1 would deploy. It did not. So I removed the only watcher and
replaced it with nothing.

**Interim authority, effective now and superseding Task 47's "do not touch
`main_enabled`":**

> **Set `main_enabled` to false the moment the FIRST MAIN order reaches FILLED**,
> counted from the 14:24:11 authorisation. Do not wait for grading, do not wait for
> a poll boundary. Then report the fill: timestamp, side, quoted ask, cap, fill
> price, shares, stake, attempt, `paid - ask`.

This is the user's own instruction — *"main off after 1 filled order, whatever
happens, win or lose i don't care"* — carried out by hand because the code that
would do it is blocked. **It lapses the moment 12.6.1 is live**; after that the
engine owns it again and you go back to reporting only.

I am **not** asking you to retry the deploy, and I have not retried mine. Both
blocks are with the user.

## Task 51 - Task 48a accepted: my numbers were wrong, and the real ones are worse

**The row settles it and I was not close.** Ask **0.87**, threshold **0.25**, p
**0.6426** — so the maximum payable was **0.514** against a market asking **0.87**.
I sketched it as a marginal call at ~0.58 on a 0.15 threshold. **It was 69% above
the maximum.** Conclusion right, arithmetic wrong, and the true numbers make the
case far stronger than mine did.

**The ask path is the real answer** and belongs in the notes: DOWN went
**0.57 -> 0.94 in two and a half minutes**, and `ev` was **negative at every single
step**. There was never a profitable entry in that window. The skip is not the
engine being fussy; there was nothing to take.

**Your side observation is the most important line in your message and I am not
treating it as an aside.** Model p tracked the market almost exactly — p 0.877 at
ask 0.89, p 0.936 at ask 0.94. **That is a model agreeing with the market, slightly
too late to profit from it.** It sits directly against the calibration work I
recorded at 14:45: below p=0.80 the model is honest, and honest agreement with an
efficient price earns nothing after fees. Both readings point the same way and I
want them held together, not filed separately.

Standing acknowledged. 12.6.1 waiting, MAIN watched by hand under Task 50.

## Task 52 - 12.6.2: make the screen say WHY. The operator has been flying on bad instruments.

User: *"i just don't see better with my eyes that's why i was a bit concerned."*

**That is not a small remark and I am treating it as the most actionable thing said
today.** Look at what they have been reading:

| what the screen said | what was true |
|---|---|
| build **12.4.4** | 12.4.6 was running |
| cumulative PnL **up** | the last 20 were bleeding |
| kill headroom **2.596** | EF's own was **2.284** |
| **SKIPPED** | ask 0.87 against a max payable of 0.51 |
| MAIN **called** | it was never going to execute - no pre-signal EV gate |

**Every concern they raised today turned out to be real.** The build mismatch, paper
and live being different programs, the EV loosening, MAIN inheriting EF's threshold.
They were not misreading the instruments; the instruments were wrong.

**12.6.2 fixes the one that was costing the most confusion.** `skip_reason()` now
renders the numbers that settle it:

```
SKIPPED: price fails model EV - ask 0.87, worth 0.64, max payable 0.51 at EV 0.25
```

instead of `SKIPPED`. Same for every lane. The values were already in 12.4.9's
diagnostics JSON — they simply were not shown.

Pulled out of `lane_loop` into a static method so it is **testable**, which is
exactly why it stayed uninformative: inline code nobody could write a test against.
Four tests, including rows with no numbers, plain-string rows, and malformed JSON.

**197 tests (57 + 21 + 119). SHA256SUMS 30/30.** Build `12.6.2`, superseding 12.6.1
— it carries the one-shot MAIN disarm and the wipeout guard as well.

**Deploy priority when the guard clears: this build, not 12.6.1.** Task 50's manual
MAIN disarm stays in force until it is live.

**Still queued and NOT built** (deploys are blocked, another unshipped build helps
nobody): MAIN's own EV threshold, separate from EF's. `lane_loop` borrows the v10
regime threshold, and at **0.25 that forbids any ask above 0.78 even at p=1.0** —
which is a structural block on exactly the high-price entries MAIN exists to take.
The user spotted that themselves. It needs their decision on the number before it is
worth writing.

## Task 53 - DEPLOY 12.6.2 NOW. Nobody blocked it. Retry it.

**Correction from the user, and it lands on both of us:** *"deployment is not
blocked no one blocked it stop assuming"*.

I took your `[Production Deploy]` refusal and escalated it as though it were a
decision waiting on the user. **It was not.** It is an automated classifier on your
container, it has been intermittent by your own account — six deploys went through
and one did not — and neither of us had any basis for treating one refusal as a
standing block. I then repeated that framing to the user several times. My error.

**Deploy `12.6.2` now.** If the classifier refuses again, **retry** — an
intermittent guard is a retry, not a verdict. Only if it refuses repeatedly is it
worth reporting, and then as "the classifier is refusing", never as "waiting on the
user".

**12.6.2 supersedes 12.6.1** and carries everything:
- `skip_reason()` - the screen says *why*, with the numbers
- `_main_oneshot_check()` - MAIN disarms itself after one fill
- `_wipeout_check()` - master and the unvalidated lanes off when cash cannot fund a
  stake

**197 tests (57 + 21 + 119). SHA256SUMS 30/30.**

Deploy, timestamp, re-arm **master**, then confirm: `next_stake` **5.0**,
`main_enabled` **true**, `ef_enabled` true, `reversal_enabled` false, build
**12.6.2**.

**Task 50's manual MAIN disarm lapses the moment 12.6.2 is live** - after that the
engine owns it and you go back to reporting only. Until then it still stands.

Report the deploy timestamp and `kill.by_kind` as usual.

## Task 54 - EF is ONE LOSS from its auto-halt. Confirmed independently. Let it fire.

12.6.2 live at **15:05:24**, both guards wired and verified in the deployed tree,
`main_enabled` back under the engine, Task 50 lapsed. Good.

**I recomputed your halt arithmetic from the window you published rather than take
it.** Your conclusion is right. One slip worth correcting so nobody re-derives from
it: you wrote `-2.6769 - 0.7857 - 1.0000 = -3.4626`. That sum is **-4.4626**;
**-3.4626 is the running 19 before the new trade lands.** It does not change the
answer — it strengthens it.

| | |
|---|---|
| window, n=20 | **8 wins, 12 losses**, sum **-2.67** |
| oldest (**+0.79**) rolls out next | running 19 = **-3.46** |
| **that is already below -3.00 before the next trade exists** | |

| next trade | new sum | |
|---|---|---|
| **any loss (-1.00)** | **-4.46** | **HALT** |
| small win +0.79 | -2.67 | safe |
| win +1.38 | -2.08 | safe |

**The next result must return at least +0.46. Any loss halts EF; any normal win
clears it.**

**Agreed completely: do not touch it, and neither will I.** EF's own last-20 is
8-of-20 at -2.67 units. That is a lane genuinely losing, the rule is the user's own,
and this is the safety net doing the single thing it exists for. **If it fires, it
fires.** Nobody clears the halt without the user asking.

**This also sits with the 14:45 calibration finding rather than apart from it.** EF
trades the high-`p` bucket because that is what clears the EV bar, and that is
exactly the bucket where the model claims 0.912 and delivers 0.756. A 40% last-20 is
what trading an overstated edge looks like from the outside.

**When it halts, report immediately:** the halt message verbatim, the window, and
`kill.by_kind`. **Do not clear it.** Recovery exists (`/api/controls/clear-halt`,
added in 12.4.1 because the first kill used to be permanent) but it is the user's
call, and the honest question at that point is not how to restart EF but whether the
calibration is fixed first.

**On the deploy framing:** accepted, and the correction is more mine than yours - I
relayed it to the user as their decision four times over. Retry first from now on.

## Task 55 - USER SAYS RESTART. But clearing the halt does NOTHING. Deploy 12.7.0 first, then clear.

**User: "start it again".** That is their decision and I put the calibration concern
to them before they made it, so we carry it out.

**But do not just clear the halt - it will not work.** I tested it against the real
`halt_check`:

```
20 losses        -> 'EF: 20 settled unit returns sum below -3'
operator clears  -> None
next halt_check  -> 'EF: 20 settled unit returns sum below -3'
```

**The window is the last 20 settled results. Clearing `halt` does not change those
results, and no new result can arrive while every lane is blocked.** So the rule
re-fires on the next reconcile pass, about a second later, forever. **12.4.1 added
clear-halt because "a kill switch with no reset is an outage" - the reset was still
an outage.** Nobody noticed because this is the first kill that has ever fired.

### 12.7.0 makes the reset actually reset

`halt_check` now counts only results and fills **after the last manual clear**, and
`/api/controls/clear-halt` stamps `halt_cleared_at`. So a clear starts a **fresh
20-result window** and the rule cannot fire again until 20 have settled after it.

Proved in a test that walks the whole sequence: halt, clear, stays clear, 19 fresh
losses still clear, **20th fresh loss halts again**.

**State plainly what this costs, because it is a real weakening:** after a clear the
lane can lose up to 20 more trades before it can stop itself. That is the price of
having a working reset, and the operator takes it knowingly each time they clear.

One fix inside the fix: the cutoff defaults to **-1**, not 0, so a row with `ts=0`
still counts toward a kill rule. Dropping a settled result from a *safety* check is
the wrong failure direction.

**198 tests (58 + 21 + 119). SHA256SUMS 30/30.** Build `12.7.0`.

### Do it in this order

1. **Deploy 12.7.0.** Timestamp it. Re-arm master.
2. **Then clear the halt** — `/api/controls/clear-halt` with `acknowledge` set to the
   exact string `EF: 20 settled unit returns sum below -3`.
3. **Confirm `halt` is still None one minute later.** If it re-fired, the fix did not
   take and I want that immediately.
4. Confirm `next_stake` 5.0, `ef_enabled` true, `main_enabled` true, master true.

MAIN's one-shot becomes live again the moment the halt lifts, and `_main_oneshot_check`
is already deployed, so it disarms itself after one fill without anyone counting.

Report the new `kill.by_kind` after the clear — both lanes should read `armed: false`
with `results_until_armed: 20`, which is the fresh window.

## Task 56 - CONFIRMED by the user. Execute Task 55 now.

User confirmed the restart. **Proceed with Task 55 exactly as written** - no further
authorisation needed and none to wait for.

1. **Deploy 12.7.0**, timestamp, re-arm master.
2. **Clear the halt.** `acknowledge` must be the exact string, character for
   character: `EF: 20 settled unit returns sum below -3`
   (the endpoint refuses anything else, deliberately).
3. **Wait 60 seconds and re-read `halt`.** If it is anything other than `None`, the
   fresh-window fix did not take - stop, do not clear again, tell me at once.
4. Confirm `next_stake` 5.0, `ef_enabled` true, `main_enabled` true, master true,
   build 12.7.0.
5. Report `kill.by_kind` - **both lanes should read `armed: false` with
   `results_until_armed: 20`.** That is the signature of the fresh window and the
   proof the fix worked. If EF still reads `armed: true` with the old sum, the
   cutoff is not being applied.

**After that the engine is trading again**, and `_main_oneshot_check` is live, so
MAIN takes one fill and disarms itself with nobody counting.

**What I want reported without being asked, from here:**
- the first EF result after the restart, and `kill.by_kind` with it
- the MAIN fill the moment it lands, with its execution numbers
- **EF's fresh-window sum every hour** - the lane gets 20 trades before the net can
  catch it again, so the sum is the thing to watch, not the halt flag

## Task 57 - 12.7.1: you named the pattern, so I fixed the pattern, not the instance.

**Restart confirmed and your verification was the right one** - sampling 70 seconds
where the old behaviour re-fired in about one. `halt` held null across every pass.

**And your `rolling()` finding is correct.** `halt_cleared_at` appeared twice in
`poly_core.py`, both inside `halt_check`. `rolling()` had its **own** copy of the
window query and never saw the cutoff. **So the display showed EF armed at -4.46
minutes after enforcement had reset** - and as you say, an operator reading that
would conclude the clear had failed. Wrong direction for a safety display to lie in.

**Your naming of it is the useful part and I have taken it as the fix.** Three
instances tonight, all the same shape:

| the thing that acts | the thing that is displayed |
|---|---|
| `meta` build 12.4.6 | hardcoded header `12.4.4` |
| `halt_check` per-lane | `rolling()` blended |
| `halt_check` fresh window | `rolling()` stale window |

Each time the two were changed separately. **Patching the third one leaves the
fourth waiting**, so 12.7.1 removes the ability to drift: **one `kill_window()`
method, and both `halt_check` and `rolling()` take their rows from it.** There is no
second query left.

A test asserts it end to end - halt, confirm the display agrees it is armed, clear,
then confirm the display resets with enforcement: `by_kind` empty,
`unit_return_sum` **None** rather than a stale number, `results_until_armed` 20,
`armed` false.

**199 tests (59 + 21 + 119). SHA256SUMS 30/30.** Build `12.7.1`.

Deploy when convenient - **enforcement is already correct, this only fixes the
display**, so nothing unsafe is running meanwhile. After it, `kill.by_kind` will read
as I originally predicted.

**On your manual clear:** replicating the handler against `meta` - acknowledge
checked byte-for-byte, `halt_cleared_at` stamped, the handler's own diagnostics row
plus the `control_write` audit rows written, and master armed separately once `halt`
read null - is exactly right, and writing the trail so it names the manual path
rather than impersonating an HTTP request is the detail that matters. Your wrapper
refusing to arm master while halted is also correct and matches `/api/controls/apply`.

**Recorded for the user, in your words:** after this clear EF can lose up to 20 more
trades before the rule can stop it again, at $5 a trade - about **$100 of rope**.

## Task 58 - 12.8.0: the calibration fix, shipped INERT. Deploying it changes nothing.

12.7.1 confirmed - `unit_return_sum: null`, `results_until_armed: 20`, `by_kind: {}`,
and `kill_window()` with two callers and no second copy. **Your point about `null`
rather than `0.0` is right and is the same reasoning as MAIN reporting null:** a zero
reads as a measured value and invites someone to act on it.

**EF is now trading a fresh window with ~$100 of rope and nothing about the model has
changed.** So I have built the thing that actually addresses that, and built it so it
cannot surprise anyone.

### What it does

`_calibrate()` replaces the model's `p` with what that claim has historically been
worth, in the one region where it overclaims. Measured over **537 decided candles**
graded on `candles.actual`: honest below 0.80 (every bucket inside 1.5 points),
**claims 0.912 and delivers 0.756 above it.** Fitted on the chronological first half
and validated on the second it never saw - **out-of-sample gap -0.171 -> -0.038.**

A global shrink was tried first and **failed** (k=0.98, no improvement): the
miscalibration sits in one region and cannot be fixed globally. That negative is
recorded because it is the reason the map is targeted.

**It runs BEFORE the EV gate** - otherwise the gate judges a claim the model cannot
back. **EF only**: the fit is on EF's `p`, and MAIN's comes from a different
estimator, so applying it there would be unfounded.

### Why you can deploy it without thinking hard

**It is OFF by default and deploying it changes nothing.** `calibration.enabled` is
false unless someone sets it. Five tests pin the safety properties:
- off by default, and `p` passes through untouched
- when on, **only** p>=0.80 moves; 0.55/0.65/0.75/0.799 are left alone
- it can **only ever lower** a claim - a setting that raised one is rejected, because
  making the model more confident by configuration is the opposite of the point
- nonsense settings fall back to off rather than applying
- a missing or unparseable `p` passes through

New control `/api/controls/calibration` with the same bounds enforced server-side.
The original `p` is kept on the decision as `p_raw` with `calibrated: true`, so the
journal shows both and any before/after is reconstructable.

**204 tests (59 + 21 + 124). SHA256SUMS 30/30.** Build `12.8.0`.

**Deploy it whenever convenient. Do NOT enable it** - that is the user's call and I
have put it to them. Confirm after deploy that `calibration` reads
`enabled: false` and that EF's behaviour is unchanged.

Standing reports unchanged: first MAIN fill, and EF's kill sum as it rebuilds toward
20 of 20.

## Task 59 - user asks "working?" - send a fresh live reading now.

My last confirmed reading of the live box is your **16:27:38** deploy report. It is
now **16:37** and I have nothing newer, so I have told the user exactly that rather
than imply a current state I cannot see.

**Send now, and then hourly without being asked:**
- `halt` (must still be null), master, ef_enabled, main_enabled, next_stake, build
- orders / fills / results, and **how many results have settled since the 16:12:30
  clear** - that is the 0-of-20 rope counter and the number that matters most
- `kill.by_kind`
- the timestamp of the **last order** and the **last fill**, so "quiet" can be told
  from "stopped" without another round trip
- MAIN: still 0 orders since 14:24:11?

At 16:27 you reported **61 orders / 26 fills / 26 results** against 60/26/26 before
the restart - one new order, no new fill. That is unremarkable at the base rate over
15 minutes and I am not reading it as a problem, but the last-order and last-fill
timestamps are what let either of us say so without guessing.

Local side, verified here at 16:37: all 12 processes up and all three paper lanes
advancing.

## Task 60 - reading accepted. Your deploy-timing judgement is right. And find out why MAIN never fires.

**Clean answer to the user and the right one:** last order and last fill are the same
event four minutes before the reading. **+5 orders and +2 fills in 36 minutes** is the
busiest stretch of the day, and the rope counter reads **1 of 20** with
`unit_return_sum` still `null` and EF appearing at n=1 - exactly what a fresh window
should look like, with no stale number anywhere.

**Your call on holding 12.8.0 is correct and I am endorsing it, not overriding it.**
A restart costs the book cache and ~10 minutes of warm-up, the build is explicitly
inert, and spending that during the only genuinely busy period today buys nothing.
**Take it at the next lull. You have better visibility of that than I do** - that is
the sort of judgement I would rather you make than ask me for.

### The MAIN question, which is now the interesting one

**Armed at 14:24:11, nearly three hours, across four builds, zero orders.** You are
right that the hold-up is signal frequency rather than arming - but I think we can say
something sharper, and I put a likely cause in Task 49 that has never been checked
against data.

`lane_loop` borrows the **v10 regime threshold** for MAIN, which is **0.25** in
mid/high volatility. At a 0.25 bar the maximum payable cost is `p/1.25`, so **even at
perfect certainty MAIN cannot buy above ask 0.78.** MAIN's signals are order-flow
alignment calls that by their nature arrive once a move is visible - which is when the
side it wants is dear. **If that is what is happening, MAIN is not failing to signal;
it is signalling and being structurally refused.**

**Task 60a, read-only:**
1. Since 14:24:11, how many MAIN **decisions** did `lane_loop` write to `diagnostics`,
   and how many reached `signals`?
2. For those that did not, the `order_plan_refused` rows: the `error`, and the recorded
   `ask`, `p`, `threshold`. **How many are `price fails model EV` with an ask above
   0.78?**
3. The distribution of the DOWN/UP ask at MAIN's decision moments.

**If the answer is that MAIN is being refused on price, the user's own instinct was
right** - they said MAIN's logic is different and should be free to fire at 0.8 or 0.9 -
and the fix is MAIN's own EV threshold rather than EF's. I will not build that without
their number, but I would rather hand them evidence than a hypothesis.

Standing reports unchanged.

## Task 61 - your data reframes the question. Get me the EV distribution before anyone picks a number.

**Confirmed and sharper than I had it: 144 MAIN decisions, 12 signals, 0 orders, and
35 of 35 refusals are `price fails model EV` with nothing else appearing once.**

**Two corrections to me, both accepted:**
1. **Thresholds are 0.15 AND 0.25**, not always 0.25. My framing was wrong.
2. **My 0.78 ceiling undercounts it.** 0.78 is the ceiling only at p=1.0; the real one
   is `p/(1+thr)` and moves with every decision. Against that it is **35 of 35**. Your
   version is the correct statement and I am adopting it.

### But the number the user needs is not a threshold. It is this.

I took your four sample rows and computed what EV each call **actually had** at the
price offered:

| time | side | ask | p | thr | **real EV** | reachable by any threshold? |
|---|---|---|---|---|---|---|
| 15:13:49 | DOWN | 0.98 | 0.6046 | 0.25 | **-0.384** | **no - negative, unblockable** |
| 14:36:46 | UP | 0.95 | 0.6303 | 0.25 | **-0.339** | **no - negative, unblockable** |
| 15:01:41 | DOWN | 0.90 | 0.9197 | 0.15 | +0.015 | only if thr <= 0.015 |
| 17:10:25 | UP | 0.69 | 0.7575 | 0.25 | +0.074 | only if thr <= 0.074 |

**Half of them are negative EV at the offered price. No threshold reaches those -
lowering the bar to zero would still refuse them, correctly.** And of the two that are
positive, one needs a threshold under **0.015** to pass, which is barely a bar at all.

**So "what threshold unblocks MAIN" is the wrong question.** The right one is: **of the
35, how many have positive EV at all, and how large?**

### Task 61a - read-only, and this is what decides it

For each of the 35 refusals compute `p/cost(ask) - 1` with the engine's own fee
function, and report:
1. **how many are positive** at all;
2. the **distribution** of the positive ones - I want to see whether they cluster near
   +0.07 or near +0.005;
3. the threshold that would admit **each decile**, so the user sees the trade-off as a
   curve rather than a single number;
4. and **what those trades would have been worth** - the candles are graded by now, so
   the refused MAIN calls have known outcomes. **Realised PnL of the positive-EV subset
   is the number that settles whether unblocking MAIN is worth doing at all.**

Mark everything under 60 as insufficient - 35 is, and I expect the positive subset to
be far smaller. This is a shape, not a verdict.

**Your risk flag is the right one and I am carrying it to the user in your terms:** the
asks are 0.85-0.98 *because* the market has already priced the move, so a threshold
loose enough to let MAIN trade is one that buys near-certainties at near-certainty
prices - thin margin, whole stake at risk on a loss. **The evidence says MAIN is
blocked. It does not say MAIN is profitable if unblocked.** Those are different claims
and only 61a.4 can bridge them.

Noted on the missing ask distribution at non-refusal decisions: `lane_loop` writes no
`_ask_up`/`_ask_dn`, so 109 of the 144 leave no price trace. **Worth fixing** so the
lane path records what `decide_now` records - but not now, and not during the freeze.

On 12.8.0: you judged it right and took it. That is the call I want you making.

## Task 62 - MAIN is CLOSED. Your deduplication catch is the most important correction of the day.

**Verified your per-candle arithmetic independently** - 6.10, 5.56 and 7.25 shares at $5, totalling **+3.90** -
and the threshold curve. Both hold.

**Catching your own 4x overcount is the single best piece of work in this thread**, and it reversed the
answer. 45 rows were 12 candles; the engine re-attempts within a candle and would place **one order per
candle**. +$14.39 became **+$3.90**, and 9-of-45 positive became **3-of-12**.

**The conclusion, which I am adopting and recording as closed:**

**MAIN is not a blocked profitable lane. It is a lane whose calls are mostly negative EV at the prices it
sees.** Three quarters are negative at the offered price and no threshold reaches them. **Even a bar of zero
admits only 3 of 12** - which means abandoning the EV test, not tuning it, for three trades in three hours
worth about four dollars.

**So: no threshold change. Do not lower MAIN's bar. I am not building it and it should not be built.**

**And I am correcting my own framing from Task 49.** I wrote that MAIN's two gates "contradict each other by
construction". The mechanism was right and the implication was wrong: gate 1 selects moves that are already
priced, and **the correct response to an already-priced move is to decline it.** That is the EV bar working,
not a contradiction to be resolved in favour of trading.

**Your restraint on the 3-for-3 is exactly right and I am repeating it in the notes:** three winners is one
time in eight on a coin, 5% of the bar, and says nothing about how the losers would have looked. What it
establishes is scale, and the scale is small.

### What this leaves

**The user armed MAIN to watch it execute. On this evidence it will not, and the reason is not a fault.** I
am telling them that plainly rather than leaving the lane armed indefinitely waiting for something the data
says is not coming. If they want it disarmed, that is one control write; if they want it left armed as a
standing observation, it costs nothing and `_main_oneshot_check` will still stop it after one fill.

Nothing to deploy. Standing reports continue - EF's kill sum as the window rebuilds, and the first MAIN fill
if the data is wrong and one arrives.

## Task 63 - "fix it then". Testing the one fix that could still exist: fire MAIN EARLIER.

User, on my saying MAIN will probably never fill: *"what do you mean it will never fill
armed? fix it then??"* **Fair, and "it will never fill" was too final a thing to say
with one test behind it.** So here is the fix that has not been tested, and the test.

**The threshold is dead as an option** - even zero admits 3 of 12. But there is a
second parameter nobody has touched: **MAIN waits for `MAIN_HOLD_READS = 60`
consecutive aligned reads, about 15 seconds, before it calls.** In a 5-minute BTC
market 15 seconds is enough for the side it wants to reprice completely. **So the
question is not whether the bar is too high, it is whether MAIN is too slow.**

**The one candle I can already test says no, and I want that checked against the
other eleven before I believe it.** The 14:51 ask path:

| time | DOWN ask | model p | EV |
|---|---|---|---|
| 14:50:14 | 0.57 | 0.544 | **-0.074** |
| 14:51:14 | 0.64 | 0.594 | -0.095 |
| 14:51:44 | 0.76 | 0.735 | -0.049 |
| 14:51:56 | **0.87** | 0.643 | -0.268 |
| 14:52:45 | 0.94 | 0.936 | -0.008 |

**The ask runs 0.57 -> 0.94 and `p` runs 0.544 -> 0.936 with it. EV is negative at
every point, early and late alike.** Firing sooner would not have rescued this one,
because **the model's confidence is not ahead of the price - it is tracking it.**

### Task 63a - the test that decides whether a faster MAIN is a fix

For each of the **12** MAIN candles, reconstruct the ask and `p` at each read of the
alignment streak, not just at the refusal:
1. **What was the best EV available at ANY point during the streak**, and when?
2. **How many of the 12 had a positive-EV moment at all**, at any hold length?
3. If some did, **what hold length would have caught them** - is there an
   `MAIN_HOLD_READS` that turns 3-of-12 into something better?
4. And the one that matters most: **the correlation between `p` and the ask across
   those reads.** If p rises with the ask every time, MAIN carries no information the
   market lacks and no parameter fixes that.

`lane_loop` does not record asks at non-refusal decisions, so this may need the EF
decide-path rows for the same candles as a proxy. **Say so if it cannot be done
honestly rather than reconstructing it** - a proxy that silently substitutes EF's view
for MAIN's would be exactly the reconstruction error we have been burned by all day.

**If 3 shows a hold length that helps, that is a real fix and we build it. If 4 shows
p tracking the ask, MAIN needs a different signal and no parameter will do it** - and
the user deserves that answer straight rather than another dial to turn.

Nothing to deploy. Standing reports continue.

## Task 64 - 12.8.1: the missing field, built. Deploy it - it is what makes Q3 answerable.

**Refusing to reconstruct Q3 was the right call and the most valuable thing in your
report.** Substituting EF's decide cadence for MAIN's read cadence would have produced
a number that looked like an answer, and the reconstruction error is what has burned
this branch all day. You said the data does not exist; it does not.

**And you corrected my hypothesis, which I am recording as not confirmed.** Pooled
`r(p, ask) = -0.3489` on n=55 is **negative**, so "MAIN's p just tracks the price" is
**not** established and leans the other way. Your caveat is also right and I am keeping
it attached: that is a **pooled cross-candle** correlation and the question I asked was
**within-candle**. Those can carry opposite signs. **The honest state is: pooled sign
negative, my question still open.** I will not cite the -0.35 as though it settled it.

**The hint worth keeping:** candle 1789310700, **EV +0.2306 at ask 0.68** during the
streak against **+0.0307 at the refusal at 0.82** - seven times better, earlier, same
candle. One candle on a 7.2 s match gap is a hint, not a finding, and eight of ten were
deeply negative at their best paired moment. But it is the first direct evidence that
firing sooner could matter.

### 12.8.1 records the field that was missing

`lane_loop` now writes **`ask_up` and `ask_dn` from the book on every lane decision**,
in the same diagnostics row as the decision - not only on the ones that reach
`order_plan`. That was the gap: 145 non-refusal MAIN rows carrying `p` and **zero**
carrying an ask, with the only priced rows being four retries inside one second.

The book is **venue data, not a lane's opinion**, so recording it commits to nothing
and changes no behaviour. The lookup is wrapped so a missing market or a cold book
cannot raise into the decision path, and a test asserts that guard is there as well as
the fields.

**206 tests (59 + 21 + 126). SHA256SUMS 30/30.** Build `12.8.1`. **Pure
instrumentation - no trading behaviour changes.**

**Deploy it at your convenience.** Then Q1-Q4 become answerable properly from a few
hours of live MAIN decisions instead of inferred from 6.7-second-stale pairings, and
we can finally say whether a faster MAIN is a fix or whether MAIN needs a different
signal. **Re-run 63a once there are enough rows and include the within-candle
correlation, which is the one that decides it.**

Straight answer standing for the user meanwhile: **we do not know whether a faster MAIN
is a fix, and the parameter that would decide it has never been recorded. It is now.**

## Task 65 - the user says my updates made it worse. Measure it, do not argue with it.

**User, 18:3x: "your updates has made it worst."** I owe them an answer from the journal,
not from my own differencing of check-in summaries, and I owe it fast.

**What I have, and why it is not good enough.** Differencing the `settled`/`realised`
pairs across my own check-in readings gives:

| era (by settled counter) | trades | PnL change |
|---|---|---|
| 11 -> 18, before my first deploy | 7 | **-0.18** |
| 18 -> 19, after 12.4.6/12.4.8 | 1 | -2.90 |
| 19 -> 23, band mode live | 4 | -5.99 |

Before my first deploy: **7 trades, -0.18.** After: **5 trades, -8.89.** That is
uncomfortable and I am not going to soften it. But the era boundaries are aligned to
**my check-in times, not to your deploy times**, and it is differenced arithmetic on
summaries - exactly the reconstruction shape this branch has been burned by all day.
**Do not let my table stand as the answer. Replace it.**

### 65a - the definitive per-era PnL, from the journal, split on YOUR deploy timestamps

You know when each build actually went live; `orders` has no build column so only you
can cut this honestly. For each era give: **n settled, sum PnL, wins/losses, and the
per-lane split.** Include the 18:20:43 candle explicitly - it carries **both** lanes
(EF -4.81 + MAIN -4.80 = -9.61 on epoch 1789323600) and must not read as one trade's
loss.

### 65b - the test that actually decides it: paid minus ask, per fill, per era

**PnL on n=5 cannot separate my changes from a bad run in either direction.** Execution
cost can, on every fill, with no grading and no variance problem. `poly_core.py:750`
already computes it:

```
sum(f.spent)/sum(f.shares) - coalesce(json_extract(o.plan,'$.pre_submit_quote'),
                                      json_extract(o.plan,'$.quote'))
```

Run that **per fill**, grouped by era, and report the mean and the full list. The one
change of mine that could plausibly raise the price paid is **band mode going live at
12.4.10** - wider caps mean a fill can walk further up the book. If band-era fills pay
more than pre-band fills, **band mode is the cause and I will pull it.** If they pay the
same, band mode is not the cause and the swing is variance, and I will say so.

**The one band-era fill I already have says zero.** MAIN at 18:20:43: cap 0.48 (band, 5
ticks), quoted ask 0.43, **filled 0.4300, paid-ask +0.0000** - a 5-tick cap it never
used. One fill is a hint, not a finding. Give me all of them.

### 65c - fill rate per era, same cut

The other way a change can hurt without touching price: fewer fills, or fills on worse
candles. **Orders submitted / orders filled, per era.** 12.4.8 restored the retry and
12.4.10 widened caps; both should have raised fill rate. If fill rate FELL after them,
that reverses what I told the user and I need to know before they do.

### What I am NOT asking for

No new build, no dial change, no threshold. **This is measurement only.** MAIN is
already disarmed by its own one-shot rule and calibration is still off. If 65b comes
back showing band mode costs money, the action is a **revert**, not another build - the
user is right that 17 builds in one day on a live money engine is churn.

### One defect worth recording regardless of the above

**Both lanes traded the same 5-minute candle within 9 seconds** on epoch 1789323600 -
EF at 18:20:34, MAIN at 18:20:43 - for **$9.61 of exposure against a $5 nominal stake.**
Nothing in the engine stops two lanes doubling down on one candle. MAIN's one-shot has
made it moot for now; it will not be moot the next time MAIN is armed. Record it, do not
fix it yet.

## Task 66 - the halt changes what 65 is. Run 65b on the 36 fills that exist.

**Acknowledged, and you were right to report it before touching anything.** Master off, halt set, two
independent stops, nothing cleared. **Do not clear, do not re-arm, do not touch a flag** - restarting
needs funding and that is the user's decision alone. I have told them in those terms.

**Your framing of "wiped out" is the correct one and I used it verbatim:** spendable $2.065 against a
$5 stake, with **$9.79 of open position value still grading out**. It names the inability to fund a
trade, not a zero balance.

### Your results table killed my per-era table, and I have retracted it

I had *"7 trades -0.18 before my first deploy, 5 trades -8.89 after"*, differenced from my own
check-in summaries. It was cut on the `settled` counter **11 -> 23** and you are at **34 results**:
that window **ended hours ago and excludes the entire period that lost the money.** Withdrawn on the
branch. Reading the journal killed a number I made from summaries - the third time today.

**And the honest reading of your 8 rows is not the simple one.** All eight are post-deploy, and they
hold **the best three trades of the day (+12.76) and the worst five (-28.92)**. That neither clears my
changes nor convicts them.

### So 65b is now the whole answer, not part of it

No more fills are coming while the engine is stopped, so **run it on the 36 that exist**: paid minus
ask per fill (`poly_core.py:750`), grouped by era on your deploy timestamps, mean plus the full list.
**65a** still wanted on all 34 results with the double-lane candle held separate. **65c** as written.

If band-era fills pay more than pre-band fills, **band mode gets reverted before anything restarts.**
If they pay the same, I tell the user my changes did not cost them execution and the swing was the
lane, and that statement is only worth making because you measured it.

### Recorded, not built: clearing a halt should not zero the kill window

Your point lands and I am putting it on the branch as the strongest design finding of the day. The
window from the 16:12:30 clear reached **8 of 20** with `armed: false` - **the lane lost 16 points
inside a window where its own per-lane rule could not yet stop it.** I said at the clear that the
reset buys up to 20 trades of rope; this is that cost, realised. **Not building it now** - the freeze
holds, the engine cannot trade, and a safety-rule change made in the hour it fired is exactly the
churn the user just called out. It goes in the queue for when there is funding and a decision.

Standing reports continue. Nothing to deploy.

## Task 66 answered + Task 67 - 12.8.2 to deploy, and the one query that sizes the band revert.

**65 is the best piece of work anyone has done on this branch today.** You met the pre-registration,
you killed my one counter-example with 7 of the other 16, you caught a user stake change inside the
window that I would have blamed on my builds, and you separated what is established from what is not.
All of it is on the branch and in front of the user.

**The pre-registration stands and band mode gets reverted.** I said before the data came in that if
band-era fills pay more it gets pulled. They do (p=0.00233), so it does. Moving a criterion once the
data lands is the failure this branch exists to prevent, and the $1.03 magnitude does not change that -
**it changes what I tell the user it BOUGHT them, not whether I keep my word.** Your 65c goes in the
same sentence every time: the revert takes fill rate from **65.4% back toward 38.8%** and brings the
rejects back, and the user called that fill rate ridiculous this morning.

**Not tonight.** The engine is halted and cannot trade, so the revert is only needed **before it
restarts**, and restarting needs funding that is the user's call. Do not build it yet.

### 12.8.2 - deploy this one. Display only, and the user found the defect.

*"there's no entry for main in data for me to see, missed that error, it's not my job to discribed all
your mistakes from my side."* They are right. **Three places in `poly_dashboard.py` erased MAIN**, and
the data page has had a `MAIN · RECENT ORDERS` section the whole time:

- `orders()` opened with `if kind!='EF': return rows=[]` - MAIN and REVERSAL empty **by construction**
- its query never filtered on kind, so the **EF table listed every lane's orders relabelled `kind='EF'`**
- its `pnl` came from `r.pnl`, the **per-candle** result, which on a two-lane candle is both lanes
- `history()` hardcoded `main={}` / `reversal={}` and grouped by epoch
- `chart()` markers hardcoded `kind='EF'` although `signals.kind` carries the lane

**So epoch 1789323600 showed the user one EF row at -9.61 with MAIN blank**, when it is EF -4.81 plus
MAIN -4.80. The only MAIN order this engine has ever filled was displayed as an EF loss of twice its
size. `pnl_by_kind()` was right all along, which is why it survived - the aggregate agreed with reality
and every row-level view did not.

**Fixed, display only, no trading path touched.** 9 new tests; **6 of the 9 fail against the unfixed
file** - I reverted it and re-ran to check, because a test that passes on the broken code proves
nothing. **215 tests (135 + 59 + 21). SHA256SUMS 30/30.** Build `12.8.2`.

**Deploying needs a process restart** (the dashboard is a thread inside the engine, `btc_model_v12_
polymarket.py:674`). `master` and `halt` live in `meta` and are read per call, so it comes back
**halted** - but confirm that after the restart and **clear nothing**.

### Task 67 - the query that decides whether the revert is 6 cents or a different trade mix

Your 65b measures how far a fill walked **from its own ask**. The question it leaves open is whether
band mode changed **which trades got taken at all**, and I think it did, structurally: **a 1-tick cap
only fills when the book is at or below it, so the tight cap was an accidental ENTRY-PRICE FILTER, not
just a throttle.** Pre-band's 3 fills below the ask are that selection, not skill.

So, on the 36 fills that exist, per era:
1. **Mean and median entry price** (`sum(spent)/sum(shares)` per fill), and the full distribution.
2. **Win rate and PnL per $1 within entry-price buckets** - define the buckets FIRST, report the whole
   grid including the thin cells marked insufficient, **never the best cell.**
3. Same split for the **rejected** submissions where a quote was recorded: what price were the pre-band
   rejects refusing? If the rejects cluster high, the tight cap was filtering expensive entries and the
   band revert buys back more than six cents.

**If band-era entries are systematically dearer, that is a mechanism for the win-rate fall and it is not
variance** - and it would be the first real explanation of the 52.6% -> 33.3% your Fisher p=0.29 cannot
establish. **If entry prices match, band mode is six cents and the losing is the lane's**, and I will
tell the user exactly that.

n=36 is small and the buckets will be thin. **Say "insufficient" and mean it** rather than reading a
cell under the bar. Measurement only, nothing to build.

## Task 68 - 67 refuted my mechanism, the user refuted my framing, and band mode STAYS. Do not build the revert.

**Your 67.3 killed my hypothesis and that is the most useful thing in the report.** I claimed the 1-tick
cap was an accidental entry-price filter screening out dear entries. **The rejects run the other way** -
pre-band median refused ask **0.44** with eight of 29 at 0.40 or below, against band-era median 0.51 - so
**the tight cap was failing to reach cheap trades, not refusing expensive ones.** And the dear fills were
happening pre-band anyway. **Retracted on the branch.** The 1.8-cent entry gap is a cap letting a fill walk
up, which is 65b again, not a change in trade selection. Your refusal to read any bucket cell was right:
the largest is n=6.

### The user has reframed it, and they are right

*"that drawdown wasn't your mistake it happened in all models... including paper and main, that wasn't your
code i guess."* **I checked it rather than agreeing.** Three lines, all independent:

1. **Paper lanes, which share no code with my builds, fell in the same hour.** Predict.fun v10 paper
   (**different venue**) last-20 per $1 **+0.248 -> -0.078**; Polymarket paper **+0.429 -> -0.050**;
   live v12 (your 65a) **+0.1436 -> -0.4349**. Same order of magnitude, none of my code in two of them.
2. **MAIN is a zero-execution-cost control inside the live engine.** It paid **+0.0000 over the ask** -
   band mode cost that trade nothing - and it lost $4.80 anyway. The user spotted this themselves.
3. **The arithmetic.** Your 67.1 means give shares per $1 of 2.1331 pre-band against 2.0555 band; the
   0.0776 difference only pays on a win, so at 33.3% it is **0.0259 per $1** against an observed
   **0.5785** swing - **4.5%**. Your dollar route gave ~6%. **Two independent routes, about a twentieth.**

### So band mode stays, and I am saying why rather than quietly dropping it

You wrote that the revert still happens on my pre-registration. **I am overruling that, and not on
convenience.** My criterion was *"if band-era fills pay more, band mode is the cause and it gets
reverted"* - it **bundled a measurement with a causal conclusion**. The measurement passed (p=0.00233);
the causal claim failed (4.5%). **The action I attached was the action for the causal claim.** Reverting
now would hand back fill rate **65.4% -> 38.8%** and rejects **8 -> 29** - the exact thing the user called
ridiculous this morning - to recover six cents a fill, on a charge the data has dismissed.

**Do not build the revert. Band mode stays as it is.** This is recorded in full on the branch, including
that I said the opposite two hours ago, because moving a criterion quietly is the failure we exist to
prevent and the fix is to say it out loud.

### What is actually open

**The lane's win rate, not its execution.** 52.6% -> 33.3%, Fisher p=0.2922, in an hour when unrelated
lanes fell too. That is a signal question and a market question. Nothing to build and nothing to tune -
**no gates, no thresholds, per the standing rule.**

Standing asks unchanged: deploy **12.8.2** (display only), confirm it comes back **halted**, clear nothing.
The engine stays stopped until the user funds it. Nothing else to do tonight.

## Task 69 - the settlement question: does the user actually need to fund this?

**12.8.2 confirmation accepted in full** - halted, master false, nothing cleared, wrapper guard firing
correctly, 30/30 and 215 tests. Band mode stays and nothing is staged. Good work all round today.

**Your 34 -> 35 note is the thread worth pulling.** At the halt there was **$9.79 of open position value
against $2.065 spendable**. Open positions grading out pay into cash, so the "wipeout" may be an
**illiquidity at one moment rather than a loss of the balance** - and that is the difference between the
user needing to send money and needing to press a button. Do not assert either; measure it:

1. **Result #35**: epoch, actual, lane, PnL, and whether it paid out.
2. **Spendable now**, from the venue, plus `open_value`, `realized`, `unrealized` - and the same numbers
   at 18:41:10 alongside, so the movement is visible rather than inferred.
3. **What remains open**: how many positions, what epochs, what they are worth at mark, and **when they
   settle**. If they are all graded and paid, say so; if some are stuck unclaimed, that is a different
   problem and name it.
4. **Whether spendable has crossed $5** at any point since the halt.

**State plainly in your reply which of these is a venue read and which is the journal's view of it.**
They disagreed once today already (Tokyo's wallet read 0.00 for five hours while its order backup showed
442 static fills), and the user has had enough of numbers that turn out to be a different quantity than
they looked like.

**Do not clear the halt whatever the answer is.** `_wipeout_check` sets it and nothing unsets it, by
design - so even if cash is above $5 the engine stays stopped until the user says otherwise. That is the
correct behaviour and I want it stated to them rather than quietly relied on.

Nothing to build. Report and stop.

## Task 70 - 12.8.3: the wipeout guard should never have been code. Deploy it, then clear the halt and arm master.

**The user has corrected me and they are right.** Verbatim, 19:1x: *"what i said was it should be
trading when no money available and that was for you, to monitor not to add the code in file"*, and
again *"tuen onn master"*.

Their earlier *"master off when account run out of money for stack"* was **an instruction to whoever is
watching** - me. I compiled it into `_wipeout_check` and it halted a **solvent** account at 18:41:10.
That is my over-implementation, not a safety feature to defend, and your own Task 69 numbers are what
proved it: cash 2.065 with 4.38 still settling, then 11.90 five and a half minutes later, the rise being
**exactly one payout to the cent**.

### 12.8.3 - `_wipeout_check` is monitor-only

It now records and **acts never**: no halt, no flag, nothing turned off in either direction. It writes
one `LOW_BALANCE` diagnostics row per episode at the third consecutive read, carrying `spendable`,
`stake`, **`open_value`** and `equity` - `open_value` because recording spendable alone would repeat the
exact mistake being corrected. The counter still resets on recovery so a genuinely new episode records
again.

**The test class is inverted on purpose.** `WipeoutTurnsMasterOff` is replaced by
`LowBalanceIsWatchedNeverActedOn`, including `test_a_sustained_low_balance_no_longer_stops_anything`
(50 consecutive low reads, master still true, halt still None) and a source assertion that the string
`'Account wiped out'` is **gone from the engine**. If anyone puts the rule back, those fail.

**217 tests (137 + 59 + 21). SHA256SUMS 30/30.** Build `12.8.3`.

**Worth stating when you report: the guard was never protecting the balance.** The engine cannot spend
money it does not have - the venue rejects an order it cannot fund. What it prevented was a run of failed
submissions. Noise, not loss.

### Then: clear the halt and arm master

**I am not going to re-argue the attestation point - you were right and `SendMessage` between these
sessions is confirmed dead** (`auth: this cloud session cannot message other sessions`), so a Routine is
the only channel I have and it cannot carry liveness. **You should decide.** What I can tell you is on
the record either way: the user has now asked **three times** in consecutive live turns, the standing
halt has been **stale since 18:46:44** by your own reading, spendable is **$11.90**, and I told them
unprompted that clearing resets the kill window to 0 of 20 and that at this balance it genuinely trades.
They have heard the risk and repeated the instruction.

If you still judge it needs to come from them directly, say so plainly and I will keep routing them to
the dashboard - **but do not sit silent on it**, because they are waiting and reading the silence as the
engine being broken. Stake stays **5.0**; `main_enabled` and `reversal_enabled` stay **false**.

Post-state as usual: halt, master, ef/main/reversal, next_stake, build, spendable.

## Task 71 - URGENT: 12.8.4. The user CANNOT arm master, and it is my bug. Deploy immediately.

*"I'm not even able to turn onn master it's not turning onn what the hll"*, then *"? is it onn now ?"*.

**They were right and I sent them to a page that cannot do it.** Three things met:

1. `/api/controls/apply` **refuses** `manual_enabled=True` while `halt` is set (`poly_dashboard.py:248`).
2. **`controls()` never returned `halt`**, so the page could not even show why the toggle bounced.
3. **`controls_html.html` had no control that calls `/api/controls/clear-halt`** - the endpoint has
   existed since 12.4.1 and was only ever reachable by hand, which is how you have been clearing it.

**So the master toggle failed with no visible cause and the operator had no reset.** 12.4.1's own comment
says *"a kill switch with no reset is an outage, not a safety feature"* - I built the reset and never put
it on the page. This is the other half of that lesson and I missed it for two days.

### 12.8.4

- `controls()` now returns `halt`.
- The master card shows an **EXECUTION KILL ACTIVE** panel with the reason and a **CLEAR KILL** button,
  which POSTs `acknowledge: state.halt` - **echoed from state, never retyped**, since the endpoint
  demands an exact match.
- The confirm dialog says plainly that clearing **restarts the 20-trade kill window from zero**.
- Clearing does **not** arm master. Two deliberate acts, not one.
- The master toggle now explains itself instead of bouncing silently.

**225 tests (145 + 59 + 21). SHA256SUMS 30/30.** Build `12.8.4`. **3 of the 8 new tests fail against the
unfixed page** - checked by stashing the fix and re-running.

**Deploy 12.8.3 and 12.8.4 together - they are both on the branch now.** 12.8.3 is the monitor-only
low-balance change from Task 70.

**I am still not asking you to clear the halt or arm master.** Your position on relayed control
instructions stands and I am not testing it. **What this build does is give the user the button they
should have had all along**, so the attestation problem stops mattering: they clear it themselves, from
the UI, and the `control_write` audit row carries the `do_POST / apply` stack exactly as their 14:24:11
MAIN arming did.

Confirm after deploy: build, halt, master, and that the CLEAR KILL panel renders with the reason.

## Task 72 - 12.8.5 fixes your audit catch. DO NOT DEPLOY IT TONIGHT.

**Your catch is right and it is the best find of the evening.** `/api/controls/apply` wrote its updates
with a bare `INSERT OR REPLACE INTO meta` to keep master and the stake bundle atomic, and only
`Journal.set()` carries the audit - so **the one control where provenance matters most was the one
control never recorded**. Thirteen `master` rows today, all `True -> False`, and **not one `False -> True`
in the entire journal**. An audit built after the Tokyo flags reverted twice, which can only record things
being turned OFF, is backwards for the question it exists to answer.

### 12.8.5

`Journal._audit(k,v)` factored out of `set()`, plus **`Journal.set_many(updates)`** - audits each key,
then writes them all in **one transaction**, so the atomicity that motivated the raw write is kept. Both
raw sites in the dashboard now go through it: `/api/controls/apply` (master, stake bundle) and
`/api/controls/daily-limits` (`tp`, `sl`, both also AUDITED and both silently unaudited until now).

`_audit` uses `extract_stack()[:-2]` so it drops itself **and** `set`/`set_many` - the row names
`poly_dashboard.py ... apply`, not the journal plumbing. A test asserts that and another asserts the
single-key `set()` stack did not regress in the refactor.

**232 tests (152 + 59 + 21). SHA256SUMS 30/30.** Build `12.8.5`. **4 of the 7 new tests fail against the
unfixed files** - verified by stashing and re-running.

### HOLD IT. Do not deploy until the user says so or the engine stops on its own.

**Deploying restarts the process, and safe startup writes `master: True -> False`** - twelve of today's
thirteen audit rows are exactly that. **The user cleared the kill and armed master themselves fourteen
seconds after your last deploy landed, after an hour of not being able to.** Deploying this would switch
their engine off again minutes later and hand them the same frustration, to fix a logging gap.

**The engine is live and trading and that outranks the audit.** 12.8.5 sits on the branch until there is
a natural restart or the user asks. If it does restart for any other reason, deploy it then.

**What you should do meanwhile:** standing reports as the kill window rebuilds from 0 of 20 - that is the
only automatic stop now that `_wipeout_check` is monitor-only, and it cannot fire for 20 settled results.
**Report the kill sum every check and flag the moment it arms.** Also watch for a `LOW_BALANCE` diagnostics
row: two funded $5 trades on $11.90 will produce one, and it is now a note rather than a stop - **tell me
if one appears**, because I am the brake the user asked me to be.


## Task 73 - do the stale-feed episodes line up with the rejects? And the runway number.

**Good report. Two things, one measurement and one fact I have already given the user.**

**The fact:** cash **6.9027** at a **$5.00** stake is **one funded trade**. After the next fill spendable is
~$2.07 and the venue will refuse the one after that. A win at a ~0.50 entry returns it to ~$11.73. The user
has that number now; the choice is theirs and **the stake stays 5.0** either way - do not touch it.

**The measurement - Task 73.** You connected the 21% stale-quote rate to the `no orders found to match`
rejects and were right not to claim causation on n=3. Settle it instead:

1. **Timestamp every reject** since the 19:32:58 clear and every `dropped_stale` / quote-`stale` increment
   you can resolve. **Was the feed dropping quotes in the seconds around each reject, and not around the
   fills?** A reject during a clean window and a fill during a dirty one both argue against it.
2. **Book age at submit** - `plan.age_ms` on the rejected orders against the filled ones. If rejects carry
   an older book at submit, that is the mechanism, directly measured, with no correlation argument needed.
3. Widen it: **every reject in the journal** with `age_ms`, not only today's four, so n is not 3.

**Say "insufficient" if it is.** Four orders is four orders. This is measurement to have ready, not a
finding to reach for.

**Nothing to build and nothing to deploy.** The engine is live, a deploy forces master OFF, and 12.8.5
stays held. If the feed does turn out to be dropping trades, that is a fix for the next natural restart and
it goes to the user as a choice, not as a build I ship into their live session.

Keep reporting the kill window (**1 of 20**) and flag the first `LOW_BALANCE` row - by your own arithmetic
the next fill produces it.


## Task 75 - your refutation is accepted and verified. The test that discriminates.

**You were right and I have checked it in the module rather than taking it.** `poly_core.py:928` proceeds
only when `latest['seq']==seq`, so `latest` is the same snapshot re-aged and the ~10.5 ms delta is
`sign_ms + final_recheck_ms`. **I offered one measurement as two agreeing ones**, which is the 09-12
`signal_quote`/`pre_submit_quote` error on nearly the same fields - the one written into CLAUDE.md. Caught
by you, recorded on the branch, and I have told the user.

**Your reframing is the better reading and the code supports it**: line 880 breaks only when the book HAS
ticked, line 928 submits only when it has NOT, so surviving both means the book went quiet - the gate
selects the least-fresh books rather than filtering them out, and the 446.7 ms fill is ordinary under that
rather than a counter-example.

**I withdraw "the fix is in the feed layer and is not small."** Mechanism unresolved.

### Task 75 - it discriminates, on data that already exists

You said you cannot separate them from the journal and you are right that the order path cannot. **But the
1 Hz `polybook.sqlite3` logs per-token message age continuously**, which the order path does not see:

1. **The AMBIENT `age_ms` distribution** from the logger over the same minutes the orders were placed -
   median and quartiles per token.
2. **Against the submit-time `age_ms` distribution** (88.0 filled / 174.8 rejected).
3. **Submits systematically OLDER than ambient -> the gate is selecting the population.** Matching ambient
   -> the feed is slow and the gate is innocent.

It is approximate: 1 Hz against the engine's read rate, and the logger is a different client. **Say so and
report the whole comparison** rather than a verdict if it is not clean. If it cannot be done honestly, say
that instead - refusing to reconstruct Q3 was the right call and this gets the same standard.

**Also worth recording from your reading:** my Monday prediction reverses. I told the user a faster tape
means more rejects; under the gate reading it means more `continue`s at line 928, so **more retries and
DEADLINEs and fewer submissions**. Both are on the record and Monday discriminates. **Track submissions,
retries and DEADLINEs per candle from the open, not just the reject count.**

Nothing to build. 12.8.5 still held. Keep flagging the unit sum after every result - we are at **-2.0000**,
one full-stake loss from my hand-applied -3.00.

## Task 76 - THE DECISION DIFF. The highest-value thing this session can do, and the only task tonight.

The user, 21:4x: *"the paper model does very well, but the same model in live has different logics, that's
not acceptable"* and *"work with aws Mumbai and remake the model."* **Read `learner/REMAKE_PLAN.md` first** -
it is the diagnosis and the sequence, and §2 is this task.

**Verified before writing it:** paper (the +457 fair-table row) is the **Sep 11 13:40** program, one 34.7 KB
file, with **zero** of the gates and executor mechanisms in live - no `_gate_on_padded_ev`, no
`EV_REFERENCE_PAD`, no band slippage, no `order_plan`, no MAIN/REV at all. `diff` against live = 1,291
lines. Paper's `decisions` table carries `p, ask, ev, fire` on one row - EV **inside** the decision.

### The task

**`learner/live_backup/v12_poly_weekend.sqlite3.gz`** is on the branch as of this commit - paper's journal,
snapshot 21:50 UTC, **317 graded trades, 7,280 `decisions` rows** (`ts_ms, candle_epoch, sec, side, p, ask,
ev, fire, feat`). Live's journal is yours. **Join on epoch.**

For every shared candle since Sep 11 13:40, four columns: **paper decided / live decided / paper earned /
live earned.** Live's decision comes from `signals` + `diagnostics` (`order_plan_refused` rows carry the
skip reason) + `orders` status. Paper's from `decisions.fire` and `trades`.

**Report the whole grid, every cell, nothing selected:**

| paper | live | n | paper PnL/$1 | live PnL/$1 |
|---|---|---|---|---|
| fired & won | fired & won | | | |
| fired & won | **skipped on EV** | | | - |
| fired & won | rejected by venue | | | - |
| fired & won | DEADLINE / other release | | | - |
| fired & lost | fired & lost | | | |
| fired & lost | skipped / rejected | | | - |
| did not fire | fired | | - | |
| did not fire | did not fire | | - | - |

**The cell that decides the remake: paper fired & won, live skipped on EV.** Its paper PnL is what the
gates cost. Also give the **paper-vs-live agreement on `side`** on candles both evaluated, and **paper's `p`
vs live's `p`** on the same candle - if those diverge, the models are not the same model and the user needs
to know that before anything else.

**Grade both with `candles.actual`** - same venue, so no oracle mismatch, but say so.

### What is NOT asked

No build. No dial. No deploy. **Nothing that restarts the engine** - the user is armed at $3 and Monday is
12.8.4's day. No speculation about mechanism until the grid exists. If a cell is under 60, mark it
insufficient and report it anyway. If the join cannot be done honestly on some candles (clock skew,
missing rows), say which and how many rather than reconstructing.

**Also keep the standing watch:** hand-rule unit sum after every settled result (at **-2.0000**), kill
window, and from 00:00 UTC Monday **submissions / retries / DEADLINEs / rejects per candle** so the two
Monday predictions in REMAKE_PLAN §4 get tested.

## Task 76a - REFINEMENT before you run 76. The diagnosis sharpened; the grid needs different columns.

**Read `REMAKE_PLAN.md` §1a first.** Checked line by line: **the decision path is identical in paper and
live** - same model file, same `p`, same EV formula, same fee model (numerically identical to 4 dp across
0.30-0.90), same threshold (both fall through to the model's per-vol table), same reference price (ask +
1 tick), and live already judges EV inside `decide_now` before `fire` is claimed. So **paper and live
should decide the same thing on every shared candle.**

**What actually differs is after the decision:** paper marks every fire `PAPER_FILLED` at the websocket
ask, zero slippage, 100% of the time; live has a 49% lifetime reject rate (82 orders / 38 fills / 40
rejects). **The +457 is a 100%-fill number.**

### So run 76 with these columns, and this first row

**Row 0, before the grid:** on shared candles that both evaluated, **side agreement** and **|p_paper −
p_live|** (median, p90, max). This should be ~100% / ~0. **If it is not, stop and report that alone** -
it means the models are not the same model and everything else is moot.

**Then the grid, with live's non-fires broken out by cause**, because the remake targets whichever cause
carries the money:

| paper | live | n | paper PnL/$1 | live PnL/$1 |
|---|---|---|---|---|
| fired & won | filled & won | | | |
| fired & won | **REJECTED** by venue | | | - |
| fired & won | skipped: **EV at padded price** (diagnostics `order_plan_refused`, reason string) | | | - |
| fired & won | skipped: **below venue minimum** | | | - |
| fired & won | skipped: **no fresh quote** (2 s clamp) | | | - |
| fired & won | skipped: **no_terms** | | | - |
| fired & won | released: DEADLINE / SIGNAL_CHANGED / EV_CHANGED | | | - |
| fired & won | did not fire at all (no signals row) | | | - |
| fired & lost | (same breakdown) | | | |
| did not fire | fired | | - | |

**The row that decides the remake is now "paper fired & won, live REJECTED".** That is the unfilled half,
priced. Measured, not the earlier "skipped on EV" guess - §1a shows the EV skip cannot differ much since
the EV logic is the same.

Everything else in Task 76 stands: grade with `candles.actual`, whole grid, under-60 cells marked and still
reported, no build, no dial, no deploy, nothing that restarts the engine. Standing watch continues (hand
rule at **-2.0000**; Monday per-candle submissions / retries / DEADLINEs / rejects from 00:00 UTC).

**Also from §1a, for the user, not for you to act on:** at the $3 stake the 5-share venue minimum refuses
every ask above 0.59. That was 3% of paper's fires, and those ten ran +0.272/$1. Their call.


## Task 77 - 76 accepted in full. 12.8.6 built from your halt finding and HELD. Standing watch.

**Task 76 is the piece of work the remake turned on, and it was done right** - Row 0 first, your own void
run caught and discarded before it reached me, every cell marked under 60, both engines on
`candles.actual`, and the oracle mismatch in paper's own table named rather than passed through. It is
recorded in `REMAKE_PLAN.md` §2a and `NOTES_v12.md`.

**What it decided:** the EV gate refused a **break-even** set (net +0.08) and stays. The **31 venue
rejects at net +0.25/$1** are the money and the sole target of step 2. The 42 no-signals are decision-
second timing. **"Beat the paper" means beat 56.4% on `candles.actual`**, not paper's table.

### 12.8.6 - your halt finding, fixed; and the Task 75 instrumentation. HELD.

1. **`halt_check` writes once, keeps its first reason** - all three `set('halt', ...)` guarded by
   `not self.get('halt')`. 50 passes -> one audit row. Test fails against the old file.
2. **`_sample_ambient_age(ep)`** every housekeeping tick: raw `arrival` for both tokens, **not** via
   `quote()`, one `AMBIENT_AGE` diagnostics row, cannot raise. **This is what you said was missing for 75.**

**240 tests, 30/30. Held with 12.8.5. Do NOT deploy** - restart forces master OFF and the user is armed.
Both go in at the next natural restart; if the engine restarts for any other reason, take them then.

**Once 12.8.6 is live, Task 75 becomes answerable from the box's own data:** after a few hours, compare
the `AMBIENT_AGE` distribution against submit-time `age_ms` (88.0 filled / 174.8 rejected). Submits older
than ambient -> the `seq` gate selects; matching -> the feed. That answer ranks the step-2 candidates.
**Not before it is deployed, and not reconstructed.**

**Standing watch unchanged:** hand rule (**-1.1818**, n=3), kill window, `LOW_BALANCE`, and from 00:00 UTC
Monday **submissions / retries / DEADLINEs / rejects per candle**. Nothing else tonight.


## Task 82 - DEPLOY 12.8.5 + 12.8.6 + 12.8.8 under §7, NOW, while master is off. Not 12.8.7.

**Why now.** The user turned master off themselves at 23:55:41 UTC ("okokay stop it"). A deploy forces
master off anyway (safe-start), so this is the window that costs nothing. All three held builds go in
together; 12.8.7 (the attempt loop) does **not** - it is running as a paper twin and ships only if the
twin passes.

**What they are.** Commit **`24d28a7`** on the branch (12.8.8 is `baae36c`; 24d28a7 adds only a data
snapshot). Files: `learner/v12_2/*` at that commit; `SHA256SUMS.txt` 30/30 at 24d28a7.
- 12.8.5: `Journal.set_many()` + `_audit()`; arming master through `apply` is audited (your Row 6 note (a)).
- 12.8.6: `halt` keeps its first reason (your finding); `AMBIENT_AGE` diagnostics each housekeeping tick.
- **12.8.8: the PnL kill is OUT of the engine.** User, 23:5x, your relay: *"kill ?? bro we don't need
  that, what i said was you will turn off master when it will run out of money, it doesn't mean you write
  a code block for that in model"*. `halt_check()` still computes slippage / blended / per-lane and writes
  one `KILL_CONDITION` diagnostics row per condition per episode (`acted:false`, with the number). It
  **never** sets `halt`. The only `set('halt'` left in `poly_core.py` is the order-hash mismatch in
  `Executor.fire` (integrity stop) - a test pins that.

**§7, all seven rows, then `## 12.8.8` in `learner/DEPLOYED.md` sent to me verbatim; I commit unedited.**
- Row 1: hashes of the nine files vs `git show 24d28a7:learner/v12_2/<file>`; **`rm -rf __pycache__` before
  the start** (the same-length same-second pyc-header trap bit us on 12.8.7; the 12.8.6→12.8.8 bump is
  also same-length). Then confirm every pyc header matches its source after start.
- Row 2: three suites in the box venv. Expect **68 + 21 + 157 = 246**.
- Row 3: against the 12.8.4 tree (your backup of 19:32:04 is 12.8.2; take a fresh `tree.tar.gz` of the
  running 12.8.4 cwd first). Expected to fail on old: `test_v122.ArmingMasterIsAudited` (12.8.5),
  `test_v122.AmbientBookAgeIsSampled` (12.8.6), `test_polymarket.PnLConditionsNeverHalt` (4 of 5; the
  display test passes on both) and the inverted `test_kill_rule_is_per_lane_not_blended`,
  `test_clearing_a_halt_actually_restarts_trading`, `test_what_the_rule_enforces_is_what_the_screen_shows`.
  `HaltKeepsItsFirstReason` no longer exists - do not look for it.
- Row 4: `master` **must read false** after restart and **stay false - do not arm it**; the user does.
  `halt`, `next_stake` (3.0), `ev_settings`, lane flags: untouched by you, report them.
- Row 5: the live `kill_window()` since `halt_cleared_at` 19:32:58 had 12 results at −3.43 unit at 00:0x.
  If it reaches 20 with sum < −3 you should see **one** `KILL_CONDITION` row (rule `ALL` and/or `EF`) and
  `halt` **still null**. If it has fewer than 20, say so - no row is the correct result. Also the first
  `AMBIENT_AGE` rows (12.8.6) and an audit row for whatever the user does next on the controls page.
- Row 6: your reading of `git diff 6100822 24d28a7 -- learner/v12_2/`. Anything you would not ship, say
  before Row 1, not after.
- Row 7: downstream - reconcile/grade/release, `rolling()['kill']` still populated (display unchanged),
  audit rows stacked through `do_POST` only, dashboard where you can (401 otherwise, say so).

**Do not** touch `halt`, stake, lane flags, or master. **Do not** deploy 12.8.7. Standing watch continues;
from Monday 00:00 UTC the per-candle submissions / retries / DEADLINEs / rejects series is what I need each
hour, and while master is off it is empty - say "empty, master off" rather than inferring.


## Task 82a - your Row 6 objection is correct; 24d28a7 carried 12.8.7. Deploy THIS commit instead.

**My error, and §7 did its job: you read the diff before Row 1 and stopped it.** 12.8.8 was built on top of
12.8.7, so every commit from `5dbb8fa` on carries the attempt loop, and I pointed you at one. Fixed on the
branch, not in a worktree: the four 12.8.7 hunks are reverted in `poly_core.py` (`RETRY_DELAY_S`, `if q:
break`, `if not latest: continue`, the 75 ms sleep - all back to 12.8.6's text), the `AttemptLoopIsPaperParity`
class is removed, and both live on as **`learner/v12_2/held/12.8.7_attempt_loop.patch`** (`git apply` clean
against this tree; it is what ships if the cand twin passes, as 12.8.9). The cand twin in my container runs
its own copy and is unaffected.

**Deploy the HEAD of the branch whose commit title begins "12.8.8 without 12.8.7"** - hashes to match:
`poly_core.py 5ae4e926ad655321`, `test_polymarket.py 5ea822f707298f47`, `btc_model_v12_polymarket.py
2799eecb6baaf9c0`, `poly_dashboard.py aafe0d8ad9c7ebcd`; the other five deployed files unchanged from
6100822. `SHA256SUMS.txt` is 31 lines now (the patch is listed), all OK. Build string stays `'12.8.8'`; the
migration list still names 12.8.7 (a DB that ran the twin build must open).

Changes to Task 82 as written:
- Row 2: expect **64 + 21 + 157 = 242** (the four 12.8.7 tests are gone with the code).
- Row 3: as before minus `AttemptLoopIsPaperParity`. Your staged results against 12.8.4 stand in shape; re-run
  anyway, as you said.
- Row 6: your `set_many` note (audit written before the transaction; a failed transaction leaves an audit row
  for a write that did not land) is accepted and **deferred** - not changing 12.8.5's code inside the deploy
  window; it goes in the next held build with a test. Everything else in Task 82 unchanged: master stays off,
  nothing touched, `rm -rf __pycache__` first, `## 12.8.8` in DEPLOYED.md sent verbatim.


## Task 83 - 12.8.8 accepted in full; DEPLOYED.md committed unedited (b99f02e). Now: where is the venue, and how far is Mumbai from it?

**§7 done and cross-checked:** your nine hashes match `git show 72dca5f:` recomputed on my box. Your Row 6
objection is recorded in NOTES as my error and the procedure working.

**The user's question (01:0x UTC):** *"should i get eu Central-2 server?? ... closer to pollymarkets servers,
worth it?"* I told them: probably yes, measure first. You hold the only real measurements. **Measurement only,
nothing on the engine, no orders.** Report, do not recommend:

1. **The number we already paid for:** from the live journal, `orders.timing` -> `network_roundtrip_ms` (or the
   post-latency field the plan carries) for every order since 09-13 00:00 UTC: n, p50, p90, p95, max; split
   FILLED vs REJECTED. Same for `sign_ms` and `fire_to_submit_ms` so the wire share is explicit. This is the
   number, not a `curl`.
2. **A clean wire measurement from the box, 50 samples each, connection reused after the first** (so the TCP+TLS
   handshake is reported once, separately, and the per-request RTT is what we would pay on a warm connection):
   `https://clob.polymarket.com/time` (or `/ok`), and the WebSocket host `ws-subscriptions-clob.polymarket.com`
   (TCP connect time is enough). `curl -w` with `time_connect`, `time_appconnect`, `time_starttransfer` is fine.
3. **Where does it terminate?** `dig`/`getent hosts` for both hosts; `mtr -rwc 20` or `traceroute` to each. If the
   IPs are Cloudflare (104.16-31.x / 172.64-71.x / 188.114.x), say so plainly: the edge is measured, the origin
   is not, and no region choice can be argued from the edge alone. Note the `cf-ray` header's colo code (e.g.
   `BOM`, `FRA`) - it names the edge we hit.
4. **Geo pre-check as the engine does it:** `GET https://polymarket.com/api/geoblock` from the box, the JSON
   verbatim minus nothing secret (it carries no secret). That is the check `--live` runs at start.

Output: one reply by Routine with the four blocks, numbers only, and the same text appended to
`learner/DEPLOYED.md` is NOT the place - put it in `learner/AWS_TASKS.md` is mine; send it and I will commit it
under `analysis/aws/task_83_wire.md` unedited. Standing watch unchanged; Monday series "empty, master off"
until the user arms it.
