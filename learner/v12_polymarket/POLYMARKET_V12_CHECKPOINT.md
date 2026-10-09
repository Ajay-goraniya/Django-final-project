# Polymarket v12 checkpoint — 2026-09-11

## What was preserved
- The profitable signal remains `engine/btc_model_v10.py` + `engine/model_v10.json`.
- Binance spot/perp/depth features and the Polymarket UP/DOWN websocket book remain inputs.
- The new file does **not** retrain or rewrite the direction model.

## What was added
`engine/btc_model_v12_polymarket.py` adds a separate guarded execution lane:
- PAPER is default; live requires explicit CLI confirmation + wallet environment variables + eligibility confirmation.
- Entry quote comes from the websocket book.
- BUY is FAK with `max_price = fresh ask + pad ticks` and `max_spend = requested stake`.
- The model EV rule is rerun at the padded cap before each attempt.
- Up to 3 retries only after an explicit no-fill/rejection and each retry reads a fresh websocket quote.
- Any ambiguous submit/network exception disables the live lane instead of blind-resubmitting.
- Accepted/matched orders are reconciled against authenticated account trades before settlement PnL is graded.
- Quote, cap, attempt latency, order/trade IDs, raw fill price, fee-rate field, slippage and PnL are persisted in SQLite.
- Rolling live kill: >$0.03 mean slippage over 20 fills; README's -3.0 PnL/$ threshold is preserved literally.
- Stake ladder: $1 under $30 equity, $2 at $30, $3 at $40, +$1 per +$10, cap $20; down immediately, up after 2 checks.

## Live prerequisites intentionally NOT faked
- No private key or wallet is bundled.
- No live order was sent from this build environment.
- Jurisdiction/account eligibility must be confirmed by the user.
- The weekend evidence gap remains until Saturday/Sunday data exists.
- The exact fee economics should be reconciled against the first real fill; v10's conservative 0.07 model fee is retained for continuity.

## Resume point
Start with `engine/btc_model_v12_polymarket.py`. Do not move the signal to Build11 unless a new comparison proves it beats the v10 Polymarket lane. The remaining production validation is a tiny funded smoke test after eligibility/funding/allowances are confirmed, then compare websocket quote vs matched trade price and fee field.
