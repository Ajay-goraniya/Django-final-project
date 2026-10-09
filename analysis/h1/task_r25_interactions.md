# R-25 — the representability gap is real. There is nothing on the other side of it. Drop it.

V's diagnosis is architecturally correct: `model_v10` is L2 logistic then isotonic, so it is linear in
`imb5`/`imb20`/`ofi15`/`pos_in_range` and monotone in p, and it cannot express "flow signed by the side
we take". I tested whether closing that gap buys anything. It does not.

**Non-circular construction, stated as the brief requires.** Signing by `sign(p − 0.5)` is banned —
circular, and unusable at fit time since the target appears in its own input. I used two signings,
both from inputs the engine holds *before* the model runs, so neither is feature × own-output:

- **venue-signed** `s_v = sign(p_venue − 0.5)` — by R-13 the side we take is the venue's side on 92%
  of candles, so this is the closest honest proxy for "our side".
- **move-signed** `s_m = sign(move_bps)` — the candle's own direction so far, independent of the venue.

They agree on 75.7% of ticks, so a result driven by one signing would not survive the other.
Four terms per signing: `imb5·s`, `imb20·s`, `ofi15·s`, `(pos_in_range − 0.5)·s`.

## Result — walk-forward by day, 28,141 rows, 7 held-out days

| arm | logloss | Brier | fires | hit% | per $1 | total | max run |
|---|---|---|---|---|---|---|---|
| frozen v10 (live) | **0.4926** | **0.1637** | 856 | 53.2% | +0.143 | **+122.41** | 4 |
| plain 30 | **0.5092** | 0.1707 | 505 | 50.5% | +0.176 | +89.12 | 5 |
| +4 venue-signed | 0.5102 | 0.1713 | 513 | 48.7% | +0.149 | +76.33 | 6 |
| +4 move-signed | 0.5099 | 0.1712 | 488 | 50.2% | +0.182 | +89.00 | 5 |
| +8 both | **0.5116** | 0.1718 | 485 | 49.3% | +0.162 | +78.61 | 5 |

**Every interaction arm has worse logloss than plain 30.** Not neutral — worse, and the +8 arm is
worst. The L2 penalty spends coefficient budget on terms that carry nothing.

verify.py against plain 30, all three arms **NOT A FINDING**:

| arm | per fire | halves | discordant | McNemar p | null |
|---|---|---|---|---|---|
| +4 venue-signed | −0.028 | −0.007 / −0.054 | **26** (11 v 15) | 0.557 | FAIL (76.33 vs 89.12) |
| +4 move-signed | +0.006 | +0.008 / +0.003 | **12** (7 v 5) | 0.774 | FAIL (89.00 vs 89.12) |
| +8 both | −0.014 | −0.007 / −0.020 | **27** (10 v 17) | 0.248 | FAIL (78.61 vs 89.12) |

The discordant counts are the tell: **12 to 27 changed fires out of ~450 shared.** The interactions
barely move the fire set. There is no effect to size, in either direction.

Loss runs (≥3 / ≥5): plain 19/1, venue-signed 17/2, move-signed 13/2, both 17/1. Move-signed cuts the
≥3 count and raises the ≥5 count. **All of these are far under MIN_CELL — marked, not read** — and
R-15 already showed the loss runs sit at chance for an independent-Bernoulli null, so there is no
target here either.

## Verdict

**It does not beat the plain model out of sample, so we drop it, and I am not tuning it into working.**

Worth keeping from this: the gap V identified is genuine, and the prior I recorded before running held.
R-15's lgbm arms — which find interactions of this shape automatically — beat the logistic by +0.0049
logloss on 4.75M rows while moving the direction call by +0.0004 against the momentum null. That was on
the 18-feature store where `imb5`/`imb20`/`ofi15` are masked, so this run was the honest test with them
present. Same answer: the architecture can be enriched, and enriching it changes nothing, because the
direction call is pinned to the venue price (R-13) and not to anything the book-flow features carry.
