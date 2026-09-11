# The EF flat-bucket edge, tested properly — still not established
H1, 2026-09-11 07:25 UTC. Re-check of the one queued item that had grown enough fills to revisit.
Uses **no venue quote** (EF's own direction vs the kline path), so Task 20's stale-quote artifact
does not touch it. Graded on Tokyo's venue `actual`, the settling source.

## What happened, and why I nearly reported it

At n=120 the claim "EF beats *follow the move already underway* inside the `<1 bps` bucket" was
+3.3pp with a weak second half, and I recorded it as **not established**. Tokyo's fills have since
grown from 256 to 320 EF fills, and that bucket from 120 to **150**. Re-run:

| | edge | halves |
|---|---|---|
| at n=120 | +3.3pp | +5.0 / +1.7 |
| **at n=150** | **+5.3pp** | **+5.3 / +5.3** |

Bigger edge, and **both halves identical to three decimals.** That looks like a finding.

## It is not. Exact McNemar says p = 0.341.

Two rules judged on the *same* candles are a **paired** comparison, so the only informative trades
are the ones where they disagree. Of 150 fires the two rules **agree on 96**. Among the 54
discordant pairs:

- EF right / follow-the-move wrong: **31**
- follow-the-move right / EF wrong: **23**

The entire edge is **31 − 23 = 8 trades.** Exact two-sided McNemar on 54 discordant pairs gives
**p = 0.341**. At this effect size it would take roughly **n = 490 fires** to reach significance —
more than three times what we have, and the bucket accrues at about 47% of EF's fire rate.

**The identical halves were noise, not corroboration.** With 54 discordant pairs total, each half
carries ~27 — far too few for agreement between them to mean anything. My `halves()` check tests
whether the sign is stable; it cannot tell a stable signal from symmetric noise, and here it was
the latter.

## The methodological point worth keeping

**For a rule-vs-rule comparison on shared candles, the raw edge and the halves check both overstate
the evidence.** The right test is McNemar on the discordant pairs, because the ~64% of trades where
the two rules agree carry no information about which is better — they inflate `n` without adding
power. A 150-trade sample was really a 54-trade sample.

This is the second time today a number survived the standard checks and failed a sharper one (the
first being Task 20's quote rule). The pattern in both: **the checks test the shape of the result,
not the thing the result actually depends on.**

## Status

- `<1 bps` EF edge: **not established**, p=0.341, needs ~490 fires. Revisit at that point, not before.
- `2.5–5 bps` cell (EF 47.8% vs a 71.7% null, −23.9pp): **n=46, still under the 60 bar.** It has
  moved 40 → 46 since 02:50 and holds its shape. Still marked, still not read.

Repro: inline in this commit's message; the fire profile is `analysis/h1/task15_part3_fire_profile.py`.
