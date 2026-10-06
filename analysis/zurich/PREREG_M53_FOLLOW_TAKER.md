# PREREG M53 - "FOLLOW THE TAKER", PAPER-ONLY FORWARD TEST

Owner approved 2026-10-06 02:2x via V. **PAPER ONLY. No money, no live orders, no key, London
untouched.** This document is frozen at its commit. Forward data counts only from candles whose
epoch is at or after this commit's timestamp. Nothing before that date may be added to the primary
result, and no parameter in section 2 or 3 may change afterwards.

## 1. Where this came from (so the prereg is not read in isolation)
`PFAV_taker` in `pfav.py` was built as a pairing reference, not a strategy: it takes the first
taker BUY print in a window and grades it. It came out +0.1601 per $1, n 994, t +8.95, 7/7 green -
the only one of 36 running paper arms clearing n>=60 and |t|>=2 positive (`PAPER_RANK_1006.txt`,
05cca15 / 721dd4e). Retrospective checks: the price is reachable (own-side ask at the print second
0.6897 vs the booked 0.6898); timing is not the explanation (same window/band as PFAV, median entry
sec 84.5 vs 83.0); the clean full-universe control reproduces M44/M52 (-0.42pp, t -0.35) and the
print condition splits that fairly-priced universe +5.38pp (print) / -12.90pp (no print, t -5.48).
Mechanism: the mirror of this project's recurring adverse-selection result - if the taker lifting
the favourite is informed, following it gains what resting against it loses.
**Everything above is retrospective and is NOT evidence for this test.** This prereg exists because
three things were never established: it has never run forward, depth was assumed, and real-time
detection latency was never measured. Those are what M53 measures.

## 2. THE RULE, FROZEN
Per BTC 5-minute candle on Polymarket (`btc5`), at most ONE decision, no re-entry, no exit:
1. Watch Polymarket taker prints (`data-api.polymarket.com/trades?market=<cond>&takerOnly=true`).
2. TRIGGER = the FIRST print satisfying ALL of: `side == 'BUY'`; candle second of the print's own
   timestamp in **60..180 inclusive**; print price in **0.60..0.80 inclusive**.
3. SIDE = the token that print was on (`asset`), i.e. follow the taker. No favourite check.
4. ENTRY = buy that same side at **our own-side ASK at print_ts + 3 s** (primary row), $5 stake,
   **exact Polymarket taker fee 0.07*p*(1-p)**, shares = 5 / (ask*(1+0.07*(1-ask))).
5. HOLD to settlement. Settlement = the venue's own resolution (`venues.outcome`, else gamma
   `mkt.outcome`). No stop, no take-profit, no re-buy.
6. Candles with no qualifying print are NOT decisions and are excluded from n.
7. Hard exclusions, frozen: ask missing, ask >= 0.99, no book row within +-2 s of the target
   second, or no settlement label. These are logged with a reason and excluded from n.

### Fill model - misses are NO-FILL, counted, never dropped
At print_ts+3 s, from the 1 Hz book (`pm_multi/multi_market.sqlite3` `books`, which carries
level-1 `up_ask_sz`/`dn_ask_sz` and a snapshot age):
- MISS ON PRICE if the own-side ask is outside 0.60..0.80 at that second, or >= 0.99.
- MISS ON SIZE if level-1 own-side ask size is less than the shares $5 needs.
- Either miss = **NO-FILL**: the decision still counts in the decision tally with its reason, and
  contributes **$0** to the decision-level result. It is never silently removed.

### Secondary rows (logged, never promoted)
Identical rule priced at **+0 s, +2 s, +10 s**. These exist to show latency sensitivity only.
The primary row is +3 s and the verdict is read off +3 s alone. No best-cell picking.

## 3. PASS RULE, FROZEN BEFORE ANY DATA
At the verdict checkpoint, the primary (+3 s) row must satisfy ALL FIVE:
1. **n >= 60** filled decisions at that checkpoint;
2. **t >= 2.0** on per-fill $ (fee-exact, $5 stake);
3. **both halves > 0** (split by candle epoch, first/second half of fills);
4. **>= 60% green UTC days**;
5. **beats the no-print control on the same candles, PAIRED** (control = on the same candle, buy
   the first side whose own-side ask is in 0.60..0.80 during sec 60..180, at that second's ask,
   ignoring prints entirely; same stake and fee; paired per-candle difference must be > 0).
Fail any one => FAIL. A pass is a pass of this rule only and still carries no authority to trade.

