# H1 — Task 13 ("rain or sun") for candidate J: the t=120 second entry

**Verdict: J looks UNCONDITIONAL. It is ON in both halves in every bucket that has enough fires.
The only hint of weather is high trailing volatility, and it is under-sampled — so I am NOT
proposing a switch. Keep it on everywhere and watch one cell.**

Set: 215 fires (EF's side, t=120, ask ≤ 0.60). Regime buckets defined **before** looking at outcomes;
the trailing-range cut points are the quartiles of the 252-day kline set, fixed in advance:
**31.4 / 48.9 / 76.4 bps.** Full grid below, not the best cell.

## By UTC day

| day | n | hit | PnL | per-fire | h1 | h2 | verdict |
|---|---|---|---|---|---|---|---|
| 09-08 | 17 | 59% | +13.34 | +0.785 | +9.13 | +4.21 | insufficient |
| 09-09 | 77 | 49% | +22.21 | +0.288 | +9.00 | +13.21 | **ON both halves** |
| 09-10 | 121 | 46% | +52.14 | +0.431 | +47.45 | +4.69 | **ON both halves** |

## By 8-hour block

| block | n | hit | PnL | per-fire | h1 | h2 | verdict |
|---|---|---|---|---|---|---|---|
| 00-08 | 66 | 50% | +31.22 | +0.473 | +0.52 | +30.70 | **ON both halves** |
| 08-16 | 77 | 48% | +31.49 | +0.409 | +21.63 | +9.86 | **ON both halves** |
| 16-24 | 72 | 47% | +24.98 | +0.347 | +29.91 | **−4.93** | mixed |

## By trailing 12-candle realised range (quartiles fixed from the 252-day set)

| bucket | n | hit | PnL | **per-fire** | h1 | h2 | verdict |
|---|---|---|---|---|---|---|---|
| Q1 quiet (≤31.4 bps) | 31 | 52% | +16.66 | +0.537 | +6.10 | +10.56 | **ON both halves** |
| Q2 (≤48.9) | 81 | 52% | +46.91 | +0.579 | +34.61 | +12.30 | **ON both halves** |
| Q3 (≤76.4) | 78 | 46% | +28.62 | +0.367 | +7.52 | +21.10 | **ON both halves** |
| **Q4 busy (>76.4)** | **24** | 38% | **−5.58** | **−0.233** | −1.35 | −4.24 | **insufficient** |

## By flips (close-to-close direction changes) in the last 6 closed candles

| bucket | n | hit | PnL | per-fire | h1 | h2 | verdict |
|---|---|---|---|---|---|---|---|
| 0 | 5 | 60% | +7.06 | +1.413 | +0.97 | +6.09 | insufficient |
| 1 | 30 | 53% | +9.69 | +0.323 | +11.06 | −1.37 | mixed |
| 2 | 72 | 42% | +20.22 | +0.281 | +17.75 | +2.47 | **ON both halves** |
| 3 | 66 | 48% | +21.51 | +0.326 | +4.76 | +16.75 | **ON both halves** |
| 4+ | 42 | 55% | +29.20 | +0.695 | +12.59 | +16.61 | **ON both halves** |

Choppier recent history is *better* for J, not worse — the opposite of the intuition, and consistent
with it being a mispricing rather than a trend bet.

## By Polymarket book width at the fire second

| bucket | n | hit | PnL | per-fire | h1 | h2 | verdict |
|---|---|---|---|---|---|---|---|
| tight (≤1.010) | 189 | 47% | +71.35 | +0.377 | +35.95 | +35.39 | **ON both halves** |
| wide (>1.010) | 26 | 58% | +16.34 | +0.629 | +8.51 | +7.83 | insufficient |

## By weekday/weekend

**Unanswerable.** All 215 fires are weekdays — the fire record still does not span a weekend. The
first one available is 09-12/09-13.

## The answer to the user's question

**No weather switch is justified yet.** J is positive in both halves in 9 of the 9 buckets that clear
30 fires. Two cells want watching, and neither is actionable now:

1. **Q4, the busiest trailing range: −0.233 per fire on 24 fires.** This is the only bucket with a
   negative sign in both halves, and it is the one I would expect to be real — a fast tape is where a
   printed 0.36 is least likely to have been takeable, which is also my main staleness worry. But
   **24 fires is below any bar we use** and calling it now would be exactly the trap the user warned
   about. **Watch it; do not switch on it.** If it is still negative at 60+ fires, that becomes the
   rule: *EF2 off when the trailing 12-candle range is above 76.4 bps.*
2. **The 16-24 block's second half (−4.93)** — the block is positive overall (+24.98) and the other
   two blocks are clean, so this is most likely noise.

**Recommended rule line for the autopilot, for now:** `EF2: ON unconditionally` — with the Q4 range
bucket logged separately at every check-in so the switch can be armed the moment it has the sample.

## Caveats

215 fires over three weekdays, all one venue. The trailing-range and flip features are computed from
the twins' `candles` tables, so a fire whose candle history is missing is dropped. "Flips" is
close-to-close direction changes, not crossings of the open — the intra-candle crossing count needs
kline coverage the fire dates do not yet have. Book width is `poly_up + poly_dn` at the fire second,
a proxy for one-sidedness rather than a true depth measure.
