# R-28 — does the adapt_ratio carry EF information? **No.**

Script `analysis/h1/r28_adapt_ef.py`. 2,080 graded Polymarket fires (poly_pnl + v12 lanes), all on
`venues.outcome`; Predict.fun excluded, never pooled. Ratio reconstructed from the engine's own code
(`btc_model_v10_live.py` `_adapt_rms` / `_refresh_adapt_ratio` / `_engaged_adapt_ratio`, constants
875–889), not from a description of it. Prices: `paths.npz` 1 s closes as one absolute-second series.

**Label clash:** V assigned R-28 to this task at 20:5x; I had already used the R-28 label for the
loss diagnostic in `r28_why_today_lost.md`. Different files, unrelated questions.

## Buckets fixed first (V's, and they are the engine's own identity band)

`raw < 0.85` / `0.85–1.15` / `> 1.15` = `ADAPT_IDENTITY_LO/HI`, so MID is exactly where the engaged
factor is 1.0 and the ratio does nothing. Raw distribution: p5 0.446, med 0.958, p95 2.333. The
engaged factor is exactly 1.0 on **724/2080 = 34.8%** of fires.

| bucket | n | W% | per $1 | total | h1 | h2 | perm p |
|---|---|---|---|---|---|---|---|
| LOW `<0.85` | 753 | 54.3% | +0.123 | +92.44 | +0.097 | +0.148 | 0.641 |
| MID `0.85–1.15` | 724 | 50.3% | +0.088 | +63.55 | +0.166 | +0.009 | 0.929 |
| HIGH `>1.15` | 603 | 55.1% | **+0.210** | +126.48 | +0.080 | **+0.339** | 0.031 |

All three ≥ 60. HIGH is the best bucket and the only one with perm p < 0.05 — but its halves run
+0.080 → +0.339, so the second half carries it, and it is one of three buckets tested (p≈0.09
Bonferroni). MID nearly flips (+0.166 → +0.009).

## The p-scaling grid, `p' = 0.5 + (p−0.5)/raw^k`, refired through the real EV rule

| k | n | W% | per $1 | **total** | h1 | h2 |
|---|---|---|---|---|---|---|
| 0.0 | 2078 | 53.1% | +0.135 | **+280.84** | +0.119 | +0.151 |
| 0.5 | 1754 | 52.2% | +0.139 | +244.32 | +0.115 | +0.164 |
| 1.0 | 1672 | 52.4% | +0.147 | +245.13 | +0.126 | +0.167 |
| 2.0 | 1574 | 52.4% | +0.148 | +233.63 | +0.143 | +0.154 |

Per $1 rises with k and **total money falls at every k > 0**. That is the R-19 signature exactly:
the scaling is not improving the calls, it is dropping ~500 fires and the survivors are cheaper.

## The decisive null: does it beat just ranking by EV at the same n?

| k | n | ratio /$1 | ratio total | **top-n by EV /$1** | top-n by EV total | random /$1 |
|---|---|---|---|---|---|---|
| 0.0 | 2078 | +0.135 | +280.84 | +0.136 | +282.85 | +0.136 |
| 0.5 | 1754 | +0.139 | +244.32 | **+0.163** | **+285.20** | +0.136 |
| 1.0 | 1672 | +0.147 | +245.13 | **+0.170** | **+283.67** | +0.135 |
| 2.0 | 1574 | +0.148 | +233.63 | **+0.180** | **+283.55** | +0.137 |

**The dumb rule beats the ratio at every k, on both per-$1 and total.** Same inside HIGH, where the
ratio looks strongest: k=0.5 ratio +0.291/+93.57 vs top-EV +0.323/+103.55; k=1.0 +0.304/+80.38 vs
+0.331/+87.25. Only the n=209 k=2 cell is a wash (+0.387 vs +0.374) and its total is lower.

## Verdict

**The adapt_ratio does not carry EF information.** It is a strictly worse selector than the EV
ranking the engine already has, and per R-19 that ranking is itself cheapness, not accuracy. Nothing
here supports 12.16.0's ratio touching EF. The HIGH bucket's +0.210 is a real difference in the
record but is unstable across halves and does not survive its own null.

## Two limits, stated not hidden

1. **This grid can only REMOVE fires.** Every cell is a subset of fires the engine actually took, so
   in LOW — where dividing by `raw<1` only ever *raises* confidence — the k column is identical at
   every k (n=753 throughout). That is an artifact of the dataset, not a finding about LOW.
2. **A bug this run caught, worth keeping as a permanent guard.** `p` in `trades` is **already the
   chosen-side probability**, not P(up). My first pass flipped it for DOWN fires and the k=0 identity
   cell reproduced only 1,192 of 2,080 fires. Verified against the stored column: `ev_of(p, ask)`
   matches stored `ev` to 4e-4 median 3.7e-5, the flipped form is off by a median of 0.048. After the
   fix k=0 reproduces **2078/2080** (the 2 are stored fires whose own ev sits just under threshold).
   **Any re-fire study must print the k=0 / identity cell and check it reproduces the real count.**
   This is the same side-handling shape as the `fire_set` wrong-side-ask bug of 09-16 13:2x.

## Gates

`sample()` — all read cells ≥60, sub-60 cells marked INSUFFICIENT and not read. `halves()` — reported
on every cell; HIGH and MID flagged unstable above. `permutation()` — per bucket, resampling the pool,
predictions permuted not labels. `null()` — the top-n-by-EV table above, and it is what kills the
finding. `sweep()` — the k grid is reported whole, and total money is monotone *down*. `grading()` —
Polymarket fires on `venues.outcome` only. `costs()`/`quote_age()` — not applicable: these are the
engine's own executed taker fills at the logged ask, fee-adjusted through `per1`.
