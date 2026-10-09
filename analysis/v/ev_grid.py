"""EV-threshold grid on the FROZEN model - the one that is actually live.

Whole grid, every cell reported, per day as well as pooled. No best cell picked.
"""
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
print("live default: thr=%.2f regime=%s" % (m.thr, m.regime.get("thresholds") if m.regime else None))

def run(thr):
    out, seen = [], set()
    for day, ep, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0, ev_threshold=thr)
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            win = (side == "UP") == (y == 1)
            out.append((day, ep, win, (1.0 / m.cost(ask) - 1.0) if win else -1.0))
    return pd.DataFrame(out, columns=["date", "epoch", "win", "pnl"])

print(f"{'thr':>6} {'n':>5} {'hit%':>6} {'per$1':>8} {'total':>9} {'H1':>8} {'H2':>8}  worst day")
grid = {}
for thr in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
    F = run(thr); grid[thr] = F
    if F.empty: print(f"{thr:6.2f} {0:5d}"); continue
    h = len(F) // 2
    byday = F.groupby("date").pnl.sum()
    print(f"{thr:6.2f} {len(F):5d} {100*F.win.mean():6.1f} {F.pnl.mean():+8.4f} {F.pnl.sum():+9.2f} "
          f"{F.pnl[:h].mean():+8.4f} {F.pnl[h:].mean():+8.4f}  {byday.min():+7.2f} ({byday.idxmin()}) "
          f"pos {int((byday>0).sum())}/{len(byday)}")

print("\nper-day total at each threshold (rain or sun):")
days = sorted(d.date.unique())
print("  thr  " + "  ".join(x[5:] for x in days))
for thr, F in grid.items():
    if F.empty: continue
    b = F.groupby("date").pnl.sum().reindex(days).fillna(0)
    print(f" {thr:5.2f}  " + "  ".join(f"{v:+6.1f}" for v in b))