### Reported alongside (not pass criteria, so they cannot be traded off against the bars)
- Decision-level result with NO-FILLs as $0, and the fill rate with the price/size miss split.
- **Measured detection latency**: our-feed detect time minus the print's own timestamp, p50/p90/max.
- Ask drift print->+3 s; level-1 size available vs needed; book snapshot age.
- The full-universe control (ALL candles with a book and a label, no print condition) - the row
  that read -0.42pp retrospectively and must keep reading ~0 if the harness is sound.

## 4. METRICS
`per1(win, px)` fee-exact $ per $1; per $1 = total $ / total deployed. t on per-fill $.
Green day = positive total for that UTC day. Halves by candle epoch.

## 5. CHECKPOINTS AND VERDICT
- One line per day in the FAV daily report, tagged M53.
- **Verdict at 7 full UTC days (through 2026-10-13) OR n >= 300 filled decisions, whichever is
  LATER.** No early verdict, no stopping on a good run.
- Rows are tagged `M53` in `/home/ubuntu/m53/m53.sqlite3`.

## 6. WHAT THIS CANNOT DO
No stake, no arming, no live order, no change to any running arm, no London contact. A PASS is
evidence to put to the owner and V, nothing more. Kelly/dynamic staking is out of scope and
remains behind two separate owner confirmations.

---
## EXECUTION NOTE 2026-10-06 02:4x - MEASURED BLOCKER. The frozen rule above is UNCHANGED.
The arm was built, started (cron + `flock`, pid 946788, paper only, places nothing) and immediately
measured the one thing this prereg existed to measure. Result:

**The `data-api.polymarket.com/trades?takerOnly=true` feed is lagged by roughly 1-3 minutes, so a
print that happens in sec 60-180 cannot be SEEN inside sec 60-180.**
Evidence, candle 1791254100 (02:35 UTC):
- pulled after the fact, that candle contained **101** qualifying prints (BUY, sec 60-180,
  price 0.60-0.80);
- the live arm polled it **60 times** during the window and saw **none** of them;
- at 02:40:52 the newest print visible anywhere in that feed was **145 s old** (sec 207 of a candle
  that had already ended); the same measurement on two earlier candles gave 58 s and ~200 s.

### What this does and does not mean
- It does NOT falsify the retrospective +0.1376 per $1. That number stands as a measurement of
  *what informed takers achieved*.
- It DOES mean the rule is **not executable on this detection path**: entry at print_ts+3 s requires
  knowing about the print within 3 s, and this feed delivers it in 60-200 s. Acting on what we can
  actually see would mean buying 1-3 minutes after the print, which is not the rule and is not
  covered by the +0/+2/+10 s secondary rows either.
- My first latency probe was INVALID and I am recording that rather than quietly replacing it: I
  started polling at sec 211 with an empty seen-set, so every print already in the feed counted as
  "newly observed" and I measured my own start time (205-210 s), not the feed. The numbers above come
  from the corrected method - compare what a completed candle actually contained against what the
  live arm saw during the window.

### Consequence for the test
The arm stays up and keeps logging, but it will produce **n ~ 0** on this path: it records
"no qualifying print" for candles that in fact had 101. A verdict on 10-13 would therefore be a
verdict on nothing. The pass rule is untouched and no parameter has been changed.

### The one thing that would unblock it, for V and the owner to decide
Find a taker-print source with sub-second delivery and re-point the arm's DETECTION at it, leaving
the frozen rule identical. Candidates, in order of likelihood: the CLOB websocket market/trade
channel; the `ws-live-data.polymarket.com` activity topic (that host is already proven reachable
from this box by `rtds.py`, which had to force AF_INET because there is no IPv6 route); the
authenticated CLOB REST `/trades`. Swapping the detection path is not a change to the rule, but it
changes what the arm can see, so I am not doing it on my own initiative - it needs sign-off, and
until then M53 has no executable path and I am not reporting progress against its checkpoints.

### MEASURED, 02:5x - the lag is 132-342 s, NOT the "1-3 min" I first estimated
The estimate above came from one active candle. This is the controlled version, and it supersedes it.
Method: prime the seen-set at sec 21 of a live candle, poll every second to sec 200, then re-snapshot
the SAME candle twice after the fact. Candle 1791254700 (02:45 UTC):
- the primed live probe polled every second from sec 21 to sec 200 and observed **0** new prints;
- at sec 246 - 66 s AFTER the arm's window had closed - the feed showed **21** prints for that
  candle and **0** inside sec 60-180; its newest print was at sec **-33**, i.e. before the candle;
- at sec 396 the same query returned **500** prints (the limit cap), **327** of them inside
  sec 60-180, newest at sec 265;
