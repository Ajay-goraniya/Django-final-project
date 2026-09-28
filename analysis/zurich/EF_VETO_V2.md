# Veto v2 on every raw25 fire — wider sample, and a label I do not trust

Read-only, Zurich data, London untouched, nothing live. `analysis/zurich/ef_veto_v2.py`.

**Bottom line: v2 more than doubles the sample but its label is wrong in the one way that matters, and the
error flatters it. v1's +250 ms numbers remain the ones to use. What survives both labels is the ordering:
KEEP beats VETO with permutation p=0.000 and both halves positive; the threshold sweep is NOT monotone
under either.**

## Sample

Every EF signal across all four journals whose **stored** decision gives raw EV ≥ 0.25, deduped on epoch:
**425 fires on 7 days (09-22..09-28)**, win 53.9%, ask p50 0.40 — against v1's 263 on 4 days. Dropped: 0
duplicate epochs, 168 ungraded, 93 with no usable tape1s ask. Walk-forward scored **311 fires on 5 test
days**. Ridge, same 35 inputs, standardised on training rows only.

## The two-source trap, caught — and then a worse one introduced

The naive label ("our side's tape1s ask at +1 s") charges **+9.82c** against the decision ask. Measured,
not assumed:

| gap | mean | p50 |
|---|---|---|
| tape ask at the **fire second** − decision ask | **+8.88c** | +5.00c |
| one second of repricing, **tape-to-tape** | **+0.95c** | +0.00c |

So 8.9 of the 9.8 cents is `tape1s` (the engine's periodic 1 Hz read) not being the same series as the
executor's decision ask — the artifact `TIMING_TEST.md` already documented, walked into again here. I
rebuilt the label tape-to-tape: `q1 = decision ask + (tape@+1s − tape@fire second)`.

**That fix is wrong for this purpose, and I only found out by reconciling against v1.** In v1 the delayed
ask is a later `decide_log` row's own read, and I verified that `decide_log`'s chosen-side `up_ask`/`dn_ask`
equals its `ask` **exactly, on 100% of 385,345 rows** — so v1 had no source gap. Yet on v1's raw25 set the
+250 ms ask sits **+6.02c above** the decision ask (p50 +3c, p90 +18c), far more than the +0.43c
market-wide drift.

That +6c is **selection, not drift**: EF fires at the first pass where the ask is low enough to clear the
bar, so the fire moment is a selected dip in the engine's own read, and one row later it has reverted. The
winner's curse on the ask *is* the NC-10/NC-13 mechanism. My tape-to-tape label removes the source gap but
also removes that reversion, so it prices a trade London would never get.

| same raw25 set, v1 | per$1 |
|---|---|
| at the decision ask | **+0.193** |
| at the +250 ms ask (reversion included) | **+0.035** |

The −0.158 between those two lines is the thing being measured. v2's label keeps only +0.95c of it.

## v2 results — read as an upper bound, not as London-exec per$1

| cell | n | hit | delayed | H1 | H2 | perm p | LONDON* | total $* | pos days* |
|---|---|---|---|---|---|---|---|---|---|
| **KEEP (pred ≥ 0)** | **191** | **58.1%** | +0.418 | +0.426 | +0.410 | **0.000** | +0.205 | +238.4 | 75% |
| VETO (pred < 0) | 120 | 44.2% | +0.019 | −0.117 | +0.154 | 0.332 | −0.154 | −114.8 | 26% |
| ALL raw25 fires | 311 | 52.7% | +0.264 | +0.223 | +0.305 | 0.000 | +0.063 | +120.7 | 61% |

`*` these columns inherit the optimistic label — do not quote them as London-exec per$1.

Per day (n, delayed, London*):

| day | keep n | keep dly | keep LON* | veto n | veto dly | veto LON* |
|---|---|---|---|---|---|---|
| 09-24 | 51 | +0.440 | +0.227 | 54 | −0.019 | −0.187 |
| 09-25 | 68 | +0.355 | +0.149 | 33 | +0.122 | −0.079 |
| 09-26 | 31 | +0.609 | +0.379 | 13 | −0.175 | −0.308 |
| 09-27 | 35 | +0.539 | +0.344 | 18 | +0.036 | −0.143 |
| 09-28 | 6* | −0.737 | −0.778 | 2* | +0.409 | +0.209 |

KEEP positive on 4/5 days, VETO on 1/5. **The ordering is the durable part**: VETO is worse than KEEP on
4 of 5 days and its halves flip sign (−0.117 / +0.154) with permutation p=0.332, i.e. the vetoed half is
noise-to-negative under either label.

## (2) Sweep of the veto bar — NOT monotone

| keep when pred ≥ | n | hit | delayed | LONDON* | H1 | H2 | perm p |
|---|---|---|---|---|---|---|---|
| −0.10 | 211 | 59.2% | +0.438 | +0.225 | +0.441 | +0.435 | 0.000 |
| −0.05 | 200 | 57.5% | +0.400 | +0.181 | +0.380 | +0.421 | 0.000 |
| **0.00** | 191 | 58.1% | +0.418 | +0.208 | +0.426 | +0.410 | 0.000 |
| +0.05 | 178 | 58.4% | +0.424 | +0.208 | +0.432 | +0.416 | 0.000 |
| +0.10 | 169 | 57.4% | +0.404 | +0.184 | +0.407 | +0.401 | 0.000 |

**Not monotone** (+0.225, +0.181, +0.208, +0.208, +0.184) — it dips at −0.05 and +0.10. Same verdict as v1:
the direction holds everywhere (every bar is positive with perm p=0.000 and both halves positive), the
exact bar is not established. The flatness is actually reassuring in one respect: the result does not hinge
on the threshold, which is what a non-monotone-but-uniformly-positive sweep means.

## (3) Cross-check with the 250 ms brain

On the 206 candles both score: **agreement 58.7%** (both keep 79, both veto 42, disagree 85). v2 keeps
140/206, the 250 ms brain keeps 103/206.

**That is barely better than a coin flip on two models built from the same 35 features.** The labels differ
(+1 s tape-to-tape vs +250 ms same-source), the training sets differ (7 days vs 5), and evidently the
resulting keep/veto decisions are close to independent. So "the veto" is not one stable object yet — two
reasonable implementations of it disagree on 41% of candles.

## Verdict

1. **v2 does not widen the v1 result; it weakens the label.** Use v1's +250 ms numbers (KEEP London
   +0.035 on n130) as the honest level. v2's +0.205 is an upper bound that omits the ask reversion which is
   the entire mechanism.
2. **The wider sample is still worth having** — 425 fires on 7 days confirms KEEP > VETO with perm p=0.000
   and both halves positive, and VETO worse on 4 of 5 days.
3. **58.7% agreement between the two implementations is the most important number here.** Before anything
   goes near London, the two need to be reconciled onto one label — the right one being a *same-source*
   delayed ask that keeps the selection reversion, i.e. v1's construction extended backwards, which needs
   decide_log-grade data for the earlier days and does not exist.
4. Nothing here changes my recommendation: do not move London on this.
