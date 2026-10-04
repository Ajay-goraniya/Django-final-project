#!/usr/bin/env python3
"""evaluate.py -- stress the out-of-sample predictions the way every earlier
'result' was stressed: cheap-entry dependence, day-by-day consistency,
real-order-book-only significance, and the fixed 100-candle sample."""
import json, pathlib, sys
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from train import trade_sim, summarize, cost

ROOT = pathlib.Path(__file__).resolve().parent
df = pd.read_parquet(ROOT / "oof_predictions.parquet")
MODEL = sys.argv[1] if len(sys.argv) > 1 else json.load(open(ROOT / "train_summary.json"))["best"]
THR = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
p = df[MODEL.replace("/", "__")].values
n_c = df.epoch.nunique()
print(f"model {MODEL}   EV threshold {THR}   {n_c} candles\n")

t = trade_sim(df, p, THR)


def line(lbl, tt, nc=None):
    s = summarize(tt, nc or n_c)
    if not s["trades"]:
        print(f"  {lbl:34} no trades"); return
    print(f"  {lbl:34} n={s['trades']:4}  acc {s['acc']:5.1f}%  ask {s['ask']:.3f}  "
          f"PnL ${s['pnl']:+8.2f}  /trade {s['per_trade']:+.3f}  t={s['t']}")


print("1. CHEAP-ENTRY DEPENDENCE (the artifact that killed r6.4's +$465)")
line("all trades", t)
line("entries >= 0.15", t[t.ask >= 0.15])
line("entries >= 0.25", t[t.ask >= 0.25])
line("entries 0.25 - 0.75", t[(t.ask >= 0.25) & (t.ask <= 0.75)])
print(f"  share of PnL from entries < 0.15: {100*t[t.ask<0.15].pnl.sum()/t.pnl.sum():.0f}%   (r6.4 was 90%)\n")

print("2. REAL ORDER BOOK ONLY (no inferred prices anywhere in the fill)")
line("book fills", t[t.is_book == 1])
line("book fills, entries >= 0.15", t[(t.is_book == 1) & (t.ask >= 0.15)])
print()

print("3. DAY BY DAY (each day predicted by a model that never saw it)")
tt = t.merge(df[["epoch", "date"]].drop_duplicates(), on="epoch")
print(f"  {'day':12}{'trades':>7}{'acc':>8}{'ask':>7}{'PnL $':>9}")
for d, g in tt.groupby("date"):
    print(f"  {d:12}{len(g):>7}{100*g.win.mean():>7.1f}%{g.ask.mean():>7.3f}{g.pnl.sum():>+9.2f}")
pos = (tt.groupby("date").pnl.sum() > 0).sum()
print(f"  positive days: {pos}/{tt.date.nunique()}\n")

print("4. BY DECISION SECOND")
print(f"  {'offset':>7}{'trades':>7}{'acc':>8}{'ask':>7}{'PnL $':>9}")
for o, g in t.groupby("offset"):
    print(f"  {o:>6}s{len(g):>7}{100*g.win.mean():>7.1f}%{g.ask.mean():>7.3f}{g.pnl.sum():>+9.2f}")
print()

print("5. THE FIXED 100-CANDLE SAMPLE (same candles r6.4 and v9.6 were scored on)")
sel = json.load(open(ROOT.parent / "week_replay" / "candles100.json"))["candles"]
eps = {int(c["epoch"]) for c in sel}
sub = df[df.epoch.isin(eps)]
for thr in (0.0, 0.15, THR):
    tt = trade_sim(sub, sub[MODEL.replace("/", "__")].values, thr)
    line(f"thr {thr:.2f}", tt, 100)
print(f"\n  for reference on the same 100 candles:  r6.4  99 trades 39.4% +$465 (+$48 excl <0.15)   v9.6  73 trades 46.6% +$0.67")

print("\n6. FREQUENCY DIAL  (what each threshold gives you per day)")
print(f"  {'thr':>5}{'trades/day':>11}{'acc':>8}{'PnL/day':>9}{'t':>6}")
for thr in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
    tt = trade_sim(df, p, thr); s = summarize(tt, n_c)
    if s["trades"]:
        print(f"  {thr:>5.2f}{s['trades']/8:>11.1f}{s['acc']:>7.1f}%{s['pnl']/8:>+9.2f}{str(s['t']):>6}")
