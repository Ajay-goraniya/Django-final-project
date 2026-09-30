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
