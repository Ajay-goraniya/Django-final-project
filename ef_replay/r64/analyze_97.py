#!/usr/bin/env python3
"""Head-to-head on the candles both builds have covered so far, repriced at real Polymarket ladders."""
import json, sqlite3, pathlib, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq
R = pathlib.Path("/home/user/Django-final-project"); sys.path.insert(0, str(R / "ef_arch/polymarket/fiveday"))
from hybrid_stake import run_hybrid
W0 = 1785542400
def cost(q, r): return q / (1.0 - r * (1.0 - q))
def classify(adx, wick, crosses, vol):
    if vol >= 2.5: return "HIGH_VOL"
    if adx >= 25.0 and wick < 0.30: return "TRENDING"
    if wick > 0.50 or crosses > 3: return "RANGING"
    return "NEUTRAL"
L = pq.read_table(R / "ef_arch/polymarket/polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (float(r.vwap_s10) if r.fill_ok_s10 else np.nan, float(r.best_ask)) for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}
def load(db, label, want_regime=False):
    c = sqlite3.connect(db); out = []
    for cid, side, ts, feat in c.execute("select candle_id, direction, ts_ms, features from ef_predictions order by ts_ms"):
        ep = cid // 1000; o = max(5, min(295, int(((ts - cid) / 1000) // 5 * 5)))
        q, ba = lad.get((ep, side, o), (np.nan, np.nan))
        reg = None
        if want_regime and feat:
            f = json.loads(feat)
            reg = classify(abs(f.get("path_efficiency", 0.0)) * 100.0,
                           f.get("upper_wick_ratio", 0.0) + f.get("lower_wick_ratio", 0.0),
                           f.get("open_cross_count", 0.0), f.get("volume_ratio", 1.0))
        out.append(dict(build=label, cid=cid, ep=ep, side=side, off=o, sec=(ts - cid) / 1000.0, q=q,
                        best_ask=ba, win=(outcome.get(ep) == side), regime=reg))
    return pd.DataFrame(out)
A = load(R / "ef_replay/r64/replay_r64_full.sqlite3", "r6.4", want_regime=True)
B = load(R / "ef_replay/deliver/build36_replay_2026-08-01.sqlite3", "Build36")
NC = 97; last_ep = W0 + 300 * (NC - 1)
A = A[A.ep <= last_ep]; B = B[B.ep <= last_ep]
print("=" * 100); print(f"EF HEAD-TO-HEAD  2026-08-01 first {NC} candles (00:00-08:00 UTC)  same data, same real Polymarket asks, MASTER OFF"); print("=" * 100)
print(f"{'build':<9}{'fires':>6}{'/100':>7}{'acc%':>7}{'avg q':>7}{'avg s':>7}{'PnL/100 f0':>12}{'PnL/100 f7':>12}{'fix$5 f0':>10}{'hyb$50 f0':>11}{'hyb$50 f7':>11}{'maxDD':>8}")
for D, nm in ((A, "r6.4"), (B, "Build36")):
    d = D[np.isfinite(D.q)]
    if d.empty: print(f"{nm:<9}{0:>6}"); continue
    tr = [((lambda s, qq=qq: (float(qq), 1e9)), bool(w)) for qq, w in zip(d.q, d.win)]
    p0 = np.where(d.win, 1 / cost(d.q, 0.0) - 1, -1.0); p7 = np.where(d.win, 1 / cost(d.q, 0.07) - 1, -1.0)
    h0, _, _, _ = run_hybrid(tr, 0.0); h7, _, _, _ = run_hybrid(tr, 0.07)
    print(f"{nm:<9}{len(D):>6}{100*len(D)/NC:>7.1f}{100*d.win.mean():>7.1f}{d.q.mean():>7.3f}{d.sec.mean():>7.1f}"
          f"{100*p0.sum()/NC:>+12.2f}{100*p7.sum()/NC:>+12.2f}{5*p0.sum():>+10.2f}{h0['end']:>11.2f}{h7['end']:>11.2f}{h0['maxdd']:>8.2f}")
print(f"\ncandles where both fired {len(set(A.cid)&set(B.cid))}   r6.4 only {len(set(A.cid)-set(B.cid))}   Build36 only {len(set(B.cid)-set(A.cid))}")
d = A[np.isfinite(A.q)]
print(f"\nr6.4 BY REGIME (label recomputed with the model's own classify_regime from the stored fire features):")
print(f"{'regime':<10}{'fires':>6}{'acc%':>7}{'avg q':>7}{'PnL/fire f0':>13}{'PnL/fire f7':>13}{'total f0':>10}")
for reg, g in d.groupby("regime"):
    p0 = np.where(g.win, 1 / cost(g.q, 0.0) - 1, -1.0); p7 = np.where(g.win, 1 / cost(g.q, 0.07) - 1, -1.0)
    print(f"{reg:<10}{len(g):>6}{100*g.win.mean():>7.1f}{g.q.mean():>7.3f}{p0.mean():>+13.3f}{p7.mean():>+13.3f}{p0.sum():>+10.2f}")
print(f"\nr6.4 BY HOUR:")
d = d.copy(); d["h"] = (d.ep - W0) // 3600
for h, g in d.groupby("h"):
    p0 = np.where(g.win, 1 / cost(g.q, 0.0) - 1, -1.0)
    print(f"  h{h:02d}  fires {len(g):>2}  acc {100*g.win.mean():>5.1f}%  avg q {g.q.mean():.3f}  PnL {p0.sum():+6.2f}  regimes {g.regime.value_counts().to_dict()}")
A.to_csv(R / "ef_replay/r64/r64_fires_97.csv", index=False)
print("\nLABEL: 97 of 288 candles. EF signal untouched in both builds. Real $10 ask-ladder VWAP at the 5 s grid point at or before each fire; market's own Chainlink outcome.")
