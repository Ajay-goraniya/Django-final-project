# H1 — self-check on the REVERSAL entry cap before build 11.2 ships it

**I applied the same robustness test to my own Task 1 finding that I used to kill the trend guard.
It partly fails. The entry cap is a capital-efficiency improvement, not a PnL edge, and one specific
claim I made about it was wrong. Correcting it before the dial is deployed.**

Data: `predict_pnl` REVERSAL lane, freshest snapshot — **113 graded fires**, 77/36 (68%),
**+42.44 @$1**, halves +13.26 / +29.18.

## Threshold sweep

| cap | kept | hit | PnL | **per-fire** | removed | removed record | removed PnL | h1 | h2 |
|---|---|---|---|---|---|---|---|---|---|
| none | 113 | 68% | +42.44 | +0.376 | 0 | — | — | +13.26 | +29.18 |
| 0.80 | 110 | 68% | +43.10 | +0.392 | 3 | 2/1 | −0.67 | +13.11 | +30.00 |
| 0.75 | 108 | 68% | +42.56 | +0.394 | 5 | 4/1 | −0.12 | +12.85 | +29.71 |
| 0.70 | 105 | 67% | **+41.44** | +0.395 | 8 | 7/1 | +1.00 | +12.11 | +29.33 |
| 0.65 | 95 | 66% | **+41.26** | +0.434 | 18 | 14/4 | +1.18 | +13.20 | +28.06 |
| **0.60** | 71 | 70% | **+45.00** | +0.634 | 42 | 27/15 | −2.56 | +15.42 | +29.58 |
| 0.55 | 44 | 77% | **+45.44** | +1.033 | 69 | 43/26 | −3.00 | +14.74 | +30.70 |
| 0.50 | 29 | 79% | +40.16 | +1.385 | 84 | 54/30 | +2.28 | +13.71 | +26.45 |
| 0.45 | 23 | 78% | +35.90 | +1.561 | 90 | 59/31 | +6.54 | +12.58 | +23.32 |

## What I got wrong

In `2026-09-10_1130_task1_task2_results.md` I wrote that the cap *"degrades gracefully either side of
0.60, so it is not a knife-edge fit."* **That is false on 113 fires.** At 0.65 and 0.70 the capped
run is **below baseline** (+41.26, +41.44 vs +42.44), then it spikes at 0.60. On total PnL this is
the same shape I condemned in the trend guard — a non-monotone curve with the benefit sitting on the
chosen value. It is milder (no sign inversion, and the neighbouring 0.55 is also good), but my
"degrades gracefully" claim came from a 110-fire slice where I only checked 0.55/0.60/0.65 and
happened to see three good numbers. I should have swept the whole range then, as I later demanded of
V's guard.

**Total-PnL gain over baseline is at most +3.00 (at 0.55) or +2.56 (at 0.60), on 113 fires.** That
is inside the noise floor I told V to apply to twin comparisons. Treated as a PnL edge, the cap is
not supported.

## What is real, and it is a different claim

**Per-fire PnL is monotone in the cap and rises steeply**: +0.376 → +0.434 → +0.634 → +1.033 →
+1.385 → +1.561. That is smooth, has no spike, and holds all the way down. The price relationship
itself is genuine. The deciles show where it lives:

| entry price | n | hit | PnL | per-fire |
|---|---|---|---|---|
| **0.13-0.35** | 14 | **86%** | **+30.80** | **+2.200** |
| 0.39-0.49 | 14 | 71% | +8.36 | +0.597 |
| 0.49-0.54 | 14 | 79% | +6.50 | +0.464 |
| 0.55-0.58 | 14 | 29% | −7.06 | −0.504 |
| 0.58-0.60 | 14 | 86% | +5.77 | +0.412 |
| 0.60-0.62 | 14 | 50% | −2.81 | −0.200 |
| 0.62-0.66 | 14 | 64% | −0.33 | −0.024 |
| 0.66-0.85 | 15 | 80% | +1.21 | +0.081 |

**73% of the lane's entire PnL comes from the cheapest 14 fires.** Everything above 0.60 is
approximately zero per fire. But note the 0.55-0.58 bucket at 29% and −0.504 — the middle of the
range is not clean, which is why the total-PnL curve wobbles.

## The honest recommendation

**The cap's benefit is capital efficiency, not profit.** At 0.60 it earns the same money (+45.00 vs
+42.44, i.e. the same within noise) from **71 fires instead of 113** — 37% less capital deployed,
37% fewer orders into the thin ~190 s book I measured in the depth check. That is a genuine and
worthwhile reason to ship it, and it is robust because it does not depend on the PnL delta at all.

It is **not** a reason to expect more profit. If build 11.2 ships `rev_max_entry`, I would:

1. Ship it **default off**, as V already has it — correct call.
2. Describe it in the ledger as a **risk/exposure dial, not a PnL dial**, so a flat PnL result is
   not read as failure.
3. Prefer **0.60 over 0.55** despite 0.55's marginally higher total: 0.55 keeps only 44 fires, and
   the fire count matters more than the 0.44 difference.
4. Judge it live on **PnL per fire and per unit of capital**, not total PnL, with the ≥100 kept-fire
   bar still unmet (71 at 0.60).

## Caveats

113 fires, deciles of 14 — small, and the cheapest decile carrying 73% of PnL means the whole
picture rests on ~14 outcomes. One venue, ~41 h. The kline-matched subset in Task 7 pass 2 gave the
same direction (52 kept, 69%, +27.92 vs 87/67%/+24.79), which is reassuring but is a subset of these
same fires, not independent evidence.
