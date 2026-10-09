# Task 114 - EF + REVERSAL, MAIN calls on but MAIN orders OFF, PAPER lane D (port 8796, build 12.14.0)

Lane: `/home/ubuntu/pm_ef_rev_114`, `--db paper_ef_rev_114.sqlite3 --model model_v10.json
--capital 50 --port 8796 --host 127.0.0.1`, pid 128432, started 2026-09-16 11:36 UTC.
Armed in one command: master true, ef_enabled true, reversal_enabled true, **main_enabled false**,
next_stake 3.0, stake_settings mode fixed / fixed 3.0 / min 1.0 / max 50.0.
Build read back from the journal: 12.14.0. Checksums 31/31 OK against commit 25405a4.
Local test count on the staged tree: test_polymarket 71 + test_lanes 23 + test_v122 215 = 309.

## Ledger

| UTC | kind | fires | orders by status | results n | W | pnl $ | pnl per $1 |
|---|---|---|---|---|---|---|---|
| 11:43 | EF | 0 | - | 0 | - | - | - |
| 11:43 | REVERSAL | 0 | - | 0 | - | - | - |
| 12:54 | EF | 2 | 2 FILLED | 1 | 0 | -3.00 | -1.00 |
| 12:54 | MAIN (call only) | 0 | n/a - orders off | - | - | - | - |
| 12:54 | REVERSAL | 0 | - | 0 | - | - | - |

78 minutes, 2 EF fires, 1 graded. **Insufficient.** Fills: epoch 1789559100 UP at 0.428 for 6.73
shares, settled DOWN, -2.99; epoch 1789559400 DOWN at 0.340 for 8.41 shares, ungraded.

## Why REVERSAL is still at zero, and it is not the trigger

The 12.14.0 change is in place and reachable - `main = self.current_main or self.main_signal`
(poly_lanes.py:508) and the only diff against 12.13.1 is that trigger. The lane is alive and
evaluating: `/api/state` on 127.0.0.1:8796 reports `main_block "flow and odds do not agree"`,
`pressure_text BALANCED`, `pending {MAIN: false, REVERSAL: false}`, `reversal {status: idle}`,
`main_attempts 0`. Controls read back `MAIN manual_enabled false / effective false`,
`REVERSAL manual true / effective true`, master true.

So REVERSAL has nothing to watch because **no MAIN call has been made at all** - zero MAIN lane
decisions in the journal's diagnostics in 78 minutes, against 23 in 28 minutes on the Task 113 lane
with identical `_try_main` code. That is market state, not build: the alignment gate needs odds
past 0.60/0.40 with volume ratio >= 0.70 held 12 s over 60 reads, and the tape has been balanced.

**Consequence for the test's cadence:** REVERSAL's arrival rate is bounded above by the MAIN *call*
rate, and that rate is sporadic enough to swing between 0 and 23 per half hour. A REVERSAL sample
worth grading is many hours away, not one 4-hour block. Reported so the schedule is not mistaken
for a fault.

REVERSALs on a MAIN call that was never placed: 0 of 0. With main_enabled false every MAIN view is
a call only, so once REVERSAL fires at all, 100% of its fires must carry detail "call only"; any
fire that does not would mean a MAIN order escaped the disable, which is the thing to watch for.

EF+REV combined per-$1 vs EF alone on the same candles: not computable at n=0.

Grading is on `venues.outcome`, not `candles.actual`.

## Not touched

8787, 8793, 8794, 8795, both loggers, Zurich. Nothing live. Paper only.

## 2026-09-16 11:57 UTC - RETRACTION: "0 MAIN calls is market state" was WRONG. It is ours.

V's test, run as asked. `SELECT count(*) FROM diagnostics WHERE json_extract(detail,'$.lane')='MAIN'`
on every lane over the SAME wall-clock window (11:36:09 -> 11:55:48, the whole life of 8796). The
permission gate does not hide these rows - btc_model_v12_polymarket.py:387 journals the decision and
:389 is the `ui.allowed(kind)` return, and `main_enabled` is false on all five lanes, so this is a
like-for-like count.

