# M18 - EF-maker: keep EF's direction, stop paying taker execution (V, 10-01 14:4x, BEFORE running)
Why: every check agrees EF's paper edge dies at London execution (stable-EF: +0.153/$1 paper -> -0.012 London; sessions: both lose at
London exec). The leak is execution: ask paid + taker fee 0.07p(1-p) + slippage. The maker probe buys at the bid with no fee.
Test: for each London real fixed15 fire (analysis/london/M17_FILLS.csv), instead of taking the ask, post a $10 BUY on EF's side at
bid = ask_paid - d, d in {1c, 2c, 3c}, resting W in {30, 60, 120} s after the fire (never past sec 270). FILL = a Polymarket print on
our token STRICTLY BELOW our bid inside the window (trade-through, strict). Filled: shares = 10/bid, no fee, graded on the venue
outcome. Unfilled: $0. Compare with the SAME fires taken at London's real price, scaled to $10.
Grid 9 cells, all reported. Train 09-23..27, sealed test 09-28..10-01 (cell chosen on train, read once on test).
PASS: on the sealed test maker total > 0 AND > taker total on the same fires, both halves of test > 0, >= 60 fills,
and filled-fire win% vs taker win% shown (adverse selection: fills happen when price moves against us).
Nothing deployed; a pass becomes a proposal to the owner.
