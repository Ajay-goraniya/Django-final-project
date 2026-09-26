# H1 — Task 7: confidence as a stake modifier (the last remaining form)

**Verdict: better than the on/off gate, still not shippable. And the sharper finding underneath —
the model's confidence does not beat the market's price.**

182 matched v10-runner fires (the set that clears the ≥100 bar), model trained on 71,967 candles
strictly earlier than the first fire. "norm" rescales PnL to the same total capital as the flat book,
so the columns are comparable.

| stake rule | capital | PnL | per-unit | **norm** | h1 | h2 |
|---|---|---|---|---|---|---|
| **FLAT 1.0 (baseline)** | 182.0 | +23.57 | +0.129 | **+23.57** | +13.20 | **+10.37** |
| linear in conf | 100.9 | +14.11 | +0.140 | +25.43 | +8.82 | +5.29 |
| linear, floor 0.25 | 101.0 | +14.13 | +0.140 | +25.46 | +8.78 | +5.35 |
| two-tier 0.5× below 0.50 | 157.5 | +22.18 | +0.141 | +25.63 | +13.89 | +8.29 |
| **two-tier 0.5× below 0.55** | 149.0 | +22.56 | **+0.151** | **+27.56** | +13.63 | +8.93 |
| EDGE = conf − ask | 21.5 | +2.66 | +0.124 | +22.50 | +1.24 | +1.42 |
| EDGE, floor 0.1 | 28.3 | +3.30 | +0.117 | +21.26 | +1.61 | +1.69 |
| EDGE^0.5 | 51.0 | +6.94 | +0.136 | +24.75 | +3.59 | +3.35 |

## 1. The modifier is a real improvement on the gate, and still not enough

The best rule (two-tier, half stake below conf 0.55) lifts per-unit return from +0.129 to +0.151,
about +17%, and normalised PnL from +23.57 to +27.56. **Unlike the on/off gate it does not destroy
PnL** — that part of the pass-2 diagnosis was right, and sizing down beats skipping.

But **+4.0 normalised on a +23.57 base is inside the noise floor** I have been applying all day
(roughly ±17 on twin comparisons; smaller here, but not by enough to call +4 an effect on 182 fires).
And **every single variant makes the second half worse** — flat is +13.20/+10.37, the best modifier
is +13.63/**+8.93**, the linear forms collapse to +5.29. That is the same h1-loaded shape that
sank the on/off gate. Sizing changed the magnitude of the failure, not its structure.

## 2. The finding that actually matters: confidence does not beat the ask

The EDGE rules stake proportionally to `conf − ask` — the model's probability minus the price's
implied one. That is the principled construction, and the one that should win if the model knows
anything the book does not.

**It does not win. Per-unit return is +0.124, slightly *below* flat staking's +0.129.**

And this is not because the edge is absent on paper: median edge is **+0.092**, and **141 of 182
fires show positive edge**. The model says it is getting 9 points of value per fire on average, and
acting on that produces no more per unit of capital than betting flat.

**The book is already pricing what the path model knows.** That is a coherent story with everything
else today: the model's AUC gain over raw sign is real (+0.035 at t=20) but it never changes the
call, and the quantity it improves — ranking — is the quantity the market maker has also priced.

## 3. Where this leaves Task 7

The descriptive half is finished and solid: **P(another crossing) = 45.5% at t=5, 41.7% at t=20,
20.9% at 190** on 72,331 candles; AUC 0.62 / 0.70 / 0.86 at t=20 / 60 / 180; logistic beats a
shallow tree and both beat the prefix table. The user's intuition about multi-reversal candles is
confirmed and quantified.

The prescriptive half has now failed in all three forms tried: **on/off gate** (pass 2, destroys
cheap winners), **entry-price interaction** (the cap is a capital dial, not a PnL dial), and
**stake modifier** (this file — inside noise, second half worse, and no edge over the ask).

I would not try a fourth form on this data. What would change the picture is **new information the
book does not have** — the tree is built from price alone, and the engine already has depth,
imbalance and trade-flow features the market maker may weigh differently. Testing whether path
features add anything *conditional on* the engine's existing feature set is a different and better
question than the one Task 7 has been asking. Worth putting to the user before more effort goes in.

## Caveats

182 fires from one engine, one venue; the model is walk-forward with no leakage but the fire set is
the same one used in pass 2, so this is a new construction on old data, not new evidence. Tokyo's
live fills still cannot enter until 09-10 klines publish. Per-unit figures assume capital is the
binding constraint, which is true here given the equity floor.
