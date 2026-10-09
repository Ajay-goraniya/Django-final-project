# Polymarket v12 — original dashboard, v10 PnL model

Paper release candidate. Original model and JSON weights preserved. Nothing has been deployed or traded live. The live adapter is included but has not been exercised against an account.

## Start on Linux / WSL (Python 3.11+)

Extract this archive, then from its `polymarket_v12` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-paper.txt
python btc_model_v12_polymarket.py --mode pnl --capital 50 --db polymarket_v12_paper.sqlite3 --port 8787
```

Open http://127.0.0.1:8787. Controls: `/controls`; history: `/data`; detailed export: `/export.csv`. The old dashboard layout, candle chart, markers, history, PnL and control panels are retained. The original EF panel displays the v10 lane; MAIN and REVERSAL cannot be enabled because they are different strategies. Features and weight tables now show the actual v10 inputs and coefficients. No online learning.

Paper mode starts enabled and needs roughly ten minutes of continuous feed history before it can fire. It consumes live Binance spot/perpetual feeds and Polymarket books, simulates taking available depth at a capped price, then waits for Polymarket's official final outcome. Quote freshness, minimum size and EV gates can skip candles. There is no promise of a daily profit or fill rate.

The default ladder starts at $1, rises after two balance checks ($2 at $30, $3 at $40, +$1 per $10, maximum $20), and drops immediately. At $50 it rises to $4 after two checks. Select Fixed in the old controls for a constant $1 stake. If the venue's minimum share size exceeds the selected stake, the trade is skipped; the engine never silently increases it. Daily limits reset at London noon; schedule rules use London time.

## Stop and resume

Use Ctrl+C; restart with the same command, database and capital. Back up the database while stopped. It retains controls, reservations, fills, results and claims. Accepted paper fills survive a broker restart. One process per database; model hash and PAPER/LIVE identity are checked. The earlier pre-release database schema is rejected: retain that file and choose a fresh v12 database. The supplied historical paper DB is an audit input, not a v12 operating DB.

Production SQLite uses FULL synchronization. This hosted development filesystem rejects fsync, so a production process could not be validated here. Use a normal local filesystem; do not disable synchronization in production. Tests substitute a connection only inside the test module. Power-loss durability and continuous network operation remain untested.

## Execution rules

FAK taker orders, one-tick price pad by default, post-fee EV recheck after signing, up to three attempts within two seconds and before candle second 240. Retries require a new book update. Timeouts and ambiguous acceptance remain pending for reconciliation; no blind resubmission. Per-token freshness and reconnect snapshots prevent another market's activity from refreshing a stale quote. Confirmed fills alone are graded; no Binance settlement substitute.

Orders persist the quote, price cap, budget, attempt, response latency and reason. Fills persist shares, price, collateral and estimated fees. CSV includes these as structured JSON columns. Dashboard fill rate counts candles with recorded fills / attempted candles. Response latency is not exchange-confirmed fill latency. Automatic halt: mean slippage above $0.03 over 20 filled candles, or sum of the last 20 settled returns per dollar below -3. A halt stays latched for review.

## Live adapter — separate validation required

The adapter targets official `polymarket-client==0.10.0` and uses private SDK signing/metadata helpers, so the version is pinned. Do not assume this is account-tested or production certified. SDK signing, returned order hashes, trade reconciliation, redemption and actual fee debits must be verified before arming. Unresolved order IDs remain pending; a claim with an unknown submission result requires account review instead of an automatic repeat.

Install `requirements-live.txt` only for that validation. Required environment variable names: `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_WALLET_ADDRESS`, `RELAYER_API_KEY`, `RELAYER_API_KEY_ADDRESS`. No credentials are included. After account eligibility, funding/allowances, relayer capacity, weekend evidence and fee reconciliation are confirmed, live mode is selected with `--live --db polymarket_v12_live.sqlite3`. It starts with the master OFF every time; the old controls provide the explicit arming step. No live process was started during this work.

The live PnL fee is an estimate attached to confirmed trades, not reconciled wallet profit. Paper uses a 0.07 fee-rate estimate; live reads metadata. The historical log's share-deduction formula differs from this adapter's additive collateral estimate. Their PnL values must not be treated as interchangeable. Unknown wallet transfers and gas are not attributed to trading PnL.

Bind to localhost by default. External binding requires `DASHBOARD_PASSWORD` of at least 12 characters (username `ajay`); use an HTTPS proxy or SSH tunnel for remote access because the server itself uses HTTP.

## Supplied paper evidence

`paper_audit.json` audits `baseline_paper.sqlite3`, the second uploaded snapshot. 412 settled trades: 216 wins / 196 losses, +$487.9495 on $4,120 staked; one pending. All 412 stored probabilities match the supplied model within the audit tolerance; the legacy fee/PnL formula also matches. One invalid dust quote is explicitly excluded.

| UTC date | Settled | Paper PnL |
|---|---:|---:|
| September 8 (partial) | 45 | +$139.91 |
| September 9 | 136 | +$105.77 |
| September 10 | 159 | +$202.70 |
| September 11 (partial) | 72 | +$39.57 |

This is a logged-result audit, not a fresh market-depth replay or independent outcome verification. There is no weekend evidence. The user chose to proceed without `l2 full.zip`; full depth replay is excluded from this release. Recorded prices and book features may contribute to the edge, but this audit does not isolate their causal contribution.

## Checks and remaining validation

```bash
python -m unittest test_polymarket -v
python audit_paper.py baseline_paper.sqlite3
```

32 tests pass: quote gates, price/size budgeting, partial fills, retry deadlines, no duplicate submission after timeout, durable paper-fill recovery, resolution/grade rules, out-of-order settlements, control validation, original dashboard panels and HTTP pages/APIs. Embedded JavaScript passes syntax checks. Browser screenshot verification did not complete in this environment; visual rendering and interaction should be checked in the target browser. Live SDK/account integration, network endurance and power-loss behavior are not covered by these tests.

Reference interfaces used: https://github.com/Polymarket/py-sdk , https://docs.polymarket.com/trading/place-orders , https://docs.polymarket.com/trading/fees .

## Phone / Termux launch

Keep the extracted project under Termux home so its SQLite database is on the private filesystem. With Python, NumPy and websockets installed, run from the project directory:

```bash
bash start_paper.sh
```

This starts PnL paper mode on port 8787, requests a wake lock when Termux provides it, and resumes its existing database. It never resets the DB. Open http://127.0.0.1:8787 in your phone browser. Override the port with `bash start_paper.sh --port 8788`. If dependencies are absent on Termux, install Python and NumPy through Termux packages (`pkg install python python-numpy`) and websockets with `python -m pip install 'websockets>=12,<16'`. This phone setup has not been tested on a physical device.
