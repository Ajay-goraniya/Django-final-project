# Every candidate decayed toward zero as the evidence got more honest
H1, 2026-09-11 08:55 UTC. Prompted by V refuting candidate J at its pre-set 100-fire live verdict —
the fifth candidate to die, and the fifth to die the same way.

This is not another candidate. It is the pattern across all of them, and it is the thing that should
govern how any future number on this venue is read.

## The ladder

Five levels of evidence, worst to best:

1. **Wrong grading** — scored against a different venue's resolution.
2. **Stale quote** — fresh price observation, ask forward-filled from up to 5 s earlier.
3. **Honest quote** — ask taken at or after the decision (Task 20's `NEXT`/`STRICT`).
4. **Real fills** — replayed against Tokyo's actual executions.
5. **Live forward test** — decided in advance, graded at a pre-set n.

## Every candidate, at every level it reached

| candidate | wrong grading | stale quote | honest quote | real fills | live forward |
|---|---|---|---|---|---|
| **Task 12a cross-venue** | **+0.44** | — | ~0.00 | — | — |
| **11.2 direction model** | — | **+0.207** | **+0.018** | — | **−0.179** *(16, early)* |
| **Task 16 market prior** | — | **+0.087** | **−0.064** | — | — |
| **Task 18 EF @ Polymarket** | — | **+0.361** | **+0.182** *(h1 negative)* | — | — |
| **Candidate J** | — | **+0.408** | **+0.195** | **+0.153** | **+0.07…+0.12, h2 negative → REFUTED** |

**Not one candidate improved at any step. Every single one fell, and the ones that reached a live
verdict failed it.**

J is the cleanest case because it climbed the whole ladder: **+0.408 → +0.195 → +0.153 → ~+0.10 and
a negative second half.** Roughly a halving at each step toward reality, and then the both-halves
rule killed it at the pre-set sample.

## The discount that follows

On this venue, a **recorded-quote replay number has historically overstated live performance by
roughly 3–4×**, and that is before the both-halves test, which is what actually killed J and would
have killed Task 18's Polymarket claim.

So the working rule I would apply to any future replay result here:

> **Divide a recorded-quote per-fire number by at least 3 before treating it as an expectation, and
> assume the both-halves test is the binding constraint rather than the level.** A replay number is
> a screening device for what to shadow, not an estimate of what you will earn.

## Why the standard checks did not catch this

Each candidate passed the checks that were run on it at the time. The failures were not statistical
sloppiness inside the replay — they were the replay *being the wrong instrument*:

- Task 12a: the labels were a different venue's.
- 11.2 and the prior: the price was one that no longer existed.
- J: nothing was wrong with the replay at all — **it was simply not predictive of the forward
  window.** Honest quote, real fills, correct grading, and it still did not carry.

That last one is the important one. **J is the case where careful methodology produced a number that
was correct about the past and still wrong about the future.** No amount of retrospective rigour
substitutes for a forward test at a pre-committed sample size.

## What this does not say

It does not say the underlying signal work is worthless. The two results that never touched a venue
quote — the **distance premise** (72,863 candles) and its **regime stability** (14,442 held-out
candles, spread 1.5–1.7 pp) — are unaffected by every failure above, because they are statements
about the tape, not about tradeable edge. They remain the only things in this project that have not
been walked back.

The honest summary of the project so far: **we understand the market better than we did, and we have
not yet found anything that makes money at prices we can prove existed.**

## Standing consequence

The 11.2 forward ledger (`task17_forward_11_2.md`) is the only live verdict still open. It is at 16
of 100 fires with an ETA of about **Sun 13 Sep 07:47 UTC**, and it is testing against **+0.018**,
not the retracted +0.266. Given the ladder above, the prior should be that it lands at or below
zero — which is exactly why it was set up with a pre-committed n rather than a running judgement.
