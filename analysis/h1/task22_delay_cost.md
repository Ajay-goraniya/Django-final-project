# Task 22 — what an order delay actually costs, on both venues
H1, 2026-09-11 14:05 UTC. **Asked by the user:** *"check the pollymarket book few miliseconds after
the signal fired? i mean if predict has 300ms delay in order then you check pollymarket book 300ms
later?"* — yes, that is the right correction, and it is answerable. Script `task22_delay_cost.py`.

## The measurement
An EV filter only ever takes a **cheap** print. Task 20's lesson is that quote noise is unbiased on
average but becomes a one-directional cost the moment you condition on cheapness. So the question is
not "how much does the ask move in 300 ms" (answer: nothing, on average) but **"how much does a
cheap print move back in 300 ms"**.

For every 1 Hz book sample, take prints ≥2c below that candle's median for their side, then look at
the same side `lag` seconds later. Sources: `polybook.sqlite3` (25,070 samples, live websocket,
quote age median 8 ms) and `book1s.sqlite3` (Predict.fun, 1 Hz).

| lag | Polymarket | n | Predict.fun | n |
|---|---|---|---|---|
| 1 s | **+0.16c ± 0.02** | 19,492 | **+0.22c ± 0.02** | 30,995 |
| 2 s | +0.34c ± 0.03 | 19,410 | +0.59c ± 0.03 | 30,900 |
| 3 s | +0.52c ± 0.04 | 19,329 | +0.87c ± 0.04 | 30,804 |
| 5 s | +0.88c ± 0.05 | 19,169 | +1.25c ± 0.04 | 30,537 |
| 10 s | +1.69c ± 0.07 | 18,752 | +2.13c ± 0.06 | 29,873 |

Monotone in lag on both venues, both halves agree at every lag, and the mirror control is symmetric:
**rich** prints move the other way by almost exactly the same amount (Polymarket −0.16c at 1 s,
−0.88c at 5 s). Unconditionally the move is +0.00c. That symmetry is the proof it is mean-reverting
quote noise rather than drift — and the reason conditioning is what costs you.

`verify.py`: sample size, both halves and sweep monotonicity PASS on both venues. `grading()` does
not apply — no outcome label enters this measurement.

## What it says about the user's question

**Tokyo's real lag is 236 ms**, not 300: order `delay_ms` median 85 ms (p75 189, p90 798) plus book
age median 151 ms, over 427 real fills. Reversion is linear in lag, so at 236 ms it is

- **Polymarket ≈ 0.04c**
- **Predict.fun ≈ 0.05c**

**The delay is essentially free.** Checking the book 300 ms later, as asked, changes the answer by
about four hundredths of a cent — worth doing for correctness, but it is not where the money went.

**Where it did go: the 5-second collector.** At 5 s the same measurement costs **0.88c (Polymarket)**
and **1.25c (Predict.fun)** — twenty to twenty-five times the real-latency figure. That is the Task 20
artifact, quantified independently and on a far larger sample: my retracted 11.2 replay paid a quote
forward-filled up to 5 s old, and the EV filter selected the randomly cheap ones.

**So the fix is not "use 300 ms".** It is: take the book **at or after the signal second**, which
costs ~0.04c, and never the last sample before it, which costs up to ~1c.

Cross-check for coherence: real crossing on Predict.fun measured on 380 live fills is +0.46c ± 0.09c
(Task 21). Delay explains ~0.05c of that. The other ~0.4c is genuine spread and queue cost, not
latency — consistent, and it means shaving milliseconds off the order path would buy almost nothing.

## The one point that favours Polymarket, with its limit

**Polymarket's book is quieter than Predict.fun's at every lag** — 0.16c vs 0.22c at 1 s, 0.88c vs
1.25c at 5 s, 1.69c vs 2.13c at 10 s. Same direction, same shape, consistently about 30% smaller.
On the same 1-second horizon the ask moves more than 1c on 35.3% of Polymarket samples against 33.4%
on Predict.fun, but more than 5c on 4.7% against 4.9% — so the two have similar small-move churn and
Polymarket has the thinner tail, which is what the conditional number is picking up.

**Limit, and it is a real one:** `polybook.sqlite3` starts at 06:03 UTC today and spans **7 hours of
one weekday**. Both halves of that window agree, but that is within-day agreement — this is **not
rain-or-sun**. It says nothing about the weekend, about US hours, or about a volatile session. Do not
promote "Polymarket's book is quieter" past "true in one 7-hour window, n=19,492" until the logger
has run across a weekend.

## What this does NOT answer
The Polymarket paper's +0.187/$1 is still unverified. Only 48 of its 427 trades fall inside the 1 Hz
book window — **under the 60 bar, so I am not reading it**. Re-pricing +0.187 under the at-or-after
rule needs either more book coverage or the `book_age_ms` column requested from V in Task 21.
