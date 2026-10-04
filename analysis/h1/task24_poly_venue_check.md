# Task 24 — checking "the venue IS the finding, stop testing and build" (V, 5f96d1e)
H1, 2026-09-11 13:55 UTC. Not requested; run because the conclusion is *build the live executor*, and
a live-money call gets the gate. Script `task24_poly_venue_check.py`.

**Summary: the core claim mostly survives, one supporting argument does not, and one of my own
objections was wrong. It still fails the single check that has caught every false finding here.**

---

## 1. The gate

| check | result |
|---|---|
| grading provenance | **PASS** — Polymarket trades settle on Polymarket's oracle, and the paper's own labels match the `outcome` table on 429/429. The right source is being used. |
| sample size | **PASS** — 429 fires; UP 189, DOWN 240, every cell over 60 |
| both halves | **PASS** — +0.099 / +0.147 |
| cost sensitivity | **PASS** — +0c: +0.123 · +0.5c: +0.110 · +1c: +0.097 · +2c: +0.072 |
| beats the null | **PASS** — +0.123 vs V's always-buy-the-cheap-side −0.276 |
| **quote age** | **FAIL** — only 23 of 427 paper asks match the collector at the same second |

**Verdict: NOT A FINDING — on one check.** Everything else is clean, and it is clean by a wide
margin. This is not the shape of the four candidates that died on the evidence ladder.

Note my per-fire on all 429 trades is **+0.123**, not the +0.187 in your note — different window or
subset. Worth reconciling before either number is quoted onward.

**Why a haircut does not fix it.** Cost sensitivity says a 2c haircut still leaves +0.072, which
looks like it settles the matter. It does not. Task 20's lesson was that the honest quote rule does
not merely shift prices — it **removes fires**: 55 of 97 vanished, and those were worth +0.290/fire.
A flat haircut prices the trades that survive; it cannot price the trades that were never available.
Only re-running the filter on at-or-after quotes answers it, which is exactly what your new
`book_age_ms` column makes possible. At ~2 fires/hour that is hours away, not days.

## 2. "204 candles Predict.fun's book never offered it at all" — not supported

The collector has a Predict.fun quote on **every single candle Polymarket fired on** (429 of 429;
0 with no Predict.fun quote). On the candles where only Polymarket's paper fired, Predict.fun quotes
are present **100%** of the time.

So the extra candles are not opportunities Predict.fun's book failed to offer. They are candles where
Predict.fun's book **was there and the filter declined it** — because the price was worse. That is a
real difference and it may well still be worth money, but it is a *pricing* difference, not an
*availability* one. Which matters, because pricing is precisely the thing the quote-age check says we
cannot yet certify. The availability framing makes the finding look independent of the open question;
it is not.

(My fire counts differ from yours — 429 poly against 672 on the Predict.fun side — so I am matching a
different Predict.fun runner than your 303. The 429/429 coverage result does not depend on that.)

## 3. The strict-vs-broad tension: the rule says take the strict one

Your note: matched on candle AND side AND decisions within 5 s, n=80, the venues are level
(+0.3078 vs +0.3027); on the broad 225 shared candles Polymarket leads by +0.052; *"the narrow test
is the stricter one; the broad one is the one with the money in it."*

Choosing the broad cell because it is the one with the money in it is the "never the best cell" rule,
and n=80 is above the 60 bar so the strict test is readable. Also: a subset comparison on
non-shared candles is not a rule-vs-rule test — it needs `paired()`, exactly as you said about your
own yes/no split in Task 22. Until that exists, **level** is the defensible reading of the matched
evidence and +0.052 is not.

## 4. Where I was wrong — this part supports you

On the 1 Hz loggers, matched second by second (n=43,552 samples, both halves stable):

| | poly − pred | poly cheaper |
|---|---|---|
| **UP ask** | **−3.33c ± 0.12** | 57% |
| **DOWN ask** | **+2.62c ± 0.12** | 41% |

I expected the UP discount to be fair value for a different settlement rule. **It is not.** On the
same 808 candles Predict.fun settles UP 48.6% of the time and Polymarket 48.5% — a −0.1 pp
difference. The two venues resolve UP at the same rate, so a 3.3c cheaper UP ask is not being paid
for with a lower win probability. That is a genuine, large, stable price difference in your favour.

**But it is side-dependent, and that is new:** Polymarket is cheaper on UP and *dearer* on DOWN by
almost as much. The venue is not uniformly better — it is better on one side. The paper's mix is
44% UP / 56% DOWN, and per $1 it earns +0.162 on UP against +0.092 on DOWN, consistent with the price
skew. An executor built on this should know it is harvesting a **side-skew**, not a flat venue edge,
and should expect the advantage to move with the side mix the model happens to produce.

## 5. What I would do

Not "stop testing and build" and not "keep testing". Build the executor **and** close the one open
check in parallel — they do not block each other:
- the executor needs writing either way, and nothing about it depends on the answer;
- the go/no-go on *switching real money* needs the at-or-after re-run, which your `book_age_ms`
  column now makes possible and which costs hours, not days;
- when it lands, report it with the side split (UP/DOWN separately), since section 4 says the two
  sides are not the same trade.

If the at-or-after number comes back near +0.10 with both halves positive, this is the first thing on
this branch to reach a live verdict without falling — and it would deserve the money.