- the 500 prints that appeared in those 150 s carried timestamps from sec 55 to 265 and so were
  visible only **132-342 s after their own timestamps**.
So 327 qualifying-window prints existed on that candle and the live arm could see none of them.
This is the clean proof; the arm's three "no qualifying print" lines (candles 02:35, 02:40, 02:45)
are all explained by it.

**Also correcting an intermediate mistake of mine rather than burying it:** mid-diagnosis I briefly
read candles 02:40 and 02:45 as "genuinely quiet, so the arm was right to pass". That was wrong and
was my own timing error - I queried the 02:45 candle at 02:43, before it had even started, and the
02:40 candle while it was still live at sec 210. Both looked empty because of WHEN I sampled them,
not because they were quiet: 02:45 in fact carried 327 in-window prints. The lesson is the same one
that invalidated my first probe - with a lagged feed, any pull taken before the lag has elapsed
measures the sampling time, not the market.

**Status: M53 has no executable detection path and will record n = 0 on this feed.** The arm is left
running exactly as specified (unmodified, paper, ~122 polls per candle) so the blocker keeps being
documented, but it provably cannot fire, so I recommend pausing it pending the detection-source
decision rather than spending ~35k requests a day on a guaranteed-empty result. That is V's and the
owner's call, not mine, and I have changed nothing about the frozen rule or the pass rule.

---
## AMENDMENT 2026-10-06 03:2x - DETECTION RE-POINTED (V sign-off). RULE UNCHANGED.
**New detection source: the Polymarket CLOB websocket market channel,
`wss://ws-subscriptions-clob.polymarket.com/ws/market`, `last_trade_price` events.**
Only DETECTION changed. The frozen rule, the +3 s primary, the +0/+2/+10 s secondaries, the fill
model, the control and the five-part pass rule are all exactly as committed in 0c859d8.

**SWITCH EPOCH = 1791257400 (2026-10-06 03:30:00Z). Forward n counts only from that candle on.**
Everything the data-api path produced before it (3 candles, n = 0) is void and counts for nothing.

### Confirmation required by V, run BEFORE counting anything - both gates PASS
Captured 2 full candles live (1791255900 and 1791256200) and cross-checked each after the data-api
lag had elapsed:
1. **Sub-second delivery: PASS.** n 2,508 events, latency (our receive time minus the event's own
   timestamp) **p50 0.013 s, p90 0.061 s, max 1.046 s**. The first qualifying in-band BUY was seen at
   lag 0.01 s on both candles (sec 60 and sec 86). Against the old path's 132-342 s, this is the
   difference between a rule that can run and one that cannot.
2. **Same taker-side convention: PASS, and proved two ways.**
   - On every event whose `transaction_hash` also appears in the data-api `takerOnly=true` set, the
     `side` string agrees: **499/499** on each candle.
   - The count ratio settles what the feed actually emits. Paging data-api past its 500-row cap gives
     **1281** taker trades inside candle 1791255900; the websocket captured **1282** events on the
     same candle - **ratio 1.00**. So the channel emits ONE event per taker trade and its `side` is
     the TAKER's side. It is not emitting both sides of each fill, which was the risk worth ruling
     out: had it done so we would have followed the maker half and inverted the signal.
   - Qualifying in-band BUY counts: ws 147 vs data-api 142 on that candle. I am stating the 5-event
     gap rather than rounding it away - it comes from the boundary, ws timestamps being milliseconds
     (so a trade at sec 59.8 or 180.3 can fall either side) while data-api reports whole seconds.
     It cannot affect which side we follow, only occasionally which print is "first".

### Operational facts found during confirmation, recorded so they are not rediscovered
- The server CLOSES the socket with `1000 (OK) all subscribed assets resolved` as soon as the
  subscribed market settles. A long-lived single connection is therefore impossible; the arm
  reconnects and re-subscribes per candle. My first confirmation pass died on exactly this.
- `AF_INET` must be forced: this host has no IPv6 route and Polymarket resolves v6-first. Same
  lesson already recorded in `rtds.py`.
- Token ids come from `pm_multi.markets`, written by the recorder ~5 min AHEAD of each candle, so the
  arm can subscribe before the candle opens (it subscribed at sec -1 in confirmation). Gamma's `mkt`
  table must NOT be used - it is a settlement mirror and only ever holds closed candles.
- A quiet or already-resolved market emits very few `last_trade_price` events (7 in 75 s on one
  settled candle) while an active one emits ~1,250 per candle. Low event counts are not evidence of
  a throttled feed.
