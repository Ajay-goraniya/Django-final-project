# The EF delay veto, leakage fixed, on both selections — and exported for London

Read-only, Zurich data, London untouched, nothing live. `analysis/zurich/ef_veto.py`, export
`analysis/zurich/ef_veto_brain.json`.

**Headline: the veto works on raw25 and does NOT work on FIXED15, which is the selection London actually
runs.** On raw25 it turns −0.102/$1 into **+0.035** under London execution; on FIXED15 the keep half is
still **−0.097** with halves that flip sign and permutation p=0.287.

## V's leakage fix, and what it changed

`ef_delay_brain.featmat` standardised over **all** rows, so each fold's scaler saw its own test day. Fixed:
the mean/sd is now fitted on that fold's **training rows only** and applied to the test rows.

It changed essentially nothing — raw25 KEEP is +0.201 at the delayed ask both before and after. That is the
expected size of the effect for a mean/sd (it shifts no ranking, only the scale the ridge penalty acts on),
but it was leakage and it is gone.

## (1) Export — `analysis/zurich/ef_veto_brain.json`, 14.7 KB

| field | content |
|---|---|
| `feature_names` | 35, in order: the 32 `decide_log` keys, then `logit_ask`, `logit_p_raw`, `sec_over_300` |
| `folds[]` | 4 folds — test day 09-25/26/27/28, each with `train_days`, `n_train`, training-only `mean`/`sd`, and 36 `weights` |
| `all_days` | one frozen fit on all 35,855 rows (same shape) |
| `exec_model` | the fill/slippage/fee constants used here, so London scores against the same model |
| `intercept_first` | `true` — `weights[0]` is the intercept; standardise with the fold's mean/sd **before** the dot product |

Target is the **+250 ms delayed ask** throughout, which is London's latency. Use the fold whose
`train_days` precede the day being scored, or `all_days` for a single frozen model.

## (2) raw25 — Zurich's selection. The veto works.

263 fires on the 4 scored days.

| cell | n | hit | delayed ask | H1 | H2 | perm p | perm mean | **LONDON** | London total $ |
|---|---|---|---|---|---|---|---|---|---|
| **KEEP (pred ≥ 0)** | **130** | **58.5%** | **+0.201** | +0.167 | +0.236 | **0.000** | −0.030 | **+0.035** | **+27.4** |
| VETO (pred < 0) | 133 | 45.1% | −0.081 | +0.010 | −0.170 | 0.667 | −0.040 | **−0.229** | −188.8 |
| ALL fires | 263 | 51.7% | +0.059 | +0.033 | +0.084 | 0.062 | −0.035 | **−0.102** | −164.3 |

The keep half clears n≥60, both halves positive, permutation p=0.000 (a flip pays the OPPOSITE side's
delayed ask), and — the new part — it is **positive under London execution** where the full set is not.
The vetoed half is −0.229/$1 executed, i.e. the veto removes about $189 of loss on 133 fires.

Per day (delayed / London):

| day | keep n | keep dly | keep LON | veto n | veto dly | veto LON |
|---|---|---|---|---|---|---|
| 09-25 | 55 | +0.160 | **−0.026** | 64 | −0.021 | −0.187 |
| 09-26 | 29 | +0.246 | +0.080 | 33 | −0.079 | −0.202 |
| 09-27 | 40 | +0.354 | +0.195 | 34 | −0.204 | −0.331 |
| 09-28 | 6* | −0.651 | −0.710 | 2* | +0.093 | −0.046 |

**The keep half is London-positive on 2 of 4 days.** 09-25 is slightly negative and 09-28 is a partial day
with 6 fires. So the +0.035 rests on 09-26 and 09-27, and the veto is the consistent part: it is negative
under execution on all four days, which is what a veto needs to be.

## (2b) FIXED15 — London's own selection. The veto does NOT work.

148 fires on the same days (first pass with Platt-calibrated EV ≥ 0.15 taken at **ask + 1 tick**, the
engine's own reference).

| cell | n | hit | delayed ask | H1 | H2 | perm p | **LONDON** | London total $ |
|---|---|---|---|---|---|---|---|---|
| KEEP (pred ≥ 0) | 77 | 51.9% | +0.067 | **−0.166** | **+0.295** | **0.287** | **−0.097** | −45.9 |
| VETO (pred < 0) | 71 | 46.5% | −0.083 | +0.184 | −0.342 | 0.715 | −0.229 | −100.7 |
| ALL fires | 148 | 49.3% | −0.005 | +0.007 | −0.017 | 0.473 | −0.162 | −147.5 |

| day | keep n | keep dly | keep LON | veto n | veto dly | veto LON |
|---|---|---|---|---|---|---|
| 09-25 | 41 | −0.055 | −0.216 | 37 | +0.170 | −0.021 |
| 09-26 | 12* | +0.350 | +0.175 | 16* | −0.330 | −0.434 |
| 09-27 | 20* | +0.256 | +0.083 | 16* | −0.427 | −0.538 |
| 09-28 | 4* | −0.477 | −0.565 | 2* | −0.035 | −0.153 |

Three things kill it here, and they are not sample-size excuses:

1. **The halves flip sign** (−0.166 / +0.295) on n=77, which is above the 60 bar. That is a fail, not a
   thin cell.
2. **Permutation p=0.287.** Coin-flip sides priced at the opposite delayed ask do about as well.
3. **It is still negative under London execution** (−0.097). The veto improves FIXED15 relative to its own
   vetoed half (−0.097 vs −0.229) but does not lift it above zero.
4. On 09-25 — the day with the most fires — the keep half is **worse** than the veto half under execution
   (−0.216 vs −0.021). The ordering inverts on the biggest day.

**Why this is coherent rather than surprising:** FIXED15 already refuses a lot (148 fires against raw25's
263). The easy bad trades are gone before the delay model sees them, so there is much less left for a veto
to remove — and what it does remove on this sample is not reliably the bad half.

## Verdict

1. **On raw25 the veto is the strongest EF result I have**: n130, hit 58.5%, both halves positive,
   permutation p=0.000, and **London-exec +0.035 against −0.102 for the unfiltered set**.
2. **On FIXED15 it fails**, and FIXED15 is what London runs. Halves flip, permutation p=0.287, still
   negative executed, and inverted on the largest day.
3. So the export is worth testing on London's **real fills** — that is exactly what it is for — but the
   honest expectation from this sample is that it will not help a FIXED15 book. If London wants to use it,
   the version with evidence behind it is raw25 + veto, which is a **profile change as well as a gate**.
4. Still thin either way: 4 test days, one of them partial. The exact threshold remains unestablished (the
   sweep in `EF_DELAY_BRAIN.md` is non-monotone) and nothing here should move London on its own.
