# Task 115 - is 12.8.11 better than the current build? Paired, same tape, venue-graded.

Owner's question, tested rather than reasoned about. 2026-09-16 12:05 UTC.

## Grading source

Every arm is graded on `results.actual`, which is the **venue** outcome, not the candle: the grade
loop fetches the Gamma market and takes `official_result(...)` (btc_model_v12_polymarket.py:708-716)
before writing the row. Cross-checked against `venues.outcome` on every overlapping epoch:
**55 agree, 0 disagree.** `candles.actual` is not used anywhere below.

## Per-arm grid (EF is the only kind any arm has fired)

| port | build | n graded | W | W% | staked $ | pnl $ | pnl per $1 | started | readable? |
|---|---|---|---|---|---|---|---|---|---|
| 8793 | 12.8.11 | 70 | 29 | 41.4% | 209.62 | -7.90 | -0.0377 | 22:36 | **60+, but see halves** |
| 8787 | 12.9.0 | 12 | 6 | 50.0% | 35.96 | +0.05 | +0.0014 | 09:03 | insufficient |
| 8794 | 12.13.0 model_venue | 0 | 0 | - | 0 | 0 | - | 10:41 (<2 h, cold) | insufficient |
| 8795 | 12.13.0 model_v10 | 6 | 2 | 33.3% | 17.98 | -6.32 | -0.3518 | 10:44 (<2 h, cold) | insufficient |
| 8796 | 12.14.0 | 2 | 0 | 0.0% | 5.99 | -5.99 | -1.0000 | 11:36 (<2 h, cold) | insufficient |

Cold-lane note: 8794, 8795 and 8796 are all inside their own 2 h `self.closed` warm-up. **EF is
unaffected** - it runs off the separate v10 FeatureState - so those EF rows are honest; MAIN and
REVERSAL from those three would not be, and none have fired.

## Halves

| arm | H1 n | H1 pnl/$1 | H2 n | H2 pnl/$1 | |
|---|---|---|---|---|---|
| 12.8.11 | 35 | -0.0759 | 35 | +0.0005 | **sign flips - arm not readable** |
| 12.9.0 | 6 | +0.3981 | 6 | -0.3952 | **sign flips - arm not readable** |
| 12.13.0 v10 | 3 | -0.4025 | 3 | -0.3012 | same sign, n=3 per half |

**Every arm with more than two fires fails its own halves test or is under 60. Not one arm is
readable on its own numbers.**

## The paired part - this is the answer

Restricted to candles where both arms fired EF:

| arm A | arm B | pairs | A wins | B wins | b (A+ B-) | c (A- B+) | exact McNemar | A-B pnl/$1 |
|---|---|---|---|---|---|---|---|---|
| 12.8.11 | 12.9.0 | 11 | 5 | 5 | 0 | 0 | undefined, 0 discordant | -0.0007 |
| 12.8.11 | 12.13.0 v10 | 6 | 2 | 2 | 0 | 0 | undefined, 0 discordant | +0.0450 |
| 12.8.11 | 12.14.0 | 2 | 0 | 0 | 0 | 0 | undefined, 0 discordant | 0.0000 |
| 12.9.0 | 12.13.0 v10 | 5 | 1 | 1 | 0 | 0 | undefined, 0 discordant | +0.0205 |
| 12.9.0 | 12.14.0 | 2 | 0 | 0 | 0 | 0 | undefined, 0 discordant | 0.0000 |
| 12.13.0 v10 | 12.14.0 | 2 | 0 | 0 | 0 | 0 | undefined, 0 discordant | 0.0000 |

8794 shares no graded candle with anything and is not comparable at all.

**Zero discordant pairs in every pairing.** On every candle two arms both fired, they picked the
same side and got the same result. McNemar has nothing to test: the statistic is defined on the
discordant cells and both are empty. To V's question - a 70-fire arm here is an **11-pair** sample
against 12.9.0, and 11 pairs with 0 discordant is no evidence of a difference in either direction.

The 11 shared candles, side / fire second / fill price:

```
09:15  8793 UP   183.1s 0.450 | 8787 UP   232.1s 0.420   -0.0300
09:35  8793 UP    61.8s 0.420 | 8787 UP    61.4s 0.420    0.0000
09:50  8793 UP   121.3s 0.470 | 8787 UP   121.5s 0.500   +0.0300
10:05  8793 UP    69.1s 0.420 | 8787 UP    68.9s 0.420    0.0000
10:20  8793 DOWN 148.6s 0.410 | 8787 DOWN 148.3s 0.410    0.0000
10:40  8793 UP    38.1s 0.560 | 8787 UP    38.1s 0.560    0.0000
11:00  8793 DOWN  94.8s 0.294 | 8787 DOWN  95.0s 0.310   +0.0158
11:05  8793 UP    96.0s 0.410 | 8787 UP    96.1s 0.410    0.0000
11:30  8793 UP    72.8s 0.550 | 8787 UP    72.7s 0.509   -0.0411
11:45  8793 UP   150.8s 0.428 | 8787 UP   151.6s 0.420   -0.0077
11:50  8793 DOWN 132.6s 0.350 | 8787 DOWN 132.9s 0.360   +0.0100
```

Same side 11 of 11. Same fire second within 0.3 s on 10 of 11 (09:15 is the exception, 183 s vs
232 s). **Median fill-price difference exactly 0.0000.** The two builds are behaving as one.

## Where 12.8.11's -0.0377 actually comes from

| 12.8.11 subset | n | W | pnl/$1 |
|---|---|---|---|
| the 11 candles shared with 12.9.0 | 11 | 5 | **-0.0743** |
| the 59 candles 12.9.0 never saw | 59 | 24 | -0.0308 |
| whole arm | 70 | 29 | -0.0377 |

8793 spans 09-15 22:55 to 09-16 11:50; 8787 only 09-16 09:15 to 11:50. The whole-arm gap between
-0.0377 and +0.0014 is **different candles, not different quality** - and on the candles they do
share, 12.8.11 is the worse of the two, not the better (-0.0743 against -0.0736 for 12.9.0 over the
same 11, a gap of 0.0007 per dollar, which is noise).

## Verdict

**12.8.11 does not win, and nothing else wins either.** On shared tape the builds make the same call
at the same second and fill at the same price, with zero discordant pairs in every pairing. The
belief that 12.8.11 was better rests on comparing its 13 hours against another build's 3, and once
the candles are matched the difference disappears. No arm passes its own halves test, so no arm's
standalone pnl should be read at all. The honest state today is **not "12.8.11 is worse" but "these
builds are not yet distinguishable, and the paired sample is 11"** - a real answer needs the arms
running side by side long enough to produce discordant pairs, which by definition needs candles
where they disagree, and so far there have been none.

Nothing was changed. Read-only throughout.
