# Polymarket v12.2 — what changed and why

Built on v12.1. The v10 model, its weights, the Binance inputs, the Polymarket
book feed, the FAK capped-buy policy, staking, settlement and the dashboard
layout are unchanged. Existing SQLite history is migrated, not replaced.

Every claim below is backed by a test in `test_polymarket.py` (45),
`test_lanes.py` (14) or `test_v122.py` (16). All 75 pass.

---

## 1. MAIN and REVERSAL are real lanes now, switchable from Trade Controls

**The problem.** v12.1 reported `source_available=false` for both lanes and
never fired them. Your dashboard shows the symptom: `MAIN 0.00 · REVERSAL 0.00`
after 54 minutes live. The stated reason was that the packaged v10 classifier
contains no MAIN or REVERSAL logic.

**That reason was true but led to the wrong conclusion.** MAIN and REVERSAL
never ran on v10 in the first place. In Build 11.2 they share a separate signal
engine that reads Binance spot trades and depth only — no v10, no Polymarket
book, no EF learner. v12 already carries every input it needs.

**The fix.** `poly_lanes.py` ports that engine. Constants, gate order and
weights are copied from the live file, and each block names the source lines.

| | MAIN | REVERSAL |
|---|---|---|
| side chosen by | pressure gauge direction | same test, re-evaluated live |
| confirmed by | fair odds ≥ 0.60 (UP) / ≤ 0.40 (DOWN) | same |
| volume gate | pace ≥ 0.70 × recent median | same |
| persistence | 12 s **and** 60 feature rebuilds | none, fires on the first flip |
| window | up to 295 s | 30 s to 285 s |
| relationship | the bet | a hedge placed beside it; MAIN stays open |

Both are gated by the same `allowed()` check EF uses, so the master switch and
the per-kind switch behave identically for all three. A lane switched off still
evaluates and is still recorded; only the order is suppressed.

**What this does not claim.** Porting makes the lanes work. It does not make
them profitable. On the live Predict.fun account MAIN has **0 settled fills**
and REVERSAL has **53 for +1.27**. Neither has ever run on Polymarket, whose
book and fee model differ. Start them in paper.

**One deliberate difference.** Build 11 drifts the 13 feature weights by online
SGD after each settled candle. This port starts from the published anchors and
will load persisted weights if present, but does not itself train. A learner
that trains on Polymarket settlement is a separate decision.

## 2. Money comes from the Polymarket API, not from local arithmetic

Your dashboard footer reads `CONFIRMED_FILL_WITH_ESTIMATED_VENUE_FEE`. That is
a local estimate presented as a result.

| figure | v12.1 | v12.2 |
|---|---|---|
| available funds | venue balance (already correct) | unchanged, still the venue balance |
| fees | local `rate × (p(1-p))^exp` estimate | `fee_rate_bps` from the venue's own trade record |
| PnL | `payout − (spent + fees)` computed locally | `realized_pnl` / `total_pnl` from the venue position |
| wins and losses | sign of the local PnL | sign of the venue PnL |
| bankroll for sizing | local capital + local PnL | venue cash + venue position value |
| portfolio value | not fetched | `get_portfolio_value()` |
| account PnL | not fetched | `get_user_pnl()` realized, unrealized, fees paid |

A new `venue_truth_loop` pulls this every 20 s and writes it to the `results`
rows and a `venue_state` table. The local figure is **kept beside** the venue
figure rather than overwritten, and `pnl_divergence()` reports the largest gap,
so if the two ever disagree you find out instead of quietly trusting one. Rows
the venue has not priced yet are excluded from the venue metrics, never
back-filled from local math.

Outcome resolution was already correct and is untouched: it reads Polymarket's
own `umaResolutionStatus` and `outcomePrices`, never Binance.

## 2b. Account, pending and fundable — the three numbers in your screenshot

Your dashboard shows `AVAILABLE $13.42` against a wallet of `$16.42`, with
`pending order reserve $3.00` and `fundable now $13.42`. Two separate problems
produce that, and the second one is the important one.

**The order that created the reserve was misclassified.** `LAST LIVE ORDER` reads
`UNKNOWN · RequestRejectedError`. A RequestRejectedError with a 4xx status is the
venue explicitly refusing the order, which is not ambiguous at all. Build 12.0
put every post exception through one handler and called them all UNKNOWN, and an
UNKNOWN holds its budget in reserve. So a rejected order kept $3.00 locked.
v12.1 already fixed the classification; v12.2 keeps it.

**The reserve was never checked against the venue.** This is the part v12.1 did
not fix. The reserve is the only figure on that panel Polymarket does not
publish — it is a local sum over rows we wrote ourselves — so it is the one that
drifts. v12.1 fetched the venue's open-order list and then did nothing with it.

v12.2 cross-checks every unresolved local order against that list on each venue
poll and reports the reserve by how far it has been verified:

| | meaning | holds funds |
|---|---|---|
| confirmed | the venue lists this order as open | yes |
| unverified | not yet proved either way, inside the grace period | yes |
| phantom | repeatedly absent from the venue with no fill | **no** |

Release is deliberately conservative, because there is a real race between
submitting an order and it appearing in the listing: the order must be older
than 5 seconds **and** absent on two consecutive checks **and** have produced no
fill. An order that traded is never phantom. The raw local figure stays
available through `live_reserve(venue_verified=False)` so the two can be
compared.

**And AVAILABLE stops being wallet minus reserve.** Build 12.0 subtracted the
local reserve from the venue balance and presented the result as what you have.
A phantom row therefore reduced the number you read as spendable, and with FAK
orders — which cannot rest — such a row is almost always phantom within seconds.
v12.2 reports the venue balance as-is, with the reserve shown beside it as
concurrency headroom.

