# M31 PREREG (V, 10-03 ~03:0x) - EF brain v2 = TWAP first + order flow for the unfinished part. HISTORY ONLY, nothing live.
Owner 10-03: "most importantly we need to follow twap"; research: order-flow imbalance predicts seconds..~1 min ahead.
V's rule now: test only inputs that can know something the market price doesn't. Owner's rule: pass on history first.

DATA: 09-22 19:30..now (real Chainlink ref + tape1s up_ask/dn_ask + gamma/venue outcome) - the only window with the
settlement feed. Order flow from data.binance.vision aggTrades (spot BTCUSDT + perp), per second. Label = venue resolution.
Gate 0: our computed TWAP60(close) vs TWAP60(open) direction must agree with the venue resolution >= 97% - report it.

DECISION SECONDS (fixed): 240, 250, 260, 270, 280 (inside the closing TWAP window 240-300).
FEATURES: locked = mean Chainlink over [240, s); need = what the remaining (300-s) s must average for UP;
  dist = (locked-projected close TWAP - open TWAP) in bps; vol_30s; OFI_5/15/30 s = (buy-sell taker vol)/(total), spot and perp;
  Chainlink-minus-Binance gap now. Market: mid and ask of each side at s (+1 s latency on the ask paid).

STEP 0 (stop/go, walk-forward by day, train on earlier days only):
  M0 = market mid only;  M1 = M0 + TWAP lock-in math;  M2 = M1 + order flow (+ CL gap).
  Report out-of-sample logloss of each and the PAIRED test (McNemar on side calls where they differ). If M2 does not beat M1
  out of sample (paired p<0.05) -> STOP, flow adds nothing the price lacks; no brain is built.
STEP 1 (only if step 0 passes): trade M2's side when p - ask - fee >= margin, first qualifying second per candle.
  Margins grid FIXED: 0.03, 0.05, 0.07, 0.10 - all reported, no best cell. Taker at real ask +1 s, fee 0.07p(1-p).
  Report per margin: n, W/L, $@10, per $1, maxDD, per-day table, green days, halves, +1c costs, nulls (M0 and M1 same rule).
PASS = per $1 > 0 at +1c AND both halves same sign AND >= 70% green days AND beats M1-rule paired AND verify.py clean.
n < 60 = INSUFFICIENT. Result file: analysis/zurich/M31_TWAP_FLOW_BRAIN.txt.

## AMENDMENT 10-03 02:5x (owner: "do it in parts, if one fails stop and try another method, same base") - fail fast
Base fixed for every variant: TWAP lock-in at s in {240..280}, graded on venue resolution, gate 0 first.
Variants, in THIS order, each a stop/go on STEP 0 (beats M1 = market + TWAP math, out of sample, paired):
  V1 order flow (OFI spot+perp 5/15/30 s)   V2 Chainlink-vs-Binance gap (feed catching up)
  V3 perp-minus-spot move last 5/15 s (perp leads)   V4 vol-scaled TWAP remainder probability vs market (pure math)
Speed: run each on the first 3 days first; if clearly flat (no logloss gain) stop it there and move on; only a variant that
shows gain gets the full window + STEP 1. All variants tried are reported (count them - 4 tries means 4 chances of luck).
AMENDMENT 2 (owner 02:5x: "first the hardest dataset"): the 3-day quick test uses the WORST days for our models inside the
Chainlink window, not the first 3: 09-23 (FAV_mid -163.89, FAV -34.79), 09-25 (FAV -65.94 worst day, FAV_mid -100.33),
10-02 (every FAV arm negative, London maker fresh lows). A variant must show gain on these before it gets the full window.
