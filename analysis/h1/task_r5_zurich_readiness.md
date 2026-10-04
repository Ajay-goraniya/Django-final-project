# R-5 — Zurich live journals landed: what is in them, and what still blocks pass 2

V pushed `learner/live_backup/zurich_v1.sqlite3.gz` and `zurich_2.sqlite3.gz` at e64b5b7
(09-15 02:29). **The access blocker is resolved.** This note records what the data actually
supports today. It changes no verdict: R-5 still does not ship, stake stays fixed 3.0.

## 1. The schema does carry what R-5 needs

`signals.decision` is JSON with `p`, `ev`, `rv60`, `sec`, `ask`, `breakeven`, `mode`, `fire`,
`features`, and the `ev_gate*` fields. Confirmed on every signal row in both journals. When the
sample arrives, pass 2 can run on real fills without further plumbing.

## 2. The blocker is now SAMPLE SIZE, not access

| journal | build | signals | fills | graded results |
|---|---|---|---|---|
| zurich_v1 | 12.8.9 | 6 | 5 | **5** |
| zurich_2 | 12.8.11 | 1 | 1 | **0** |

**5 graded live fires, against V's threshold of 100.** Nothing here is readable and nothing is
read. The 5 results are −2.87 / −2.88 / −2.87 / −2.87 / +5.31 — recorded only so the next run can
see the starting point, explicitly **not** a number.

## 3. Grading oracle — an open question, flagged not claimed

These are Polymarket fills, so they settle on `venues.outcome`, not on Binance close ≥ open.

- Zurich's `results.actual` matches **its own `candles` close ≥ open on 5/5**.
- Only **2 of the 5** epochs are inside my `venues.sqlite3` snapshot (it ends 09-15 01:10). On
  both, Zurich, Binance and `venues.outcome` all agree.
- Over the 285 candles both oracles cover, they **disagree on 25 (8.8%)**.

So: two agreeing rows at an 8.8% base disagreement rate is roughly a 0.83 chance under the null
that Zurich is Binance-graded. That was no evidence either way — n=2 cannot tell — so it was raised
as an open question for V to settle from the code, not as a claim.

### CLOSED 09-15 02:37 — the grader reads the VENUE's resolution. Verified, not just accepted.

V answered from the running code, and I checked it against the module on the branch rather than
taking the answer on trust. `learner/v12_polymarket/btc_model_v12_polymarket.py`, `grade_loop`
(line ~556): it fetches the Gamma market for the epoch and takes

```python
names=json.loads(mk.get("outcomes")); prices=json.loads(mk.get("outcomePrices"))
w=[n for n,p in zip(names,prices) if str(p)=="1"]
...
actual=w[0].strip().upper(); win=(actual==side)
```

`actual` comes from the venue's own resolved outcome prices. **It never reads `candles`.** That is
`venues.outcome`'s source, so the lane grades on the oracle it settles on and the symmetric rule in
CLAUDE.md is satisfied. (V cited a separate `official_result(m)` at lines 11–20; on the branch copy
the logic is inline in `grade_loop` instead. The substance is identical — different packaging of
the same read, most likely a later revision on the box.)

**Question closed in V's favour. Nothing to fix.** Recorded here so it is not re-derived.

## 4. The live 1-tick pad — this CORRECTS a plausible misreading of R-3

Every live decision carries `ev_gate_pad=1`, i.e. `cap = ask + 0.01`. R-3 §4 priced a +1 tick pad
at **−0.017 per $1** against a filled book earning **+0.004** — which reads like a condemnation of
this build. **It is not, and R-3 said why in its own §4: the order is a marketable limit, so it
fills at the book, not at the cap.** The pad is paid only when the book moves inside the round
trip. The 6 live fills show exactly that:

| fill | ask | cap | filled at | vs ask |
|---|---|---|---|---|
| 00:30 | 0.370 | 0.380 | 0.370 | 0.000 |
| 00:40 | 0.420 | 0.430 | **0.430** | **+0.010** |
| 01:15 | 0.400 | 0.410 | 0.400 | 0.000 |
| 01:30 | 0.370 | 0.380 | 0.370 | 0.000 |
| 01:50 | 0.350 | 0.360 | 0.350 | 0.000 |
| 02:25 | 0.360 | 0.370 | **0.340** | **−0.020** |

**4 of 6 paid nothing, 1 paid the full tick, 1 filled two ticks better than the ask.** Net across
the six: **−0.010**, i.e. the pad has so far been free. n=6 — unreadable, and not read. The
structural point does not depend on n: **R-3's −0.017 was the fully-paid worst case, and this
implementation is not the fully-paid case.** R-3 does not condemn the 1-tick pad as shipped.

## 5. What pass 2 needs

95 more graded live fires. Nothing else.
