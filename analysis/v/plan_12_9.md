# 12.9 - engine cleanup from the two audits (audit_hotpath.md, audit_deadcode_overlap.md). V, 09-15 02:4x.

Order = live-money impact first. Every item: what, measured basis, test. All ship together as 12.9.0 on the cand twin
vs ctrl (12.8.11) for 24 h, paired fires/fills/PnL, then §7 on Zurich. No decision logic changes; the model's numbers
must be bit-identical (parity test on recorded ticks).

| # | change | basis | test |
|---|---|---|---|
| 1 | Post-timeout floor: if remaining budget < 0.4 s, release BUDGET instead of posting with a few-ms timeout | audit_hotpath defect (i), poly_core C:962 | unit: attempt at 1.7 s into a 2 s budget posts; at 1.65+ releases; no post with timeout < 0.4 |
| 2 | Compute features once per decide tick; fire path and reassess() reuse the cached vector when nothing new arrived (key: last spot/perp/depth seq + now bucket) | 14.8 ms x ~7 calls = ~75 ms CPU per fire on the loop | parity: identical decision dicts on 1,000 recorded ticks; timing: fire_to_submit_ms p50 down |
| 3 | EIP-712 sign in a thread (to_thread), journal re-hash with it | 5.3 ms on the loop per attempt; build 36 signed off the hot path | unit: same signature bytes; order-identity check unchanged |
| 4 | Housekeeping: index diagnostics(ts); DELETE hourly not every 5 s; halt_check/_wipeout/_main_oneshot monitor queries every 60 s, and _main_oneshot skips when MAIN is off | unindexed DELETE every 5 s, 2 halt queries/s, 1 LIKE scan/s | unit: KILL_CONDITION rows still written; timing: housekeeping tick < 5 ms |
| 5 | One quote-age dial: publish() reads ev_settings.quote_age_ms (CLI is the default only); gate order_plan uses require_depth=False like the executor | two decision points (audit 3a, 3b); Mumbai's 4/4 rejects came from the split | unit: dial change moves both paths; "book too thin" cannot block a fire the executor would send |
| 6 | Dashboard: fill exchange_latency_ms from event_lag; label arrival age "since last trade"; poll 1 s not 250 ms | the "300 ms" the user saw is trade silence; 25 queries / 0.5 s on the shared sqlite lock | visual + unit on the JSON fields |
| 7 | Remove dead: PaperBroker.account_snapshot, BookCache.clear (test-only), --mode flag; document the 265 standalone-only Runner lines as not-live | audit_deadcode 1, 2, 6 | suites 255 still green |
| 8 | OPEN, user decides: sqlite WAL + synchronous=NORMAL (durable against process crash, not power loss) removes the 2 fsyncs (~2 ms) before post | audit_hotpath 2 | not in 12.9.0 unless told |

Not changed: decide cadence 250 ms (event-driven decide is a design change, separate proposal), FAK+cap execution
shape (R-3), any threshold.
