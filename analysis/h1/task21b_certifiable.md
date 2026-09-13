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

---

# CORRECTION, 2026-09-12 12:50 UTC — n has grown from 61 to 148 and the result has moved.

| certifiable set | n | per $1 | halves | hit |
|---|---|---|---|---|
| as reported 09-11 20:50 | 61 | **−0.062** | −0.013 / −0.108 | 45.9% |
| **now** | **148** | **+0.022** | −0.058 / +0.102 | 49.3% |

**The headline reverses: it is not negative, it is about zero.** `verify.py` now passes quote age and
sample size and **fails only both halves** (sign flip). Still not a finding — but "the Polymarket
paper does not make money on verified quotes" is no longer what the data says, and I said it.

**The part I got wrong, explicitly.** At n=61 I wrote that the fresh/stale split was "the part that
should worry you": fresh (≤1 s, n=48) −0.141 against stale (>1 s, n=13) +0.232, which I presented as
the Task 20 mechanism appearing again. I did mark both cells as under the bar and not read — and then
reasoned from them anyway, which is the same error as reading them. With 148 rows the ordering has
collapsed:

| | then | now |
|---|---|---|
| fresh ≤1 s | −0.141 (n=48) | **+0.015 (n=130)** |
| stale >1 s | +0.232 (n=13) | +0.078 (n=18) |

A 13-row cell moved 15 points and the 48-row cell moved 16. There was no stale-quote effect to see;
there was a small sample. **Retracted.**

**What stands.** The gap between the uncertifiable rows (+0.120, n=430) and the certifiable ones
(+0.022, n=148) is still there and still large — roughly a factor of five. That remains consistent
with recorded-quote optimism, and it is the reason the +0.187 should not be sized on. But the
certifiable number is *flat*, not negative, and the difference could still be the window rather than
the quote age: the certifiable rows are one 23-hour stretch, the +0.120 spans days.

**By side, now that one cell is readable:** DOWN n=93 **+0.019** (readable); UP n=55 +0.028 (under the
bar, not read). Task 24's side-skew prediction — Polymarket cheaper on UP by 3.3c, so UP should earn
more — is **not** visible here yet. Marked, not read, pending the UP cell.

**Bottom line, unchanged in direction, corrected in size:** the honest Polymarket number is about
zero, not the +0.187 of the recorded-quote rows and not the −0.062 I reported yesterday. It fails the
both-halves check. It is not ready to carry real money, and it is no longer evidence that the venue
loses money either.
