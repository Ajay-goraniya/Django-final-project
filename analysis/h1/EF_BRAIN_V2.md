# EF_BRAIN_V2 — context-aware and adaptive calibration. **Nothing beats what is already live.**

Owner (09-23 01:3x): *"more accuracy, more pnl, less drawdowns and adjustable frequency (low
frequency in drawdowns/bad market)"*. No gates — frequency falls only because `p` falls.

`r42_ef_brain_v2.py`. 1,107 venue-graded fires, 9 days, day 1 training-only. **Rule fixed before any
result and never swept: `ev_cal ≥ 0.15`, `ask ≤ 0.60`, stake $5**, `ev = p/cost − 1`,
`cost(q)=q/(1−0.07(1−q))`. Calibrated `p` clamped to ≤ raw `p`, matching the live hook.
Walk-forward: every arm fitted strictly on fires before the test day.

## Headline

| arm | n | right | per $1 | total $ | maxDD $ | longest run |
|---|---|---|---|---|---|---|
| raw p (no calibration) | 1040 | 51.8% | +0.1468 | **+763.31** | 87.71 | 8 |
| **A pooled Platt (LIVE)** | 283 | **58.0%** | **+0.3233** | +457.47 | 43.37 | 6 |
| B context-aware | 299 | 54.2% | +0.2404 | +359.47 | 59.65 | 4 |
| C adaptive N=200 | 350 | 52.0% | +0.2559 | +447.74 | 110.87 | 8 |
| C adaptive N=400 | 322 | 55.3% | +0.3164 | **+509.34** | 51.26 | 6 |
| **C adaptive N=800** | 280 | 57.1% | **+0.3265** | +457.08 | **39.51** | 6 |
| C adaptive N=all | 283 | 58.0% | +0.3233 | +457.47 | 43.37 | 6 |
| D ctx + N=200 | 459 | 51.4% | +0.1817 | +417.00 | 98.72 | 8 |
| D ctx + N=400 | 346 | 53.2% | +0.2416 | +417.98 | 62.70 | 7 |
| D ctx + N=800 | 306 | 53.6% | +0.2345 | +358.72 | 59.65 | 4 |
| D ctx + N=all | 299 | 54.2% | +0.2404 | +359.47 | 59.65 | 4 |

**B fails.** Adding `sec_left`, `rv60`, `|move_bps|`, `p_venue` and `logit(p)×sec_left` makes
accuracy *and* money *and* drawdown worse than plain Platt (54.2% vs 58.0%, +0.240 vs +0.323,
DD 59.65 vs 43.37). More features did not help; they diluted a score that was already the best
single input. **D inherits B's loss at every window.**

**C is neutral at best.** The N sweep on per-$1 — 0.2559, 0.3164, **0.3265**, 0.3233 — and on
maxDD — 110.87, 51.26, **39.51**, 43.37 — both say *more history is better*, flattening once you
pass ~800. `N=800` and `N=all` are within noise of A (+0.3265 vs +0.3233, DD 39.51 vs 43.37) and
`N=all` is *identical* to A by construction. **A rolling window buys nothing; a short one (N=200)
actively hurts — worst drawdown in the table at $110.87.**

**`N=400` is the only cell that beats A on total money** (+$509.34 vs +$457.47) and it does so by
firing 39 more times at a lower per-$1 and a higher drawdown. That is a frequency trade, not a
better brain, and it sits on a non-monotone corner of the sweep.

## `paired()` returned ZERO discordant pairs for every single arm

Every arm — B, C at all four windows, D at all four — **never changes a side**. On shared candles
the outcome is identical by construction; the arms differ only in *which* fires they take. So none
of these is a different brain, they are different fire counts on the same calls. This is the third
time this pattern has appeared in the EF series and it is the single most useful thing to know about
calibrating `p`: under an EV rule, calibration is a frequency dial, not a direction change.

## Adjustable frequency — the arms do respond to bad days

A's 3 worst days: 09-16 (+$2), 09-13 (+$33), 09-15 (+$39). A's 3 best: 09-14 (+$130), 09-10 (+$120),
09-11 (+$88).

