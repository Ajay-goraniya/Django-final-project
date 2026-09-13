# The weekend cell passes the gate — and it is still not a rule
H1, 2026-09-12 14:50 UTC. Follow-up to `task17_verdict.md` (11.2 REFUTED at 104 fires).

The weekday/weekend buckets were **defined before any weekend data existed** (the original replay was
Tue–Thu with zero weekend fires), and I said in advance what would happen if the weekend cell cleared
60: *"that is a NEW hypothesis needing its own forward test, not a rescue of this one."* It has now
cleared 60. Holding to that.

## The full grid — both cells, not the best one

| | n | hit | per-fire | halves |
|---|---|---|---|---|
| **weekend** | **62** | 51.6% | **+0.073** | +0.025 / +0.121 |
| weekday | 57 | 43.9% | −0.177 | −0.257 / −0.099 |
| all | 119 | 47.9% | −0.047 | −0.167 / +0.072 |

`verify.py` on the weekend cell: quote age **PASS**, sample size **PASS** (62), both halves **PASS**,
beats-the-null **PASS** (+0.073 vs +0.018). **Verdict True.**

The weekday cell is **n=57, under the 60 bar, and is not read** — so the honest statement is "the
weekend cell passes", not "weekend beats weekday". The comparison the eye wants to make is not yet
available.

## Why this is not a finding, despite passing every check

**1. It is one weekend.** Every fire in that cell comes from a single Saturday. "Rain or sun" is not
satisfied by one draw of a regime, however many fires it contains — 62 fires from one day is one day.

**2. Its both-halves check is nearly empty.** The halves here are the first and second half of *the
same continuous Saturday*, not two independent weekends. That is the weakest possible version of the
check: it rules out a result driven by one hour, and nothing more. On this branch a halves pass across
a contiguous window has been wrong before (the 09-11 flat-bucket case was "identical to three decimal
places" and still died on McNemar at p=0.341).

**3. Shipping it would be a gate on a refuted score**, which the standing rule forbids: *"no on/off
gates, stake modifiers, or threshold sweeps on a score already known to be weak."* The parent model
failed its own 100-fire test two checks ago. A weekend-only switch is precisely the banned shape, and
four such attempts already failed on 09-10.

**4. The mechanism is unexplained.** There is no reason on the table why this model should work at
weekends and not weekdays. Without one, a calendar split is a label on a subset, not a regime.

## What would make it real — registered now, before more data arrives

A **new** forward test, on this frozen model, weekend fires only:
- **≥100 weekend fires accumulated across at least two SEPARATE weekends**, so the halves can be
  weekend-vs-weekend rather than morning-vs-afternoon;
- **positive in both halves split by weekend**, not by fire index;
- `verify.py` verdict True;
- and the weekday cell reported alongside it at whatever n it has reached, so the grid stays complete.

Until all four hold, the weekend cell is **marked, not actionable**. The current ledger keeps accruing
and the next weekend supplies the second block. Nothing is proposed for v12 from this.

## Status
- Parent (11.2 overall): **REFUTED**, unchanged.
- Weekend cell: **passes the gate at n=62 on one weekend — recorded, not a finding, not a rule.**
- Weekday cell: n=57, insufficient, not read.

---

# Two hours later: the weekend cell has already failed. 2026-09-12 16:50 UTC.

| weekend cell | n | per-fire | halves | verify.py |
|---|---|---|---|---|
| 14:50 | 62 | +0.073 | +0.025 / +0.121 | **all four PASS** |
| **16:50** | **71** | **+0.004** | **+0.032 / −0.024** | **FAILS both halves and beats-the-null** |

**Nine added fires moved it from "passes every check" to "fails two of them."** It is now flat
(+0.004 against a +0.018 null) with halves of opposite sign.

This is the cleanest vindication of the bar this project has produced. Two hours ago the weekend cell
had 62 fires — over the 60 threshold — a positive level, both halves positive, a clean quote rule and
a `verify.py` verdict of True. Everything a finding is supposed to look like. Had it been shipped on
that basis, it would have been shipped on nine fires' worth of noise.

The four objections registered at 14:50 all still stand, and objection 2 turned out to be the
operative one: the halves were morning-vs-afternoon of one Saturday, which is not a real
out-of-sample split, and it broke the moment the afternoon extended.

**Status: the weekend cell is not a candidate.** The registered test is unchanged — ≥100 weekend fires
across ≥2 separate weekends, halves split by weekend, `verify.py` True, full grid reported — and
nothing that happened today counts toward passing it. The parent verdict (11.2 REFUTED) is untouched.

---

# Closed: the weekend cell reached 100+ fires and landed on zero. 2026-09-13 00:50 UTC.

| weekend cell | n | per-fire | halves | verify.py |
|---|---|---|---|---|
| 14:50 Sat | 62 | +0.073 | +0.025 / +0.121 | all four PASS |
| 16:50 | 71 | +0.004 | +0.032 / −0.024 | fails 2 |
| 18:47 | 81 | −0.021 | — | — |
| 20:47 | 89 | +0.010 | — | — |
| 22:47 | 94 | −0.019 | — | — |
| **00:50 Sun** | **104** | **−0.001** | **+0.098 / −0.100** | **fails both halves and beats-the-null** |

**−0.001 per fire on 104 fires.** Essentially exactly zero, with halves of equal magnitude and
opposite sign. Six readings, oscillating around nothing: +0.073, +0.004, −0.021, +0.010, −0.019,
−0.001.

**This closes the weekend hypothesis on its own merits.** The registered test asked for ≥100 weekend
fires across ≥2 separate weekends; it has the 100 fires but they are all from one weekend, so strictly
the test is not complete. It does not matter: at −0.001 the cell fails on level and on halves
regardless of how many weekends contribute. **There is no reason to wait for next weekend.** Nothing
further is owed to this hypothesis.

Final state of the whole forward test: **all n=161 −0.063 · weekend n=104 −0.001 · weekday n=57 −0.177
(under the bar, not read).** The parent verdict — 11.2 REFUTED — stands, and the calendar split that
briefly looked like a rescue is now measured and is nothing.

**The worked lesson, in one line:** a cell that read +0.073 with every check passing at n=62 was worth
−0.001 at n=104. That is the cost of reading a cell the moment it crosses a threshold, and the value
of the bar being 100 rather than 60.
