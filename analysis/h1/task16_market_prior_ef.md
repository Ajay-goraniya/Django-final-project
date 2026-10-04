# Task 16 — the market-prior EF replay
H1, 2026-09-11 01:32 UTC. V's task (REQUEST.md 01:05). Engine grading throughout
(`candles.close >= open` from the snapshots — never the venues `outcome` table).

648 evaluation candles (venue book × engine candles × kline path). **The prior is walk-forward: it
is estimated on the 72,207 candles that end before the venue window opens, and never sees an
evaluation candle.** Rule exactly as V specified, nothing hand-tuned.

Prior at S=20, P(same side): `<1` 0.527 · `1-2.5` 0.581 · `2.5-5` 0.634 · `5-10` 0.680 ·
`10-25` 0.718 · `25+` 0.774.

## Headline: the prior does NOT beat the model — and neither is established

**Answer to V's question: no, and the data cannot currently say otherwise.** At matched fire counts
the two are inside noise of each other, and the prior rule **fails `verify.py` on sweep shape**.

| EV margin | prior rule | | | model-p rule | | |
|---|---|---|---|---|---|---|
| | n | per-fire | halves | n | per-fire | halves |
| 0.15 | 127 | +0.108 | +14.31 / **−0.64** | 146 | −0.043 | −4.43 / −1.88 |
| 0.20 | **76** | **+0.137** | +7.88 / +2.57 | 124 | +0.018 | +5.17 / −2.96 |
| 0.25 | 40 *(n<60)* | +0.175 | +6.86 / +0.12 | 105 | −0.042 | +0.76 / −5.13 |
| 0.30 | 28 *(n<60)* | +0.288 | +8.24 / −0.18 | **79** | **+0.109** | +5.56 / +3.06 |
| 0.40 | 18 *(n<60)* | +0.104 | +2.62 / −0.75 | 40 *(n<60)* | +0.168 | +6.55 / +0.17 |

At matched fire count — prior at 0.20 (n=76, **+0.137**) against model-p at 0.30 (n=79, **+0.109**) —
the gap is 0.028 per fire on ~77 fires. That is noise, not a result.

`verify.py` on the prior's best readable cell (margin 0.20): grading PASS, sample PASS, halves PASS
(+0.207 / +0.068), null PASS — **sweep FAIL**: the curve runs 0.108 → 0.137 → 0.175 → 0.288 → 0.104,
peaking at an interior point and collapsing. **VERDICT: not a finding.** In fairness the two cells
driving that shape (margins 0.30 and 0.40) are themselves n=28 and n=18, under our bar — so the
honest summary is *insufficient evidence in both directions*, not *refuted*.

**The current EF fire set** on the same candles: n=220, 53.6% hit, **+0.049/fire**, +10.81 total —
but halves of **−0.01 / +10.83**. All of EF's profit on this window is in the second half. That is
its own instability and V should note it.

## The one solid, large-sample result — and it reframes 11.2

**The naive null fires on every candle at S=20, on the side price is already on, at the recorded
ask. It is right 59.2% of the time and it LOSES money: −0.019 per fire over 638 fires, negative in
both halves (−8.51 / −3.42).**

Median ask paid: **0.58**. Being right 59% of the time while paying 58 cents is a losing business
after a 2% fee. This is the clearest quantification yet of the rule we keep restating:

> **Accuracy is not PnL.** The venue prices the favourite approximately fairly, so a direction model
> that is merely *more often right* cannot make money. It has to be right **where the ask is cheap
> relative to the truth.**

That is the constraint 11.2 has to be built against. The prior rule's own profile shows the shape of
the opportunity — at margin 0.25 it puts **18% of its fires in the 5–10 bps band earning +0.93/fire**,
where the current EF fire set puts **1%** — but that cell is ~7 fires and is **not readable**. It is
a direction to test, not a result.

## Limits

- 648 candles, ~2.3 days of venue coverage, one regime. The prior behind it is solid (72,207 candles)
  but the *evaluation* is small, and every margin above 0.20 is under the 60-fire bar.
- Fires are capped at one per candle at the first clearing second, so margins are not independent
  samples of each other — the sweep is a nested family, which is part of why its shape is unstable.
- Liquidity filter: notional ≥ $10 at the recorded ask. No slippage haircut applied; candidate J took
  ~2.5× from recorded quotes to real fills, so treat every per-fire number above as optimistic.
- Grading is the engine's `candles` table. My Binance-derived close disagrees with Tokyo's venue
  `actual` on 2.2% of orders, all under 1 bps; the engine table is the settling source and is used
  here, but the `<1` bucket remains the least trustworthy cell in any of this work.

Repro: `analysis/h1/task16_market_prior_ef.py`.
