# EF_CHAINLINK_DIV (NC-16) — a second box's read of London's number

Zurich, 2026-09-28. READ-ONLY replication plus a PAPER shadow arm. **Master OFF, nothing live, no order path.**

London's candidate, as relayed by V: `div = (Chainlink ref − Binance spot) / Binance` in bps; when
`div <= −3` at second 45, buy DOWN at the ask. London reports **+0.24/$1 on 167 tape candles**, beating a
cheapness-matched null at −0.115, with 5 of 6 days positive — but a rolling version dies, there is no
mechanism, and **London's 10 real fills in it lost −0.30**.

## What V asked for, and what was already there

**(1) "log div at 1 Hz alongside up/dn ask"** — this already exists and nothing new had to be built. The
engine's own `tape1s` writes `spot_px`, `ref_px`, `up_ask` and `dn_ask` in the *same row* at 1 Hz, and the
hourly research-archive export has been copying all four since **09-22 19:30**. `ref_px` is the venue's own
RTDS `crypto_prices_chainlink` topic (`poly_feeds.py:90-94`) — the Chainlink BTC/USD the market settles on.
That gives **437,992 shared seconds over 135.4 hours** without waiting for new data.

**(2) the PAPER shadow arm** is running — see the end of this file.

**(4) the independent read** is the rest of it, and it is the part that matters today.

## Headline: Zurich does not reproduce the magnitude

**+0.016/$1 on 224 candles, against London's +0.24 on 167.** Same rule, same threshold, same second, a 34%
larger sample and a different box's feeds.

| arm | n | win% | per $1 | H1 | H2 | permP | mean ask |
|---|---|---|---|---|---|---|---|
| `div <= −3` → buy DOWN | **224** | 48.2% | **+0.016** | −0.021 | +0.053 | 0.178 | 0.468 |
| cheapness-matched null | 948 | 48.6% | **−0.012** | +0.069 | −0.092 | 0.180 | 0.476 |
| all candles → buy DOWN | 1352 | 50.8% | −0.026 | +0.025 | −0.076 | 0.166 | 0.500 |
| all candles → buy UP | 1352 | 49.2% | −0.091 | −0.134 | −0.048 | 0.834 | 0.511 |

The edge over the cheapness-matched null is **+0.028**, not the +0.355 that +0.24 against −0.115 implies. And
the fired set **wins less often than its own null** (48.2% vs 48.6%) — whatever the +0.016 is, it is not
accuracy.

This is not proof London is wrong. It is a different window on a different box, and the two could differ in
the tape, the ask source or the exact span. But a second independent read landing at 6% of the claimed
magnitude, on a larger sample, is the outcome that should be acted on — and it sits much closer to London's
**10 real fills at −0.30** than the +0.24 does.

## The mirror arm barely exists

`div >= +3` fires on **2 candles in 135 hours** (0.1% of seconds), because the divergence is almost always
negative: mean −2.12 bps, p90 −0.95. **The rule is one-sided by construction**, not by choice, and the mirror
V asked for cannot be evaluated on this data at all. Any framing of NC-16 as a symmetric basis signal is
already contradicted by the distribution.

## The full run

```
tape rows with BOTH feeds 438067, 09-22 19:30 -> 09-28 10:56 = 135.4 h; gamma-graded 5m candles 1747
scannable candles at sec 45 with both feeds, both asks and a venue outcome: 1352
  div at sec 45: mean -2.12  p10 -3.27  p50 -2.13  p90 -0.95  sd 1.07   |   frac <= -3: 16.6%,  frac >= +3: 0.1%

====================================================================================================================
1. LONDON'S CELL AS SPECIFIED - fixed threshold at sec 45
====================================================================================================================
  arm                                    n   win%    per$1      H1      H2  permP    askper$1@+1s days
  div <= -3  -> buy DOWN               224   48.2%   +0.016  -0.021  +0.053  0.178  0.468   +0.174    6
  div >= +3  -> buy UP   (mirror)        2   50.0%   +0.595  -1.000  +2.178  0.476  0.360   +2.178    2  *n<60
  ALL candles -> buy DOWN (null)      1352   50.8%   -0.026  +0.025  -0.076  0.166  0.500   -0.025    7
  ALL candles -> buy UP   (null)      1352   49.2%   -0.091  -0.134  -0.048  0.834  0.511   -0.091    7

  CHEAPNESS-MATCHED NULL - London's own control. The fired set buys DOWN at a mean ask of 0.468 if it fires at all;
  the null buys DOWN on every NON-firing candle whose DOWN ask sits in the same range.
  arm                                    n   win%    per$1      H1      H2  permP    askper$1@+1s days
  null: ask in [0.18,0.75], no signal   948   48.6%   -0.012  +0.069  -0.092  0.180  0.476   -0.016    7

====================================================================================================================
2. THE SAME RULE ON THE DE-MEANED DIVERGENCE (past-only 600 s median)
====================================================================================================================
  arm                                    n   win%    per$1      H1      H2  permP    askper$1@+1s days
  div_z <= -3 -> buy DOWN                6   50.0%   -0.179  +0.226  -0.580  0.438  0.428   -0.579    2  *n<60
  div_z >= +3 -> buy UP                  9   33.3%   -0.265  -0.581  -0.010  0.724  0.442   +2.178    4  *n<60

====================================================================================================================
3. PER DAY - the fire rate is the tell
====================================================================================================================
  day       candles  mean div  fires <=-3  fire rate    per$1   win%  fires_z  per$1_z
  09-22          47     +0.01           0       0.0%     +nan   nan%        0     +nan
  09-23         263     -1.58          23       8.7%   -0.160  34.8%        3   +0.226
  09-24         256     -2.80         108      42.2%   -0.038  44.4%        3   -0.580
  09-25         253     -2.19          42      16.6%   +0.113  47.6%        0     +nan
  09-26         262     -1.95           3       1.1%   -0.119  66.7%        0     +nan
  09-27         252     -2.49          45      17.9%   +0.160  62.2%        0     +nan
  09-28          19     -2.19           3      15.8%   -0.073  66.7%        0     +nan

  If the fire count tracks the day's mean divergence rather than anything about the market, the
  rule is selecting a BASIS REGIME and not a signal - which is what "the rolling version dies" means.

====================================================================================================================
4. SWEEPS - a real effect should strengthen as the threshold tightens, and should not live at one second only
====================================================================================================================
  threshold sweep on div (buy DOWN):
       thr      n    win%    per$1    ask
      -2.0    758   49.9%   -0.058  0.498
      -2.5    446   48.0%   -0.053  0.486
      -3.0    224   48.2%   +0.016  0.468
      -3.5     87   41.4%   -0.022  0.413
      -4.0     42   35.7%   -0.072  0.399  *n<60

  second sweep at div <= -3 (is sec 45 special, or is any second the same?):
       sec      n    win%    per$1    ask
        15    233   45.5%   -0.034  0.465
        30    229   43.7%   -0.044  0.461
        45    224   48.2%   +0.016  0.468
        60    209   45.0%   -0.014  0.460
        90    226   47.3%   +0.028  0.463
       120    231   46.8%   -0.218  0.485
       180    181   43.1%   -0.082  0.451
       240     94   37.2%   -0.407  0.426
```

