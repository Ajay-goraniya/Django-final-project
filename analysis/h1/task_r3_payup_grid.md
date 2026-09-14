# Task R-3 — does paying up buy fills worth having?

Data: `analysis/h1/r3_submissions.csv`, 189 live submission attempts sent in 3 chat parts by the
AWS session (it cannot push). md5 `970d05b79a424116bec936820152f930`, 17587 bytes, 190 lines,
byte-exact as sent. 2026-09-12T14:15:29Z → 2026-09-14T13:50:53Z. 82 FILLED / 104 REJECTED /
3 UNKNOWN. Script: `analysis/h1/task_r3_payup_grid.py`.

## 0. Venue attribution — done first, because the CSV has no venue column

The project's signature error is grading on the wrong venue's oracle, so the venue was established
from data, not assumed. `pre_submit_quote` against each logger, same side, same second:

| source | median diff | MAD | inside 1c |
|---|---|---|---|
| `polybook.pb` ask (1 Hz, Polymarket) | +0.000 | 0.010 | 52% |
| `book1s.b1` ask (1 Hz, Predict.fun) | −0.100 | 0.100 | 9% |
| `venues.q` `poly_*` (5 s) | +0.000 | 0.030 | 42% |
| `venues.q` `pred_*` (5 s) | −0.050 | 0.080 | 10% |

The two venues' asks differ by a median 6c over 81,148 paired samples, so the test discriminates.
A lag scan over polybook peaks at lag 0 (exact-match count 43 → **59** → 21 at −1/0/+1 s); book1s
shows no peak at all. **These are Polymarket orders**, so they are graded on `venues.outcome` and
pay the 7% Polymarket fee. 183 of 189 rows grade (148 candles).

Provenance check (non-circular): `venues.outcome` vs the Polymarket lanes' own recorded `actual`
— **0/868 disagreements**. For reference, `venues.outcome` vs `candles.actual` disagree on
159/1180 (13.5%), and grading this same set on `candles.actual` would read FILLED +0.387 instead
of +0.038 — a ~10× inflation. That is the error the rule prevents.

## 1. Selection test — do the rejected candles lose more? (asked first, on purpose)

Both sets priced at their own paper price (`pre_submit_quote`), `venues.outcome`, 7% fee:

| set | n | win% | med ask | per $1 |
|---|---|---|---|---|
| FILLED | 78 | 48.7% | 0.450 | **+0.038** |
| REJECTED | 102 | 55.9% | 0.450 | **+0.181** |
| ALL | 183 | 53.6% | 0.450 | +0.134 |

Gap REJECTED − FILLED = **+0.143 per $1** — i.e. the rejected candles looked *better*, not worse.

**This is not a finding.** `verify.py`: grading PASS, sample PASS (both cells ≥ 60), quote-age PASS,
**halves FAIL** — the REJECTED set reads h1 **+0.408** / h2 **−0.046**. The sign flips, so the whole
gap sits in the first half. Verdict: NOT A FINDING.

So the selection test comes back **inconclusive in both directions**: there is no evidence that
paying up buys losses, and no evidence it buys wins. It does not license paying up.

## 2. How far the ask moves after the submission instant

Both loggers are 1 Hz, so **+0.35 s is not resolvable from them and is not reported.** polybook
covers 162 of 189 rows at the submission second (book1s, the Predict.fun control, 159).

| lag | n | median move | mean move | ≥1c against you |
|---|---|---|---|---|
| +1 s | 162 | +0.0100 | +0.0202 | 54% |
| +2 s | 162 | +0.0150 | +0.0298 | 55% |

The ask moves **up** — against the taker — a median full tick within one second, on 54% of rows.

## 3. Pad grid on rejected rows — and why it cannot be read

Fill model, validated first: of FILLED rows with a book sample, **65/67 had ask ≤ cap**. The model
holds on fills. But on rejects it does not explain the rejection:

- **37** rejects had ask > cap — a pad could have bound.
- **56** rejects had ask ≤ cap *already* — the cap was **not** what rejected them (size, latency,
  or a venue-side refusal was).
- 9 had no book sample.

So the pad is only testable on 37 rows, and every cell below is under the 60-fire bar:

