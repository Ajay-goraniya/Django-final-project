# Task 17.2 — THE VERDICT. The frozen 11.2 model is REFUTED on its own pre-set test.
H1, 2026-09-12 10:50 UTC. Script `task17_verdict.py`. **104 forward fires, the bar was 100.**

## The criteria, set in advance
Registered when the forward window opened and restated at n=95 **before the 100th fire landed**:
**≥100 forward fires, POSITIVE IN BOTH HALVES, and `verify.py` verdict True.** Nothing below chose a
cell, a margin or a window after the fact.

## The result

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | **104** | 48.1% | **−0.040** | −4.16 |
| first half | 52 | — | −0.214 | −11.11 |
| second half | 52 | — | **+0.134** | +6.95 |

`verify.py`: quote age **PASS** (at-or-after rule), sample size **PASS** (104), **both halves FAIL**
(sign flips −0.214 → +0.134), **beats-the-null FAIL** (−0.040 against the +0.018 honest-rule replay
it was tested against).

## Verdict: REFUTED
It fails on two of the four checks, and on the one that has decided every candidate on this branch:
the halves disagree in sign. The level is also below the baseline it was measured against. This is the
same outcome as candidate J, at the same pre-set bar, for the same reason.

**What is NOT the right reading.** The second half is +0.134 and the whole thing is drifting upward
(−0.330 at n=25 → −0.040 at n=104). It is tempting to call that "improving" and extend the test. That
would be moving the goalpost after seeing the ball: the bar was 100 fires and both halves, the test
has run, and a rule that only passes if you keep looking is not a rule. The upward drift is recorded
as an observation, not a reprieve.

**The honest lesson about the early numbers.** At n=8 this ledger read −0.734/fire with p=0.0054; at
n=25, −0.330 with p=0.039. Both looked like strong evidence of a badly broken model and both were
noise — the p-value walked 0.0054 → 0.039 → 0.063 → 0.049 → 0.035 → 0.054 → 0.058 → 0.067 → 0.074 →
0.133 → 0.146 → 0.184 → 0.154 → 0.088 → 0.143 → 0.126 → 0.133 → 0.274. Refusing to read it early was
right in both directions: it would have produced a false "catastrophic" verdict as easily as a false
positive one.

## The weekday/weekend split — buckets defined in advance, still not readable

| | n | per-fire |
|---|---|---|
| weekday | 57 | −0.177 |
| weekend | **47** | **+0.126** |

**The weekend cell is under the 60 bar, so it is marked, not read.** It is worth finishing, because
the original replay was Tue–Thu with zero weekend fires, so this is the first weekend evidence this
model has ever had — and because these buckets were defined before the data arrived, so the comparison
is legitimate rather than a regime fished out afterwards. But note what it cannot become: a
weekend-only version of this rule would be a regime switch on a score that has just failed its
overall test, which is exactly what the standing "no gates" rule forbids. If the weekend cell clears
60 and holds positive on both its own halves, that is a *new* hypothesis needing its own forward test,
not a rescue of this one.

## Status
- Ledger row M: **REFUTED at the pre-set 100-fire verdict** (V's ledger already carried it as refuted
  as a replay claim after Task 20; this closes the forward test too).
- The direction signal itself is untouched by this — Task 11.2 found real predictive structure, and
  the distance premise (72,863+ candles) and its regime stability still stand. **What is refuted is
  the monetisation**, for the sixth time on this branch: the market prices the model's side about
  fairly in real time.
- The ledger keeps accruing for the weekend cell only. No new candidate is proposed from it.