## Why it is a regime, not a signal — three independent tells

**1. The fire rate tracks the day's mean divergence, and nothing else.** 09-24 has a mean div of −2.80 and
fires on **42.2%** of candles; 09-26 has a mean of −1.95 and fires on **1.1%**. A fixed −3 threshold on an
offset that drifts between −1.6 and −2.8 bps day to day is a *regime dummy* with the market's name on it.
Per-day per $1: −0.160, −0.038, +0.113, −0.119, +0.160, −0.073 — **2 of 6 days positive**, not 5 of 6.

**2. De-meaning does not "weaken" the rule, it nearly deletes it.** Against a past-only 600 s rolling median
the rule fires **6 times in 135 hours** (and the mirror 9). That is the precise content of "the rolling
version dies": once the drifting offset is removed, the divergence essentially never reaches ±3 bps, because
its de-meaned standard deviation is about **0.8 bps**. There is no signal to weaken.

**3. Both sweeps peak exactly at the chosen value.**

```
threshold:  -2.0 -0.058 | -2.5 -0.053 | -3.0 +0.016 | -3.5 -0.022 | -4.0 -0.072
win%:        49.9%        48.0%         48.2%         41.4%         35.7%
second:       15 -0.034 |  30 -0.044 |  45 +0.016 |  60 -0.014 |  90 +0.028 | 120 -0.218 | 180 -0.082 | 240 -0.407
```

The threshold sweep peaks at −3.0, the interior point that was chosen, and the **win rate falls monotonically
as the threshold tightens** (49.9 → 35.7%) — the exact opposite of a real signal, where a stronger condition
should select better trades. The second sweep has no structure: 45 s and 90 s are marginally positive and
everything else is negative.

## Verdict

**Not a finding on Zurich's data, and the three tells say why.** Nothing here met the standing precondition
for verify.py — the one arm with n ≥ 60 has a sign flip across its halves (−0.021 / +0.053) — so there was no
candidate to run the harness on.

The useful part is the mechanism, which was missing from the original: `div <= −3` is a *level* condition on a
slowly drifting basis offset, so it selects days, not moments. That explains all three of V's reservations at
once — why the rolling version dies, why there is no mechanism, and why London's real fills went the other
way.

## The PAPER shadow arm

`/home/ubuntu/pm_chaindiv/chaindiv_shadow.py`, started 2026-09-28 10:58:31 UTC, own sqlite, flock keep-alive
in cron, **PAPER ONLY**. There is **no order path in the file**: it imports only the standard library plus
`websockets`, never imports `poly_live`, holds no credentials, and never reads or writes master.

- **div comes from the engine's own `tape1s`, opened read-only**, not from a second Chainlink subscription.
  That is deliberate — the shadow and the frozen-tape cell above then run on the *identical* divergence
  series, so the two reports V asked for are comparable by construction rather than differing by feed.
- **the book is its own WS**, because the fill simulator needs the own-side ask again 250 ms after the
  decision and a 1 Hz tape cannot supply that. Delta handling carries the 09-27 list-vs-dict fix; the REST
  resync runs at 10 s, the period established in the 09-28 ARB_5M_15M correction.
- rule: at second 45, `div <= −3` → buy DOWN at the ask, `div >= +3` → buy UP; $10 nominal; ef_persist's FAK
  rule — fills iff the ask at +250 ms is within one tick, at that later ask.
- both arms are recorded, and every non-firing candle is written to `skips` with its div, so the denominator
  is never lost.

Reported at each ledger from 13:30 onward: n, simulated fills, win%, per $1, beside the same cell from the
frozen 1 Hz tape. On the base rates above, expect roughly **1 in 6 candles to fire** — about 48 a day — though
that rate is a function of where the basis offset happens to be sitting, which is the whole finding.

## Files

- `ef_chainlink_div.py` — the frozen-tape replication, sweeps and per-day decomposition
- `/home/ubuntu/pm_chaindiv/chaindiv_shadow.py` — the PAPER shadow arm
