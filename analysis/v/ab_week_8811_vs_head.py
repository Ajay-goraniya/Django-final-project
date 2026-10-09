"""12.8.11 vs HEAD: both builds' own decide(), same 8 days of real features.

No reimplementation of the EV rule - each build runs its own Model.decide() on a
state whose features() hands back the precomputed row, so any difference in the
decision path shows up as a different fire, side, offset or price.
"""
import importlib.util, json, sys, types
import numpy as np, pandas as pd

S = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/cmp"
MJ = "/home/user/Django-final-project/learner/v12_2/model_v10.json"

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m); return m

old, new = load("v10_8811", S + "/v10_8811.py"), load("v10_head", S + "/v10_head.py")

d = pd.read_parquet(S + "/f8.parquet")
pv = d.p_venue.clip(0.02, 0.98)
d["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
d["mv_x_sec"] = d.move_bps * d.sec_left / 300.0
d["lv_x_sec"] = d.lv * d.sec_left / 300.0
FEAT = json.load(open(MJ))["features"]

class Row:
    """Stands in for FeatureState: features() returns the row already built."""
    def __init__(self, f): self.f = f
    def features(self, *a, **k): return self.f

def rows_for(df):
    out = []
    for r in df.itertuples(index=False):
        f = {k: float(getattr(r, k)) for k in FEAT}
        ok = bool(np.isfinite(r.ask_up) and np.isfinite(r.ask_dn)
                  and 0 < r.ask_up < 1 and 0 < r.ask_dn < 1)
        f.update(_ask_up=float(r.ask_up), _ask_dn=float(r.ask_dn),
                 _venue_ok=ok, sec_left=float(r.sec_left), p_venue=float(r.p_venue))
        out.append((int(r.epoch), int(r.offset), int(r.y), f))
    return out

def run(mod, rows):
    m = mod.Model(MJ)
    fires, seen = [], set()
    for ep, off, y, f in rows:
        if ep in seen: continue
        dec = m.decide(Row(f), 0, 0)
        if dec.get("fire"):
            seen.add(ep)
            side = dec["side"]; ask = f["_ask_up"] if side == "UP" else f["_ask_dn"]
            win = (side == "UP") == (y == 1)
            fires.append(dict(epoch=ep, off=off, side=side, p=round(dec["p"], 6),
                              ask=ask, ev=round(dec.get("ev", float("nan")), 6),
                              pnl=(1.0 / m.cost(ask) - 1.0) if win else -1.0, win=win))
    return pd.DataFrame(fires)

rows = rows_for(d.sort_values(["epoch", "offset"]))
print("rows %d, candles %d, days %s..%s" % (len(rows), d.epoch.nunique(), d.date.min(), d.date.max()))
A, B = run(old, rows), run(new, rows)

def line(tag, F):
    if F.empty: return f"{tag}: no fires"
    return (f"{tag}: n={len(F)} W={int(F.win.sum())} ({100*F.win.mean():.1f}%) "
            f"pnl/$1={F.pnl.mean():+.4f} total(on $1 each)={F.pnl.sum():+.2f}")
print(line("12.8.11 ", A)); print(line("HEAD    ", B))

same_set = set(A.epoch) == set(B.epoch)
print("same candles fired:", same_set, "| A only:", len(set(A.epoch) - set(B.epoch)),
      "| B only:", len(set(B.epoch) - set(A.epoch)))
if same_set and not A.empty:
    M = A.merge(B, on="epoch", suffixes=("_a", "_b"))
    for col in ("side", "off", "p", "ask"):
        diff = (M[col + "_a"] != M[col + "_b"]).sum()
        print(f"  differing {col}: {diff} of {len(M)}")
    print("  max |p_a - p_b| = %.3g" % (M.p_a - M.p_b).abs().max())
    print("  pnl difference total: %+.6f" % (M.pnl_a.sum() - M.pnl_b.sum()))

# halves, on whichever arm has fires
for tag, F in (("12.8.11", A), ("HEAD", B)):
    if len(F) >= 2:
        h = len(F) // 2
        print(f"  halves {tag}: H1 {F.pnl[:h].mean():+.4f} / H2 {F.pnl[h:].mean():+.4f}")
