# H1 — Task 5: trend-guard reconciliation

**Verdict: the guard is not a stable mechanism. Its apparent benefit peaks exactly at the shipped
parameter and collapses either side of it, and its sign reverses between the two halves of the live
fire set. That is why the 27 h replay said −111 and the live twin says +37: both are true, on
different windows, of a boundary that is fitted to noise. It is live on Tokyo now.**

`retro_trend.py` is not in the repo, so I could not re-run V's exact replay. Instead I applied the
guard rule **directly to twin A's own fires**, using A's own `candles` table for the trend — which is
the same operation the replay performs, on the live v11 path. 155 EF fires, 151 with 9 prior candles
available, 09-09 21:10 → 09-10 13:15. PnL at $10 from A's quoted prices with the 2% fee.

## The guard does help on A's full fire set — at 20 bps

| group at 20 bps / 9 candles | n | record | PnL |
|---|---|---|---|
| against the lean (guard acts) | 25 | 11/14 (44%) | **−49.6** |
| with the lean | 32 | 17/15 (53%) | −2.5 |
| neutral (\|move\| ≤ 20) | 94 | 50/44 (53%) | −19.4 |
| **A total** | 151 | | **−71.5** |

Blocking the against-the-lean group takes A from −71.5 to **−21.9**, a +49.6 improvement. Taken
alone this corroborates the live twin and contradicts the replay. It does not survive either check
below.

## Check 1 — the sign reverses between halves

| half | all fires | against-lean group | guarded total |
|---|---|---|---|
| **H1** | n=75, **+42.7** | n=11, 7/4, **+21.0** | +21.7 |
| **H2** | n=76, **−114.2** | n=14, 4/10, **−70.6** | −43.6 |

**In the first half the guard removes a *winning* group** (7/4, +21.0) and costs 21 points. In the
second half it removes a losing one and saves 70.6. The entire measured benefit is H2. By the
ledger's own both-halves clause the guard fails on its own mechanism, not merely on its PnL.

## Check 2 — the benefit peaks at the shipped parameter and inverts below it

| threshold | against-lean n | **against-lean PnL** | with-lean n | with-lean PnL |
|---|---|---|---|---|
| 5 bps | 51 | **+25.9** | 63 | −31.0 |
| 10 bps | 40 | −4.0 | 54 | **−64.8** |
| 15 bps | 32 | −40.4 | 47 | −45.6 |
| **20 bps (shipped)** | 25 | **−49.6** | 32 | −2.5 |
| 25 bps | 16 | −15.4 | 22 | −45.4 |
| 30 bps | 10 | −16.4 | 16 | −23.8 |
| 40 bps | 9 | −6.4 | 10 | −20.1 |

Read the middle column down. The premise of the guard is "fires against the recent lean lose". At
**5 bps that group is the best performer on the board (+25.9)**. At 10 bps it is break-even while
the *with-the-lean* group is the big loser (−64.8) — the premise exactly inverted. The claim is only
true in a narrow band, and the maximum benefit falls precisely on 20 bps, the value that shipped.

A real mechanism degrades gracefully as you move its threshold. This one spikes at the chosen value
and reverses sign twice. **That is the signature of a boundary fitted to noise.**

## The reconciliation

The replay and the live twin are not in conflict once you see the surface they are sampling. On a
27 h window the boundary lands one way (−111); on this 14 h window it lands the other (+49.6). Both
are measurements of an unstable statistic. Combined with **Task 4** — where B's +37.7 edge over A
decomposes into +9.3 blocking, +13.4 from five side flips, and **+15.0 of pure fill noise on
identical calls** — there is no stable trend-guard effect in evidence at this sample size. The
disagreement never needed a mechanism explanation; it needed a robustness check.

## What I would do

Not my call, and V holds the lanes. But stated plainly: **I would revert the guard rather than wait
for the 17:23 verdict.** The 150-graded verdict tests PnL and halves on B's realised fires, which
carry the fill-noise term from Task 4 and sit on the same unstable boundary — so it can pass for
reasons that have nothing to do with the guard working. The threshold sweep above is a cheaper and
harder test, and the guard fails it. Tokyo's equity was 17.07 at apply, already under the 18 floor,
so the downside of leaving a noise-fitted rule running is not symmetric with the upside.

If V prefers to let it run to 17:23, the honest reading of a pass would be "did not fail", not
"confirmed" — and the revert rule already covers the fail case.

## Sample sizes and caveats

151 A fires with trend available; the against-the-lean group is 25 fires at 20 bps (11 and 14 in the
halves) — small, which is itself part of the finding. Trend computed as the net open→close move of
the 9 closed candles before the fire's candle, from A's own candles table; V's `retro_trend.py` may
define it differently (e.g. close-to-close, or including the live candle), which could shift the
numbers but not the shape of the threshold sweep. Halves split by fire count. Single twin, one day.
