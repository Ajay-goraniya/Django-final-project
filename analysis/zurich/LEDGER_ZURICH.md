
## 2026-09-28 05:4x UTC — master OFF, lane PAPER throughout

Cadence note: this covers **two** slots (01:30 and 05:30 were due; the 21:30 ledger was the last one sent).
The lapse was mine — overnight research tasks ran back to back. Nothing was hidden by it; the engine was
untouched and every number here is read-only from the journal.

### BTC lanes, cumulative, graded on results.actual

```
line                  n     hit     spent       pnl    per$1  lane
EF (v10)             28   46.4%     56.78    +9.817   +0.173  PAPER  * insufficient (n<60)
EF (v10 mixed cfg)  454   53.7%   2173.80  +623.845   +0.287  PAPER
EF (build11)          3   33.3%     10.98    -4.437   -0.404  PAPER  * insufficient (n<60)
MAIN                523   69.0%   2570.71  -117.166   -0.046  PAPER
REVERSAL             93   68.8%    439.57   +31.644   +0.072  PAPER
EF raw_v10_live25 (stitched, the only single-config line): n 440, right 53.2%, per$1 +0.277,
  sum pnl +587.99 at $5, maxDD 52.98, longest losing run 6
```

### The lapsed 8 h on its own (since 09-27 21:30)

```
EF        n  39  hit  53.8%  spent 188.57  pnl  +62.803  per$1 +0.333   *n<60
MAIN      n  37  hit  70.3%  spent 184.85  pnl  -16.812  per$1 -0.091   *n<60
REVERSAL  n   5  hit  80.0%  spent  24.98  pnl   +4.410  per$1 +0.177   *n<60
graded candles in the window: 65 of the 96 that elapsed
```

Every line in this slice is under the 60-fire bar and none of it is a reading.

### ETH/SOL EF shadow — the 24 h report (frozen arms 26 h old, Platt arms 19 h)

```
arm            n     hit    spent      pnl   per$1   maxDD        since  top skip reasons
eth frozen   185   31.9%   907.16   -61.59  -0.068  109.78  09-27 03:15  no_book 633  no_klines 266  engine_ev_ref 122
sol frozen   207   27.1%   998.89  -265.46  -0.266  291.63  09-27 03:15  no_book 1113 no_klines 252  engine_ev_ref 95
eth platt     96   28.1%   465.88  -118.21  -0.254  161.13  09-27 10:05  no_book 1394 no_klines 410  engine_ev_ref 106
sol platt    123   41.5%   579.46   +54.06  +0.093   42.65  09-27 10:15  no_book 1261 no_klines 213  engine_ev_ref 92
```

**Three of the four arms are negative**, and the one that is positive (sol platt +0.093) is the twin of the
worst arm on the board (sol frozen −0.266). Two calibrations of the same model on the same coin landing
0.36 apart is the signature of noise, not of an edge. Hit rates of 27–41% are what they should be — these
fires are cheap longshots (asks 0.14–0.21 in the sample) — but the money is not there.

Read this as the answer to "does it work individually, before merging": **on 24 h it does not, on either
coin, on either calibration.** And these are SHADOW fills at the quoted ask, which EF_TRIGGER_SOURCE and
EF_PERSIST both say is the optimistic case; real fills would be worse, not better.

`no_book` is the dominant skip on all four arms. That is the shadow's own 3 s freshness gate, not the
recorder bug fixed this hour — `eth_sol_shadow.py` resyncs REST /book every 5 s and its markets are all
step-300, so its `ep >= now//300*300` test is correct. Observed `book_age_s` on fires is 0.02–4.5 s.

---

## 2026-09-28 14:0x UTC — ledger (covers the lapsed 09:30 and 13:30 slots; EF-3 ran through both)

**Safety first.** `master = false`. **All 1160 orders ever written by this box are `lane = PAPER`** —
not "currently", ever, which is the strongest form of the check. `ef_engine = v10`,
`ef_profile = raw_v10_live25`, `ev = fixed 0.25`, `calibration.enabled = false`, stake `fixed 5.0`.
`meta.lane = "LIVE"` is the *configured* lane and is overridden by `master = false` → PaperBroker →
`lane = PAPER` on every write; the orders table is the proof, not the setting.

