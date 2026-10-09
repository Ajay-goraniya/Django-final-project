# Task 20 — the 11.2 replay WAS a stale-quote artifact. Retracted.
H1, 2026-09-11 03:55 UTC. V's charge (REQUEST.md 03:45) is **correct**. This retracts the Task 11.2
headline of +0.266/fire and the "first thing to pass every check" claim that went with it.

## The test

Three quote rules, identical fire logic, identical grading (engine candles), 684 candles:

| rule | quote |
|---|---|
| **ORIGINAL** | last collector sample with `sec ≤ S` — what my replay did. Quote age **median 1 s, p90 3 s** |
| **NEXT** | first sample with `sec ≥ S` — quote at or *after* the price observation |
| **STRICT** | first sample with `sec ≥ S`, **and features recomputed at that sample's own second** — observation and quote at the same instant, no look-ahead anywhere |

## Result

| margin | ORIGINAL | NEXT | STRICT | fires vanishing under STRICT |
|---|---|---|---|---|
| 0.10 | +0.161 (n=184, 61.4%) | **−0.025** | +0.077 (n=145) | 77 of 184, worth +0.178/fire |
| **0.15** | **+0.207** (n=97, 60.8%) | **−0.077** | **+0.018** (n=66, 51.5%) | **55 of 97, worth +0.290/fire** |
| 0.20 | +0.148 (n=60) | **−0.140** | +0.030 *(n=39)* | 36 of 60, worth +0.199/fire |
| 0.25 | +0.133 *(n=38)* | **−0.144** | −0.009 *(n=19)* | 26 of 38, worth +0.316/fire |
| 0.30 | +0.019 *(n=25)* | **−0.167** | −0.017 *(n=13)* | 16 of 25, worth +0.295/fire |

**ORIGINAL is positive at every margin. NEXT is negative at every margin. STRICT is ≈ zero and
drifts negative.** The edge lived entirely in the gap between the two.

**The fires that disappear are the profitable ones.** At margin 0.15, 55 of 97 fires do not exist
once the quote is taken at or after the observation, and those 55 were worth **+0.290/fire** — more
than the headline itself. What remains is +0.018 on 66 fires: nothing.

## The mechanism — and it is not the one I would have guessed

**The stale quote is not systematically cheaper.** NEXT minus ORIGINAL on the UP ask has
**mean −0.0005 and median exactly 0.000**. There is no directional bias in the quote itself.

But the two differ by more than 5 cents on **17.3% of samples**, and **the fire rule selects on
cheapness**: it fires when `p/ask` clears a margin, so among stale quotes it preferentially picks
the ones that happen to be randomly low — prices that were not available at the decision second.
**The bias is in the selection, not in the quote.** An unbiased measurement error becomes a
one-directional profit as soon as you condition on it.

That is why the effect survived every check I ran. Permutation, seed stability, both halves,
monotone sweep and cost sensitivity all test the *signal*; none of them test whether the **price was
real**. My cost sensitivity test added a haircut to an ask that was already fictional.

## What this retracts, and what survives

**RETRACTED:**
- Task 11.2's **+0.266/fire** headline and its "passes every verify.py check" status.
- The claim that the model beats the market prior and the current EF fire set at the ask. Under
  STRICT it beats neither.
- The Task 17.2 forward ledger's baseline. Its 1-of-8 start is no longer a surprise — **it is the
  first honest measurement**, and it agrees with STRICT/NEXT rather than with the replay.

**SURVIVES — the signal is not what failed:**
- Task 15's distance premise (72,863 candles, no venue quotes involved).
- Task 17.3's regime stability — measured on **accuracy**, never on an ask. The direction signal is
  still real and still regime-stable; it simply cannot be monetised at quotes we can prove existed.
- Task 16's naive null (−0.019 at 59.2% accuracy) — that used the same 5-s asks, but it is a
  *negative* result, and the stale-quote selection bias can only have flattered it. It stands a
  fortiori.
- Task 18's conclusion that 11.2 does not transfer to Polymarket — a negative, and now doubly so.

## Standing rule adopted

**The collector's `q` table is 5-second data and must be treated as "quote age unknown, up to 5 s"
in every study from now on.** A replay must state the quote age relative to the decision, and must
never pair a fresh price observation with an earlier quote. `verify.py` now has a `quote_age()`
check that fails a finding when the quote can precede the decision.

`book1s.sqlite3` (1 Hz, both asks, sizes and `age_ms`) is the right source as it accumulates.

Repro: `analysis/h1/task20_stale_quote.py`.
