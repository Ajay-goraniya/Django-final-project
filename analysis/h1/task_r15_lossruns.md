# R-15 — the 7–9 loss run does not exist. It is a coin at the observed loss rate.

User (via V, 09-16 00:5x): *"keep working on finding the solution for how the drawdowns can be
stopped"*, framed as **runs of 7–9 same-side losses in one trend**. R-15 (a) exists to give the brain
trend state so it can avoid them. Before building the fix I measured the thing being fixed, against
the running artifact rather than a replay. **The premise does not survive the measurement.**

Data: `poly_pnl` lane, **1,020 graded fires**, the largest graded set on the branch.
Grading verified against an independent file: `poly_pnl.actual` vs `venues.sqlite3 outcome` —
**1,019 agree, 0 disagree, 1 missing**. (Polymarket settles on `venues.outcome`; that is the rule
that has produced fake edges in both directions here, so it is checked, not assumed.)

## 1. The runs are real — and they are exactly chance

Loss rate 0.4667. Simulating 2,000 independent sequences of the same length at the same rate:

| run length | observed | null mean | null p95 |
|---|---|---|---|
| ≥ 3 | 55 | 55.29 | 65 |
| ≥ 4 | 23 | 25.68 | 33 |
| ≥ 5 | 9 | 11.92 | 17 |
| ≥ 6 | 5 | 5.49 | 9 |
| ≥ 7 | **3** | 2.50 | 5 |
| ≥ 8 | **1** | 1.16 | 3 |
| ≥ 9 | 0 | 0.56 | 2 |

Longest observed run: **8**. Null mean longest run: **8.48**. **P(a pure coin produces a run ≥ 8) =
0.678.** Every observed count sits at or *below* the null expectation except ≥7 (3 vs 2.5), which is
far inside p95 = 5.

**A 7-or-8 long losing run is not a malfunction. It is what 1,020 fires at a 47% loss rate look
like.** If anything this sequence clusters slightly *less* than chance.

## 2. The runs are not same-side, and they are not in a trend

**0 of the 9 runs of ≥ 5 are on one side.** Every one alternates:

| len | window (UTC) | sides | pnl |
|---|---|---|---|
| 7 | 09-09 18:00 → 18:55 | U U U U D U U | −70.00 |
| 8 | 09-10 02:45 → 04:10 | D D D U U D D U | −80.00 |
| 7 | 09-13 17:55 → 18:30 | U U U D D U D | −70.00 |
| 6 | 09-14 07:10 → 07:50 | D D D U D D | −60.00 |
| 6 | 09-15 23:50 → 00:30 | D D U D D D | −60.00 |
| 5 | 09-10 00:45, 09-10 19:50, 09-13 08:00, 09-13 22:25 | all mixed | −50.00 each |

Longest **same-side** loss run anywhere: **4** in poly_pnl (n=1,020), **3** in the live Zurich fills
(n=70), **4** in the 5-day paper replay of frozen v10 (n=756, zero runs ≥5). Under independent sides
(UP share 0.459) a 5-run would be all-one-side 6.7% of the time — 0.6 expected across 9 runs, 0
observed. Even the absence is chance.

Market state during the runs is not a trend either — though n=48 fires here, so this is context, not
a finding: median |streak| 1.5 vs 1.0 elsewhere, |ret_1h| 17.6 vs 14.9 bps, **rv_1h 3.18 vs 3.53**
(lower, not higher). Side-flip rate inside the runs 0.467 vs 0.393 overall, one-sided binomial
**p = 0.193** on 45 transitions — not significant.

## 3. What this means for R-15

**The specific goal "cut the 7–9 same-side loss runs" has no target.** There is no persistence to
remove: the engine is not stubbornly holding one side against a trend, and a trend-state feature
cannot shorten a run that a coin already explains. Building (a) to fix *this* would have been the
fourth attempt at a problem the data does not show — exactly what "don't do unnecessary or unuseful
work, go in a right direction not wrong" is for.

Two things this does **not** say:

1. It does not say the drawdowns are acceptable. They are real — `r12s3_drawdown.md` measured the
   live model **$94.50 under water at the $10 stake** before it made anything. But the drawdown comes
   from the **level of the loss rate (46.7%) and the price paid**, not from clustering. Reducing it
   means winning more often or paying less, not smoothing a sequence.
2. It does not close R-15's feature question. *"Do higher-timeframe state and futures positioning
   carry direction information the 18 features lack?"* is still open on its own merits and the
   walk-forward arms are still running. Only the loss-run justification is withdrawn.

## 4. The feature arm, measured anyway (5 logged days, walk-forward by day)

| bucket | arm | n | hit% | per $1 | max run | ≥5 | ≥7 |
|---|---|---|---|---|---|---|---|
| ALL | frozen v10 (live) | 756 | 52.5% | +0.129 | 4 | 0 | 0 |
| ALL | 8 days, 30 feats | 446 | 51.3% | +0.198 | 4 | 0 | 0 |
| ALL | 8 days, 30 + 16 HTF | 503 | 51.5% | +0.145 | 5 | 2 | 0 |
| TREND \|streak\|≥3 | frozen v10 | 184 | 52.2% | +0.116 | 4 | 0 | 0 |
| TREND \|streak\|≥3 | 8 days, 30 feats | 107 | 50.5% | +0.200 | 4 | 0 | 0 |
| TREND \|streak\|≥3 | 8 days, 30 + 16 HTF | 122 | 53.3% | +0.223 | 4 | 0 | 0 |

`|streak| 5+` is insufficient for all three arms (47 / 26 / 31) and is not read. Full grid including
the `|ret_1h|` terciles and per-day max runs is in `/tmp/claude-0/r15lr.log` and
`analysis/h1/r15_lossruns.py`.

verify.py on the HTF candidate vs frozen v10: **NOT A FINDING** — halves flip (+0.085 / −0.088),
paired 269 discordant 135-vs-134 **McNemar p = 1.000**, and it loses to the null (+73.12 vs +97.70).
The HTF block **adds nothing on the 5 logged days**, and it does not shorten the runs — it lengthens
them slightly (max 5, two runs ≥5, against frozen v10's zero), which on these counts is noise.

The large-sample version — does HTF or futures positioning beat stage-1 across 2019–2026 — is still
building and is reported separately.
