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

---

# R-29b — "test both in last 2 days data" (owner, 09-16 21:5x)

Same machinery, sliced by UTC day. 09-15 is the winning day, 09-16 the losing one, so this is the
rain-or-sun test rather than another pooled average. Halves shown where n ≥ 60.

## 09-15 (the good day)

| arm | n | W% | per $1 | total | h1 | h2 |
|---|---|---|---|---|---|---|
| frozen v10 | 188 | 60.1% | **+0.297** | **+55.84** | +0.413 | +0.181 |
| candidate m=1 | 137 | 59.9% | +0.275 | +37.66 | +0.256 | +0.293 |
| top-EV null @137 | 137 | 56.9% | +0.279 | +38.21 | n<60 | — |

## 09-16 (the losing day — the one the candidate exists for)

| arm | n | W% | per $1 | total | h1 | h2 |
|---|---|---|---|---|---|---|
| frozen v10 | 185 | 42.7% | −0.081 | **−15.05** | −0.195 | +0.031 |
| candidate m=1 | 153 | 39.2% | **−0.175** | **−26.70** | −0.386 | +0.034 |
| top-EV null @153 | 153 | 42.5% | −0.046 | −7.02 | n<60 | — |

**This is the finding.** The candidate is sold as adaptive protection in accelerating volatility.
On the one day in this window that actually went wrong it did the opposite: it **lost 77% more
money** than frozen v10 (−26.70 vs −15.05) and its win rate fell further (39.2% vs 42.7%). It also
lost to the trivial EV null, which was the best arm of the three on that day (−7.02).

## Both days combined

| arm | n | W% | per $1 | total | h1 | h2 |
|---|---|---|---|---|---|---|
| frozen v10 | 373 | 51.5% | **+0.109** | **+40.80** | +0.311 | −0.091 |
| candidate m=1 | 290 | 49.0% | +0.038 | +10.96 | +0.205 | −0.129 |
| top-EV null @290 | 290 | 49.0% | +0.099 | +28.84 | n<60 | — |

## Verdict, unchanged and now stronger

Worse on the winning day, **much** worse on the losing day, worse combined, and worse than the null
on all three. It fails rain-or-sun in both directions — there is no regime in this window where it
is the right arm. The R-29 verdict stands: do not ship it.

Caveat kept in view: both days' halves straddle zero for every arm (frozen v10 combined runs
+0.311 → −0.091), so two days remains two days. That is an argument against reading *any* arm's
two-day number as an edge, not a rescue for the candidate — on the same two days it is behind on
every cut.
