# Task 20, continued — Task 16 and Task 18 re-run under the honest quote rule
H1, 2026-09-11 05:00 UTC. Both used an **EV filter** (probability compared directly against the
ask), which Task 20 identified as the maximally exposed shape. Both had to be re-checked.

## A. Task 16's market prior — was also an artifact. The negative gets STRONGER.

Engine grading. ORIGINAL = last 5-s sample ≤ S. NEXT = first sample ≥ S.

| margin | ORIGINAL | NEXT |
|---|---|---|
| 0.10 | +0.111 (n=253, 58.1%) | **−0.042** (n=283, 49.8%) |
| 0.15 | +0.087 (n=135) | **−0.064** (n=171) |
| 0.20 | +0.094 (n=81) | **−0.166** (n=116) |
| 0.25 | +0.169 *(n=42)* | **−0.245** (n=80) |
| 0.30 | +0.243 *(n=29)* | **−0.308** *(n=52)* |

**Positive at every margin under the stale quote; negative at every margin under the honest one.**

Task 16 concluded "insufficient evidence in both directions — the prior neither beats nor loses to
the model". **That was too generous to the prior.** Honestly priced it **loses money at every
margin**, and the loss deepens as the filter tightens — exactly the signature of selecting on quote
noise. The Task 16 headline (the naive null loses money at 59.2% accuracy) is untouched and, if
anything, reinforced.

## B. Task 18's EF-at-Polymarket — survives, but materially weaker. **This corrects what I reported.**

Polymarket asks, 7% taker fee, graded on Polymarket's own resolution.

| margin | ORIGINAL | NEXT | halves (NEXT) |
|---|---|---|---|
| 0.10 | +0.249 (n=104, 59.6%) | **+0.223** (n=67, 62.7%) | **−1.22 / +16.14** |
| 0.15 | +0.361 (n=76) | +0.182 *(n=43)* | −2.55 / +10.36 |
| 0.25 | +0.559 *(n=40)* | +0.184 *(n=24)* | −2.83 / +7.24 |

**Still positive — but the number I reported was +0.281 and the honest number is +0.223 at the only
margin that clears the sample bar, and its first half is NEGATIVE.** All of the profit is in the
second half. That **fails the both-halves check**, which I previously reported as passing.

### The correction

I told V and the user: *"the current EF fire set transfers to Polymarket (+0.281/fire), and does
better there than on Predict.fun (+0.049)."* The honest version:

- **EF at Polymarket: +0.223/fire, n=67, hit 62.7% — but halves −1.22 / +16.14, so it does NOT pass
  both halves.** It is suggestive, not established.
- **The Predict.fun comparison is unaffected.** That number used `ef_v11_ask`, the ask the engine
  itself recorded at fire time — a quote the engine actually saw, not a collector sample. No
  staleness there.
- So the direction of the comparison survives (Polymarket still looks better for EF's signal) but
  **the strength of it does not**, and it should not carry a platform decision on its own.

## What this means for the two conclusions that still stand

1. **11.2 does not transfer to Polymarket** — a negative, and the artifact could only have flattered
   it. Unchanged and now doubly safe.
2. **A Binance-close model is a Predict.fun model** — a structural argument about resolution
   sources, not a PnL claim. Unchanged.

## The pattern across all four re-runs

| rule | shape | stale → honest |
|---|---|---|
| 11.2 direction model | EV filter | **+0.207 → +0.018** (collapses) |
| Task 16 prior | EV filter | **+0.087 → −0.064** (flips negative) |
| Task 18 EF @ poly | EV filter | +0.361 → +0.182 (halves fail) |
| **Candidate J** | **loose cap** | **+0.230 → +0.195** (survives) |

**Every EV-filter rule was inflated. The one rule that only excludes expensive entries was not.**
That is the cleanest statement of the lesson: exposure scales with how hard the rule hunts the
cheapest quote.

Repro: `analysis/h1/task20c_rerun_16_18.py`.
