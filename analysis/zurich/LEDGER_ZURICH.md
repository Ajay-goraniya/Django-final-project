
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
