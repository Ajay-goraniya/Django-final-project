# Resume checkpoint — 2026-09-12

Implementation and local checks complete for paper release candidate. Read README.md first.
Exact model_v10.json and btc_model_v10.py preserved. Old HTML dashboard layout retained; v10 inputs, controls and execution data connected. 32 tests pass. No live activation or deployment.

Latest fixes: monotonic settlement IDs; all-or-nothing validation of settings; paper fills persisted before acknowledgement; second EV/control check before POST; failed attempts do not inherit PnL; raw average entry excludes fees; complete order/fill CSV; actual v10 feature and weight display.

Remaining external validation: target-machine paper run and browser rendering, weekend collection, full depth replay excluded by user request (proceed without l2 full.zip), official SDK installation and account-backed signing/order-hash/reconciliation/fee/redemption checks. Do not represent the live adapter as certified or the historical PnL as a fill-rate test. Hosted fsync unsupported; tests explicitly use a test-only connection substitute, production keeps FULL synchronization.

Historical audit: 412 settled, 216 wins,196 losses,+487.949503497194,1 pending. 412 probability checks match. Baseline DB and audit code included to reproduce. No new market data or independent outcome fetch was used.

Restart a paper run with its same v12 DB, capital and model. Do not reset or replace operating DBs with baseline_paper.sqlite3. Before further changes, retain this package and re-run tests only for material risks.

User explicitly waived the missing l2 full.zip on the latest turn. Do not request it again as a condition of delivering/running this package. Smaller l2.zip successfully reassembles to August 31 perp-depth files. One-second quote ZIP also reassembles; its supplied manifest distinguishes real books from trade-inferred prices. No new replay PnL has been computed. Added start_paper.sh for port8787 and persistent local DB.
