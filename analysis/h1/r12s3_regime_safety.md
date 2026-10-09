# R-12 step 3 — who is safe in *all* regimes? (PnL + average + drawdown together)

User, 09-16 00:5x: *"so after comparing drawdown and pnl and avarge whos safe in all regimes?"*
Script `analysis/h1/r12s3_regime_safety.py`, full output `/tmp/claude-0/r12s3_regime.txt`.
Same four arms, same fires, same grading as `r12s3_full_features.py` / `r12s3_drawdown.md`.

**Buckets were fixed before any result was read** and are the ones already in use here (R-12 stage C,
R-11): rv60 at 0.35 / 0.75; ret60 terciles of this window (−0.3975 / 0.3510); UTC day; hour-of-day in
6 h blocks. All 24 cells per arm are reported. Anything under MIN_CELL=60 fires is `insufficient` and
is not read. Units are $1 of stake per fire; live stake is $10 flat.

**"Safe" needs all three of the user's measures at once**, so a cell passes only if
`per-$1 ≥ 0` **and** `that cell's own max drawdown ≤ that cell's own total PnL` **and** `n ≥ 60`.

## Scorecard over every readable cell

| arm | readable cells | safe | unsafe | which cells fail |
|---|---|---|---|---|
| **8 days, 30 feats** | 18 | **17** | 1 | up/rv<0.35 |
| frozen v10 (live) | 20 | 16 | 4 | **rv>0.75**, flat, flat/rv<0.35, 09-11 |
| 8 days, 30 + p_hist | 19 | 16 | 3 | down/rv<0.35, flat/rv<0.35, 09-12 |
| p_hist alone (18) | 19 | **13** | 6 | flat, flat/rv<0.35, 09-10, 09-12, 09-13, 18-24h |

**Answer: none of them. There is no arm that is safe in every regime.**

## The one cell that matters most

| rv60 > 0.75 (high volatility) | n | per $1 | total | maxDD | safe |
|---|---|---|---|---|---|
| **frozen v10 (live)** | 76 | **−0.096** | **−7.26** | 16.83 | **NO** |
| 8 days, 30 feats | 56 | — | — | — | insufficient |
| 8 days, 30 + p_hist | 61 | +0.214 | +13.05 | 8.43 | yes |
| p_hist alone (18) | 62 | +0.176 | +10.88 | 7.95 | yes |

**The live model is the only arm that loses money in high volatility**, and it is the only arm with a
losing day (09-11, −0.10 over 169 fires). It also carries the largest drawdown in that cell — 16.83,
more than twice its own loss. The flat-trend cells are its other weak spot (flat: +0.065/fire but
maxDD 13.60 against +11.49 total, so it fails on path even while it is positive on level).

## Where each arm is strong, for completeness

| rv60 bucket | live | 8d/30 | 8d/30+p_hist | p_hist alone |
|---|---|---|---|---|
| rv < 0.35 (n 477/267/295/596) | +0.129 | +0.104 | +0.085 | +0.036 |
| rv 0.35–0.75 (n 198/130/124/181) | +0.220 | +0.308 | +0.386 | +0.133 |
| rv > 0.75 (n 76/56/61/62) | **−0.096** | insufficient | +0.214 | +0.176 |

| ret60 bucket | live | 8d/30 | 8d/30+p_hist | p_hist alone |
|---|---|---|---|---|
| down | +0.185 | +0.270 | +0.195 | +0.110 |
| flat | +0.065 **(DD fails)** | +0.098 | +0.092 | +0.007 **(DD fails)** |
| up | +0.126 | +0.141 | +0.236 | +0.093 |

Every arm is positive in all four hour blocks except `p_hist alone` at 18–24h (−0.043, −9.46,
maxDD 20.83).

## Four things that stop this being a ranking

1. **Fewer fires buys apparent safety.** The 8-day arms fire 453 and 480 times against the live
   model's 751. Less exposure means fewer chances to fail a cell *and* smaller per-cell n, which
   pushes marginal cells below the readable bar instead of failing them. `8 days, 30 feats` has the
   best score partly because it has **two fewer readable cells than the live model**.
2. **The cells are not paired.** Each arm fires on its own candles, so "live loses in rv>0.75 and the
   others don't" compares four different sets of trades, not four answers to the same trade.
3. **Five days, one market.** rv>0.75 is n=76 across five days. A regime verdict from one week is a
   description of that week.
4. **The drawdown test is strict by construction.** `maxDD ≤ total` fails any cell that is only mildly
   profitable, which is why `flat` fails for the live model at +0.065/fire. That is deliberate — the
   user asked for drawdown *and* PnL together — but it is a bar, not a discovery.

## What this does and does not license

It does **not** license a volatility gate. The standing rule is explicit: no on/off gates, no stake
modifiers, no thresholds bolted onto a score. A single n=76 cell on five days is precisely the kind of
number that rule exists to stop being turned into a switch.

What it does say, and this is worth carrying: **the live model's weakness is concentrated in high
volatility and flat trend, while its strength is in directional moves.** That is consistent with R-13 —
if the model's call is essentially the venue price, it should struggle exactly where the book is
widest and least informative, which is high rv and no trend.

**Nothing ships.** `p_hist` is still the worst arm here (13/19 safe, worst in flat, only arm negative
in an hour block), which is the third independent direction pointing at the same step-3 verdict.