| lane | build | MAIN rows in window | MAIN/hour over its own life | candles with a MAIN call, last 3 h |
|---|---|---|---|---|
| 8787 | 12.9.0 | 1 | 7.3 | 21 of 37 |
| 8793 | 12.8.11 | 1 | 6.5 | 18 of 37 |
| 8794 | 12.13.0 | 1 | 8.9 | 11 of 17 |
| 8795 | 12.13.0 | 0 | 8.4 | 10 of 17 |
| **8796** | **12.14.0** | **0** | **0.0** | **0 of 6** |

Four lanes call MAIN on ~60% of candles; 8796 has called on 0 of 6. Under the siblings' own rate
that is p = 0.38^6 = 0.003. **The difference is ours, and it is not the 12.14.0 trigger.**

## Root cause, measured at one instant on two lanes reading the same candle

`/api/state` at 11:57:27, 8795 and 8796, identical candle (time 1789559700000, open 76234.2,
close 76248.66, volume 20.25985) and identical phase (147.4 vs 147.5 s):

| | 8795 | 8796 |
|---|---|---|
| volume_ratio | 1.4975 | 0.4672 |
| fair_p_up | 0.752 | 0.99 |
| aligned | None (odds) | None (**volume**) |

`volume_ratio` (poly_lanes.py:313) is `(candle_volume / frac) / median(last 24 CLOSED volumes)`.
Same volume and same phase give the same numerator, 20.25985 / 0.4917 = 41.20, so the implied
medians are 41.20/1.4975 = **27.51** on 8795 and 41.20/0.4672 = **88.19** on 8796. 88.19 is exactly
the volume of candle 1789559400 - one of the four candles 8796 has watched close since 11:36. The
`candles` TABLE is byte-identical on both lanes (24-candle median volume 25.670, median move 27.24,
checked directly), so the divergence is not the data on disk.

`self.closed` is a `deque(maxlen=64)` fed **only** from live klines: btc_model_v12_polymarket.py:177
calls `on_closed_candle` when `k['x']` is set, and the very next line writes that same candle to the
`candles` table. **Nothing ever seeds the deque from that table at startup.** So a freshly started
lane computes `volume_ratio` and `fair_odds` over however few candles it has personally watched, and
needs 24 x 5 min = **2 hours** before either is meaningful. 8796 has 4. Its median is 3.4x too high,
`volume_ratio` sits under the 0.70 gate, and `_aligned_direction` returns None on every read.

**This also retracts the other half of my earlier comparison.** Task 113's lane showed 23 MAIN calls
in 28 minutes, 50/hour against a steady-state 7-9/hour. That was the same artifact pointing the
other way - a short window that happened to open on low-volume candles gives a small median and an
inflated ratio. Neither 23-in-28-min nor 0-in-21-min was ever the tape.

**Falsifiable prediction:** 8796 fills its 24-candle window at about 13:36 UTC. If the diagnosis is
right, MAIN calls appear there and converge on the siblings' 7-9/hour without anything being
changed. If they do not, the cause is something else and this entry is wrong.

**Not fixed, not touched.** The obvious repair is to seed `self.closed` from the `candles` table when
the lane engine starts, which is a change to a shared engine file and therefore V's call, not mine.
Every engine is exactly as it was.

## 2026-09-16 13:45 UTC - REVERSAL HAS FIRED. Trigger confirmed, every fire "call only", 0 orders.

The lane warmed (see the cold-start entry above) and REVERSAL began firing at 12:57 UTC, 81 minutes
after start. 12 REVERSAL lane decisions across 2 candles, 2 reaching `signals`, both SKIPPED.

**Acceptance criterion met in full: 12 of 12 decisions carry the detail string
"(call only - MAIN order not placed)".** There is no fire on a placed MAIN, which is correct because
`main_enabled` is false and no MAIN order exists on this lane. The 12.14.0 trigger does what the
build said it would - a MAIN *call* arms the hedge.

| epoch | UTC | side | flipped against | sec | p | ask | outcome |
|---|---|---|---|---|---|---|---|
| 1789563300 | 12:55 | DOWN | MAIN UP | 178-183 | 0.344-0.346 | 0.79-0.84 | SKIPPED |
| 1789564200 | 13:10 | UP | MAIN DOWN | 196-213 | 0.603-0.612 | 0.54-0.61 | SKIPPED |

