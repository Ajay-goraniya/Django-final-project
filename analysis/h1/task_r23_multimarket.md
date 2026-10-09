# R-23 — the edge travels without v10. A second market multiplies PnL and barely dents drawdown.

User: *"i need pnl okay and less drawdowns in different markets."* Three questions, data only.

## 1. Does the edge travel? Yes — and v10 is not carrying it

Replay the same EV rule on the same 34,121 BTC ticks with **`p` taken from the venue price alone**,
no v10 anywhere, graded on `venues.outcome`:

| p source | fires | win% | per $1 | total | maxDD |
|---|---|---|---|---|---|
| frozen v10 (live) | 1,033 | 53.2% | +0.141 | +145.81 | 14.09 |
| **venue price alone** | 547 | 52.5% | **+0.296** | **+161.93** | **13.45** |

**The venue price with no model beats the model**: more money on half the fires, at a lower drawdown.
533 of its 547 fires are ones v10 also takes, so this is not a different strategy — it is the same
strategy without the part that was supposed to add value. This is R-13's conclusion turned into a
deployment fact: **a new market needs a venue feed and the EV arithmetic. It does not need a trained
model, a feature pipeline, or 109 months of history.**

**The caveat is not small and must travel with the number.** Halves **+0.493 / +0.100**, and per day:

| 09-09 | 09-10 | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 |
|---|---|---|---|---|---|---|
| +0.573 | +0.400 | +0.521 | +0.130 | +0.107 | +0.096 | +0.077 |

Positive every readable day, but decaying hard and monotonically after 09-11. **Plan with the recent
figure (+0.08 to +0.13), not the +0.296 headline.** Either the spread is tightening as others arrive,
or the first three days were unusual; seven days cannot tell which.

## 2. Correlation — 8 weeks, and this is where the drawdown hope dies

Binance 5-minute klines, **16,129 common candles = 56.0 days (07-22 → 09-16)**, all four symbols:

| vs BTC | direction agreement | corr(return) | corr(\|move\|) | **phi(direction)** |
|---|---|---|---|---|
| ETH | 80.8% | 0.8422 | 0.7838 | **0.6163** |
| SOL | 77.2% | 0.7650 | 0.6847 | **0.5448** |
| XRP | 75.6% | 0.6775 | 0.6053 | **0.5117** |

Every pair agrees 75–81% of the time (ETH-SOL 79.3%, ETH-XRP 77.0%, SOL-XRP 77.8%). There is no
low-correlation corner here — the fourth market is as correlated with the second as with BTC.

**Plainly, as the brief asks: a second market does not halve the drawdown.** Mean phi is **0.558**.

## 3. The arithmetic at 0.558, not at independence

Per-fire std on the venue-price rule is **1.2536** (n=547). At the brief's +0.15/$1, 50 fills/day,
$10 fixed stake:

| N markets | daily mean | daily std | std / mean | vs independent |
|---|---|---|---|---|
| 1 | $75 | $88.65 | 1.182 | — |
| 2 | $150 | $156.46 | 1.043 | **+24.8% wider** |
| 3 | $225 | $223.30 | 0.992 | +45.4% wider |
| 4 | $300 | $289.85 | 0.966 | +63.5% wider |

Risk per dollar of PnL, against one market:

| N | at measured ρ=0.558 | if independent |
|---|---|---|
| 2 | 0.882 — **12% reduction** | 0.707 — 29% |
| 3 | 0.840 — 16% | 0.577 — 42% |
| 4 | 0.817 — **18%** | 0.500 — 50% |

And the number the user actually feels. Worst 3-hour window on the venue-price rule, measured over 55
windows: **−6.00 per $1 = −$60 at the $10 stake.** Scaled:

| N | worst window | daily PnL |
|---|---|---|
| 2 | **−$105.90** | 2× |
| 3 | −$151.14 | 3× |
| 4 | −$196.18 | 4× |

**The bad evening gets absolutely worse in every case.** Four markets turn a −$60 window into −$196.
What improves is only the *ratio*: 18% less risk per dollar earned at N=4.

## 4. Verdict

**Worth building — for PnL, not for drawdown, and the two must not be sold as one thing.**

- **For PnL: yes.** N markets give N× the money for ~0.82–0.88N× the risk, and part 1 says the build
  cost is a venue feed rather than a model. That is the cheapest lever anyone has found in R-3 … R-22.
- **For drawdown: no.** At ρ=0.558 diversification is worth 12% at two markets and 18% at four, and
  the absolute worst window grows every time. If the user's ask is "less drawdown", **a second market
  is the wrong instrument** — it is a scaling lever wearing a diversification label.
- **Which market first: ETH.** Not because it diversifies best — it diversifies *worst* (phi 0.616) —
  but because part 1 shows we are buying liquidity and a lagging book, not a forecast, and ETH is the
  deepest book after BTC. On this evidence pick for liquidity and spread, and treat correlation as a
  cost you cannot avoid rather than a thing to optimise. Mumbai's Task 109 venue-side map (families,
  liquidity, tick, minimum size, one-sided book rate) should decide it over my price-only view.

**Nothing here is a live change.** The decay in part 1 is the open question: if +0.08 is the true
current level rather than +0.30, the case for N markets is a case for N × a small number.
