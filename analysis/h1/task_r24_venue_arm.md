# R-24 — the venue-price arm does not survive. Do not ship it to live money. Run the paper twin.

V built it as a json option (12.13.0, `p_source`, `model_venue.json`) on the user's "test and ship".
This is the half that decides live money, and the answer is **no, not yet**.

## 1. The decay is not the book tightening — it is the win rate collapsing

| day | n | win% | mean ask | per $1 | spread | p_venue − ask |
|---|---|---|---|---|---|---|
| 09-09 | 77 | **62.3%** | 0.387 | +0.573 | 0.01 | +0.2318 |
| 09-10 | 89 | 56.2% | 0.388 | +0.400 | 0.02 | +0.2319 |
| 09-11 | 83 | **61.4%** | 0.390 | +0.521 | 0.03 | +0.2273 |
| 09-12 | 80 | **47.5%** | 0.402 | +0.130 | 0.02 | +0.2046 |
| 09-13 | 60 | 46.7% | 0.413 | +0.107 | 0.01 | +0.1801 |
| 09-14 | 87 | 43.7% | 0.385 | +0.096 | 0.02 | +0.2368 |
| 09-15 | 51 | **43.1%** | 0.392 | +0.077 | 0.01 | +0.2237 |

**The price it pays is flat** (ask 0.385–0.413), **the spread is flat** (0.01–0.03), and **the gap it
buys is flat** (p_venue − ask, 0.18–0.24, no trend). V's hypothesis — the book getting faster or
tighter and competing the edge away — **is not what the data shows.**

What moves is accuracy: **62.3% → 43.1%**. The arm's direction call went from well above a coin to
below one, while everything about the price stayed the same.

## 2. verify.py — NOT A FINDING

Venue arm vs frozen v10, +0.155/fire, n=547:

- `sample` **PASS** — 547 fires
- `halves` **FAIL** — **+0.312 / −0.063**, sign flips
- `paired` **FAIL** — 519 discordant, **268 vs 251, exact McNemar p = 0.483**
- `costs` PASS — +0.296 / +0.264 / +0.233 / +0.204 / +0.150 at 0–5 ticks
- `null` PASS — +161.93 vs v10's +145.81

Permutation of the venue price (shuffle `p_venue` across ticks, keep ask and outcome paired): real
+0.2960 vs permuted mean −0.1205, **P(perm ≥ real) = 0.0000**. So `p_venue` is not noise — but that is
the floor, not the bar.

**The split at 09-12, the day the win rate breaks, is the whole result:**

| window | venue arm | frozen v10 (same window) |
|---|---|---|
| 09-08 … 09-11 | n=266, win **59.4%**, **+0.483/$1**, +128.35 | +0.086/$1, +43.67 |
| 09-12 … 09-16 | n=281, win **45.9%**, **+0.119/$1**, +33.58 | **+0.194/$1**, **+102.15** |

**In the recent window v10 beats the venue arm outright — +0.194 against +0.119, $102 against $34.**
The entire headline advantage is the first four days. And the arm's recent win rate of 45.9% is
**binomial p = 0.19 against a coin**: its direction call is currently indistinguishable from chance,
and it makes money only by buying cheap.

## 3. What it is not firing on — it drops winners, not losers

| set | n | win% | per $1 | total | mean ask |
|---|---|---|---|---|---|
| v10 only (dropped by the arm) | 500 | **58.0%** | +0.091 | **+45.46** | 0.515 |
| both | 533 | 48.8% | +0.188 | +100.36 | 0.398 |
| venue arm only | 14 | — | — | — | **insufficient** |

The arm is a near-subset of v10 (533 of 547 shared). It drops 500 fires that were **more accurate and
still profitable**, keeping the cheap half. That is R-19's cheapness sort again, and it is why the
per-$1 looks better while the total gain is only $16.

## 4. The spec — conditions, not a config

It failed two gates, so there is no shippable threshold to write. What would make it shippable:

1. **The paper twin runs and the recent level holds.** The number to beat is **+0.119/$1** — the
   09-12 onward figure — not +0.296. If the twin returns +0.10 to +0.15 over a fresh week while v10
   returns less on the same candles, that is the evidence this needs.
2. **halves and the paired test pass on the twin's own window**, not on a window containing 09-09.
3. **Live-vs-paper gap to expect: the paper number is an upper bound.** Every fire here is booked at
   the quoted ask; R-18 measured that live fills at a better price win 40.7% against 99.1% for the
   ones that do not fill. The arm buys the cheap half of v10's fires, so it is the *more* exposed
   half. Budget a materially worse live number than paper, not a matching one.

**Verdict: run the twin, do not touch live money.** The result that looked like the session's one
positive is four good days followed by three that v10 wins.
