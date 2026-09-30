# M1 - latency-protected maker (V, 09-30, written BEFORE any result)
Why re-open makers: the 09-27 test (NC-10) rested STATIC bids and lost (one-side fills lose 96%). The venue holds taker orders ~250 ms
(itode) so makers can cancel, and consistent winners are makers (TOP_WALLETS). Untested: a maker that CANCELS on a Binance move.
Data: polybook pb (1 Hz bid/ask both sides) + book1s b1 (Binance spot 1 s), 09-11..16; labels venues.outcome (Polymarket's own).
Rule: post a bid at the side's best bid when the bid is in the band and sec 30..240; fill at the first later second where that side's
ask <= our bid (level consumed - conservative; benign fills without a price move are NOT counted, so this is pessimistic).
Cancel if Binance moved >= k bps against the side over the last 3 s; a cancel at second t does NOT stop a fill at t (too late).
Repost when conditions hold again. One fill per side per candle; hold to settlement; $10 per fill; maker fee 0; rebates NOT counted.
Grid (full, no best cell): k in {none, 1, 2, 4} bps x band {0.30-0.70, 0.40-0.60} x calm {all, below the day-1 median 5-min vol}.
Columns: fills, /day, win%, $tot, maxDD, P/DD, days+, H1/H2 per $1. PASS = P/DD >= 2, both halves > 0, >= 4 of 5 test days, n >= 60.
k=none must reproduce the 09-27 loss (control). If nothing passes at 1 s granularity, the design is dead at our resolution;
if something passes, the next step is a live latency probe (tiny post-only orders on Zurich, owner's yes first) - not a deploy.

## M1 result (1 Hz sim): FAILS every cell (-0.02..-0.09 per $1, 0-1 of 5 days). Cancel-on-Binance changes nothing at 1 s. The sim sees only
price-crossing fills, so it is pessimistic by design; the public tape (M1b) is the better instrument.
## M1b (public tape, 48 h 09-26..28, 12.2 M$ of fills): makers -0.13%/$1 before rebates, takers -1.6%. Maker BUY 0.60-0.80 +2.9%/$1,
maker minus taker in the same band +2..+5 pp in 9 of 9 6-h blocks; not one wallet (all makers outside the top 10: +3.2%). 30-180 s +4..+5.5%, after 180 s negative.
## M2 PRE-REGISTERED (written before running): PASSIVE FAV vs TAKER FAV on the same public tape.
Passive: first second in 60..180 (ts - 2.2 s) with a public MAKER BUY fill on a token at p in [0.60, 0.80] and >= 14 shares filled at
<= p in that second on that token (our $10 would fit); we fill at p, no fee, no rebate. Taker: first TAKER BUY in the same window/band, pays p + fee.
Vol arms fixed from the FAV family (Binance 1 s trailing 5-min std, bps/s): all / calm < 0.304 / mid 0.304-0.466 / high >= 0.466.
$10 per candle. PASS = P/DD >= 2, both halves > 0, >= 6 of 8 6-h blocks > 0, n >= 60 - on 09-26..28 AND on a fresh 09-28..30 pull.
Paired passive-vs-taker on candles where both exist. Full grid printed.
