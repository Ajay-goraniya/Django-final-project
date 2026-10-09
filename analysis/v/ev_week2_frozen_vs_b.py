"""FROZEN vs arm (b) on WEEK 2 - held out for both, since both were fitted on week 1.

Same coefficients, same scaler, same direction call; only the isotonic differs. So every
difference in this table is the EV threshold deciding which candles clear, nothing else.
"""
import importlib.util, json, sys
import numpy as np, pandas as pd
R = "/home/user/Django-final-project"
S = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/cmp"
spec = importlib.util.spec_from_file_location("v10", S + "/v10_head.py")
v10 = importlib.util.module_from_spec(spec); sys.modules["v10"] = v10; spec.loader.exec_module(v10)

d = pd.read_parquet(R + "/analysis/h1/r26/week2_features.parquet")
pv = d.p_venue.clip(0.02, 0.98)
d["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
d["mv_x_sec"] = d.move_bps * d.sec_left / 300.0
d["lv_x_sec"] = d.lv * d.sec_left / 300.0
FEAT = json.load(open(R + "/learner/v12_2/model_v10.json"))["features"]

class Row:
    def __init__(self, f): self.f = f
    def features(self, *a, **k): return self.f

rows = []
for r in d.sort_values(["epoch", "offset"]).itertuples(index=False):
    f = {k: float(getattr(r, k)) for k in FEAT}
    ok = bool(np.isfinite(r.ask_up) and np.isfinite(r.ask_dn) and 0 < r.ask_up < 1 and 0 < r.ask_dn < 1)
    f.update(_ask_up=float(r.ask_up), _ask_dn=float(r.ask_dn), _venue_ok=ok,
             sec_left=float(r.sec_left), p_venue=float(r.p_venue))
    rows.append((str(r.date), int(r.epoch), int(r.y), f))
print("week 2: %d rows, %d candles, %s..%s" % (len(rows), d.epoch.nunique(), d.date.min(), d.date.max()))

MODELS = {"frozen": v10.Model(R + "/learner/v12_2/model_v10.json"),
          "arm b ": v10.Model(R + "/analysis/h1/r26/model_b_week1.json")}

def run(m, thr, slip=0.0):
    out, seen = [], set()
    for day, ep, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0, ev_threshold=thr)
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            paid = min(0.99, ask + slip)
            win = (side == "UP") == (y == 1)
            out.append((day, ep, win, (1.0 / m.cost(paid) - 1.0) if win else -1.0))
    return pd.DataFrame(out, columns=["date", "epoch", "win", "pnl"])

GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
print("\nno slippage. rows = EV threshold")
print(f"{'thr':>6} | {'frozen n':>8} {'total':>8} {'per$1':>7} | {'b n':>6} {'total':>8} {'per$1':>7} | {'b-frozen':>8}")
keep = {}
for thr in GRID:
    A, B = run(MODELS["frozen"], thr), run(MODELS["arm b "], thr)
    keep[thr] = (A, B)
    print(f"{thr:6.2f} | {len(A):8d} {A.pnl.sum():+8.2f} {A.pnl.mean():+7.4f} | "
          f"{len(B):6d} {B.pnl.sum():+8.2f} {B.pnl.mean():+7.4f} | {B.pnl.sum()-A.pnl.sum():+8.2f}")

print("\nflatness across 0.10-0.30 (the question that matters):")
for tag, i in (("frozen", 0), ("arm b", 1)):
    tot = [keep[t][i].pnl.sum() for t in (0.10, 0.15, 0.20, 0.25, 0.30)]
    n = [len(keep[t][i]) for t in (0.10, 0.15, 0.20, 0.25, 0.30)]
    print(f"  {tag:7s} total {min(tot):+.2f}..{max(tot):+.2f} (spread {max(tot)-min(tot):.2f}), "
          f"fires {min(n)}..{max(n)} ({max(n)/max(min(n),1):.1f}x)")

print("\nslippage, total PnL at the shipped regime rule (no override):")
def run_default(m, slip):
    out, seen = [], set()
    for day, ep, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0)
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            paid = min(0.99, ask + slip)
            win = (side == "UP") == (y == 1)
            out.append((day, (1.0 / m.cost(paid) - 1.0) if win else -1.0))
    return pd.DataFrame(out, columns=["date", "pnl"])
print(f"{'slip':>5} | {'frozen n':>8} {'total':>8} {'pos/d':>6} | {'b n':>6} {'total':>8} {'pos/d':>6}")
for s in (0.0, 0.01, 0.02, 0.03, 0.05):
    A, B = run_default(MODELS["frozen"], s), run_default(MODELS["arm b "], s)
    da, db = A.groupby("date").pnl.sum(), B.groupby("date").pnl.sum()
    print(f"{int(s*100):4d}c | {len(A):8d} {A.pnl.sum():+8.2f} {int((da>0).sum()):3d}/{len(da)} | "
          f"{len(B):6d} {B.pnl.sum():+8.2f} {int((db>0).sum()):3d}/{len(db)}")
