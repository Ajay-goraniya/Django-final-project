# Task 117 - REVERSAL tested clean. Owner: "test that rev again."

Supersedes the Task 114 comparison. Every REVERSAL number before this lane existed was either
DOWN-censored (the lane was handed `fair_p_up` instead of `1 - fair_p_up`, so no DOWN reversal could
clear the gate, fixed in 12.15.0) or refused by EF's v10 regime dial (0.15/0.25 applied to a lane
build11 gates with no EV rule at all, fixed in 12.15.5). Those journals cannot answer the question.
This one starts from zero.

## Setup, 2026-09-16 18:28 UTC

Staged tree verified before anything was stopped: **SHA256SUMS 31/31 OK**, tests
71 + 28 + 270 = **369 OK**, commit 4340859.

| lane | pid | db | build | master | ef | main | reversal | stake | halt | rev_max_entry |
|---|---|---|---|---|---|---|---|---|---|---|
| 8796 EF+REV | 135061 | `paper_ef_rev_117.sqlite3` | 12.15.5 | true | true | **false** | **true** | fixed 3.0 | none | unset (off) |
| 8795 EF only | 135062 | `paper_ef_117.sqlite3` | 12.15.5 | true | true | false | false | fixed 3.0 | none | unset (off) |

Both `--model model_v10.json --capital 50 --host 127.0.0.1`, same quote-age dial, PAPER, stake
settings mode fixed / 3.0 / min 1.0 / max 50.0 on both. **Started 0.01 s apart**, so they see the
same tape from their first candle. Untouched and still running their own dbs: 8794 (134930),
8787 (126394), 8793 (119658). The Task 114 databases are on disk untouched -
`paper_ef_rev_114.sqlite3` 6,184,960 bytes and `paper_v10_12130.sqlite3` 6,922,240 bytes.

### One thing done differently, stated plainly

A genuinely empty journal has no `candles` rows, so `_seed_lane_history()` finds nothing and the lane
starts COLD - `volume_ratio` is noise for two hours and MAIN barely calls, which would have gagged
REVERSAL for half of the first four-hour ledger. So both lanes were started twice, identically:

```
18:27  first start, fresh dbs   -> [LANE SEED] 0 closed candles from the journal; COLD - ... until 24 more
       engine's own klines backfill writes 287 candles into each fresh db within 35 s
18:28  second start, same dbs   -> [LANE SEED] 64 closed candles from the journal; warm
```

Nothing was hand-copied. The candles came from the engine's own `/api/v3/klines?...&limit=288` fetch
(btc_model_v12_polymarket.py:1110) into each fresh journal. Both lanes got the identical treatment
0.01 s apart, so the comparison is unaffected. The single `LANE_SEED_COLD` row in each db is the
18:27 start and should be read as that, not as the running process.

## Ledger - first entry due 22:30 UTC

Graded on `venues.outcome`. Every cell under 60 graded fires is marked insufficient and not read.

| | REVERSAL 8796 | EF 8796 | EF 8795 |
|---|---|---|---|
| signals | 0 | 0 | 0 |
| orders placed | 0 | 0 | 0 |
| refused at breakeven | 0 | 0 | - |
| graded n / W / pnl | 0 | 0 | 0 |
| pnl per $1 | - | - | - |

Minutes old. **Insufficient on every line.** Nothing to read.

Still to report at the first four-hour mark, per the brief:
1. REVERSAL alone - signals, orders by status, share refused at breakeven vs placed, n/W/pnl, per $1.
2. EF alone on 8795 - the same.
3. **The paired comparison** - 8796 total per $1 against 8795 per $1 **on the same candles**,
   discordant candles only, exact McNemar. Not two totals side by side.
4. **The stacking count** - candles where EF and REVERSAL both fired on 8796, same side N against
   opposite side M, with combined per $1 on each subset. The owner's decision waits on this number.
   Prior from the 114 lane, n=1: same side, and structurally it can only be same-or-independent while
   `main_enabled` is false, because there is no MAIN position for the hedge to sit against.
5. `halves()` on every arm; a sign flip is reported as "not readable".

Also to confirm as they land: the first DOWN REVERSAL and the first UP REVERSAL, each with p, ask
and fill.

## Ledger, 2026-09-17 ~07:0x UTC (both arms past the 60 bar and readable)

Per-leg, one row per filled order, graded on the venue outcome. Legs sum exactly to the per-candle
`results` totals; nothing double counted.

| arm | n | W | hit% | staked $ | pnl $ | per $1 |
|---|---|---|---|---|---|---|
| 8796 EF legs | 88 | 43 | 48.9 | 262.07 | +44.47 | +0.1697 |
| 8796 REVERSAL legs | 7 | 2 | 28.6 | 20.96 | -2.68 | **-0.1280 INSUFFICIENT** |
| 8796 LANE total | 95 | 45 | 47.4 | 283.03 | +41.79 | +0.1477 |
| 8795 EF only | 97 | 55 | 56.7 | 288.43 | +100.44 | +0.3482 |

REVERSAL signals by status: 7 FILLED, 8 SKIPPED, 2 DEADLINE. EF on 8796: 89 FILLED.

### The paired comparison - the arms still cannot be separated

| | 58 common candles (first read) | 82 common candles (now) |
|---|---|---|
| 8796 per $1 | +0.0396 | +0.1331 |
| 8795 per $1 | +0.1990 | +0.2300 |
| delta | -0.1594 | -0.0969 |
| discordant b (8796 won, 8795 lost) | 0 | 0 |
| discordant c (8796 lost, 8795 won) | 2 | 2 |
| concordant | 56 | 80 |
| **exact McNemar p** | **0.5000** | **0.5000** |

**24 additional shared candles produced zero new discordant pairs.** The per-$1 gap is therefore not
a disagreement about which side wins - it is fill price and stake on candles both arms called the
same way. On this evidence REVERSAL has not been shown to hurt or help.

### Stacking - the owner's decision number, still not readable

| subset | legs | W | staked $ | pnl $ | per $1 |
|---|---|---|---|---|---|
| EF and REVERSAL both fired, SAME side | 8 | 4 | 23.96 | +10.09 | +0.4213 |
| EF and REVERSAL both fired, OPPOSITE side | 0 | - | - | - | - |

Opposite-side remains **zero**, which is structural: with `main_enabled` false there is no MAIN
position for the hedge to sit against, so REVERSAL can only concentrate the candle or act alone.
The same-side cell went from -0.3367 per $1 at 6 legs to +0.4213 at 8 legs. **A cell that swings
0.76 per dollar on two more legs is noise, and no stacking decision should rest on it.**

### Halves

| arm | H1 | H2 | |
|---|---|---|---|
| 8796 lane | +0.1162 (n=47) | +0.1784 (n=48) | same sign |
| 8795 EF only | +0.4978 (n=48) | +0.2016 (n=49) | same sign, decaying |

Both arms now survive their own halves test, unlike the first read where 8796 flipped sign.

### Verdict at this sample

EF alone is ahead of EF+REVERSAL by 0.20 per dollar on the whole-arm totals and 0.097 on paired
candles, but **the paired test says that difference is not significant** and REVERSAL itself is
7 graded legs. The honest statement is that REVERSAL is not yet measurable, not that it is bad.
