# In-trade stop for calm FAV - PRE-REGISTERED 09-30 02:0x UTC (before any look)
Owner 01:5x: "make my drawdown lower ... at least profit but very little drawdown, so i can use compounding".
FAV's drawdown is structural: win +$2..5, loss -$10 (full stake). Test an EXIT, not an entry gate:
after a FAV fill, if our side's BID falls to <= S at any later second of the candle, SELL at that bid
(fee 0.07*p*(1-p)/share, shares = filled shares), else hold to settlement (venue label).
Entry = frozen calm FAV (vol < tercile-1 cut, fav, ask .65-.85, sec 60-180, first second, once/candle, $10).
Grid fixed now, WHOLE grid reported: S in {none, .55, .50, .45, .40, .35, .30, .25, .20}.
Sets: V independent 09-13..16 (EF-8 rows, own_bid 1 Hz); Zurich 09-24..29 history + forward (same rule, Zurich runs it).
Per S: fills, $, maxDD, P/DD, days+/-, H1/H2, # stopped, avg stop loss.
A stop level is a candidate ONLY if on BOTH sets: $ >= base-rule $ * 0.8, maxDD <= 0.6 * base maxDD,
both halves > 0, and the P/DD curve over S is monotone or flat near the pick (no lone peak).
Paper only. Stake stays fixed; compounding needs the owner's two confirmations and is not part of this.

## VERDICT 09-30 02:1x - REJECTED on V's set (Zurich run not needed: fails at every S)
No-stop calm FAV on 09-13..16: +149.15, DD 68.62, P/DD 2.17, 4/4 days, H1 +80.66 / H2 +68.49.
Every stop level CUTS profit (to +2.93..+85.58) and does NOT cut drawdown (61.7..77.5 vs 68.6).
Mechanism: the favourite's bid dips and recovers - 78..127 of 255 trades get stopped, many of them eventual winners.
In-trade stop for FAV is closed.