Both refused by `order_plan` with **"price fails model EV"**, logged as `order_plan_refused`
(poly_core.py:942-953) with pad 1, band false, stake 3.0, EV threshold 0.25:

```
12:57:58 REVERSAL DOWN ask=0.79 p=0.3464  12:58:02 ask=0.84 p=0.3448  12:58:02 ask=0.84 p=0.3438
13:13:17 REVERSAL UP   ask=0.54 p=0.6028  13:13:17 ask=0.54 p=0.6034  13:13:32 ask=0.61 p=0.6117
```

On the DOWN candle the venue wanted 0.79-0.84 for a side the model priced at 0.34, which is not a
close call. On the UP candle EV was p/ask - 1 = 0.603/0.54 - 1 = **+0.116**, genuinely positive but
under the 0.25 floor, and a tick of pad takes it to +0.096.

**What this says about the hedge, not about the code:** a REVERSAL by construction fires *after* the
tape has moved against the MAIN direction, so the side it wants to buy has already repriced upward.
Three of the six refusals are at an ask above 0.79. The structural question is whether a lane that
only ever buys post-move can clear a 0.25 EV floor at all - and the first evidence says rarely.
2 candles is far under the 60 bar, so that is a shape to watch, not a finding.

Running totals on lane D: EF 11 fires / 11 FILLED, REVERSAL 2 signals / 0 orders, MAIN 7 calls /
0 orders (correct, orders off). Nothing changed, nothing restarted.

## 2026-09-16 15:0x UTC - 12.15.3 deployed; every REVERSAL number above is a DOWN-CENSORED SAMPLE

V's nine-way audit found that REVERSAL was handed the probability of the side it was **not** buying.
`_aligned_direction` only names DOWN when `fair_p_up <= 0.40`, and the DOWN reversal then reached the
EV gate carrying `fair_p_up` itself instead of `1 - fair_p_up`. **This lane's own journal is a clean
confirmation, and it changes how the entries above must be read.**

The 12:55 candle fired DOWN with **p = 0.3438** recorded against ask 0.79-0.84. A DOWN buy at a
recorded p of 0.344 means the engine was quoting P(UP); the true P(DOWN) was 0.656. So the refusal
logged as "price fails model EV" was arithmetic on the wrong side of the book. By construction a DOWN
REVERSAL could never carry a p above 0.40 and could never clear a 0.25 EV floor: **DOWN REVERSAL
could not fire at all, on any candle, in 12.13.1 or 12.14.0.**

| | decisions | signals | orders | recorded p | ask | why refused |
|---|---|---|---|---|---|---|
| REVERSAL DOWN | 6 | 1 | 0 | 0.344-0.346 | 0.79-0.84 | **the defect** - p was P(UP) |
| REVERSAL UP | 6 | 1 | 0 | 0.603-0.612 | 0.54-0.61 | genuine - EV +0.116 under the 0.25 floor |

The UP leg was never affected: `_aligned_direction` names UP when `fair_p_up >= 0.60`, so an UP buy
carrying `fair_p_up` is already the right number. **Only the DOWN half was censored**, and it was
censored completely.

Corrected arithmetic on the one DOWN candle we have: at the true p of 0.656 against ask 0.79 the EV
is -0.17, and against 0.84 it is -0.22. So the fix makes a DOWN REVERSAL **possible**; it would not
have made *that* candle fire. One candle proves nothing either way - the point is that the sample was
structurally incapable of containing a DOWN fire, so "REVERSAL has never placed an order" carries no
information about the DOWN side at all.

**Every REVERSAL figure in the entries above is hereby marked DOWN-censored and is not to be read as
evidence about the lane.** The Task 113 zero and the Task 114 zero both sit on this.

## Ledger at 15:0x UTC, lane D, before the restart

| kind | fires | orders | graded | W | staked $ | pnl $ | pnl/$1 |
|---|---|---|---|---|---|---|---|
| EF | 11 | 11 FILLED | 11 | 5 | 32.95 | +0.46 | +0.0140 |
| MAIN (call only) | 12 calls | 0 (orders off) | - | - | - | - | - |
| REVERSAL | 12 decisions, 2 signals | 0 | 0 | - | - | - | - |

