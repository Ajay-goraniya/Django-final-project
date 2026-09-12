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
