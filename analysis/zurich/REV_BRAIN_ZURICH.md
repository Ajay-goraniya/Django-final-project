# A REVERSAL "brain" on the live-only inputs — Zurich

Read-only. No deploy, no config change. Zurich stayed 13.1.2, master OFF, `decide_mode` poll, profile
`raw_v10_live25`, stake 5. Script: `analysis/zurich/rev_brain.py`.

## Headline

**This window cannot test the idea, and what it can show is negative.** Every cell of the grid is
n<60, negative on paper, −0.12 to −0.15/$1 under London execution, with permutation p 0.27–0.58.
Adding the live-only inputs makes out-of-sample discrimination **worse than chance**
(AUC 0.431 per candle vs the venue-ask-only null's 0.725).

## Why the power is this thin — stated before the grid

`decide_log` carries feats only from **09-24 12:30**, not from 09-23. Joining it to the window-2
REVERSAL call stream (0-240 s, past-only same-second quote) leaves:

| | calls | candles |
|---|---|---|
| REV stream, window 2 | 12,396 | 149 |
| after 0-240 s + past-only quote + a `decide_log` row | **5,528** | **74** |

Candles per day: **09-24: 10, 09-25: 33, 09-26: 31** — three day buckets. Walk-forward by day makes the
first day training-only, so a one-trade-per-candle rule can score **at most 64 trades on 2 test days**.

The join itself is tight: age p50 **0 s**, max 8 s.

**Training rows are calls, not candles.** Fold 1 fits on 657 call rows drawn from **10 candles**, and
every call inside a candle shares one label. The effective training size is the candle count. Fitting
31 features on 10 effective observations is the central fact about everything below.

## Inputs

31 brain features from the engine's own `decide_log_features`: `basis_bps`, `perp_n15` (perp);
`imb5`, `imb20`, `spread_bps` (depth); `ofi5`, `ofi15`, `ofi60` (OFI); `spot_imb15`, `spot_imb60`
(flow); plus `dist_hi_bps`, `dist_lo_bps`, `hod_cos`, `hod_sin`, `lv`, `lv_x_sec`, `micro_bps`,
`move_bps`, `mv_x_sec`, `pos_in_range`, `prev1_bps`, `prev2_bps`, `range_bps`, `ref_gap_bps`,
`ref_move_bps`, `ref_open_bps`, `ret5`, `ret15`, `ret30`, `ret60`, `rv60`.

Chosen before any result was read:
- **Absolute price levels are excluded** (`_price`, `ref_now`, `ref_open`, `bn_line_now`,
  `bn_line_open`). On a three-day sample, a tree splitting on a raw BTC level is selecting a calendar
  day, not learning structure.
- `p_venue`, `_ask_up`, `_ask_dn`, `_venue_ok` are excluded from the brain: `p_venue` is a transform of
  the venue ask, which is the null's own feature.
- The venue ask and `sec/300` **are** in the brain, so the null is strictly nested and any gain is
  attributable to the live-only inputs rather than to the model class.
- **`feed_timing` is not testable.** It lives in `signals.decision`; `decide_log`'s 44 keys carry no
  timing field. That part of the brief is not answered and nothing is claimed for it.

## Full grid — every cell is n<60

`*` = n<60, not a reading. LON = London execution (`lane_exec_sim.py` model: P(fill|win) 54.1%,
P(fill|lose) 65.0%, slippage −1/+2/+11 cents, $10 stake, 1000 runs).

| model | theta | n | hit | ask | paper per$1 | H1 | H2 | LON per$1 | LON $ | perm p | test days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BRAIN LOGIT | 0.00 | 48* | 70.8% | 0.70 | −0.017 | −0.149 | +0.114 | −0.116 | −33 | 0.45 | 2 (29/19) |
| BRAIN LOGIT | 0.05 | 48* | 70.8% | 0.71 | −0.024 | −0.149 | +0.101 | −0.122 | −34 | 0.46 | 2 (29/19) |
| BRAIN LOGIT | 0.10 | 42* | 69.0% | 0.69 | −0.021 | −0.169 | +0.128 | −0.121 | −30 | 0.48 | 2 (29/13) |
| BRAIN GBM d3 | 0.00 | 53* | 67.9% | 0.70 | −0.049 | −0.118 | +0.017 | −0.147 | −46 | 0.47 | 2 (27/26) |
| BRAIN GBM d3 | 0.05 | 52* | 67.3% | 0.70 | −0.058 | −0.118 | +0.001 | −0.154 | −47 | 0.53 | 2 (27/25) |
| BRAIN GBM d3 | 0.10 | 50* | 68.0% | 0.69 | −0.040 | −0.082 | +0.001 | −0.145 | −43 | 0.39 | 2 (27/23) |
| NULL LOGIT | 0.00 | 31* | 64.5% | 0.68 | −0.094 | −0.168 | −0.024 | −0.192 | −35 | 0.58 | **1 (09-25 only)** |
| NULL LOGIT | 0.05 | 31* | 64.5% | 0.68 | −0.094 | −0.168 | −0.024 | −0.192 | −35 | 0.56 | **1** |
| NULL LOGIT | 0.10 | 31* | 64.5% | 0.68 | −0.088 | −0.156 | −0.024 | −0.187 | −34 | 0.56 | **1** |
| NULL GBM d3 | 0.00 | 54* | 70.4% | 0.69 | −0.027 | −0.065 | +0.011 | −0.122 | −39 | 0.42 | 2 (30/24) |
| NULL GBM d3 | 0.05 | 49* | 69.4% | 0.68 | −0.031 | −0.061 | −0.002 | −0.128 | −37 | 0.28 | 2 (30/19) |
| NULL GBM d3 | 0.10 | 42* | 66.7% | 0.66 | −0.017 | −0.069 | +0.035 | −0.125 | −31 | 0.27 | 2 (30/12) |
| **reference: every candle, first call ask≤0.90** | — | 59* | 69.5% | 0.70 | **−0.020** | −0.055 | +0.014 | **−0.118** | −41 | 0.42 | 2 (31/28) |

Note the NULL LOGIT rows score **one** test day: at theta ≥ 0 its predicted p never cleared the bar on
09-26 at all, so those three cells are a single day of 31 trades.

**No model beats simply taking the candle.** The reference line (−0.020 paper, −0.118 LON) matches or
beats every modelled cell, and beats BRAIN/GBM at every theta (−0.040 to −0.058). Raising theta does
not help anywhere — the sweep is flat-to-worse, which is what a rule with no signal looks like.

## Discrimination, measured apart from PnL

AUC on the walk-forward test days, using every call and every candle rather than the 30-60 trades a
theta rule selects. 0.50 = no signal.

| model | AUC per call (n 4,871) | AUC per candle (n 64, 46 wins) |
|---|---|---|
| BRAIN LOGIT | **0.406** | **0.431** |
| BRAIN GBM d3 | 0.499 | 0.519 |
| NULL LOGIT | 0.646 | **0.725** |
| NULL GBM d3 | 0.501 | 0.628 |

Two things follow, and they point the same way.

1. **The venue ask alone discriminates (0.725 per candle); the 31 live-only inputs destroy that
   (0.431).** Below 0.5 out of sample is the signature of a fit that has memorised its training fold —
   expected with 31 features and 10 effective training candles. This is evidence that the sample cannot
   support the model, not proof that perp/depth/OFI/flow are uninformative.
2. **Discrimination is not profit.** The null reaches AUC 0.725 and still loses −0.094/$1, because the
   ask it discriminates on is the price you have to pay. Rank-ordering candles by the market's own
   probability does not beat the market's own probability.

## Verdict

- **Not a finding, in either direction.** Nothing here is readable: every cell n<60, 2 test days,
  74 candles total.
- What the window does establish: **on this much data the brain cannot be fit** — it is worse than
  chance out of sample and worse than not modelling at all.
- To test the idea properly this needs `decide_log` coverage across many more days. It retains 4 days
  (`DECIDE_LOG_KEEP_S = 4*86400`), so a real test needs either a longer retention or an export that
  accumulates. That is a change to a running box and I have not made or proposed one here.
- The `feed_timing` half of the brief is untestable as specified: those fields are in
  `signals.decision`, not in `decide_log`.
