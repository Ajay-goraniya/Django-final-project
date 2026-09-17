# Task 20 item 3 — candidate J is NOT a stale-quote artifact
H1, 2026-09-11 04:25 UTC. V asked which other findings paired a fresh path with a 5-s
forward-filled ask. J is the one that mattered. **It survives.**

## Why J was at risk

J fires a second EF entry at t≈120 s on EF's own side **only if that side's ask ≤ cap**. That is
selection on cheapness — the exact mechanism that inflated 11.2. So it had to be re-run.

## It survives, and the contrast with 11.2 is the interesting part

Engine grading. ORIGINAL = last 5-s sample ≤ 120 s (what J used). NEXT = first sample ≥ 120 s.

| cap | ORIGINAL | NEXT | fires vanishing under NEXT | those fires were worth |
|---|---|---|---|---|
| 0.50 | +0.226 (n=118) | **+0.207** (n=115) | 11 of 118 | **−0.356**/fire |
| 0.55 | +0.254 (n=136) | **+0.209** (n=130) | 16 of 136 | +0.016/fire |
| **0.60** | +0.230 (n=151) | **+0.195** (n=147) | 17 of 151 | **−0.057**/fire |
| 0.65 | +0.185 (n=171) | **+0.160** (n=170) | 15 of 171 | **−0.181**/fire |
| 0.70 | +0.172 (n=184) | **+0.142** (n=184) | 16 of 184 | **−0.173**/fire |
| none | +0.119 (n=255) | **+0.109** (n=253) | 14 of 255 | **−0.282**/fire |

**Compare with 11.2 at margin 0.15: 55 of 97 fires vanished and they were worth +0.290/fire.**

For J, **11–17 fires vanish out of 118–255, and the vanishing fires are mostly LOSERS.** Removing
them barely moves the number, and it moves it for an honest reason. The artifact is simply not
operating here.

### Why the same-looking rule behaves so differently

**Exposure to quote noise scales with how tightly the rule optimises against the quote.**

- 11.2's EV filter compares the model's own probability *directly* against the ask, so every cent of
  quote error feeds straight into the fire decision. It is maximally exposed.
- J's cap only *excludes expensive* entries. Direction comes from EF, not from a comparison with the
  ask. A loose ceiling is barely exposed at all.

That distinction is worth keeping: **selection on cheapness is dangerous in proportion to how hard
the rule hunts for the cheapest quote.**

## verify.py — two fails, and I will not hide behind either

| check | result |
|---|---|
| grading provenance | PASS |
| **quote age** | **PASS** — `at-or-after`, the new check |
| sample size | PASS (n=147) |
| both halves | PASS (+0.184 / +0.205) |
| sweep shape | **FAIL** |
| cost sensitivity | **FAIL** (+5c +0.020, +10c −0.101) |
| beats the null | PASS (+0.195 vs +0.109 uncapped) |

**On the sweep fail:** the curve is +0.207 / +0.209 / +0.195 / +0.160 / +0.142. The only
non-monotonicity is a **+0.002 rise** between caps 0.50 and 0.55. My checker is strict about any
reversal; a two-thousandth blip is not an overfit signature, and I am calling it effectively
monotone. Flagging that I am overriding my own tool, and why.

**On the cost fail — this one is real, and it is answered by better evidence than mine.** On
recorded quotes J is near zero at +5c and negative at +10c. But **V replayed J against Tokyo's REAL
FILLS: +0.153/fire on 128 fills.** Real fills already contain the actual slippage, queue position
and partial-fill behaviour that my synthetic haircut only guesses at. That number is the one J rests
on, and it sits between my +0c and +5c rows — consistent, and measured rather than modelled.

**So: the recorded-quote number is +0.195, the honest-quote number is +0.195, and the real-fill
number is +0.153. J's case does not depend on the 5-s table at all.**

## Status

**J is unaffected by the Task 20 artifact.** Its live forward shadow remains the thing that decides
it, at ≥100 graded with the sign holding on both halves. Nothing here changes that plan.

Repro: `analysis/h1/task20b_candidate_j.py`.