## 3. Feed staleness was being measured wrong

**The bug.** v12.1 recorded feed age as *time since we last received a message*.
That measures whether the socket is alive, not whether the data is current. A
lagging feed keeps delivering, so the age stayed near zero while every price in
it was seconds old, and the dashboard showed LIVE.

Every stream now carries two numbers, and must pass both:

- `arrival_age_s` — seconds since any message (socket liveness)
- `event_lag_s` — receipt time minus the message's own event timestamp (freshness)

**The second bug.** The single 2.0 s limit was applied to all three streams.
Measured over 100 s on a live connection:

| stream | median | p95 | p99 | max |
|---|---|---|---|---|
| spot | 0 ms | 690 ms | 1483 ms | **2617 ms** |
| perp | 0 ms | 302 ms | 886 ms | **2433 ms** |
| depth | 103 ms | 148 ms | 253 ms | 520 ms |

spot and perp are event driven and genuinely gap past 2 s when nobody trades, so
a healthy feed was intermittently registering as stale and blocking fires for no
reason. Limits are now per stream, set from that measurement: 6 s for spot and
perp, 2 s for depth, all configurable.

**Endpoint failover.** Hosts are lists, tried in order, and the working one is
remembered and reported. Measured from the build container: every
`api.binance.com` mirror answers **HTTP 451** while `data-api.binance.vision`
serves the identical `/api/v3` payloads; on websockets `data-stream.binance.vision`
and `fstream.binance.com` connect while `stream.binance.com` resets. v12.1's
chart seed used `api.binance.com`, so on such a host the chart was simply empty.
A stream that stops delivering is force-reconnected after 8 s rather than waiting
out the websocket ping timeout, which can leave a half-open socket hanging.

## 4. The order book no longer dies on a clock skew

v12.1 dropped every book event more than 2 s from local time. On a host whose
clock had drifted — a fresh VPS before NTP settles — that discarded the entire
Polymarket feed and reported an empty book rather than a clock problem. The
offset is now measured, seeded from the first event, corrected for, and exposed.
Genuinely old events are still dropped. Quote age is taken from a monotonic
clock, so an NTP step cannot make a stale book look fresh.

## 5. Execution and retry

- **Latency telemetry covered only accepted submissions.** Rejections and
  timeouts — the slow ones — were excluded from the published p95. Every attempt
  is sampled now, with the outcome recorded, and percentiles are reported per
  stage (quote wait, decision, signing, final recheck, network round trip) and
  per outcome.
- **The 2.0 s total budget and 1.2 s post timeout were hardcoded.** Fine beside
  the venue, too tight from Mumbai, where three attempts of signing plus round
  trip do not fit. Both are now `--execution-budget-ms` and `--post-timeout-ms`,
  with `--max-attempts`. Set them from the latency block, not from guesswork.
- **Slippage for the kill rule** was measured against the signal quote, which can
  be hundreds of milliseconds old and flatters the number. It now uses the
  pre-submit ask, the price the fill can fairly be judged against.

## 6. Schema

`signals` was keyed by candle alone, which is correct while EF is the only lane.
MAIN and REVERSAL both trade the same candle — REVERSAL is a hedge beside an open
MAIN — so the key now carries the lane. The migration rebuilds the table, stamps
every existing row `EF` (which is what it was) and drops nothing. Grading is per
lane, so a hedge is not netted into one meaningless number.

## 7. Observed on the first paper run — read this before enabling MAIN live

MAIN fired end to end on the smoke run and was then **skipped by the EV guard**:

    MAIN UP  p=0.824  reason: "UP strong ~$35 with fair 0.99 held 15s"
    skipped: padded price fails model EV

This is the system working, and it points at a real tension. MAIN requires its
alignment to hold for 12 seconds before it fires. On a 5-minute binary, `fair`
reaching 0.99 means the candle is already decided, so by the time MAIN is
confirmed the market has usually repriced and the contract is no longer worth
buying. The EV check then refuses it, correctly.

Expect MAIN to generate signals that are frequently skipped. That is not a bug
and it is **not** something to fix by lowering the EV bar: the guard is the only
thing stopping the lane from buying near-resolved contracts. Run it in paper
first and count how many of its signals actually clear the EV bar before giving
it any money. REVERSAL fires on the first flip with no persistence requirement,
so it should not suffer the same lateness, but that is a prediction, not a
measurement.

---

# 12.2.2 — fixes found on your live box

**The dashboard still showed the lanes as DISABLED.** Trade Controls reported
MAIN and REVERSAL correctly, but the front page carried a hardcoded
`text('mainDirection','DISABLED'); text('revDirection','DISABLED');
text('revMeta','Not part of v10 Polymarket strategy')` left over from when the
lanes were stubs. I changed the Python and missed the page. Both panels now
render engine state, and each of the five cases was exercised directly:

| situation | MAIN panel | REVERSAL panel |
|---|---|---|
| armed, no alignment | WATCHING · flow and odds do not agree | WATCHING · waits for a MAIN to hedge |
| master switch off | ARMED · master switch is off | ARMED · master switch is off |
| switched off in controls | OFF · switched off in Trade Controls | OFF |
| MAIN fired | UP · held alignment · p 0.820 | WATCHING · signal still agrees with MAIN UP |
| REVERSAL fired | UP | DOWN · hedge against MAIN |

