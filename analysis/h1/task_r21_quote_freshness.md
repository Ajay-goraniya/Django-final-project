# R-21 — quote freshness: the mechanism is visible, the decision is not. Closes undecided.

V's brief: 72% of rejects are "the ask rose" with a median rise of 8 ticks (R-18a), which is
implausible as pure movement inside a 250 ms round trip. The engine accepts a book up to
`ev_settings.quote_age_ms` old (Zurich runs 750 ms) and `book_age_ms` is on every fire. Grid it, and
measure the cost of a limit before proposing one.

## 1. Book age is bimodal, not a smooth tail

poly_pnl, 606 fires carrying `book_age_ms`: **p10 1 ms, median 8, p75 37 — then p90 440, p99 8835,
max 9528.** 10.4% of fires are over 250 ms and **9.6% are over 750 ms**. There is a fresh cluster and
a stale cluster with almost nothing between them, so "250 ms" and "750 ms" select nearly the same
rows. A threshold anywhere in that gap is the same threshold.

| book age ms | n | win% | per $1 | total |
|---|---|---|---|---|
| 0–50 | 477 | 50.1% | +0.077 | +36.97 |
| 50–100 | 47 | — | — | **insufficient** |
| 100–250 | 19 | — | — | **insufficient** |
| 250–500 | 3 | — | — | **insufficient** |
| 500–750 | 2 | — | — | **insufficient** |
| 750+ | 58 | — | — | **insufficient** |

Only the fresh bucket is readable.

## 2. V's question — yes, and in the direction suspected

Live Zurich orders, split by what the independent book tape says happened:

| | n | median book age | p90 | share > 250 ms |
|---|---|---|---|---|
| **fills** | 45 | **47 ms** | 149 | **2%** |
| rejects, **ask rose** | 29 | **117 ms** | 317 | **14%** |
| rejects, ask flat | 11 | 99 ms | 179 | 0% |

**Stale quotes are over-represented among "ask rose" rejects — 14% against 2% for fills.** That is
exactly the mechanism V proposed: part of the apparent 8-tick "rise" is not the market moving in
250 ms, it is us having decided against a book that was already old. **But n = 29 and 11, both under
MIN_CELL.** Marked, not read as a measurement.

## 3. The cost, which is the part that kills the change

| limit | refuses | refused per $1 | refused total | keeps | kept per $1 | kept total |
|---|---|---|---|---|---|---|
| 250 ms | 63 (10.4%) | **+0.369** | **+23.22** | 543 | +0.125 | +67.63 |
| 500 ms | 60 (9.9%) | +0.380 | +22.79 | 546 | +0.125 | +68.06 |

**A 250 ms freshness limit would have refused the most profitable cohort in the lane.** The refused
fires earn three times the per-$1 of the ones it keeps. That is precisely the backfire V named.

And that cohort does **not** survive its own reading: n=63 is barely at the bar, halves are
**+0.107 / +0.622** — a fourfold gap, not a stable effect — and **every per-day cell is insufficient**
(16 / 12 / 7 / 16 / 10 / 2). This is the failure the standing rule describes exactly: a halves pass
inside one contiguous window is nearly worthless. So I am not claiming stale quotes are profitable
either. **I am claiming the number that would have to justify the change points the wrong way and
cannot be read.**

## 4. Verdict

**R-21 closes undecided, and nothing ships.** Both sides are below the readable bar:

- the mechanism (stale book → "ask rose" reject) is visible at n=29,
- the cost (refusing the best-paying cohort) is visible at n=63 with no readable day inside it.

A freshness limit is a one-line control change, which makes it cheap to ship and cheap to regret.
On this evidence it would cost ~$23 of paper PnL per 606 fires to chase a fill-rate gain that the
data cannot size. **Do not change `quote_age_ms`.**

What would settle it is the same field R-18a already asked for: **an independent book read at submit,
stamped with the submit timestamp.** With it, "the ask rose" splits cleanly into "the market moved"
and "our quote was old", and the fill-rate side becomes an observation instead of an inference. Until
then this needs roughly 3–5× the current live order count to have readable cells on either side.
