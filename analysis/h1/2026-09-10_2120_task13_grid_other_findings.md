# H1 — Task 13 grid for the remaining findings

**Two results that contradict currently-live dials, and one of them contradicts my own earlier
claim. Both need V's attention: the EF ask floor should be regime-conditional, and the REVERSAL
cap's skipped group is not a loser.**

Same fixed buckets as the J grid; trailing-range cut points 31.4 / 48.9 / 76.4 bps from the 252-day
kline set, chosen before looking at outcomes. `+` = both halves same sign positive, `−` = both
negative, `~` = mixed, `*` = under 30 fires.

---

## 1. EF ask floor 0.48 — **NOT unconditional. It should be OFF in fast and choppy tape.**

The floor is right only where the group it **skips** loses money. Skipped group (EF fires quoted
below 0.48), n=289, overall −0.095/fire:

| bucket | per-fire | halves |
|---|---|---|
| 8-h 00-08 (n=78) | −0.063 | ~ |
| 8-h 08-16 (n=141) | −0.078 | − |
| 8-h 16-24 (n=70) | −0.163 | − |
| range Q1 (n=38) | −0.073 | − |
| range Q2 (n=114) | −0.196 | ~ |
| range Q3 (n=95) | −0.134 | ~ |
| **range Q4 busy (n=42)** | **+0.250** | **+** |
| flips 2 (n=118) | −0.191 | ~ |
| flips 3 (n=73) | −0.318 | − |
| **flips 4+ (n=56)** | **+0.296** | **+** |

**In the busiest range quartile and in the choppiest recent history, the fires the floor throws away
are profitable — positive in both halves, on 42 and 56 fires.** Those are real cells, not the
under-30 ones.

The kept group (n=520, +0.055/fire) has its own weak cells: **16-24 block −0.019 negative in both
halves**, and **flips 4+ −0.255 negative in both halves** (n=100).

**Recommended rule:** `EF ask floor ON, except when trailing 12-candle range > 76.4 bps or flips in
the last 6 candles >= 4`. Both are readable at the fire second. Note this is the mirror image of the
J watch-cell: J weakens in Q4 while the floor's skipped group turns profitable there — consistent,
since both say fast tape behaves differently, and it is the one regime signal appearing twice today.

---

## 2. REVERSAL cap 0.60 — **the skipped group MAKES money. I got this wrong earlier.**

Skipped group (REVERSAL quoted above 0.60), n=108: **77% hit, +14.44 total, +0.134/fire, positive in
both halves** (+6.14 / +8.30).

**This reverses my Task 1 finding.** I reported the >0.60 REVERSAL bucket as "42 fires and NEGATIVE
(−2.56)" and used it to argue for the cap. On 108 fires from the fuller snapshots it is positive.
Sample grew, sign flipped — the fourth time today.

The cap is still defensible, but **only as the capital dial I later reframed it as**, not as
"removing losers":

| group | n | hit | per-fire |
|---|---|---|---|
| kept (≤0.60) | 147 | 69% | **+0.646** |
| skipped (>0.60) | 108 | 77% | +0.134 |

The cap concentrates capital in a group earning 4.8× more per unit. It **costs +14.44 of total PnL**
to do it. That is the right trade only while capital is the binding constraint — which it is, with
the equity floor in play — but nobody should believe the skipped fires are losing.

---

## 3. REVERSAL lane itself — strong and close to unconditional

n=255, 73% hit, **+0.429/fire**, both halves (+57.75 / +51.66).

| bucket | per-fire | halves |
|---|---|---|
| 00-08 (n=91) | **+0.961** | + |
| 08-16 (n=65) | −0.002 | ~ |
| 16-24 (n=99) | +0.223 | + |
| range Q1 (n=53) | +0.392 | + |
| range Q2 (n=110) | +0.252 | ~ |
| range Q3 (n=81) | +0.664 | + |
| flips 2 (n=94) | +0.440 | + |
| flips 3 (n=70) | +0.252 | + |
| flips 4+ (n=52) | +0.313 | + |

Only the 08-16 block is flat (−0.002 over 65 fires, mixed halves). Everything else is positive.
**No switch justified; watch the 08-16 block.**

---

## EV scale 1.0 — not done here

It is a twin-vs-twin comparison rather than a rule with an affected group, so it needs the paired
common-ask treatment rather than this grid. Flagging it as the remaining gap in the Task 13 table.

## Caveats

Fires pooled across the twins and the v10 engine, so candles are shared and cells are not fully
independent. Trailing range and flips come from the twins' `candles` tables; fires without candle
history are dropped. "Flips" is close-to-close direction changes over the last 6 closed candles.
Cells under 30 fires are marked and not used for any recommendation.
