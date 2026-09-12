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
