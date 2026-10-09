# R-18a — the pad grid is not runnable on this data. Here is exactly why, and what to log.

V's brief (the user's idea): grid the submit pad in {−2..+4} counterfactually on real rows, split
rejects into "ask rose" vs "size vanished", cross with fire-second and rv60, and if the best pad
differs by condition then a fitted pad rule is the adaptive frequency the user wants.

I could not run it, and I am not going to run it anyway and label the output a grid. Three
independent reasons, in order of how badly each one kills it.

## 1. The fill model fails its parity gate — 74.1%

A counterfactual pad grid needs a fill model: *would this order have filled at cap + k?* The only
model the data supports is `ask_at_submit ≤ cap`, using the `polybook` 1 s tape at the order's submit
second. Tested against what actually happened on the 92 usable orders (48 filled, 44 rejected):

**63 agree, 22 disagree — 74.1%.**

| failure | n | what it means |
|---|---|---|
| model says FILL, really REJECTED | 14 | the price was there in my snapshot and the order still died |
| model says REJECT, really FILLED | 8 | the book improved inside the second my snapshot cannot see |

Both directions, at similar rates. A size condition does not rescue it — parity is **74.1% at every
threshold from 0 to 5 shares** and *falls* to 71.8% at 10. It cannot be a size problem: median
displayed size is **169 shares** against a median order need of **9.5** (which independently confirms
R-14's "size is not the constraint").

The cause is resolution. Submit round trips are ~210–250 ms; the book moves inside the second that my
snapshot flattens. **A grid built on a fill model that is wrong 26% of the time in both directions
would fabricate fills and rejects at roughly the rate of the effect being measured.** That is the
R-18 lesson applied to myself one step earlier.

## 2. Sample — every cell is insufficient before the grid is even cut

92 usable orders; 44 rejects with a book reading. V's grid is pad(7) × fire-second × rv60. Cells
would hold about **four** rows. Even the coarsest cut I tried is under MIN_CELL:

| ask rose by | n | win% | per $1 (upper bound) | |
|---|---|---|---|---|
| did not rise | 11 | 36.4% | −0.175 | **insufficient** |
| +1..2 ticks | 6 | 16.7% | −0.712 | **insufficient** |
| +3..4 | 4 | 75.0% | +0.467 | **insufficient** |
| +5..9 | 9 | 66.7% | +0.203 | **insufficient** |
| +10 or more | 10 | 80.0% | +0.372 | **insufficient** |
| all rejects | 40 | 55.0% | +0.031 | **insufficient** |

Marked, not read. (These also assume the fill happens, so they are upper bounds twice over.)

## 3. The proposed pad range cannot reach what it is aimed at

The reject split V asked for, which **is** solid:

- **29 of 40 rejects (72%) are "the ask rose"** — the kind a pad could in principle reach.
- **11 (28%) are not** — size, latency or a vanished level. A pad does nothing for these.

But of the 29 risers, **the median rise is 8 ticks and the p90 is 19** (distribution: 1,1,1,2,2,2,3,3,3,4,5,6,7,8,8,8,8,9,9,10,12,12,13,14,16,19,20,23,34). **Only 10 of 29 are inside
+4 ticks.** So the whole {−2..+4} range addresses about a third of the risers — roughly 10 of 44
rejects — and covering the rest means paying 8 to 19 ticks over. On a 0.45 ask an 8-tick pad cuts the
winning payout from +1.137 to +0.825 per $1, a 27% haircut on every win, to chase a minority of
rejects.

## 4. One trap confirmed on the current journal

`plan.quote == plan.pre_submit_quote` on **182 of 191 orders**. These are two fields set from the same
read, exactly as CLAUDE.md records, so neither can serve as an independent submit-time price. Anyone
building slippage or pad analysis from that pair is measuring zero by construction. Confirmed here so
it stays confirmed.

## 5. What to log — the one field that makes this runnable

**An independent book read taken at submit and stamped with the submit timestamp: best ask and
displayed size on the side being bought, read separately from the signal read.** With that, the fill
model becomes an observation rather than an inference and the parity gate can pass. Without it, no
amount of sample fixes reason 1.

Sample is the second blocker and only time fixes it: at the current rate this needs roughly **20–30×
the current order count** before a pad × fire-second × rv60 grid has readable cells.

**Not done, and not to be attempted again on this data.** The reject split (72/28) and the size
finding are the parts worth keeping. On the EV question V attached: I have not touched R-10's modes,
and I would not read an EV sweep off a pad arm that cannot be simulated.
