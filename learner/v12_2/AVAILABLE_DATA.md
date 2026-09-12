# Available-data review

The user chose to proceed without l2 full.zip. It is not needed to launch the paper engine.

- l2.zip: successfully reassembled its six parts; inner archive lists 24 hourly August 31 perpetual-depth Parquet files plus another entry. Archive listing inspected; rows not replayed.
- 1s pollymarket.zip: successfully reassembled both parts; inner archive lists 24 entries. Its supplied README says actual book rows are available on September 2 (103,354), September 3 (142,305) and September 4 (2,850). Those counts are manifest claims, not freshly recomputed. Other coverage mainly uses trade-inferred prices.
- Trade-inferred prices are not executable asks. Do not fill gaps with these in a depth-aware execution backtest.
- The existing September 8–11 paper-log audit remains the only historical PnL result delivered. Its 412 outcomes and probabilities were audited previously; it is not a replay of the newer execution code.

No full depth replay is claimed. Exact model, dashboard and order-policy checks do not depend on the missing archive.
