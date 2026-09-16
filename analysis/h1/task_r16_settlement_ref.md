# R-16 — the settlement disagreement is an identity, and the money is in candles that move

V's lead (from the user's review, verified by V on 76 live fills): losses concentrate where the
Binance direction disagrees with the venue settlement — 12 lost that Binance called wins, 2 the
reverse, disagreement 18% vs ~10% base. The brief asks for the venue's price-to-beat so distance to
it can become a feature. Script `analysis/h1/task_r16_settlement_ref.py`.

Data: `venues.outcome` (2,036 candles, independent file, the oracle Polymarket settles on) against
Binance 5-minute klines from `data-api.binance.vision` (api.binance.com is geo-blocked).
Lanes: poly_pnl 1,019, v10_poly_long4 777, v12_poly_lane 463, Zurich live 70.

## 1. The lead reproduces — and it is arithmetic, not signal

The gap is large and it is in every lane: poly_pnl wins **57.9% when the two agree, 27.9% when they
disagree**; v10_long4 56.8 / 28.3; v12 57.6 / 36.7.

But on a disagreement candle, `win` *means* `side ≠ Binance direction`, so the win rate there is
`1 − P(side == Binance)` by construction. Checked:

| | predicted | observed |
|---|---|---|
| win% on disagree = 1 − P(side==bdir \| disagree) | **0.2792** | **0.2792** |
| win% on agree = P(side==bdir \| agree) | **0.5792** | **0.5792** |

Exact to four decimals, both cells. **"Disagreement" carries no information beyond how often the
engine sides with Binance** (0.6006 overall). It is a restatement, not a discovery. The afternoon
9-vs-0 split on 76 live fills is the same identity at n=14.

## 2. There is nothing to log — the two references differ by about one basis point

| \|Binance move\| at close | n | disagree% |
|---|---|---|
| 0–1 bps | 298 | **43.3%** |
| 1–2 bps | 240 | 24.2% |
| 2–5 bps | 567 | 9.7% |
| 5–10 bps | 505 | 2.0% |
| 10–20 bps | 317 | 1.6% |
| 20–50 bps | 99 | 1.0% |

Median |move| when they agree **5.15 bps**; when they disagree **1.00 bps**. The oracles agree
essentially perfectly whenever the candle actually moved. **The venue is not settling on a materially
different price — it is breaking near-ties on a reference that differs by roughly a basis point.**

**Answer to V's question "say exactly what to log":** nothing. A price-to-beat field would record a
number within ~2 bps of the Binance open, and a "distance to settlement reference" feature would be
fitting rounding noise. If V wants the gap measured exactly for its own sake the field is the venue's
reference price at candle open and at close — but it does not become a feature, and I would not spend
logger changes on it.

## 3. What is actually under the lead: near-tie candles bleed, moving candles pay

Splitting every lane on |close move| — this is the real structure the disagreement was pointing at:

| lane | cell | n | win% | per $1 | total |
|---|---|---|---|---|---|
| poly_pnl | ALL | 1019 | 53.4% | +0.141 | +144.01 |
| poly_pnl | **near-tie <2 bps** | 284 | **41.5%** | **−0.144** | **−40.92** |
| poly_pnl | 2–5 bps | 312 | 51.0% | +0.101 | +31.57 |
| poly_pnl | **moved ≥5 bps** | 423 | **63.1%** | **+0.363** | **+153.36** |
| v10_long4 | near-tie / moved | 238 / 290 | 40.3 / 62.4% | −0.174 / +0.319 | −41.34 / +92.64 |
| v12_lane | near-tie / moved | 158 / 156 | 46.2 / 59.0% | −0.049 / +0.276 | −7.79 / +43.00 |

Near-tie win rate 118/284 = 0.4155, **two-sided binomial vs a coin p = 0.0052** — the engine is
*worse than chance* there. Subset control: 2,000 random 284-row subsets average +0.1401 per $1;
**P(random ≤ near-tie) < 0.0001**, so this is a real partition, not any 284 rows.

**Rain or sun, and this is the part that decides it:**

| day | n near-tie | per $1 | n moved | per $1 |
|---|---|---|---|---|
| 09-10 | 30 | −0.366 | 129 | +0.242 |
| 09-11 | 38 | −0.457 | 132 | +0.132 |
| 09-12 | 71 | −0.016 | 77 | +0.252 |
| 09-13 | 54 | +0.029 | 63 | +0.219 |
| 09-14 | 30 | −0.021 | 116 | +0.373 |

The **moved** cell is positive on **8 of 8 readable days** (+0.132 to +0.467). The near-tie bleed is
**two days**: it was −0.37/−0.46 on 09-10/09-11 and has been −0.02 to +0.03 since. Halves −0.364 /
−0.001. So "near-ties lose money" is a description of 09-10 and 09-11, not a standing property.

verify.py on the near-tie cell: `sample` PASS, `halves` PASS (same sign), `null` PASS, `costs` FAIL —
but that FAIL is not meaningful here: `costs()` asks whether a claimed *profit* survives slippage, and
adding cost to an already-negative cell can only make it more negative. Recorded, not read.

## 4. Verdict

1. **V's lead is closed: it is an identity.** No retrain, no feature, no logger change follows from it.
2. **The durable fact is the other one:** the engine's entire edge lives in candles that move, and
   that cell is positive every readable day at +0.36/$1 on n=423.
3. **It is not yet a lever, and it is not a gate.** "Near-tie" is a property of the *close*; a live
   engine cannot see it. What it can see is |move so far|, and that barely predicts it:
   `corr(|move so far|, |move at close|) = 0.4319`, and conditioning on |move so far| < 1 bps lifts
   `P(|close move| < 2 bps)` only from **0.279 to 0.335**. That ceiling is why this does not become a
   threshold on rv60 or a fire filter — the standing rule bans the gate, and the data does not
   support one anyway.

This fits R-13 rather than contradicting it: if `p ≈ p_venue`, then on a candle heading nowhere the
book is near 0.50, the engine has no edge to capture, and it pays the spread for the privilege.
