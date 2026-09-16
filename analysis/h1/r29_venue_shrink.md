# R-29 — the owner's v12.16.1 venue-shrink candidate: **worse than frozen v10 on money**

Script `analysis/h1/r29_venue_shrink.py`. Transform copied from the candidate's own source
(`analysis/v/candidates/btc_model_v12_16_1_adaptive/btc_model_v10.py:385-425`), not from a summary:
`trust = min(1, 1/max(ratio,1))`, `z = logit(anchor) + trust*(logit(base) − logit(anchor))`,
`anchor = clamp(p_venue, .02, .98)`. Shrinks toward the **venue**, not 0.5 (that is the R-28
difference), engages only when ratio > 1. Ratio = build11 fast/slow **engaged**, reconstructed from
the running engine's code (R-28). 2,079 graded Polymarket fires on `venues.outcome`; 1 dropped for a
missing venue price or side ask. **It engages on 603/2079 = 29.0% of fires.**

## Identity cell first

`m=0` refires **2077 of 2079** actual fires (the 2 are stored fires whose own ev sits just under
threshold), **0 side flips**. Guard passes; everything below is readable.

## The grid — `m` is the shrink exponent, `trust = min(1, 1/ratio^m)`

| m | n | W% | per $1 | **total** | h1 | h2 | |
|---|---|---|---|---|---|---|---|
| 0.0 | 2077 | 53.1% | **+0.136** | **+281.84** | +0.120 | +0.151 | frozen v10 |
| 0.5 | 1705 | 53.0% | +0.130 | +221.50 | +0.139 | +0.121 | |
| 1.0 | 1621 | 52.4% | **+0.115** | **+185.70** | +0.130 | +0.099 | **the candidate** |
| 2.0 | 1583 | 52.7% | +0.120 | +189.69 | +0.128 | +0.111 | |

**The candidate loses to frozen v10 on both axes: −0.021 per $1 and −$96 total.** It drops 456 fires
and is paid less for the ones it keeps. This is worse than R-28's shrink-to-0.5, which at least
bought a higher per-$1 while losing total; this one gives up both.

## The `ratio > 1` bucket — the whole test, since `≤1` is identity by construction

| m | n | W% | per $1 | total | h1 | h2 |
|---|---|---|---|---|---|---|
| 0.0 | 602 | 55.0% | +0.209 | +125.59 | +0.082 | +0.335 |
| 0.5 | 230 | 57.4% | +0.284 | +65.24 | +0.188 | +0.380 |
| 1.0 | 146 | 53.4% | +0.202 | +29.45 | +0.118 | +0.285 |
| 2.0 | 108 | 58.3% | +0.310 | +33.44 | +0.262 | +0.357 |

At the candidate's own setting it keeps **146 of 602** fires in the bucket it exists to improve, for
**no per-$1 gain** (+0.202 vs +0.209) and a total that falls from +125.59 to +29.45. The sweep is
non-monotone (0.209 → 0.284 → 0.202 → 0.310), peaking away from the candidate's value — the `sweep()`
failure signature, so the m=2 cell is noise, not a better setting.

`≤1` bucket confirmed untouched: n=1475, +0.106 per $1 at every m, as construction requires.

## The R-19 null — does it beat "fewer, cheaper fires"?

| m | n | candidate /$1 | candidate total | top-n by EV /$1 | top-n by EV total |
|---|---|---|---|---|---|
| 0.5 | 1705 | +0.130 | +221.50 | **+0.166** | **+283.79** |
| 1.0 | 1621 | +0.115 | +185.70 | **+0.172** | **+278.90** |
| 2.0 | 1583 | +0.120 | +189.69 | **+0.179** | **+284.09** |

No. At the same fire count, ranking by EV and ignoring the ratio entirely beats it by +0.057 per $1
and +$93 total.

## Verdict

**Do not ship it.** It is worse than frozen v10 on per-$1 and on total money, worse than the trivial
EV null, and its sweep peaks away from its own setting. The fault is not the ratio plumbing — R-28
already showed the ratio carries no EF information — it is that shrinking toward the venue removes
the only thing the engine is being paid for.

## One incidental confirmation of R-13, worth recording

**0 side flips at every m.** A transform that pulls the model's log-odds all the way to the venue's
never changes which side gets bought, on any of 2,079 fires. That is R-13 stated in a new way: the
model and the book already agree on direction, so anchoring to the book can only ever change *size
of conviction*, never the call. It also means the wrong-side-ask hazard I guarded for did not fire
here — the guard stays in the script, because the next venue-anchored candidate may not be so tame.
