# Z-4 - the stuck UNKNOWN order: facts from the live journal and the venue. Read-only; nothing changed.

> Zurich session, 2026-09-15 01:5x UTC. Journal `~/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3` (ro), venue via the
> deployed `LiveBroker` read methods only (`get_order`, `list_account_trades`, `list_open_orders`, `get_balance_allowance`).

## (a) The reconcile diagnostics row - there is none
`diagnostics` has **0 rows** mentioning reconcile for epoch 1789432500. `Executor.reconcile` only writes a diagnostics row when
`broker.reconcile(r)` **raises**; here it returns normally with `terminal=False`, so nothing is logged and the reason is never
persisted. The `TimeoutError` in the orders row is the **original POST** (`phase: post`, `request_reached: UNKNOWN`), not reconcile.

**Which call fails, measured live (01:56:09 UTC):**
- `get_order(order_id)` -> **FAILED in 0.04 s: `UnexpectedResponseError`, status None, "OpenOrder response did not match expected shape"**.
  Not a timeout, not a 404. It takes the non-404 branch in `poly_live.reconcile` (`order_error` set -> `terminal=False`) every second, forever.
- `list_account_trades(token, after=ts-120)` -> OK in 0.06 s: **0 taker trades** for this id, qty 0.0, unsettled False.

## (b) The orders row
| id | epoch | ts | status | error | reconcile_count | venue_absent | venue_live | venue_checked | budget | cap | amount |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ...64f7d150 | 1789432500 | 00:36:19 | UNKNOWN | TimeoutError, phase post, request_reached UNKNOWN | **4292** | **232** | 0 | 01:54:36 | 3.0 | 0.44 | 2.88 |

plan quote 0.43, max_shares 6.545, kind EF, side DOWN, request_reached 0. Signal row status PENDING.

## (c) Venue truth (deployed client, plain reads)
- Open orders: listing succeeded, **n=0**; the id is **not** in the account's open orders.
- Account trades: **none** with this taker_order_id (see (a)).
- Cash: **venue 61.6186** vs engine `venue_state.cash` **53.4471** with `open_value` **8.1714** @01:55:57. The gap (8.17) equals the engine's
  open_value, which includes the **2.88 still reserved by this row**. Positions listed: 0.

So the venue has never had this order: not open, never traded. The engine cannot conclude that because `get_order` errors instead of 404ing,
and `venue_absent=232` (from `open_order_ids`) is counted but never used to resolve.

## (d) Did the epoch grade
- `results` row for 1789432500: **absent** - `grade()` skips the candle while an UNKNOWN row exists. Graded epochs: 1789432200, 1789432800,
  1789434900, 1789435800.
- Candle (Binance): open 78038.76, close 77997.92 -> **DOWN**. Venue (gamma): `closed`, `umaResolutionStatus resolved`, outcomePrices
  `["0","1"]` for `["Up","Down"]` -> **Down**. The signal was DOWN: an unfilled winner. No fill, so no PnL either way; the budget line is the only effect.

## Not measured / not done
No engine change, no restart, no writes. The SDK error's underlying HTTP body was not captured (the client raises before exposing it);
if the fix wants it, one `httpx` GET of the same endpoint with the API key would show the raw shape - not done here (read-only brief).
