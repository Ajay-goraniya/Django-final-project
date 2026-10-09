# R-13 — what the engine actually is

Came out of the user's question *"did you test our live model with the same data?"* and their push
*"it should be a fair comparison so do it."* Both were right, and following them produced the
single most useful result of this sequence. Scripts: `r12b_frozen_on_history.py`, `r12c_fair.py`.

**The live model's direction call is statistically indistinguishable from reading the Polymarket
price, and its EV signal is a book-spread measurement rather than a forecast.**

## 1. The model is the venue price

On the logged window, 32,175 evaluated ticks, graded on `venues.outcome`:

| | direction accuracy |
|---|---|
| frozen v10, all 30 features | 0.7494 |
| null A — "the candle is up so far" | 0.7085 |
| **null B — the venue price alone (`p_venue ≥ 0.5`)** | **0.7496** |

It clears the momentum null at every second bin (+3.4 to +7.1 points) — that part is real. It does
not clear the venue price. The paired test settles it:

- the model and the price **agree on 29,644 of 32,175 candles (92.1%)**
- on the **2,531 where they disagree: model right 1,263, venue right 1,268**
- **exact McNemar p = 0.937**

verify.py: **NOT A FINDING** — halves flip (−0.003/+0.003), paired fails, null fails.

Numerically the same story: `corr(p, p_venue) = 0.9808`, median `|p − p_venue| = 0.028`.
**The model's probability is the venue price plus about three cents of noise.**

## 2. So EV is a spread, not an edge

`EV = p/ask − 1`, and if `p ≈ p_venue` then EV is measuring the ask against the venue's own implied
probability — which is the book spread.

| | |
|---|---|
| `corr(EV_model, EV_from_venue_price)` | **0.9594** |
| **`corr(EV, p_venue − ask)`** | **0.9569** |
| `corr(EV, −ask)` | 0.4738 |

**The engine is a spread-capture strategy wearing a forecasting model's clothes.**

## 3. This retro-explains every negative result in R-3 … R-12

| result | why it happened |
|---|---|
| R-4: EV separates money but it is *price, not accuracy* | EV **is** price |
| R-5: `p` overconfident, Brier 0.2435 vs the venue's 0.2463 | `p` **is** the venue price |
| R-6: calibrating `p` drops profitable fires | recalibrating a price does not improve it |
| R-8/R-9: new features and a stacked brain change nothing | they compete with the venue price, which already dominates |
| R-10: accuracy mode is 86% accurate and earns +$0.31 | buying favourites at the price that made them favourites |
| R-12 B2: history + venue ≈ frozen, dead heat | frozen **is** venue; history adds nothing on top |
| R-3: live book earns +0.004 vs +0.038 quoted | the spread is thin once you actually pay it |

Seven independent negatives, one cause. That is what a correct explanation looks like.

## 4. What this does and does not mean

**It does not mean the system is broken.** A spread-capture strategy is a legitimate thing to run;
it earned +0.131/$1 on paper and +0.004/$1 live. It means the system is **not** what it is modelled
as, and that mis-modelling is where the effort has been going.

**It does mean the direction-model work should stop.** R-6, R-8, R-9 and R-12 all tried to improve
a forecast that is already pinned to the market price — 92% agreement, coin-flip on the rest.
Improving it is not possible in the way those tasks assumed, and the failures were not bad luck.

**Where the edge actually lives, if anywhere:** in execution — which ask you get, how often you are
filled, what the spread is at the moment you submit. R-3 already measured that side: 105 of 108
rejects were FAK-killed because resting size was gone, the ask moves +1.0c against the taker within
one second, and the filled book earns +0.004/$1 against +0.038 quoted. **That gap is the whole
game, and it is an execution problem, not a modelling one.**

## 5. Caveats, stated

- Paper fills at the quoted ask throughout; live is 70 graded fires.
- `p_venue` is an **input** to v10, so the correlation is not a surprise in mechanism — what is new
  is the **magnitude**: it does not merely inform the model, it *is* the model's output.
- One fix to the shared harness fell out of this: `verify.py`'s exact McNemar overflowed at 2,531
  discordant pairs (`comb(2531, k)` does not fit in a float). It now uses the normal approximation
  with continuity correction above 1,000, exact below.