```
line                  n     hit     spent       pnl    per$1  lane
EF (v10)             28   46.4%     56.78    +9.817   +0.173  PAPER  * insufficient (n<60)
EF (v10 mixed cfg)  486   53.1%   2329.46  +648.977   +0.279  PAPER
EF (build11)          3   33.3%     10.98    -4.437   -0.404  PAPER  * insufficient (n<60)
MAIN                546   68.7%   2685.62  -140.642   -0.052  PAPER
REVERSAL             97   67.0%    456.93   +19.855   +0.043  PAPER
results n=908  sum(shadow_pnl) +533.57  sum(pnl) +0.00 (master OFF)
EF raw_v10_live25 (single config, stitched): n 472 | right 52.5% | per$1 +0.270 | +613.12 at $5
```

### The live EF line on the owner's new rubric — and why it does not mean the goal is met

Same 486 EF fires, re-cut into the columns the owner asked for:

```
  $ total +648.98   worst drawdown $52.98   profit/drawdown 12.25
  fires 486, 69.4/day, days positive 7/7, longest losing run 6
  per day: 09-22 +17.1  09-23 +156.8  09-24 +125.7  09-25 +125.1  09-26 +75.8  09-27 +105.1  09-28 +43.4
```

Read cold, that line **meets the standing goal outright**: large profit, a small drawdown, 69 fires a
day, every single day positive, a profit/drawdown of 12.25 against the best thing EF-3 could find (3.85).

**It does not, and the reason is one assumption.** This ledger records a *shadow fill at the quoted
ask*: every fire is booked as if it filled, instantly, at the price we saw. EF-3 scores the same rule
through the per-pass FAK simulator — fill only if the own-side ask 250 ms later is still within a tick,
and fill AT that later ask. The same `raw_v10_live25` rule, same box, same days:

| | $ total | worst DD | P/DD | fires/day | fill% |
|---|---|---|---|---|---|
| this ledger — assumes every fire fills at the quoted ask | +648.98 | 52.98 | **12.25** | 69.4 | 100% assumed |
| EF-3 §1 `raw25 S≥0` — per-pass FAK fills | +107.3 | 98.4 | **1.09** | 65.2 | **42.3%** |

**The entire distance between 12.25 and 1.09 is the fill assumption**, and it moves the drawdown the
wrong way too ($53 → $98), because the fires that *don't* fill are disproportionately the ones that were
about to win — EF_PERSIST measured unfilled rows winning 6.1 pp more often than filled ones.

So: this ledger line is a correct record of what the shadow booked, and it is **not** an answer to the
owner's goal. When the goal is finally met it will be met on a table with a `fill%` column in it. I am
flagging this here because the ledger's own headline number is the most flattering figure this box
produces, and it is the one most likely to be quoted back as evidence that the work is already done.

### Health

* `decide_log` 1,343,305 rows, 09-24 13:33 → 09-28 14:03 = **4.02 days** against `DECIDE_LOG_KEEP_S`
  of 4.00 — **the prune is working.** (Standing verification item: closed for this cycle.)
* Recorder (`pm_multi`) alive, ~180 book rows/min steady, 474 tokens in book, 85.9 MB.
* **Websocket `1013 slow consumer: send buffer full` at ~12 drops/hour**, every hour, on every day in
  the log — this is a *steady-state* condition, not a regression: the apparent doubling to ~25/h in the
  07:00–13:00 buckets is those hours appearing twice in a log that spans just over a day. Each drop
  reconnects and re-syncs within 10 s (the fix from the btc15 stale-book bug). It affects **my research
  recorder only** — the EF-3 tables come from the engine's own `decide_log`, which is a separate writer
  and is unaffected.
* Engine process up: `btc_model_v12_polymarket.py --live --mode pnl --capital 50 --quote-age-ms 2000`.

### Standing items

* ETH/SOL 48 h report due 09-29 03:35.
* REV brain re-run when the archive holds 14 days (10-08).
* EF-3 delivered and pushed (`f5a3539`): five items, no arm meets the goal, none passes verify.py.
