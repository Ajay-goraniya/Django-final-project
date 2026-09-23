# EF step 6 (EV pricing) - checked against the running code, V 09-23 03:0x UTC

**Live code path.** `poly_core.order_plan` judges EV at ask + EV_REFERENCE_PAD (1 tick = 0.001) with the venue fee
f = rate*(p(1-p))^exp (rate 0.07, exp 1), cost = max(px+f, px/(1-f/px)), fire if p/cost - 1 >= threshold. v10's own
`cost(q) = q/(1-0.07(1-q))` agrees to <0.001 at every price. London's first fill confirms the fee: 11.43 sh @ 0.42,
fee 0.195 = 0.07*0.42*0.58 per share. **No bug in the EV maths.**

**Correction to V's own tables.** Earlier backtests used a flat 1.67%-of-payout fee shortcut. The exact venue fee,
paid inside the stake, lowers fixed15's 9-day paper profit at $5 from +$512 to **+$476** (-7%). Drawdown unchanged.

**EV bar, whole grid, exact fees, $5, 9 days** (raw rows exist only where the old paper engine fired, EV >= 0.15,
so raw bars below 0.15 cannot be tested and fixed bars below 0.15 are a lower bound):
| arm | bar | /day | right | profit | maxDD | losing days |
|---|---|---|---|---|---|---|
| fixed | 0.05 | 86.0 | 53.7% | +745 | 82 | 1 |
| fixed | 0.10 | 60.7 | 54.4% | +644 | 71 | 1 |
| fixed | **0.15 live** | 31.2 | 56.9% | +476 | 33 | 1 |
| fixed | 0.20 | 16.6 | 51.7% | +241 | 20 | 2 |
| fixed | 0.25 | 8.2 | 55.4% | +196 | 22 | 1 |
| fixed | 0.30 | 5.9 | 52.8% | +143 | 22 | 2 |
| raw | 0.15 | 117.0 | 52.3% | +692 | 92 | 1 |
| raw | 0.25 | 63.2 | 52.5% | +637 | 71 | 1 |
| raw | 0.30 | 33.4 | 52.8% | +483 | 41 | 1 |
Profit falls monotonically with the bar; accuracy does not rise with it (non-monotone, 51.7-56.9%). The bar is a
frequency/drawdown dial, not an accuracy dial. 0.15 has the best profit per $ of drawdown (14.4) - flagged: it is
also the value already chosen, so that ratio is not evidence for it.

**Slippage stress, exact fees, $5** (pay more than the recorded ask on every fill):
fixed15: +0c +476 | +1c +430 | +2c +387 | +3c +345 | +5c +268 - still positive at +5c, DD 33->37.
raw25:   +0c +637 | +1c +554 | +2c +475 | +3c +401 | +5c +261.
London's live retries cost about one tick (0.001), not a cent, so execution slippage is not the risk here.