2.9 h of journal, 11 graded fires. **Insufficient** on every line. REVERSALs on a MAIN call never
placed: 2 of 2, both carrying "call only - MAIN order not placed", which remains 100% as required.

## Deploy record - 12.15.3, commit 1d13305

Staged tree verified before anything was stopped: **SHA256SUMS 31/31 OK**, tests
71 + 28 + 251 = **350 OK**.

| lane | pid | build read back | seed line | master | ef | main | reversal | stake | halt |
|---|---|---|---|---|---|---|---|---|---|
| 8794 | 131381 | 12.15.3 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none |
| 8795 | 131367 | 12.15.3 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none |
| 8796 | 131354 | 12.15.3 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | **true** | 3.0 | none |

Zero `LANE_SEED_COLD` rows on any lane. Arming is byte-identical to what it was before the restart.
All three read the same lane features immediately after start: volume_ratio 1.0740 / 1.0736 / 1.0739,
fair_p_up 0.9900 on all three, aligned UP on all three.

**Not touched: 8787 (12.9.0, pid 126394) and 8793 (12.8.11, pid 119658)** - the owner's pin and the
reference arm for his own build question, same pids as before this deploy.

`MEDIAN_WINDOW` is now 23, so both lane gates loosen slightly against build11 parity. MAIN and
REVERSAL call rates are expected to rise; that rate is being watched against the cold-start effect
and will be reported if it moves by more.

## 2026-09-16 15:5x UTC - 12.15.4 deployed (commit 0cae0bd)

Staged tree verified before anything was stopped: **SHA256SUMS 31/31 OK**, tests
71 + 28 + 266 = **365 OK**.

| lane | pid | build read back | seed line | master | ef | main | reversal | stake | halt |
|---|---|---|---|---|---|---|---|---|---|
| 8794 | 132144 | 12.15.4 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none |
| 8795 | 132129 | 12.15.4 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none |
| 8796 | 132116 | 12.15.4 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | **true** | 3.0 | none |

Zero `LANE_SEED_COLD` rows. Arming byte-identical to the pre-restart read. All three read the same
lane features on start: volume_ratio 0.4183 / 0.4259 / 0.4177, fair_p_up 0.3579 on all three.
**8787 (pid 126394) and 8793 (pid 119658) untouched, same pids as before.**

### MAIN p distribution across the restart - BASELINE CAPTURED, AFTER SAMPLE PENDING

Four of the thirteen weighted MAIN features (`ofi_1s` 0.85, `ofi_5s` 0.60,
`aggressive_cluster_bias` 0.25, `volume_profile_delta` 0.35) were hardcoded to 0.0 in the port -
2.05 of 8.75 anchor weight silent - and 12.15.4 computes all four. The before/after on MAIN's `p` is
therefore the measurement that says what that was worth. Baseline, taken from the lane diagnostics
immediately before the stop:

| lane | build | MAIN rows | n(p) | min | p25 | median | p75 | max | median confidence |
|---|---|---|---|---|---|---|---|---|---|
| 8794 | 12.15.3 | 29 | 29 | 0.5768 | 0.6702 | 0.6956 | 0.7292 | 0.8029 | 0.4935 |
| 8795 | 12.15.3 | 28 | 28 | 0.5478 | 0.6483 | 0.6859 | 0.7154 | 0.8027 | 0.4800 |
| 8796 | 12.15.3 | 22 | 22 | 0.6323 | 0.6514 | 0.6622 | 0.7284 | 0.8272 | 0.4747 |

Post-restart sample at the time of writing: **0 MAIN rows on all three lanes**, minutes after start.
The comparison is not computable yet and will be reported when each lane has a usable count. Note in
advance that 22-29 rows per lane is itself under the 60 bar, so even the baseline is a weak
distribution and the comparison will be described, not read as a result.

### Task 114 ledger, carried forward