**Venue PnL was not attaching to settled rows.** Your `/api/state` showed
`pnl_basis: LOCAL_FROM_FILLS` with `awaiting_venue: 2`, so the whole point of
the change was not taking effect. Cause: a 5-minute position is `OPEN` only
while the candle runs, becomes `REDEEMABLE` at settlement and `CLOSED` after
redemption, and the position query used no status filter — so it returned
everything except the settled positions whose PnL was wanted. All three statuses
are now queried and merged, deduplicated, and narrowed to the specific markets
still awaiting a price so it costs one small lookup rather than paging history.

**Confirmed working on your box from the state you sent:**

    reserve_detail: phantom 3.00, effective 0.00   <- the stuck reserve released
    funding_headroom: 18.40                        <- full wallet, not 3.00 short
    fee_basis: VENUE_CONFIRMED_TRADE_AND_VENUE_FEE
    feed: lag 0.064-0.070s, clock skew 0, zero reconnects
    controls: all three lanes source_available, manual_enabled

The `dashboard API error` you saw at 1m19s did not reproduce in any startup
state I could construct, and your later paste returned HTTP 200 with a complete
payload, so I am recording it as transient during startup rather than inventing
a cause for it. If it returns, the message itself is written into the page under
the header — send me that line.

---

# 12.2.3 — the dashboard API error, root cause found

Your box reported it exactly as the hardening intended:

    {"ok": false, "error": "Object of type datetime is not JSON serializable",
     "endpoint": "/api/state"}

**Cause.** Polymarket's account-PnL point carries `timestamp` as a Python
`datetime`. It went straight into the dashboard payload, and `json.dumps`
cannot encode one. In 12.2.1 that exception escaped the handler, the page got an
HTML traceback it could not parse, and the panel went dark with no reason. This
is the original error from the first screenshot, and it was mine: I added the
field that carried the datetime.

**It broke a second thing quietly.** The same value made `venue_snapshot()` raise
inside the venue loop's exception handler, so every venue snapshot was discarded
and the reported PnL silently stayed on the local basis. That is part of why
`pnl_basis` read `LOCAL_FROM_FILLS` with rows awaiting the venue.

**Fixed in three places**, deliberately more than one:

1. At the source — `account_pnl()` converts the timestamp to an ISO string, so
   nothing leaves the venue layer that is not JSON-native.
2. At the encoder — the response sanitiser now handles datetime, date, time,
   bytes and any other unencodable value, falling back to `str()` rather than
   failing the whole response. One bad field can no longer cost the dashboard.
3. At the database write — the snapshot uses `default=str`, so a future SDK type
   cannot silently discard venue truth.

Regression tests cover all three, including the exact payload shape from your
box: the raw encode fails as it did live, and the server's encoder succeeds.

---

# 12.2.4 — a signal is not a position

You saw MAIN reported as fired while no order existed, and the lane never tried
again. Both are real defects and both were mine.

**What actually happened to your fire.** MAIN called DOWN at probability 0.728.
The DOWN contract was asking 0.80, which after the one-tick pad and fee costs
0.8209 all-in, against a venue break-even of 0.8114. The EV was **-0.113**, so
the order was correctly refused; clearing even the lowest threshold would have
needed a probability of 0.944. The guard did its job. The reporting did not.

**Defect 1: the dashboard said fired when it meant called.** The lane set its
position the moment it produced a decision, before any order was attempted, so a
refused MAIN rendered exactly like a held one. Signal and position are now
separate throughout: a call that never reached the book shows as
`SIGNAL DOWN · called but not executed · <reason>` in muted styling, and only a
placed order shows as a position. The engine reads the order's actual outcome
back from the journal and tells the lane, so the page cannot claim more than
happened.

**Defect 2: a refused MAIN consumed the candle.** Because the position was
latched on the call, MAIN could never retry when the price improved seconds
later. A refused order now leaves the signal standing and the lane may fire
again in the same candle, capped at 6 attempts so a permanently unpayable signal
cannot retry all candle. A placed order still ends the candle: one position per
candle, as in the original.

**Consequence worth stating: REVERSAL now requires a real MAIN position.**
Previously it hedged the call. If MAIN was refused there is nothing to hedge,
and firing anyway would be an outright bet wearing the word hedge. REVERSAL
carries the same signal/position split and the same retry cap.

A note on fidelity. Build 11's MAIN has **no EV gate at all** — it fires on the
signal and economics enter only at sizing. Routing MAIN through the v10 EV check
is my decision, not a port of the original, and it is why MAIN can be refused
here when it would simply have traded there. I think refusing a -0.113 EV bet is
right, but it is a departure and it should be visible rather than buried.

---

# 12.3.0 — why live fires so much less than paper, and the dial for it

## The measurement, before the fix

You asked why almost every EF signal fires in paper and almost none live. Measured
on 206 real fires from the paper lane, re-running each through the live path:

| slippage allowance | signals that clear the live EV re-check |
|---|---|
| 0 ticks | 206 of 206 (100%) |
| **1 tick (the old default)** | **118 of 206 (57%)** |
| 2 ticks | 77 of 206 (37%) |

Before submitting, live pads the price up by one tick and re-checks EV at that
padded price. Paper never did. One tick is a median **2.1%** of the ask, and most
fires sit between 0.30 and 0.60 where **44%** get refused once that cent is added,
against an EV bar of 0.15 to 0.25.

Smaller contributors, in order: the ten-minute warm-up after every restart (five
restarts today is fifty minutes of silence), live needing master and the lane
enabled, and the cash, quote-age, minimum-size and deadline checks.

**The comparison was never like-for-like.** The paper lane books every signal at
the raw websocket ask with no pad and no re-check, so both its trade count and
its PnL describe a strategy the live path cannot execute. That is the same
recorded-quote optimism we keep finding, this time showing up as frequency.

