# Task 21b — the Polymarket paper number, on quotes whose age is actually known
H1, 2026-09-11 20:50 UTC. Asked by V (REQUEST.md 13:30). Script `task21b_certifiable.py`.
**Run the moment n crossed the 60 bar, not before.**

V's v10 runner records `book_age_ms` from 13:28 UTC. Those rows are the first Polymarket paper trades
whose entry price can be certified. Everything earlier is the set that failed `quote_age()` in Task 24.

| set | n | per $1 | hit |
|---|---|---|---|
| **certifiable (quote age known, median 15 ms)** | **61** | **−0.062** | 45.9% |
| uncertifiable (before 13:28) | 430 | +0.120 | — |

Halves of the certifiable set: −0.013 / −0.108. `verify.py` PASSES it — quote age, sample size and
both halves — so this is a readable number, and it is **negative**.

## The honest caveat, stated before the conclusion
These are not like-for-like. The certifiable rows are **one ~7-hour evening window**; the +0.120 spans
several days. The drop from +0.120 to −0.062 is therefore **not proven** to be the quote age — it
could be this evening's regime. n=61 in a single window is also not rain-or-sun.

## What has no time confound
Inside the certifiable window, split by the recorded age of the quote the trade actually paid:

| | n | per $1 |
|---|---|---|
| fresh, ≤1 s | 48 | **−0.141** |
| stale, >1 s | 13 | **+0.232** |

**Both cells are under the 60 bar, so neither is read as a result.** But the ordering is the point:
same hours, same model, same venue — and the trades that paid a *stale* quote are the profitable ones,
while the trades that paid a *fresh* quote lose. That is the Task 20 mechanism exactly: the stale
quote is unbiased, the EV filter selects the randomly cheap side of it, and the profit is an artifact
of the measurement rather than of the market. Note also that 21% of the "certifiable" rows are
themselves over a second old (p90 3.6 s, max 9.3 s), so this set is not uniformly fresh either.

By side: UP n=27 +0.032, DOWN n=34 −0.136. Both under the bar, not read. V should keep collecting
before the side-skew question from Task 24 can be answered honestly.

## What this means for the build decision
Task 24 said V's "+0.187, stop testing and build" passed every check except quote age. This is the
result of closing that check, and it goes the wrong way: **on the first 61 trades whose price can be
verified, the Polymarket paper does not make money.**

That is not yet a refutation — one evening, n=61, and a real time confound. It is enough to say the
+0.187 should not be sized on, and the honest number needs another day of `book_age_ms` rows before
it can be called either way. The right next step is more of exactly the data V has started logging,
not more analysis of the old rows.

**This is the fifth candidate on this branch to shrink at the step from recorded evidence to honest
evidence**, and the working rule from the evidence ladder held again: divide a recorded-quote number
by at least 3, and expect both-halves to be the binding constraint.
