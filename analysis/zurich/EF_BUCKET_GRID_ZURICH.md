# EF bucket grid — Zurich shadow fills (09-26). READ-ONLY.

Spec: `analysis/v/staking/EF_BUCKET_GRID_SPEC.md` (679d19c). Script: `analysis/zurich/ef_bucket_grid.py`.
Buckets were fixed in the spec before anything was looked at. Every cell below is printed; none is
selected as the finding.

**772 graded EF fills, 09-15 00:31 -> 09-26 02:18 UTC.** Halves split by time at 09-20 13:25.

## Grading — the cross-check the standing rule asks for, and it passes
`venues.outcome` covers **84** of the 772 epochs (all in `z1`/`z2`; the snapshot ends 09-16 17:15).
The other **688** are graded on the engine's `results.actual`, and every row says which.

**On the 84 epochs where both sources exist they agree 84/84, zero disagreement.** That is the first
time this box has been able to check its own grading against the oracle Polymarket settles on, and it
means `results.actual` is verified where verification is possible rather than merely assumed. It does
not prove the other 688, but it removes the specific failure mode CLAUDE.md warns about.

Break-even win% is exact, not an estimate: the engine's fee is `0.07*shares*q*(1-q)`, so `fee/stake`
is `0.07*(1-q)` and breaking even needs `W = q*(1 + 0.07*(1-q))`.

## The whole grid

```
  bucket                n     win%  BE win%    per$1          half1          half2  grading
FIRE SECOND
  [0,60)              198    51.5%     44.3%    0.188   +0.137( 66)   +0.214(132)  mixed 23v/175e
  [60,120)            272    48.2%     43.1%    0.108   -0.063( 96)   +0.201(176)  mixed 32v/240e
  [120,180)           185    45.9%     43.5%    0.123   -0.054( 68)   +0.226(117)  mixed 19v/166e
  [180,240)           117    47.9%     43.7%    0.092   -0.223( 45)   +0.288( 72)  mixed 10v/107e
  [240,300)                (no data)
ENTRY PRICE
  <0.35                95    45.3%     32.3%    0.423   +0.185( 32)   +0.545( 63)  mixed 11v/84e
  0.35-0.45           422    44.1%     41.2%    0.079   -0.135(131)   +0.176(291)  mixed 40v/382e
  0.45-0.55           222    54.5%     50.6%    0.081   -0.032( 95)   +0.165(127)  mixed 26v/196e
  0.55-0.65            31    74.2%     58.0%    0.292   +0.322( 16)   +0.261( 15)  INSUFFICIENT
  >=0.65                2    50.0%     67.1%   -0.249   -1.000(  1)   +0.502(  1)  INSUFFICIENT
|MOVE| bps
  <3                  591    48.1%     43.1%    0.123   +0.000(221)   +0.197(370)  mixed 70v/521e
  3-6                 140    48.6%     44.9%    0.131   -0.260( 40)   +0.287(100)  mixed 12v/128e
  6-10                 28    50.0%     45.0%    0.153   -0.155( 11)   +0.352( 17)  INSUFFICIENT
  >=10                 10    70.0%     48.2%    0.544   +0.438(  3)   +0.589(  7)  INSUFFICIENT
  move NOT LOGGED       3    33.3%     43.4%   -0.271      -  (  0)   -0.271(  3)  INSUFFICIENT
UTC HOUR BLOCK
  00-06               184    48.4%     43.0%    0.164   -0.070( 77)   +0.332(107)  mixed 18v/166e
  06-12               173    53.2%     45.1%    0.195   +0.185( 72)   +0.202(101)  mixed 33v/140e
  12-18               231    47.6%     43.0%    0.118   -0.096( 69)   +0.209(162)  mixed 26v/205e
  18-24               184    45.1%     43.4%    0.048   -0.212( 57)   +0.165(127)  mixed 7v/177e
SIDE
  UP                  283    53.0%     45.9%    0.174   +0.064(111)   +0.244(172)  mixed 38v/245e
  DOWN                489    45.8%     42.2%    0.104   -0.109(164)   +0.212(325)  mixed 46v/443e
```
`[240,300)` is empty because the EF decision window closes at 240 s.

## THE BOTH-HALVES TEST IS NOT DOING WHAT IT LOOKS LIKE IT IS DOING

Whole sample: **first half n=275 at -0.0391 per $1, second half n=497 at +0.2230.** The two halves are
not two samples of one process, they are a losing period followed by a winning one.

**The second half is positive in 15 of 15 cells that have data. Every single one.** So "the sign holds
in both halves" carries no information from the second half at all — it reduces entirely to "was this
cell positive in the *first* half", a one-period test on the smaller n. That is a weaker test than it
appears, and it is the same shape as the trap in `verify.py`'s `halves()` check.

## Cells with n>=60 whose sign holds in both halves

| bucket | n | per$1 | half1 | half2 | half sub-n both >=60? |
|---|---|---|---|---|---|
| FIRE SECOND [0,60) | 198 | +0.188 | +0.137 | +0.214 | **yes** (66 / 132) |
| ENTRY PRICE <0.35 | 95 | +0.423 | +0.185 | +0.545 | no (32 / 63) |
| \|MOVE\| <3 | 591 | +0.123 | **+0.000131** | +0.197 | yes (221 / 370) |
| UTC 06-12 | 173 | +0.195 | +0.185 | +0.202 | **yes** (72 / 101) |
| SIDE UP | 283 | +0.174 | +0.064 | +0.244 | **yes** (111 / 172) |

**Cells negative in both halves with n>=60: none.**

Three of the five survive with both half sub-cells over 60: fire second [0,60), UTC 06-12, and side UP.
`|MOVE| <3` should be struck from the list — its first half is **+0.000131**, which is zero, and it only
passed because my test read `> 0`. `ENTRY PRICE <0.35` has a 32-trade first half.

## What none of this establishes
`|MOVE| <3` holds 591 of 772 trades, so it is nearly the whole sample rather than a subgroup. The three
surviving cells are also not independent of each other or of the EF arm's headline, which still fails
the permutation control at every reading (p 0.065-0.280 against a 0.01 bar, the cheap-side null taking
76-88%). A bucket that looks positive inside an edge that is not yet distinguishable from buying cheap
sides is not a finding, and the spec's own bar requires London as well.
