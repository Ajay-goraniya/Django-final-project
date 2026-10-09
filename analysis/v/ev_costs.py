"""The same grid, but paying MORE than the quoted ask. The live haircut is 27x
(+0.3817 backtest at thr 0.25 vs +0.0138 live), so the quoted-ask grid cannot be
acted on until it survives realistic slippage. Cheap trades sit closest to fair,
so they should die first - that is the thing to check, not the peak."""
import importlib.util, json, sys
import numpy as np, pandas as pd
S = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/cmp"
MJ = "/home/user/Django-final-project/learner/v12_2/model_v10.json"
spec = importlib.util.spec_from_file_location("v10", S + "/v10_head.py")
v10 = importlib.util.module_from_spec(spec); sys.modules["v10"] = v10; spec.loader.exec_module(v10)
d = pd.read_parquet(S + "/f8.parquet")
pv = d.p_venue.clip(0.02, 0.98)
d["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
d["mv_x_sec"] = d.move_bps * d.sec_left / 300.0
d["lv_x_sec"] = d.lv * d.sec_left / 300.0
FEAT = json.load(open(MJ))["features"]
class Row:
    def __init__(self, f): self.f = f
    def features(self, *a, **k): return self.f
rows = []
for r in d.sort_values(["epoch", "offset"]).itertuples(index=False):
    f = {k: float(getattr(r, k)) for k in FEAT}
    ok = bool(np.isfinite(r.ask_up) and np.isfinite(r.ask_dn) and 0 < r.ask_up < 1 and 0 < r.ask_dn < 1)
    f.update(_ask_up=float(r.ask_up), _ask_dn=float(r.ask_dn), _venue_ok=ok,
             sec_left=float(r.sec_left), p_venue=float(r.p_venue))
    rows.append((r.date, int(r.epoch), int(r.y), f))
m = v10.Model(MJ)

def run(thr, slip):
    out, seen = [], set()
    for day, ep, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0, ev_threshold=thr)
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            paid = min(0.99, ask + slip)                 # we cross, we pay up
            win = (side == "UP") == (y == 1)
            out.append((day, (1.0 / m.cost(paid) - 1.0) if win else -1.0))
    return pd.DataFrame(out, columns=["date", "pnl"])

print("total PnL (on $1 a trade), rows = EV threshold, columns = cents paid over the quoted ask")
slips = [0.00, 0.01, 0.02, 0.03, 0.05]
print(f"{'thr':>6} {'n':>5} " + " ".join(f"{int(s*100):>8}c" for s in slips))
for thr in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
    cells, n = [], None
    for s in slips:
        F = run(thr, s); n = len(F); cells.append(F.pnl.sum())
    print(f"{thr:6.2f} {n:5d} " + " ".join(f"{c:+9.2f}" for c in cells))
print("\npositive days out of 8, same layout:")
print(f"{'thr':>6} " + " ".join(f"{int(s*100):>8}c" for s in slips))
for thr in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
    cells = []
    for s in slips:
        F = run(thr, s); b = F.groupby("date").pnl.sum(); cells.append(int((b > 0).sum()))
    print(f"{thr:6.2f} " + " ".join(f"{c:>9d}" for c in cells))

# What does the shipped REGIME rule (low .15 / mid .25 / high .25 by rv60) buy over a flat dial?
print("\nregime rule as shipped vs flat, total PnL on $1 a trade:")
def run_default(slip):
    out, seen = [], set()
    for day, ep, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0)          # no override: regime thresholds apply
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            paid = min(0.99, ask + slip)
            win = (side == "UP") == (y == 1)
            out.append((day, (1.0 / m.cost(paid) - 1.0) if win else -1.0))
    return pd.DataFrame(out, columns=["date", "pnl"])
for s in [0.0, 0.01, 0.02, 0.03, 0.05]:
    F = run_default(s); b = F.groupby("date").pnl.sum()
    print(f"  slip {int(s*100)}c: n={len(F)} total {F.pnl.sum():+8.2f} per$1 {F.pnl.mean():+.4f} pos {int((b>0).sum())}/8")
