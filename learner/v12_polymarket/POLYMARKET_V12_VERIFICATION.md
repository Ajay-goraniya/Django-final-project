# v12 verification

## Bundled v10 paper database snapshot
`results/v10_long4_polymarket_paper.sqlite3` contains 413 graded fires:
- wins: 216
- losses: 197
- win rate: 52.30%
- fixed paper stake: $4,130 total ($10/fire)
- summed PnL in this database snapshot: **+$477.95**

UTC breakdown in the bundled DB:
- 2026-09-08: 46 fires, 29 wins, **+$129.91**
- 2026-09-09: 136 fires, 69 wins, **+$105.77**
- 2026-09-10: 159 fires, 82 wins, **+$202.70**
- 2026-09-11: 72 fires, 36 wins, **+$39.57** (partial-day snapshot)

The target README reports a later paper snapshot of +$517.9. The two uploaded ZIPs contain different SQLite checkpoints: the main packaged snapshot above is +$477.95 / 413 graded, while the alternate uploaded snapshot (`results/v10_long4_polymarket_paper_alt_snapshot.sqlite3`) is +$497.95 / 411 graded. Neither is byte-for-byte the README's +$517.9 checkpoint, so all three are kept distinct instead of silently mixing them.

## Local code checks
- `python -m py_compile engine/btc_model_v12_polymarket.py engine/test_v12_polymarket.py`: PASS
- `python engine/test_v12_polymarket.py`: PASS
- Tested: tick rounding, stake ladder boundaries, 2-check step-up/immediate step-down, threshold recheck, EV falls as entry price worsens, SQLite metadata persistence.

## Not claimed
- No real order was submitted from this environment.
- Live fill rate and live slippage are not claimed until a funded smoke test exists.
