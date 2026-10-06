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
