# Polymarket migration research (Task 19, standing)
H1. Research only — nothing built before v12. Updated 2026-09-11 05:30 UTC.
V's summary lives in `learner/NOTES_polymarket.md`; this file is the evidence behind it.

---

## 1. Resolution mechanics — **we cannot grade Polymarket research from klines**

Polymarket's BTC 5-min markets settle on a Chainlink 60-s TWAP, not the Binance close. V asked how
close a 1-s-kline TWAP gets. **Not close enough.** All candidate rules fixed in advance, all
reported, 708 candles:

| candidate rule | agreement with Polymarket's outcome | disagreements |
|---|---|---|
| A `close >= open` (the engine's rule) | 89.7% | 73 |
| B `TWAP60_end >= open` | 91.2% | 62 |
| C `TWAP60_end >= TWAP60_start` | 87.0% | 92 |
| **E `last30_mean >= open`** | **91.4%** | **61** |

**The best kline proxy gets 91.4%, against 89.5% for simply using the engine's own actual.** A
1.9-point improvement. Either way **~9% of candles would be mislabelled**, and the disagreements
concentrate exactly where it hurts: median |close−open| of **1.47 bps vs 5.53 bps overall** — the
flat candles, which is where marginal trades live.

**Conclusion: any Polymarket study must grade on Polymarket's own `outcome` table.** A kline TWAP is
not a usable substitute, and building one would reintroduce the Task 14 error in a new place.

## 2. Fees — **an inconsistency between two official sources, unresolved**

Formula, consistent everywhere: **`fee = shares × feeRate × p × (1 − p)`**, **makers pay nothing**,
takers only. Symmetric about 0.50 — a trade at 30¢ costs the same as one at 70¢.
Per $1 staked at ask `p`: `shares = 1/p`, so **fee per $1 = feeRate × (1 − p)**.

- [Polymarket docs, Fees](https://docs.polymarket.com/trading/fees) give a table by category with
  **Crypto = 0.07** (Sports 0.05, Finance 0.04, Politics 0.04, Geopolitics 0).
- [Polymarket Help Centre, Trading Fees](https://help.polymarket.com/en/articles/13364478-trading-fees)
  says fees **"peak at 1.56% at 50% probability"**. But `0.07 × 0.5 × 0.5 = 1.75%`. A 1.56% peak
  implies **feeRate = 0.0625**, not 0.07.

**Unresolved.** Our replays used 0.07, the more conservative of the two. If the true rate is 0.0625
we are *overstating* Polymarket costs by ~11% of the fee — which would move Polymarket's numbers
slightly in its favour, not against. **V's `takerBaseFee 1000` from gamma matches neither** (0.07
would be 700 and 0.0625 would be 625 on a 1e-4 scale); I am not going to guess its units. Worth
resolving against a real fill before any migration decision.

## 3. The v10 Polymarket paper run — **weekday-only, exactly like everything else**

From the runner snapshot (`poly_pnl.sqlite3`), graded on Polymarket's own resolution, per $1:

**All trades: n=371, hit 52.8%, +0.133/fire, +49.19 total, median ask 0.45, median fire second 68.**

| split | n | hit | per-$1 |
|---|---|---|---|
| **weekday** | **371** | 52.8% | +0.133 |
| **weekend** | **0** | — | **NO DATA** |
| Tue | 46 *(n<60)* | 63.0% | +0.282 |
| Wed | 136 | 50.7% | +0.078 |
| Thu | 159 | 51.6% | +0.127 |
| Fri | 30 *(n<60)* | 53.3% | +0.179 |
| 00–08 UTC | 115 | 47.8% | **+0.014** |
| 08–16 UTC | 106 | 54.7% | +0.193 |
| 16–24 UTC | 150 | 55.3% | +0.181 |

**The Polymarket evidence has zero weekend coverage too.** The user's weekend question cannot be
answered from this run any more than from the 11.2 replay. Worth stating plainly before a weekend
migration test: *nothing we have measured on either venue includes a weekend.*

The 00–08 UTC block is near flat (+0.014 on n=115) while the two active blocks are ~+0.19. Recorded
as an observation, **not** a rule — it is one window, and a time-of-day switch is exactly the kind of
threshold the user banned.

**Note on the headline number:** V's figure is **+0.148** after the real taker fee; the runner's own
stored `pnl` gives **+0.133** over 371 trades. Close but not identical — different window or a
different fee treatment. Flagging rather than reconciling by assumption; V has the runner.

## 4. Still to gather (needs the API docs, not yet done)

- CLOB auth flow (wallet-derived API credentials), order types, tick size, min size, rate limits,
  websocket channels, how fills and redemption surface — i.e. **what the executor must do that the
  Predict.fun one does not**.
- Historical data endpoints (`prices-history`, `trades`) and how far back they reach — can we build a
  Polymarket-ask history for replay beyond our own collector?
- Published geo/eligibility policy (documentation and ToS as written; no legal interpretation).

---

### Standing caveat for everything on this page

Polymarket's own price is the engine's signal, so **on Polymarket the recorded ask can be gone by
the time an order lands** — worse than on Predict.fun, not better (Task 18). And per Task 20, any
Polymarket replay built on the 5-s collector must use an at-or-after quote rule.

Repro: `analysis/h1/task19_poly_research.py`.