The DOWN-censoring notice stands: `_aligned_direction` names DOWN only when `fair_p_up <= 0.40`, and
the DOWN leg was handed `fair_p_up` rather than `1 - fair_p_up`, so **no DOWN REVERSAL could clear
the EV gate in 12.13.1 or 12.14.0**. Every REVERSAL figure recorded before 12.15.3 is a DOWN-censored
sample and is not evidence about the lane.

Lane D at the restart: EF 12 orders, 13 graded, W 6, pnl -0.06; REVERSAL 2 signals, 0 orders, both
"call only"; MAIN 22 calls, 0 orders (correct, orders off). **Insufficient on every line.** No
REVERSAL order has been placed on any build since the DOWN fix shipped.

`still_valid` now recomputes lane signals inside the retry loop, so some lane orders that used to be
submitted stale will release as SIGNAL_CHANGED. That count is being watched and will appear in the
next ledger.

## 2026-09-16 18:0x UTC - 12.15.5 deployed (commit 4340859); REVERSAL gets its own EV floor

Staged tree verified before anything was stopped: **SHA256SUMS 31/31 OK**, tests
71 + 28 + 270 = **369 OK**. `LANE_EV_FLOOR = 0.0` at poly_lanes.py:84, and
btc_model_v12_polymarket.py:548 now does `d.setdefault('threshold', poly_lanes.LANE_EV_FLOOR)`
instead of handing the lane EF's regime dial.

| lane | pid | build | seed line | master | ef | main | reversal | stake | halt | rev_max_entry |
|---|---|---|---|---|---|---|---|---|---|---|
| 8794 | 134930 | 12.15.5 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none | unset (off) |
| 8795 | 134916 | 12.15.5 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | false | 3.0 | none | unset (off) |
| 8796 | 134901 | 12.15.5 | `[LANE SEED] 64 closed candles from the journal; warm` | true | true | false | **true** | 3.0 | none | unset (off) |

Zero `LANE_SEED_COLD` rows. Arming byte-identical. **8787 (126394) and 8793 (119658) untouched.**
`rev_max_entry` deliberately not set - the owner may supply Tokyo's value later.

### REVERSAL signal ledger AS IT STOOD BEFORE THE STOP - the before half of the record

Every one of these was judged against EF's v10 regime threshold of 0.25, which build11 never applies
to this lane.

| UTC | epoch | sec | side | p | ask | EV = p/ask - 1 | status | candle outcome |
|---|---|---|---|---|---|---|---|---|
| 12:55 | 1789563300 | 183 | DOWN | 0.3438 | 0.79 | -0.565 | SKIPPED | settled DOWN, candle -2.99 |
| 13:10 | 1789564200 | 212 | UP | 0.6117 | 0.54 | **+0.133** | SKIPPED | settled UP, candle +2.20 |
| 16:05 | 1789574700 | 74 | DOWN | 0.6510 | filled 0.32 | +1.034 | **FILLED**, 8.94 sh | settled DOWN, candle +12.33 |
| 17:40 | 1789580400 | 159 | DOWN | 0.6138 | 0.61 | **+0.006** | SKIPPED | settled DOWN, candle +4.56 |

**Two of the four died to a rule REVERSAL was never designed to face, and both would have won.**
Under `LANE_EV_FLOOR = 0.0`: the 13:10 UP at +0.133 places, the 17:40 DOWN at +0.006 places by a
hair, and the 12:55 row still refuses - correctly, because even at its true post-fix p of 0.656
against ask 0.79 the EV is -0.17. The censored row stays refused; only the two genuine ones change.
That is 1 order from 4 signals before, and 3 from the same 4 after, on this tiny sample.

### Stacking - the number the owner's decision hangs on

Candles where EF and REVERSAL both fired: **1, and they took the SAME side.** ep 1789574700, EF DOWN
at 0.3040 and REVERSAL DOWN at 0.32, $5.99 staked across the two legs returning +$12.33. With
`main_enabled` false the REVERSAL hedges a MAIN that does not exist, so it can only concentrate the
candle, never offset it. Opposite-side count so far: 0. n=1 is not a rate; it is the first
observation, and the same-vs-opposite split is what the next ledger reports.

**Expect materially more REVERSAL orders from here.** That is the port running its own rules for the
first time, not a regression.