## EV and slippage are controls now

New section in Trade Controls, and `/api/controls/ev`:

- **EV mode**: `regime` (the model's own 0.15 / 0.25 / 0.25 by volatility),
  `fixed` (one threshold on every candle), `accuracy` (confidence and EV floors
  instead). Default unchanged at `regime`.
- **Slippage allowance**: 0 to 5 ticks above the ask. This is the same dial as
  `--pad-ticks`, but settable while running and persisted across restarts. The
  running executor picks it up without a relaunch.

The panel states the measured trade-off next to the control, so the choice is
made against numbers rather than feel. More padding fills more often and fires
less often; there is no setting that gives both.

Your report that roughly half of orders are rejected for no match at the exact
price is the other side of this same dial. At 0 ticks the order is priced at the
ask and will miss whenever the ask moves between signing and arrival. At 1 tick
it crosses more reliably and loses 43% of the signals. Start at 1, watch the
rejection rate against the fire count, and move it with the evidence.

## MAIN and REVERSAL panels restored to build 36

I had replaced them with my own layout. They are back to the build 36 markup and
wording, verbatim: direction, then time and P(up), then the reason line. The call
shows on the direction line exactly as it did there, and what became of the order
goes on the reason line, which is the line that exists for it.

## Why MAIN and REVERSAL still are not submitting

Same cause as EF, measured above. MAIN calls a side only after its alignment
holds for twelve seconds, by which time the market has usually repriced, so the
EV re-check refuses it. The slippage dial moves this too, but the honest fix is
to count how many MAIN signals clear the bar in paper before funding the lane.
Lowering the EV bar to force it through would remove the only guard stopping the
lane from buying near-resolved contracts.

# 12.3.1 — one real bug, one imaginary one, and a retraction

## RETRACTED IN 12.3.3: the tick-grid "off-by-one" never existed

I claimed `order_plan` built the cap with a Decimal-from-float and gained a free
tick on 35 of 99 prices. **That is wrong.** This module defines

```python
D=lambda x:Decimal(str(x))
```

at line 5, and always has. The expression was already str-based; the cap has
always been exactly `ask + pad*tick` at every price. I "reproduced" the bug in a
scratch script that defined its own `D = decimal.Decimal` and never imported the
module's. Everything below about affected price lists, an effective pad of
`pad_ticks` or `pad_ticks+1`, and the dial being unknowable is withdrawn.

The AWS session caught it by running the engine's own `order_plan` from the
engine's own venv — which is what I should have done before shipping a fix for
it. The 12.3.1 change was a no-op and is reverted in 12.3.3; the
`TickGridRounding` tests stay, now as a guard against making this mistake in
either direction.

## MAIN and REVERSAL seeded themselves ON — this one is real

The dashboard's first-run loop writes defaults for any key that is absent:

```python
for k,v in [('master',not r.a.live),('main_enabled',True),('reversal_enabled',True),('ef_enabled',True), ...]:
    if self.db.get(k) is None: self.db.set(k,v)
```

That loop **persists** what it writes. A `True` there is not a soft default that
something downstream can reconsider — it becomes a stored flag that reads as
deliberately enabled. On a fresh live database it stored master OFF and all
three lanes ON, so the moment master was switched on, every lane armed at once.
That is the live MAIN fill at 09-12 16:51:03, on a lane that has never been
validated with money.

MAIN and REVERSAL now seed **False**. EF keeps its True, because EF is the lane
that is actually run. Two tests pin it: the seeded values, and that switching
master on leaves MAIN and REVERSAL still refused.

I had guessed the cause was the `self.db.get(key,True)` fallback in `allowed()`.
That fallback is real but redundant — the key exists, so changing it would have
fixed nothing. The seeding loop was the one that mattered.

## Retraction: the slippage dial was the wrong advice

This one stands, and it never depended on the cap arithmetic.

**Across all 11 fills on the live box, not one executed above the quoted ask.**
Two filled *better* than our book showed, by 1 and 3 ticks. Not a single fill
ever consumed a tick of pad. If the rejects were the ask outrunning the pad,
some fills would land inside the pad band; none do.

And the measurement I based the advice on could not have shown this. I compared
`signal_quote` against `pre_submit_quote` — but `order_plan` sets
`pre_submit_quote=q['ask']` from the *same* read, and the submit path only
proceeds when `latest['seq']==seq`, i.e. when the book has **not** ticked. The
two quotes are identical in 25 of 25 live rows by construction. I was reading a
structural identity as a market observation.

What does separate fills from rejects is book age: median 85.6 ms on fills
against 129.1 ms on rejects, while fire-to-submit, signing and total attempt
time are indistinguishable. The rejects are not slower — they are working from
an older book.

Corrected fill rate by the pad actually in force (from the reconstructed dial
history — pad 1 until 22:21, pad 0 across most of the late reject streak, pad 2
on one order), n=28 and under the bar, marked not read:

| pad_ticks | fills | rejects | fill rate |
|---|---|---|---|
| 0 | 1 | 4 | 20% |
| 1 | 10 | 12 | 45% |
| 2 | 0 | 1 | 0% |

# 12.3.2 — the reject mechanism, and a retraction from the box

## What the AWS session established

It withdrew its own tick-size alarm before I could build on it: recounted over
all 142 recorded book asks, **141 are exactly on the 0.01 grid**. The "eight
one-decimal asks" were a float-repr artefact of its own binning. Tick is 0.01,
`pad_ticks = n` did mean n cents, and the dial was **ineffective, not
incoherent**. Good catch on itself; I had already written the incoherence into
the 12.3.1 notes.

It also measured the feed properly. `"Waiting for fresh UP and DOWN books"`
covers **20.9% of a 12.4-hour session** — 290 gaps, median 15 s, max 166 s. But
gap proximity does **not** separate fills from rejects: 73% of fills and 76% of
rejects fall within 120 s of a gap. A real availability problem, not the reject
mechanism.

## The mechanism, and the fix

The venue sends **no per-token sequence number**. `price_change` events apply
deltas in place with only a timestamp guard and no continuity check. So a
dropped delta is *undetectable by design*: it leaves a phantom level in our book
that survives until the next full `book` snapshot for that token. A FAK priced
against a phantom top-of-book gets exactly "no orders found to match".

Since a gap cannot be detected, it can only be **aged out**. Each book now
carries a `snapshot` stamp refreshed only by a full `book` event — never by a
delta — and `quote()` reports `snapshot_age_s`. The executor refuses to price
against a book that has run on deltas alone for longer than
`MAX_SNAPSHOT_AGE_S` (90 s), recording status `BOOK_UNSYNCED` and a diagnostics
row rather than sending an order it cannot trust.

This trades some fires for fewer rejects. That is the right direction here: a
rejected order costs a round trip and the candle, while a refusal costs only the
candle.

## Feed counters are persisted

`dropped_stale`, `dropped_future`, `applied` and per-token snapshot ages lived
only in memory, so a post-mortem could not tell how many events the 8-second
clock guard had dropped. Housekeeping now writes them to `diagnostics` once a
cycle, diffable across restarts.

## Closed: the two "impossible" caps were pad 0

They reproduce exactly. Both are `cap == ask` because the dial was at 0 when
they fired. The whole puzzle was downstream of the imaginary off-by-one, and it
dissolved with it.

The AWS session settled the deployed-tree question properly while it was there:
`__pycache__/poly_core.cpython-312.pyc` records source mtime 1789250439 and size
38179, matching `poly_core.py` on disk exactly, timestamp-validated, written at
22:23:59 — PID 23010's start. It disassembled `order_plan` out of that bytecode
and confirmed the running process is that file. **The deployed tree has not
drifted from the branch**, and nothing between `order_plan` and `db.order`
touches `cap`.

With the correct `D`, all 29 live rows reproduce at tick 0.01, and the implied
dial history is coherent: pad 1 for every order to 22:21, pad 0 across most of
the late reject streak, pad 2 on one order at 01:18:47.

# 12.3.3 — reverting a fix for a bug that did not exist

The tick-grid change in 12.3.1 is reverted. `D` in this module has always been
`Decimal(str(x))`, so the cap expression was already correct and my "fix" was a
no-op wrapped around an existing `str()`. The comment at the call site now says
so, and says not to reach for `Decimal` directly, because that is precisely the
mistake that produced the phantom bug.

`TickGridRounding` stays. It was written to prove a fix that fixed nothing, but
it pins real behaviour — `cap == ask + pad*tick` on every tick from 0.01 to
0.99 — and it is the guard that would catch this being broken in either
direction.

The 12.3.1 section above is corrected rather than deleted. It shipped, it was
wrong, and the record should show that.

Nothing else changes. The snapshot-age refusal from 12.3.2 is untouched: it
rests on the phantom-level mechanism, which does not depend on any of this.

# 12.3.4 — the snapshot-age refusal is pulled; the cause is fixed instead

12.3.2 refused to price against a book that had run on deltas for more than 90 s.
**That was wrong and it is removed.** The AWS session gridded it against the live
orders before it shipped:

| limit s | fills refused | rejects refused |
|---|---|---|
| 30 | 91% | 88% |
| 60 | 82% | 59% |
| **90 (shipped)** | **73%** | **53%** |
| 150 | 45% | 41% |
| 180 | 36% | 35% |
| 300 | 36% | 24% |

**There is no threshold where it helps.** At every limit from 30 s to 300 s it
refuses a higher share of fills than of rejects. At the 90 s I picked it would
have cut roughly three quarters of the fills to remove half the rejects.

The reason is structural. `venue()` subscribes once per cycle and clears the
whole book cache, and a `market` subscribe delivers one full `book` per asset
with nothing requesting another. So snapshot age is very nearly
seconds-into-candle with a 300 s cliff: `sec - 30` after the rollover, `300 +
sec` before it. Gating on it is a **time-of-candle threshold in disguise** — the
shape the standing no-gates rule exists to stop — and fills cluster at *both*
ends of the candle, so any age cap cuts them at both extremes while letting the
mid-candle rejects through.

`snapshot_age_s` stays as recorded telemetry on every attempt. A test now asserts
`MAX_SNAPSHOT_AGE_S` is absent and `BOOK_UNSYNCED` does not appear in the module,
so the gate cannot come back by accident.

## The cause, fixed

The engine was guaranteeing its own cold books:

```python
self.books.clear()                      # every cycle, before subscribing
...
while time.time()<ep+330:               # teardown 30 s into the NEXT candle
...
finally: self.books.clear()             # and again on every reconnect
```

A token subscribed as "next market" was snapshotted once, then carried across a
cycle boundary on deltas alone — deltas the code cannot verify it received in
full, because there is no per-token sequence number. That is the phantom level,
with a cause rather than a symptom.

Three changes:

1. **`BookCache.prune(keep)`** replaces `clear()` in the venue loop. Books for
   tokens still subscribed survive a resubscribe; only dropped tokens go. The
   fresh snapshot then *replaces* a live book instead of filling an empty cache.
2. The same on reconnect — the `finally` prunes rather than wipes.
3. The socket bound moves from `ep+330` to `ep+345`, so the teardown and
   resubscribe no longer land at second 30 of the next candle, inside its
   decision window.

None of this refuses anything. It attacks why the book goes stale rather than
filtering orders after it has.

## Still unmeasured, and the honest next step

All of the above rests on full `book` events arriving only at subscribe, which
cannot be verified from the current database — 12.3.0 logged no book-vs-delta
event trail. The housekeeping counters added in 12.3.2 (`dropped_stale`,
`dropped_future`, `applied`, per-token snapshot ages) plus `snapshot_age_s` on
every attempt close that gap. Ship the instrumentation, let it run, grid the real
numbers at 60 and 100 attempts. If Polymarket does push mid-stream snapshots,
the grid above is wrong and this section needs redoing.

# 12.3.5 — the snapshot story was wrong on both sides, and a better lead

## Correcting 12.3.4, whose justification does not survive measurement

12.3.4 was written on the belief that full `book` events arrive only at
subscribe, so a token carried a cycle on deltas alone. **That is false.** The AWS
session measured the public market websocket for 300 s and cross-checked against
12.3.4's own telemetry:

| event_type | count in 300 s |
|---|---|
| price_change | 46,352 |
| **book** | **1,220** |
| last_trade_price | 585 |
| tick_size_change | 8 |

The two active tokens each received **605 full snapshots in 300 s** — a median
gap of 0.2-0.3 s. 12.3.4's own `snapshot_age_s` samples agree: 236 readings, min
0.0 s, median 2.1 s, p90 34.9 s, max 71.3 s, and **none above 90 s**.

So, in both directions:

- **My 90 s refusal would have been a near no-op**, not a fill-killer. 0 of 236
  samples exceed it. It was still pointless, but "harmless" and "cuts 73% of
  fills" are different claims and only the first is supported. The 73%/53% grid
  is void — it modelled ages of 315-329 s where the real values are 0-71 s.
- **The cold-book cause behind the prune change is refuted.** Books do not run on
  deltas for five minutes; the active token is re-snapshotted about twice a
  second, so `books.clear()` on rollover refilled within a second or two and was
  close to harmless.
- **A phantom level surviving long enough to matter is now unlikely** — a dropped
  delta is corrected by the next snapshot within about half a second. The reject
  cause is **open again**.

`prune()` and the `ep+345` rollover stay: prune is strictly more correct, and
moving the teardown out of the decision window is sane on its own. But they fix
something that was not costing anything, and the record should say that rather
than credit a mechanism that does not exist.

## The lead that replaces it: the venue changes the tick mid-candle

`tick_size_change` fired **8 times in 300 s**, every one **0.01 -> 0.001**, on the
active tokens. That makes the earlier 0.439 ask genuine signal rather than noise
— it was over-retracted — and it means `/tick-size` reporting 0.001 on resolved
markets reflects this switch, not only a post-resolution artefact.

`BookCache.apply` pops `terms` on every such event. Housekeeping refetches, but
that loop sleeps 5 s, and both the EF path and `lane_loop` return early when a
token has no terms. So each switch costs the token a window, and if a refetch
lands on the wrong side of the switch the cap is computed on one grid while the
venue matches on another.

**This is a hypothesis, not a finding.** No reject has yet been tied to a
preceding `tick_size_change` on the same token. 12.3.5 makes that decidable
instead of inferred:

- `BookCache` keeps the last `tick_size_change` per token (time, old, new) and a
  running count, surfaced in `health()`;
- every attempt records `believed_tick`, `since_tick_change_s` and
  `last_tick_change` in its `timing` blob.

Nothing is gated on any of it. The next step is to check whether rejects follow a
switch more often than fills do, on the journal rather than on a model.

One confound to keep in view: Polymarket widens the grid near the extremes, so a
switch to 0.001 may simply mark the price running to 0 or 1 late in a candle —
which is also when the book thins. Tick change and thin book would then be
symptoms of the same thing, and separating them needs the timing data now being
recorded.

# 12.3.6 — a skip for missing terms is no longer invisible

The AWS session asked for this and it is the right ask: on 12.3.4 a lane that
skips because the token has no pricing terms leaves **no trace at all**. Both
paths are a bare early return:

```python
if token not in self.books.terms: return            # lane_loop
if token in self.books.terms and stake<=...:        # EF
```

So a skip for missing terms is indistinguishable from no signal, and the third
part of the tick-switch question — *how much time per candle does a token spend
with no terms, and does the lane skip inside those windows* — is not answerable
even in principle. `terms` is dropped on every `tick_size_change` and refetched
by housekeeping's 5 s loop, so the gap is real and repeating.

Both paths now write a `no_terms` diagnostics row carrying the kind, the side and
`since_tick_change_s`. Nothing is gated; the behaviour is unchanged. It simply
becomes measurable.

## Where the tick-switch lead stands

The AWS session has largely ruled it out for the 17 historical rejects, on its
own lead, and the method is worth recording because the first cut was a trap.

28 of 29 order candles touch outside 0.10-0.90 *at some point* — meaningless,
since a binary resolves to 0 or 1 and every candle ends at an extreme. Restricted
to samples **before each order**, which is the only version that can cause
anything:

| outcome | extreme before the order | share |
|---|---|---|
| FILLED | 0 / 11 | 0% |
| REJECTED | 1 / 17 | 6% |

Fisher two-sided **p = 1.0**. Every other order, fill and reject alike, was sent
with both sides mid-range.

That rule-out is conditional on the switch being triggered by price leaving the
band, which is an assumption, so that session is probing the trigger directly
rather than resting on it. Until that lands, neither the lead nor the rule-out is
settled.

Also tightened: "the engine loses its pricing terms mid-candle" is a correct
reading of the code, but it has not been shown happening on any of our rejects,
and the timing above suggests it did not. 12.3.6 is what would show it.

# 12.3.7 — why `quote()` declines, counted

The AWS session's probe caught every `tick_size_change` on a **one-sided book**
(0 asks / 41 bids, and 41 asks / 0 bids). It said plainly that the one-sidedness
may be its own bookkeeping rather than the venue's, since it maintained that copy
from deltas itself and those were the NEXT-candle tokens which get few snapshots.
A corrected probe with three views is running.

But whichever way that lands, it points at something here:

```python
if not b or not b['asks'] or not b['bids']: return None
```

`quote()` refuses a one-sided book entirely. That is almost certainly what the
621 `"Waiting for fresh UP and DOWN books"` rows — **20.9% of a 12.4-hour
session** — actually are. Which matters a great deal depending on *which* token:

- the **NEXT-candle** token being one-sided is benign; nobody is quoting a market
  that has not opened;
- the **ACTIVE** token being one-sided is not, and the engine is refusing to
  price a book it could price, since a buy needs only the ask side.

`BookCache` now counts why each `quote()` call declined — `no_book`, `no_asks`,
`no_bids`, `stale`, `crossed`, `ok` — surfaced in `health()` and persisted with
the rest of the feed counters.

**Nothing is relaxed.** Requiring both sides is doing one real job: `bid>=ask`
catches a crossed book, and dropping that check on an argument is exactly the
move that has gone wrong three times tonight. The change that may follow —
quoting on the ask alone when the ask side is sound — needs the split first. If
`no_bids` on the active token turns out to be a large share of that 20.9%, it is
the most valuable fix available and the numbers will say so.

The AWS session's own summary of where this leaves Task 10 is the right one: the
confound is **unsettled**, not resolved. Its retrospective 0/11 vs 1/17 (Fisher
p = 1.0) stands as data, but its interpretation rests on a trigger condition that
is still unpinned, and the observed switches at second 70 are mild evidence
against the assumption it used. Reported rather than guessed, which is the whole
point.

# Findings 09-13 03:20 — staleness is dead, and the pad is the binding constraint

No code change. Three explanations died tonight and the survivor is simple.

## The number that closes the staleness story

A reject arrived against a full book snapshot **0.13 seconds old**:

| ts | outcome | snapshot_age_s | book_age_ms | submit_ms |
|---|---|---|---|---|
| 03:05:31 | **REJECTED** | **0.13** | 111.4 | 397.6 |
| 03:12:43 | FILLED | 0.44 | 84.2 | 340.5 |

Not deltas-only, not phantom, not stale. The level was published 130 ms before we
priced on it and was gone by the time a 398 ms submit landed. n=1, marked — but
it is the direct test, and it points one way: **a plain race for top-of-book
liquidity, with us roughly 400 ms behind.** That retires the cold-book story
entirely, and means the prune and rollover work in 12.3.4 is not where the fix
lives either.

## The tick switch is ruled out properly

The AWS session's corrected probe read the authoritative REST book at each
switch on the **active** pair:

| token | sec | old->new | REST ask | REST bid | levels a/b |
|---|---|---|---|---|---|
| 1042494373 | 76 | 0.01->0.001 | 0.001 | none | 34 / 0 |
| 3884524341 | 77 | 0.01->0.001 | none | 0.999 | 0 / 34 |

The switch fires exactly when the pair reaches 0.001/0.999 — one side worthless,
the other certain, both books one-sided. **Tick change and price-at-the-extreme
are the same event**, which confirms the assumption its retrospective test rested
on. Every one of our 28 orders was sent with a two-sided book at 0.30-0.56, and
only 1 of 28 had seen the band left beforehand (fills 0/11, rejects 1/17, Fisher
p = 1.0). Its own best lead, killed by its own probe.

Kept from it: markets decide by second 76 of a 300-second candle, and from that
moment `quote()` returns None on a one-sided book. That is where the 20.9%
"waiting for fresh books" comes from, and it supports 12.3.7's counters.

## The pad is what stops it trading — full grid, every arm

75 fired signals with reconstructible inputs, recomputed with the engine's own
`D` and fee maths. n=75 is under the graded bar, so this is a pass/refuse count
on a deterministic re-check, **not a PnL claim**.

| pad_ticks | pass | refuse | pass % | shortfall (threshold − EV@cap) med / p25 / p75 |
|---|---|---|---|---|
| **0** | **75** | **0** | **100%** | −0.0172 / −0.0432 / −0.0078 |
| 1 | 32 | 43 | 43% | +0.0055 / −0.0196 / +0.0132 |
| **2 (current)** | **18** | **57** | **24%** | +0.0259 / +0.0030 / +0.0334 |
| 3 | 9 | 66 | 12% | +0.0456 / +0.0247 / +0.0530 |

The refusals are **not near misses**: of 57 refused at the current pad, 2 are
within 0.01 of the bar, 12 within 0.02, and 30 are beyond 0.03 — against a 0.15
threshold, a median shortfall about a fifth of the bar.

But the model is not the problem and neither is the threshold: **all 75 clear the
bar at the raw ask.** Every refusal is created by the padding. Set beside the
measurement that has not moved all night — **no fill has ever consumed a tick of
pad, now 12 of 12**, with the newest filling at 0.47 against a 0.49 cap — the pad
has no demonstrated benefit and is currently the binding constraint on whether
the engine trades at all.

Consistent with the 0.13 s reject: this is a **size** race, not a price race.
Someone takes the liquidity; the level is gone rather than more expensive, and
padding the price cannot buy a level that no longer exists.

Neither session picks a value. That is the user's call, and the no-gates rule
cuts against choosing a cell from a grid either way.

# 12.3.8 — every control write is now audited

`pad_ticks` moved from 2 to 1 on the live box between 03:36 and 03:41 and nobody
admits to it. The AWS session's write was refused by a guard and never retried;
either the user set it from the dashboard, or it is the same silent revert that
has hit the Tokyo lane flags twice (09-11 14:40, 09-12 20:38) with no restart and
no known cause.

**I could not tell which, and that is the problem worth fixing.** `Journal.set`
was a bare `INSERT OR REPLACE`, so a control changing value left nothing behind.
Every such event on this branch has been unreconstructable after the fact.

Control writes now record the old value, the new value and the calling frame:

```python
AUDITED={'master','main_enabled','reversal_enabled','ef_enabled','ev_settings',
         'stake_settings','next_stake','halt','sx_enabled','tp','sl','rules'}
```

A write of the same value records nothing, so the trace is changes only. Next
time a flag moves on its own, the diagnostics row names the code path that did
it. This is the instrument the Tokyo fault has needed for two days.

Ruled out while looking, so nobody repeats the search:

- the `/api/controls/ev` handler is **not** the culprit. It reads the existing
  settings into a fresh dict and only assigns `pad_ticks` when `slippage_ticks`
  is present in the request, so a mode-only change cannot reset it.
- the dashboard form is **not** the culprit either. `renderEv()` fills the
  control from `ev.slippage_ticks` rather than a default, and only while the user
  has not touched it.
- `pad_ticks()` falls back to the CLI default of 1 when the key is *absent* — so
  a partial or defaulted write does land on exactly 1, which is what makes the
  observation suspicious. But the key was present with value 1, so this was a
  stored value, not a read-time fallback.

Also fixed, minor: the slippage control offered 0-3 while the endpoint accepts
0-5, so two valid settings were unreachable from the dashboard.

## Do not assume pad 0

The user's 03:25 decision was pad 0. It never applied — the write was refused by
a guard. The engine has been running at **pad 1** since roughly 03:41, and at
pad 2 before that. Any comparison of fills, rejects or PnL across tonight spans
three different pad values, and the changeover times are known only to the
minute. Treat the whole night's execution numbers as three small unpooled
samples, not one series.

# 12.4.0 — EV is a gate on the decision, and a refused candle re-arms

Two defects the user named directly, both real, both in the design rather than
in a line of code.

## 1. EV gates the signal, instead of judging it afterwards

> *"ev should be used as a gate inside the signal logics not after the signal is
> fired, because it's used after the signal it misleading because the signal
> appears triggered and inside the chart but it is not traded"*

Correct, and it is the most misleading thing this build did. The model decided
against the **raw ask**; the padded-price EV check ran later inside `order_plan`
at execution time. So a signal was recorded and drawn on the chart as fired, and
only then refused. Everything downstream inherited that lie — the fire count, the
chart, and every comparison against paper.

`decide_now()` now runs the same arithmetic at the price we would really pay,
before returning. A signal that cannot clear EV at the padded cap comes back
`fire: False` with the reason, so it never claims to have fired. The gate can
only ever narrow a fire, never widen one, and it records `ev_gate`,
`ev_gate_pad`, `ev_gate_ask` and `ev_gate_cap` so the refusal is visible rather
than silent.

This also removes the double standard against the paper lane: both now decide on
the same basis.

## 2. A refused attempt no longer consumes the candle

> *"as the signal appears triggered it does not fire again inside the same candle
> thus we will miss the second oppertunities when the odds will align again"*

Also correct. The reservation is `PRIMARY KEY(epoch,kind)` with `INSERT OR
IGNORE`, so the first attempt owned the whole five minutes. If it was refused —
EV changed, signal changed, deadline, missing terms — the candle was finished,
even though nothing had been sent and the odds might realign twice more inside
it.

`Journal.release()` now marks the attempt and frees the candle whenever **nothing
reached the venue**: `SKIPPED`, `DEADLINE`, `SIGNAL_CHANGED`, `EV_CHANGED`,
`PREPARE_FAILED`. Anything that did reach the venue — `FILLED`, `REJECTED`,
`UNKNOWN`, `PENDING` — still consumes the candle, because re-firing after an
order may have landed is how you end up holding two positions on one candle.

Bounded at `MAX_ATTEMPTS_PER_CANDLE = 4`. The count lives in its own
`candle_attempts` table, not on the signals row — the row is deleted to re-arm,
so a counter stored there would reset every time and the candle would spin. Each
re-arm writes a `candle_rearmed` diagnostics row.

Six tests pin the behaviour, including that a sent order never re-fires and that
the cap actually stops it.

## Not fixed, and not pretended otherwise

The user's list was longer than this. Still open, in their words:

- **MAIN and REV "still not proper"** — 12.2.4 separated signal from position and
  added a retry cap, but neither lane has been validated with money and the user
  is not satisfied. Needs its own pass.
- **"claim, fundable and available amount is still misleading"** — the venue-truth
  work in 12.2 changed where the numbers come from, not how they are presented.
- **"many things are not adjustable from trade control panel"** — no list yet of
  what is missing; that is the first thing to get.
- **"build 36's slippage rules are not applied"** — build 36's rules have not been
  read into this build. They should be, rather than reinvented.

Recorded here so they are not lost between sessions.
