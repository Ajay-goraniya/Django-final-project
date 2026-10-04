# Can we act earlier than the makers? The lead, measured three ways

Owner's question via V (NC-10): on winners the maker cancels the ask during the venue's 50 ms taker hold,
so we are late — can we trigger off a feed that moves FIRST?

Read-only. No engine change.

## First, what cannot be answered from the journals, and why

V's brief asked for the lead of perp vs spot vs the Chainlink ref vs the venue ask **in ms** from
`decide_log` and `tape1s`. **Neither source can resolve that**, and this is a hard limit rather than a
missing effort:

- `decide_log` is throttled to **one row per 250 ms** (`_decide_log`, 13.1.1). Its `ts_ms` is
  millisecond-precise, but consecutive samples are 250 ms apart, so a change between them is located to
  ±250 ms — five times coarser than the 50 ms hold the question is about.
- `tape1s` is **1 Hz**.

So the ms-resolution answer had to come from a purpose-built probe, and it did. What the journals *can*
answer is the per-second version, which turns out to be the decisive one.

## 1. How fast the venue reacts — the ms probe (`VENUE_REACTION_MS.md`)

From the 2 h probe: after a Binance move, the favoured side's best ask rises or is pulled at a median of
**128–136 ms** (local-receive; the two venues' clocks cannot be differenced). Within 200 ms on **77–80%**
of moves. Our order path is ~230 ms, so the venue is typically there first.

And from `ASK_LIFETIME_MS.md`: the specific shares at the touch live a median of **10 ms**, with **67.9%**
of best-ask disappearances being **cancellations** rather than trades. That is NC-10 confirmed from the
venue's own stream — the maker pulls, we are not losing a race to other takers.

## 2. What the lead is worth — the per-second measurement, and it has sample

`analysis/zurich/lag_from_books.py` on the recorder's 1 Hz books (post-fix only, from 09-27 03:33; the
earlier rows carried 45 s REST-resync freshness and cannot answer a per-second question). For every
candle-second where the frozen Binance model's EV against the **current recorded ask** ≥ 0.25, buy at that
second and at +1/+2/+3 s. 9.95 h, ETH 101 fires, SOL 98 — **both above 60**.

| delay | ETH ask p50 | ETH ask move | ETH per$1 | ETH $ at best | SOL ask p50 | SOL ask move | SOL per$1 | SOL $ at best |
|---|---|---|---|---|---|---|---|---|
| **0 s** | 0.280 | — | **+0.007** | 13.20 | 0.215 | — | **−0.124** | 4.00 |
| +1 s | 0.310 | **+1.84c** | −0.056 | 15.18 | 0.230 | **+2.09c** | −0.195 | 4.20 |
| +2 s | 0.300 | +2.14c | −0.087 | 17.85 | 0.230 | +2.81c | −0.280 | 4.14 |
| +3 s | 0.310 | +2.29c | −0.129 | 21.16 | 0.235 | +3.41c | −0.297 | 5.16 |

Three things follow, and the second is the one that matters.

1. **The lead is real and it is about one second.** The ask moves **~2 cents against us within 1 s** and
   ~2.3–3.4c by 3 s. Binance does lead the venue print, exactly as ETH_SOL_EF.md argued. Each second of
   delay costs roughly **5–7 points of per$1**.
2. **But at zero delay the rule still does not make money.** ETH is **+0.007** — indistinguishable from
   nothing — and SOL is **−0.124**. So acting earlier is worth something, and it is not worth enough:
   the gap between acting instantly and acting 3 s late is the gap between **0 and −0.13**, not between
   profit and loss. Being first does not rescue a signal that has no edge at the touch.
3. **SOL has no size anyway.** The touch holds **$4.00** at the median, so a $5 stake is depth-limited
   before latency enters the picture. ETH holds $13–21.

## 3. Why "trigger off the leading feed" does not follow

The premise is that some feed moves first and we could fire on it. Two measurements already close that:

- **Phase 1(b), 30 days, 8,351 scored candles per cell:** adding BTC's move to a coin's own move gains
  **0.000 AUC in all 32 cells**, because the moves are already ~0.88 correlated. There is no separate
  leading feed to switch to — the coin's own move already contains it.
- **This file's table:** the coin's own move *is* the leading feed, and acting on it at zero delay yields
  +0.007. The lead has already been harvested by the time the EV test clears.

So the honest answer to the owner's question is: **yes there is a lead, no it is not the problem.** The
~2c/second drift is real and worth removing latency for, but the binding constraint is that the signal at
the touch is worth about zero, and no amount of earliness multiplies zero.

## What would change the answer

A signal whose edge at delay 0 is clearly positive. Then the 5–7 points per second of decay becomes worth
engineering against, and the ms-probe numbers say where the ceiling is: with a 10 ms quote life and 67.9%
cancellations, the realistic route is resting a maker order or sizing to the second level, not a faster
taker path. That is in `ASK_LIFETIME_MS.md` and it has not changed.
