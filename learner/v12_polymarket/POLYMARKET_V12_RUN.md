# Run v12 Polymarket

## Install
```bash
cd engine
python -m pip install -r requirements_polymarket_v12.txt
```

## Safe paper run (recommended for weekend test)
```bash
python btc_model_v12_polymarket.py --execution paper --port 8788 --db ../results/v12_poly_weekend.sqlite3
```

To reproduce the old $10-per-fire paper scale:
```bash
python btc_model_v12_polymarket.py --execution paper --fixed-stake 10 --port 8788 --db ../results/v12_poly_10usd.sqlite3
```

## Live-ready command (DO NOT run until you intentionally arm it)
```bash
export POLYMARKET_PRIVATE_KEY='...'
export POLYMARKET_DEPOSIT_WALLET='...'
export POLYMARKET_ELIGIBILITY_CONFIRMED=YES
python btc_model_v12_polymarket.py --execution live --confirm-live-orders --port 8788 --db ../results/v12_poly_live.sqlite3
```

Default live stake is $1 because lane equity defaults below $30. Use `--lane-equity N` only to initialize the ladder to the actual capital allocated to this lane.

Status:
```bash
curl -s http://127.0.0.1:8788/
```
