# T0 — the ruler. 2026-09-21 (V). Read-only analysis; nothing shipped.

Question: what quantity does Polymarket's btc-5m market actually settle on, and can we rebuild it offline?

## Result on 2,232 candles, 09-08 → 09-16, graded on `venues.outcome`
| rule | matches venue | H1 | H2 | on the 1,187 candles that closed within 5 bps of open |
|---|---|---|---|---|
| TWAP60(Binance 1 s closes) at close vs TWAP60 at open | **2159/2232 = 0.967** | 0.974 | 0.961 | **0.944** |
| raw Binance close ≥ open (what v10's features measure, and what `candles.actual` is) | 1942/2232 = 0.870 | 0.875 | 0.866 | 0.774 |

The two rules disagree on 259/2232 candles (11.6%). On 155 live fills they disagreed on 32 (20.6%) —
the model fires on flat candles, where the raw rule is a coin flip against the TWAP rule.
Task 108 (Mumbai, 72 candles, Chainlink ticks) had the TWAP-of-Chainlink rule at 72/72 and this proxy at 71/72;
the residual 3.3% here is Chainlink-vs-Binance basis on near-ties, not a different rule.

## Finding about the running artifact (12.11.1 onward) — not live-affecting today, blocks T1 if ignored
`btc_model_v10.py:148-153` says the venue feed "already publishes Chainlink's 60 s TWAP" and sets `REF_IS_TWAP=1`,
so `ref_open`/`ref_now` are the feed's INSTANT value at the open / now. Checked against 5,568 engine-logged points
(zurich_2/3 diagnostics, `ref_src=1`) and the 12 verbatim frames in `analysis/aws/ref_stream_samples.jsonl`:
- feed value changes every second; corr(feed move, Binance RAW move) = 0.974 (0.983 at a 5 s lag); corr with Binance TWAP60 move = 0.818.
- residual std vs RAW 1.6 bps, vs TWAP 4.0 bps. The feed is an instant Chainlink price, not a TWAP.
- level basis Chainlink − Binance: median −9.1 bps (Task 108: 8.4).
So the engine's logged `ref_move_bps`/`ref_open_bps` are the wrong settlement quantity. The model does not use them
(`model_v10.json` has no `open_reference`), so no live decision was affected. For any retrain: `REF_IS_TWAP=0`
(average the feed) or the Binance TWAP60 proxy above. Not shipped; owner decides.

## Consequence for the plan
T1/T2/T3 features and labels are built on: line_open = TWAP60(Binance) over [open−60, open), line_now = TWAP60 over
[now−60, now), label = `venues.outcome`. Data: `data-api.binance.vision` 1 s klines (fetched 09-08 → 09-18, 870k rows,
includes taker-buy volume), `venues.q` for the venue price, `venues.outcome` for the label.
Scripts: scratchpad `t0/fetch_1s.py`, `t0/t0_parity.py`. Token budget for T0: ~40k.
