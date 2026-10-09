# Maker probe - the only untested structure (V, 09-30). SPEC ONLY - nothing built or deployed; needs the owner's explicit yes + funds.
Goal: measure, with real orders, whether a post-only bid that cancels on a Binance move avoids the adverse fills that killed M5/M10.
- Box: Zurich 8787 (London untouched). Budget: $20 total at risk; 5-share post-only bids (~$3 each); max 1 open bid; daily loss cap $10 -> off.
- Rule: favourite side, best bid in [0.60, 0.80], sec 60-180, calm (< 0.304). Post at the best bid (post-only, never crosses).
  Cancel immediately if Binance (websocket, ms) moves >= 2 bps against the side, or at 180 s. Hold fills to settlement.
- Logged per order: post ts, cancel ts, cancel reason, fill ts, fill size, Binance move in the 500 ms before the fill, outcome.
- Decision after >= 60 fills: adverse-fill share (fills followed by a >= 2 bps move against us within 1 s) and $/fill vs the M5 strict sim
  on the same candles. PASS only if $/fill > 0 after 20% rebates and adverse share clearly below M5's; otherwise the maker path is closed.

## OWNER YES 09-30 ~12:5x UTC: 'Okay test it' (reply to this spec). Build on Zurich, default OFF; live only when the owner switches it on.

## OWNER 09-30 14:14 UTC: 'yes, switch it on' (owner has no Zurich terminal; asked Zurich to create ENABLED and start the process on his behalf). Limits unchanged: -$10/day, -$20 lifetime, 5 shares.

## OWNER 09-30 20:07 UTC: 'Yes' to restart the FIXED maker probe (bab8dc4: rest-don't-chase, max 3 posts/candle, REJECTED status). Limits unchanged.

## OWNER 09-30 21:28 UTC: 'A' = remove the 'bid ran >= 2 ticks away' cancel (V's addition); back to the original spec (rest until Binance 2 bps against or 180 s). Restart still needs a fresh owner yes after the safety fixes.

## OWNER 09-30 23:11 UTC: 'Yes' to restart the maker probe build 82754c9 (option A + fill-record + same-second lockout). Limits unchanged.

## 10-01 00:57 UTC - RETRACTION (Zurich, verified at the venue; commit 3794218)
Probe DID fill: 27 fill events over 10 candles 09-30 17:00 .. 10-01 00:45, $77.60 deployed, +$42.40 realised, 27/27 won.
check_fill read a field ClobTrade does not have (maker fills live in maker_orders[]) -> fills table empty -> BOTH hard stops and
one-fill-per-candle were blind the whole time (15 fills in the 17:00 candle). Every "0 fills" report was this bug, incl. the evidence
used for the owner's option A. Result is 10 candles, not 27 - not evidence. Probe PAUSED 00:45, 0 open orders/positions at the venue.
Fix (reads maker_orders[]) deployed by another session 00:52-00:54; Zurich verified it against venue data to the cent; 102 tests.
OFF until the owner decides how to restart.

## OWNER 10-01 01:03 UTC, verbatim: 'Bro just do whatever is better' (reply to: restart fixed probe with option A or the 2-tick rule; stays off until you reply). V's choice: option A on the FIXED build (maker_orders[] fill detection), limits unchanged, restart once Zurich confirms deployed file == a committed hash and no other session is editing it.

## OWNER APPROVAL 10-01 ~11:5x UTC, relayed by V: "Yes" then "I approve, send it to Zurich"
Change approved, exactly as scoped: **a fill under 1.0 share does not set filled-this-candle.** Its
ledger row and its pnl stay, and it still counts toward BOTH stops. Nothing else changes - max 3
posts per candle, one open order at a time, the 0.60-0.80 bid band and the -$10/day / -$20 lifetime
stops are all untouched. Stated worst case per candle: **2 x 0.99 + 5 shares**, which holds because
the 3-post ceiling holds.
Cause: on 10-01 11:40 a 0.01-share fill - seven tenths of a cent - closed a whole candle and blocked
11 passes. One-fill-per-candle exists to cap exposure, and dust is not exposure; letting it close a
candle biased both things the probe measures (the fill RATE, since each dust fill burns a candle that
could have produced a real one, and the adverse-fill series, since a 0.01-share outcome is noise).
Implemented on Zurich as MIN_LOCK_SHARES = 1.0 with 9 tests covering both sides of the boundary
(0.99 does not lock, 1.00 does, the real 0.01 case does not, 5.0 still does, the dust row and its
pnl survive, dust pnl trips both stops, and the candle remains postable afterwards).

## OWNER APPROVAL 10-01 ~20:1x UTC, via V: "Yes to whatever issue Zurich has"
Approved: **fix the probe's wrong-token fill check and restart.** The fill scan now queries the
account tape with **NO token filter** and lets `matched_by()` decide ownership from `maker_orders[]`.
Limits and rules unchanged - 5 shares, one open order, 3 posts/candle, MIN_LOCK_SHARES 1.0, the
0.60-0.80 bid band, 2 bps / 180 s cancels, -$10 day and -$20 lifetime stops.
Cause being fixed: the venue books a maker fill against the COMPLEMENT token at the complement price
(order 109 was UP @ 0.60 on token 4432226411; its trade sits on token 7780369265 at 0.40), so asking
for OUR token asked for the one token the trade is not filed under. 12 fills across 10 orders were
invisible for a day while both stops read an empty table.
Also fixed in the same change, because removing the filter created it: the unfiltered tape carries
London's trades too, so "newest page only" became much likelier to miss ours. The scan now walks up to
5 pages and stops early once the tape is older than the order itself - a real bound, since a fill
cannot precede its own order.
Verified against the LIVE venue before restart: the fixed scan finds **10 of 10** of those orders
(5.0sh each bar one partial at 4.996154sh), where the old token-filtered scan found 0 of 12.
