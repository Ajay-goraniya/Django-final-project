# Task 12a — the DIRECTION model (the "trained brain"), on the venue quote table
H1, 2026-09-10 23:10 UTC. Data: `learner/live_backup/venues.sqlite3` (22:43 snapshot).
640 graded candles, 60 quote samples each (every 5 s), 54.7 h of coverage.

This is the user's ask taken literally: not a gate, a model that says which way it goes.
Walk-forward (4 folds, strictly forward, train stats only), full grid over decision second,
never one cell.

## Headline

**1. The venue's own quote path is dead. Negative at every decision second, both halves,
with and without a liquidity floor.** This closes the avenue and Tasks 12b/c should not be
queued on it.

**2. The entire edge is the cross-venue Predict↔Polymarket spread** — and it is real:
positive in both halves at all 8 decision seconds, no exception.

**3. But the edge is ~6 cents wide, so this is an execution problem, not a modelling problem.**
Median |poly − predict| traded is 0.062. A 10c haircut erases it early in the candle and
leaves it standing only late.

## Ablation — the decisive table

Decide on the venue implied probability, **pay the raw ask**, 2% fee, per $1, thr = 0.05.

| sec | level only (null) | level + cross (known) | level + own path (NEW) | everything |
|---|---|---|---|---|
| 30 | −0.147 | **+0.244** | −0.168 | +0.224 |
| 60 | +0.004 | **+0.274** | −0.067 | +0.202 |
| 90 | −0.030 | **+0.292** | −0.083 | +0.212 |
| 120 | −0.341 | **+0.296** | −0.220 | +0.135 |
| 150 | −1.000 (n=28) | **+0.267** | −0.155 | +0.092 |
| 180 | −0.449 | **+0.246** | −0.217 | +0.172 |
| 210 | +0.011 | **+0.441** | −0.095 | +0.383 |
| 240 | −0.053 | **+0.382** | −0.038 | +0.374 |

Same shape with a both-sides liquidity floor of 50 (n drops to 321–428): own path still
negative at all 8, cross still positive at all 8. **Dropping `cross` kills it entirely;
`level + cross` ≈ `everything`.** The venue's own path contributes nothing.

## Both halves and staleness, the cross set

| sec | 1st half n / per-fire | 2nd half n / per-fire | clean | +5c | +10c |
|---|---|---|---|---|---|
| 30 | 151 / +0.227 | 167 / +0.259 | +0.244 | +0.117 | +0.015 |
| 60 | 172 / +0.289 | 173 / +0.258 | +0.274 | +0.159 | +0.065 |
| 90 | 161 / +0.410 | 157 / +0.170 | +0.292 | +0.160 | +0.057 |
| 120 | 138 / +0.359 | 148 / +0.236 | +0.296 | +0.128 | +0.010 |
| 150 | 151 / +0.333 | 147 / +0.199 | +0.267 | +0.122 | +0.016 |
| 180 | 147 / +0.203 | 131 / +0.295 | +0.246 | +0.079 | −0.023 |
| 210 | 132 / +0.461 | 127 / +0.419 | **+0.441** | **+0.253** | **+0.164** |
| 240 | 126 / +0.287 | 110 / +0.491 | **+0.382** | **+0.256** | **+0.191** |

Positive in both halves in 8 of 8 rows. The slippage profile is the interesting part: at
+10c only **t = 210 and 240 survive with room to spare**. Everything earlier is a coin flip
once you pay realistically.

That is worth V's attention because **t = 210/240 is exactly where candidate J failed**
("t=190 does not replicate; t=240 negative"). This is a different rule — J is a same-side
second entry at EF's price; this is "trade the cross-venue spread" — so the two are not in
conflict, and the late window may be live for the spread rule even though it is dead for J.

## What I checked before believing any of it

The first pass of this study produced +0.2 to +0.6 per fire and I did not report it, because
that is not a credible number. Three checks:

- **The market is well calibrated** (implied vs realised gaps mostly ±0.03 across seven price
  buckets at every second), which by itself says a huge edge must be an artifact.
- **My first control was wrong and I threw it out.** Shuffling the labels also destroys the
  *market's* calibration, so cheap longshots "win" at the 50% base rate instead of their
  implied 5.6% — the shuffled control printed +4.34/fire. It was testing a broken world, not
  my plumbing.
- **The correct control** permutes the model's predictions and keeps outcome↔price paired.
  Permuted draws lose money (−0.001 to −0.341, increasingly negative later in the candle) and
  the real model beat **30 of 30** draws at every second, p = 0.00. The plumbing is sound.
- Pass 1 also charged the normalised implied probability rather than the raw ask. Fixed here;
  it costs about a cent a trade.

## Honest limits

- **640 candles, 54.7 hours, one regime.** My other studies run on 20k–72k candles. This is
  small and it is one weather pattern. It has not been through a Task 13 grid and should not
  be until it has more coverage.
- I cannot test tradability. The median spread traded is 6 cents; whether you can actually hit
  a 6-cent cross-venue dislocation on the live book is V's question, not mine. Candidate J
  took a **2.5× haircut** from recorded quotes to real fills. Apply at least that here: the
  clean +0.44 at t=210 is realistically ~+0.17, and the early seconds are ~zero.
- `cross` uses Polymarket, which the engine already consumes as its trigger. Whether "the size
  of the Predict↔Polymarket spread is itself tradeable" is genuinely new is V's call — V knows
  what the engine does with Polymarket and I do not.

## Recommendation to V

1. **Do not spend more time on the venue's own quote path.** It is negative in 16 of 16 cells.
2. If a shadow is cheap to add, the one worth shadowing is **the cross-venue spread rule at
   t = 210–240**, since that is the only cell that survives a 10-cent haircut, and it does not
   collide with J's window.
3. Treat every number above as paper. The 2.5× J haircut is the prior.

Repro: `analysis/h1/venue_path_model.py` (pass 1 + controls), `analysis/h1/venue_path_ablate.py`
(ablation, raw asks, liquidity floor, halves, staleness).