| pad | n would-fill | win% | med ask | per $1 | n still not filled |
|---|---|---|---|---|---|
| +1 tick | 4 | 50.0% | 0.470 | −0.016 | 33 |
| +2 | 7 | 57.1% | 0.490 | +0.100 | 30 |
| +3 | 11 | 36.4% | 0.490 | −0.300 | 26 |
| +5 | 16 | 56.2% | 0.500 | −0.007 | 21 |

**INSUFFICIENT — do not read these numbers.** Reported as the whole grid, not a chosen cell.
The non-monotone shape (−0.016 / +0.100 / −0.300 / −0.007) is what noise at n=4–16 looks like.

## 4. The same pad on rows that already filled — this is the part that decides it

A pad changes an already-filled row only through the price paid.

| priced at | n | per $1 |
|---|---|---|
| `avg_fill_price` (what was actually paid) | 78 | **+0.004** |
| +1 tick pad, fully paid | 78 | −0.017 |
| +2 | 78 | −0.037 |
| +3 | 78 | −0.056 |
| +5 | 78 | −0.091 |
| the signed cap itself | 78 | −0.057 |

Median slippage paid vs quoted is +0.000, but the quoted set reads +0.038 and the paid set +0.004:
**the fills already give up ~3.4c per $1 against their own quote.**

## Verdict

**The filled book earns +0.004 per $1. One tick of pad costs ~0.021 per $1.** The margin is five
times smaller than the cheapest pad, so there is no room to pay up — before considering that
60% of rejects were not rejected by the cap at all, that the pad grid is under the sample bar
everywhere, and that the selection test fails its halves check.

No recommendation beyond what the numbers carry: **on this data paying up is not affordable, and
the pad grid cannot be read.** Re-run when the cap-binding reject count passes 60.

Token budget: this report and its script, ~35k.

---

## 5. Why the other 56 rejected — added 09-14 15:0x after AWS sent the reject reasons

AWS sent the census instead of a per-row column, because the string is identical on every reject:

- **105 REJECTED** — all one error: `RequestRejectedError: no orders found to match with FAK order`,
  HTTP 400, `{"phase":"post","request_reached":true}`. The order **reached the matching engine and
  was killed there**; it was not refused locally, and the venue returns no size/price detail.
- 2 UNKNOWN `TimeoutError`, 1 UNKNOWN bare `RequestRejectedError`. 81 FILLED carry no reason.

So the venue gives one undifferentiated answer: nothing rested to match the FAK at submit. Two
candidate mechanisms — **price moved** or **size pulled** — and the 1 Hz book can test both.

**Size is not the discriminator.** Displayed size at the level, over shares needed
(`requested_usdc / pre_submit_quote`), at the submission second:

| set | n | displayed/needed, median | under 1× | under 2× |
|---|---|---|---|---|
| FILLED | 67 | 12.8 | 4% | 12% |
| REJECTED, cap not binding | 58 | 13.2 | 10% | 16% |
| REJECTED, cap binding | 37 | 7.2 | 8% | 19% |

The rejects had ~13× the size they needed, the same as the fills. Size also *grew* over the next
second in both sets (median ×1.35 filled, ×1.54 rejected).

**Price is.** Ask on the traded side, submission second → +1 s:

| set | n | median move | mean | ≥1c against | h1 | h2 |
|---|---|---|---|---|---|---|
| FILLED | 67 | **+0.000** | +0.009 | 48% | +0.000 | +0.010 |
| REJECTED | 93 | **+0.020** | +0.026 | 58% | +0.025 | +0.020 |

Difference of medians +0.020, **label-permutation p = 0.019** over 5,000 draws, same sign in both
halves (+0.025 / +0.010 — each half cell is 33–47, under the 60 bar, so the halves are
directional corroboration only, not a second measurement).

**Reading:** a reject is a candle where the book was moving away inside the ~350 ms round trip.
That is the same phenomenon as §2 seen from the reject side, and it is **diagnostic, not
tradeable** — the +1 s ask is measured *after* the decision, so it can never be an input to one.

It also settles the pay-up question from the other direction: the rejects are not orders that were
priced one tick too low against a stable book. They are orders that arrived after the price had
already gone. A pad chases that, and §4 shows the margin cannot pay for the chase.

`plan.max_shares` was offered and **declined**: the `requested_usdc / quote` proxy above already
shows a ~13× surplus, and no plausible error in the proxy closes a 13× gap.
