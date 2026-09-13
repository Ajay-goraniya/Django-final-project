# Polymarket v12.1 live execution/accounting fix

## Scope
This patch keeps the packaged v10 PnL model/weights, Binance inputs, Polymarket book feed, FAK capped-buy policy, staking, settlement, dashboard layout and existing SQLite history. It changes live execution verification, accounting presentation, error logging and latency telemetry only.

## Root causes found
1. **Available-balance mismatch:** the dashboard took the authenticated Polymarket collateral balance and then subtracted the local `SUBMITTING/UNKNOWN/PENDING` reserve a second time. A stale UNKNOWN therefore made `$13.73` venue-available display as `$7.73`. Resetting SQLite removed the stale reserve, which is consistent with this bug.
2. **Rejected order misclassified as UNKNOWN:** all post exceptions fell through the same exception handler. Only `type(e).__name__` was persisted, so `RequestRejectedError` lost its actual venue message/status/code.
3. **UNKNOWN could remain forever:** reconciliation required `get_order()` to succeed. A FAK that was rejected/expired/nonexistent could disappear from the open-order endpoint, leaving the local reservation stuck.
4. **Slippage was under-specified:** the UI effectively compared one displayed quote with a rounded fill and did not expose signal quote, fresh pre-submit ask, cap and confirmed matched VWAP independently.
5. **Latency was opaque:** the old row had one response-latency number, so a 300-600 ms attempt could not be separated into local decision/signing vs network/venue response time.
6. **MAIN/REV controls:** v12 inherited MAIN/REV dashboard controls but the supplied v10 classifier is a single probability/decision lane and contains no MAIN or REVERSAL signal implementation. The old v12 therefore hard-disabled them. The toggles now persist and are no longer hardcoded-rejected, but execution remains correctly marked source-unavailable rather than inventing a strategy.

## Fixes
- Polymarket authenticated balance is now the dashboard **Available** source of truth. Local unresolved reserve is shown separately and is used only as a concurrency/safety headroom, never subtracted from the displayed venue balance.
- Startup performs venue-first reconciliation twice before the dashboard opens, then fetches an authenticated account snapshot.
- Explicit SDK `RequestRejectedError` is now **REJECTED**, never UNKNOWN. The journal stores sanitized class, `str(e)`, `repr(e)`, HTTP status/code/restriction/retry information, and response body/JSON when available. Credentials/signatures are redacted.
- Ambiguous transport failures remain **UNKNOWN** and are not blindly resubmitted. `request_reached` is reported as `UNKNOWN`, not falsely `true`.
- Reconciliation uses the authenticated account trade tape plus order state. A confirmed matching trade proves a fill even if the FAK has disappeared from order lookup. Repeated venue-confirmed absence with no matching trade proves NO_FILL and releases the local reserve.
- Live PnL still grades only persisted confirmed fills. REJECTED/NO_FILL/UNKNOWN rows do not become a stake loss.
- Raw signal quote, fresh pre-submit quote, cap, confirmed VWAP, shares/spend/fee estimate, quote-to-fill, pre-submit-to-fill and cap-to-fill distances are exposed separately.
- Added stage telemetry: quote read/wait, decision, signing, final EV/control recheck, fire-to-submit, submit/response/network round trip, total attempt and book age; rolling p50/p95/p99/max total attempt is exposed in state.
- Warm `AsyncSecureClient` remains persistent; there is no balance/position/metadata REST call in the order-submit hot path.
- SQLite migration from build 12.0 to 12.1 is additive. Existing signal/order/fill/result history is retained.

## Simulation/tests
`python test_polymarket.py` => **44/44 PASS**.

The suite includes venue-side simulations for:
- full explicit rejection text/status/code + secret/signature redaction;
- explicit rejection immediately releasing reserve;
- timeout remaining UNKNOWN without duplicate submission;
- restart with UNKNOWN followed by repeated venue no-order/no-trade proof -> NO_FILL -> reserve released;
- confirmed account trade proving FILLED when the order endpoint no longer retains the FAK;
- failed/unresolved attempts never producing PnL;
- Polymarket cash `$13.73` staying dashboard Available `$13.73` even while a `$6.00` local UNKNOWN reserve exists;
- independent signal quote / pre-submit ask / fill / cap slippage math;
- persistence of latency stages and p50/p95/p99 telemetry;
- additive 12.0 -> 12.1 database migration without wiping history;
- master, individual control persistence, stake validation, settlement, retry fencing, price/size/EV gates and original dashboard/API behavior.

All three embedded HTML JavaScript blocks (`dashboard`, `data`, `controls`) also pass `node --check`.

## Live-latency statement
The build environment cannot send a funded Polymarket order, so it would be dishonest to claim a measured post-fix WAN latency. The patch removes no safety checks to fake a lower number; instead it keeps the client/signer hot and records the exact stage responsible for each live attempt. On deployment, `timing.response_ms` / `network_roundtrip_ms` will distinguish venue/network latency from local `decision_ms` and `sign_ms`.

## MAIN / REVERSAL source limitation
The separately supplied `btc_model_v10.py` does **not** contain MAIN/REVERSAL signal logic. Its public interface returns one side/probability/EV decision. Therefore this patch does not synthesize MAIN or REV from it. Their control state is retained and visible, but `source_available=false` until the actual MAIN/REV source implementation is provided. This is intentional strategy preservation, not a silent hardcoded OFF switch.
