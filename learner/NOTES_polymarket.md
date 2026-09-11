# NOTES_polymarket - moving (or adding) Polymarket as a live venue
Started 09-11 02:30 UTC on the user's instruction: "we might move to Polymarket at least for a test run ... keep gathering
important infos, improvements and changes in different notes, use H1 for this." Research only until v12; nothing built.
H1's working file: analysis/h1/POLYMARKET.md (Task 19). This file is V's summary of what is decided and what is verified.

## What is verified (09-11)
- v10 model paper run on Polymarket asks (runner /tmp/v10_long4.sqlite3, since 09-08 17:35): 352 fires, 186/351 wins, ~150 fires/day,
  median ask 0.445. Graded on Polymarket's own resolution (0 disagreements vs the venues outcome table on 350 candles).
  Totals at $10/fire: +493 (runner's own fee model), +519 with Polymarket's real taker fee, +655 with no fee. Max drawdown -135 at $10.
  Per $1 fire after the real fee: +0.148, both halves positive, positive every UTC day (09-08 +0.36, 09-09 +0.12, 09-10 +0.17).
- Predict.fun for comparison: Tokyo live EF +0.04 to +0.11 per $1 fire, ~120 fires/day, 2% fee, thin book.
- Fees (docs.polymarket.com fees page): crypto markets charge TAKERS fee = shares x 0.07 x p x (1-p); makers pay nothing.
  Gamma market fields makerBaseFee/takerBaseFee = 1000 on the 5-min BTC market (interpretation to confirm with H1).
- Resolution: Chainlink BTC/USD 60-second TWAP data stream (data.chain.link/streams/btc-usd-twap-60s-streams), "Up" if TWAP at the
  end >= price at the start. Disagrees with Binance close on ~10% of candles, all near-flat. Polymarket publishes only the outcome
  (gamma outcomePrices, free). Chainlink Data Streams is self-serve with credentials from app.chain.link; billing page exists,
  pricing not confirmed. Not needed to trade; needed only for research fidelity (H1 can approximate the TWAP from 1-s klines).
- Book (sampled 02:15 UTC): 280-620 shares per level at the top, 1c spread, min order 5 shares, tick 0.01, ~$16k liquidity per
  5-min market. Fine for $3-20 stakes.
- Market flag restricted=True: jurisdiction gating. The user must confirm account eligibility and funding (USDC on Polygon).

- H1 Task 18 (09-11 02:45, analysis/h1/task18_polymarket_transfer.md): the Binance-close direction model (11.2) is NEGATIVE on Polymarket at
  every margin (hit 36-45%) because Polymarket pays on the Chainlink TWAP, which differs from Binance close on 10.5% of candles, and the
  model fires exactly where it disagrees with the Polymarket ask. The CURRENT EF signal (Polymarket-derived) transfers: +0.281 per $1 fire
  at margin 0.15 (n=69, both halves, both gradings) vs +0.049 for the same fires on Predict.fun. => Test the existing EF signal on
  Polymarket; any Polymarket direction model must be trained on Polymarket's resolution.
- CORRECTION 09-11 05:10 (H1 Task 20c): the +0.281 used collector quotes up to 5 s older than the decision (the stale-quote artifact that
  killed the 11.2 replay). With the quote taken at or after the decision: +0.223 per $1 fire (n=67, 62.7%) at margin 0.10, but halves
  -1.22/+16.14 - suggestive, not established. The Predict.fun comparison (+0.049, engine-recorded asks) is unaffected. The v10 Polymarket
  paper run (real-time runner, its own live quotes, +0.148 after fee, positive every day, 352 fires) is the primary evidence for the venue.

## What changes in the engine (to scope for v12, not built)
- Executor: Polymarket CLOB API (signed orders, API credentials derived from the wallet, USDC.e on Polygon, relayer/gasless).
  Predict.fun executor stays; the engine needs a venue abstraction (quote source, order submit, position/settlement reader).
- Grading: settle on Polymarket outcomes (gamma), never Binance close, for any Polymarket lane; live calibration by venue.
- Signal: the model's venue features (p_venue, lv) come from Polymarket already; on Polymarket the ask you saw can be gone when the
  order lands (no cross-venue lag). Paper assumed the recorded ask - the live micro-test decides.
- Fees in the EV rule: 7% x p x (1-p) per share instead of the flat 2%.

## Open questions (H1 Task 19 gathers these)
- Exact fee on the 5-min BTC markets right now (takerBaseFee field vs docs), rate limits, order types (FOK/GTC), min notional,
  settlement timing and redemption, API auth flow, geo policy, historical data endpoints (prices-history, trades), websocket streams.
- 11.2 transfer at Polymarket asks (Task 18). Weekend behaviour of the Polymarket paper run (Sat-Sun live test window).


## H1 Task 19 findings (09-11 05:30, analysis/h1/POLYMARKET.md)
- Grading: a kline-built 60-s TWAP does NOT reproduce Polymarket's resolution (best proxy 91.4% agreement vs 89.5% for the engine's
  close>=open; ~9% of candles mislabelled, concentrated in flat candles). Every Polymarket study grades on Polymarket's own outcome
  table; no kline substitute. For live trading nothing changes (the outcome is public after the close).
- Fees: docs table says crypto feeRate 0.07; the help centre says fees "peak at 1.56% at 50%", which implies 0.0625. Our replays used
  0.07 (conservative). gamma's takerBaseFee 1000 matches neither; units unknown. Resolve against a real fill before any migration decision.
- v10 Polymarket paper run by time: weekday only (371 fires, zero weekend coverage - same gap as everything else); 00-08 UTC ~flat
  (+0.014 per $1, n=115), 08-16 +0.193, 16-24 +0.181. Observation, not a rule. Headline reconciliation: my +0.148 recomputed 351
  fires with the 7% formula; the runner's own stored pnl (its own fee model, 371 fires) gives +0.133 - same picture.
- Still to gather: CLOB auth flow, order types, tick/min size, rate limits, websocket channels, fills/redemption - the executor spec.
- PLAN-CHANGING (H1 09-11 05:58): Polymarket's only historical endpoint (GET /v2/prices-history) returns MIDPOINTS only; no historical
  order book, bid/ask or trades. An honest replay needs the ask at or after the decision (Task 20), so every Polymarket evaluation must
  come from OUR forward collection (1 Hz logger or live paper run) started BEFORE the window we want to judge. Nothing can be
  reconstructed later. => start a Polymarket book logger now (V, 09-11 06:00).
- Executor delta vs Predict.fun (H1): EIP-712 typed-data signing on Polygon (chainId 137; deposit wallets need ERC-7739 wrapped
  signatures); order types GTC/GTD/FAK/FOK, GTD expires one minute BEFORE its stated expiry; min_order_size and tick_size are per token
  (read from the book endpoint per market); websocket wss://ws-subscriptions-clob.polymarket.com/ws/market with book / price_change /
  last_trade_price / tick_size_change events, subscribe {"assets_ids":[...],"type":"market"}, PING text frame every 10 s; rate and
  connection limits undocumented (treat as unknown). Still open: eligibility policy, rate limits.

## Plan
- Next week (user): decide after the weekend. If go: build the executor in v12, run $1 live beside Tokyo for a day, ladder decides.