| arm | fires/day worst | fires/day best | **worst/best** |
|---|---|---|---|
| A pooled Platt | 27.3 | 61.7 | 0.44 |
| B context-aware | 25.0 | 67.0 | **0.37** |
| C N=200 | 52.7 | 57.3 | **0.92** |
| C N=400 | 43.3 | 59.7 | 0.73 |
| C N=800 | 26.3 | 61.7 | 0.43 |
| D ctx + N=all | 25.0 | 67.0 | **0.37** |

**The mechanism the owner asked for already exists in A**: it fires 0.44× as often on its worst days
as its best, with no gate — purely because `p` falls. B and D push that to 0.37 but lose more
elsewhere than they save. **C N=200 goes the wrong way (0.92)** — a short window chases the recent
tape and keeps firing into bad days, which is exactly why its drawdown is worst.

Day-by-day per-$1 on the hard day (09-16): A **+0.013**, C N=800 +0.004, C N=400 −0.028,
B −0.061, D N=200 −0.116. Only A and C N=800 stay flat.

## The `p = 0.5098` lead — real in that cell, **does not generalise**

First, a structural fact worth more than the lead: **the model emits only 37 distinct `p` values over
1,107 fires.** `p=0.5098` alone occurs 209 times. `p` is a coarse bucket label, not a continuous score.

The cell: `p=0.5098` DOWN, n=209, 41.1% right overall. **After sec 175: n=27, 22.2% right, per-$1
−0.4165.** At or before 175: n=182, 44.0%. B does cut exposure there (fires 4 vs A's 8).

But the general form fails. Within each of the 10 largest `p` buckets, early vs late:

| p | n | ≤175 | >175 | gap |
|---|---|---|---|---|
| 0.5098 | 209 | 44.0% (182) | 22.2% (27) | −21.7pp |
| 0.6776 | 143 | 63.9% (133) | 40.0% (10) | −23.9pp |
| 0.5314 | 96 | 43.4% (83) | 69.2% (13) | **+25.9pp** |
| 0.5438 | 80 | 54.9% (71) | 22.2% (9) | −32.7pp |
| 0.5943 | 55 | 37.0% (46) | 66.7% (9) | **+29.7pp** |

**Every late cell is thin (1–27) and the gaps swing both ways, −32.7pp to +48.1pp.** Pooled over all
ten buckets: ≤175 n=818 51.2% vs >175 n=102 43.1%, gap −8.1pp, **Fisher p = 0.141 — not
significant**. Per-$1 +0.1516 vs +0.0702.

So the 0.5098-late cell is one thin cell among many that scatter in both directions. **Not a finding,
and not something to build on** — which is also why B, the arm designed to exploit exactly this, lost.

## Answer to the four asks

| ask | result |
|---|---|
| more accuracy | **No.** A's 58.0% is the best in the table; B/D are 51–54%. |
| more PnL | **Only by firing more.** Raw p makes +$763 at DD $87.71; A makes +$457 at DD $43.37; C N=400 +$509 at DD $51.26. Nothing raises per-$1 above A. |
| less drawdown | **Marginally.** C N=800 gives $39.51 vs A's $43.37 — inside noise, on n=280 vs 283. |
| adjustable frequency | **Already present in A** (0.44 worst/best, no gate). B/D reach 0.37 but cost more than they save. |

**Recommendation: change nothing.** The live configuration (pooled Platt + fixed 15% EV bar) is the
best arm tested on accuracy and per-$1, and within noise of the best on drawdown. If the owner wants
more total money and will accept the drawdown, `raw p` makes the most (+$763 at DD $87.71) — that is
a stake/frequency decision, not a modelling one.

## Limits

1. All paper at the quoted ask; live has only ever taken 41% of these candles (EF_BRAIN §A).
2. 9 days, 1,107 fires; per-day cells are 20–70 fires and individually thin.
3. No fires later than 09-16 17:10 exist on the branch, so "plus any later graded fires" added none.
4. `p` has 37 distinct values — any calibration of it inherits that granularity.
