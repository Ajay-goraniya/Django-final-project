#!/usr/bin/env python3
"""
compare_r64_b36.py -- head-to-head of the 9.1.1-r6.4 EF and the 9.3-Build36 EF on the SAME causal
2026-08-01 day, both MASTER OFF, both repriced at the SAME real Polymarket BTC-5m ask ladders with
the market's own Chainlink outcome, both run through the user's hybrid staking ($50, 10%, 3W/2L).
No signal logic was changed in either build.
"""
import json, pathlib, sqlite3, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq
R = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "ef_arch" / "polymarket" / "fiveday"))
from hybrid_stake import run_hybrid, run_fixed
W0 = 1785542400
def cost(q, r): return q / (1.0 - r * (1.0 - q))     # BUY-fee semantics
L = pq.read_table(R / "ef_arch/polymarket/polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (float(r.vwap_s10) if r.fill_ok_s10 else np.nan,
        float(r.vwap_s100) if r.fill_ok_s100 else np.nan, float(r.best_ask)) for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

def price(ep, side, ts_ms, cid):
    o = max(5, min(295, int(((ts_ms - cid) / 1000) // 5 * 5)))
    return lad.get((ep, side, o), (np.nan, np.nan, np.nan)), o

def rows_from_r64(path):
    j = json.load(open(path)); out = []
    for f in j["fires"]:
        cid = int(f["candle_open_ms"]); ep = cid // 1000; (q10, q100, ba), o = price(ep, f["direction"], int(f["fire_ts_ms"]), cid)
        out.append(dict(build="r6.4", cid=cid, ep=ep, side=f["direction"], off=o, sec=f["fire_second"],
                        q10=q10, q100=q100, best_ask=ba, win=(outcome.get(ep) == f["direction"]),
                        regime=f.get("regime"), p=f.get("settlement_probability")))
    return pd.DataFrame(out), j

def rows_from_db(db, label):
    c = sqlite3.connect(db); out = []
    for cid, side, ts in c.execute("select candle_id, direction, ts_ms from ef_predictions order by ts_ms"):
        ep = cid // 1000; (q10, q100, ba), o = price(ep, side, ts, cid)
        out.append(dict(build=label, cid=cid, ep=ep, side=side, off=o, sec=(ts - cid) / 1000.0,
                        q10=q10, q100=q100, best_ask=ba, win=(outcome.get(ep) == side), regime=None, p=None))
    return pd.DataFrame(out)

A, ja = rows_from_r64(pathlib.Path(__file__).resolve().parent / "replay_r64_full.json")
B = rows_from_db(R / "ef_replay/deliver/build36_replay_2026-08-01.sqlite3", "Build36")
print("=" * 104)
print("EF HEAD-TO-HEAD, 2026-08-01, same data, same real Polymarket ladders, same outcomes, MASTER OFF")
print("=" * 104)
print(f"{'build':<10}{'fires':>6}{'/100':>7}{'acc%':>7}{'avg q':>7}{'avg s':>7}{'PnL/100 f0':>12}{'PnL/100 f7':>12}{'fixed$5 f0':>12}{'hyb$50 f0':>11}{'hyb$50 f7':>11}{'maxDD':>8}")
summ = {}
for D, name in ((A, "r6.4"), (B, "Build36")):
    d = D[np.isfinite(D.q10)]
    tr = [((lambda s, q=q: (float(q), 1e9)), bool(w)) for q, w in zip(d.q10, d.win)]
    line = f"{name:<10}{len(D):>6}{100*len(D)/288:>7.1f}{100*d.win.mean():>7.1f}{d.q10.mean():>7.3f}{d.sec.mean():>7.1f}"
    for r in (0.0, 0.07):
        p = np.where(d.win, 1 / cost(d.q10, r) - 1, -1.0); summ[(name, r)] = p
        line += f"{100*p.sum()/288:>+12.2f}" if r == 0.0 else f"{100*p.sum()/288:>+12.2f}"
    p0 = summ[(name, 0.0)]
    h0, _, _, _ = run_hybrid(tr, 0.0); h7, _, _, _ = run_hybrid(tr, 0.07)
    line += f"{5*p0.sum():>+12.2f}{h0['end']:>11.2f}{h7['end']:>11.2f}{h0['maxdd']:>8.2f}"
    print(line)
print(f"\nboth builds priced: r6.4 {int(np.isfinite(A.q10).sum())}/{len(A)}   Build36 {int(np.isfinite(B.q10).sum())}/{len(B)}")
ov = set(A.cid) & set(B.cid); print(f"candles where BOTH fired: {len(ov)}   r6.4-only: {len(set(A.cid)-set(B.cid))}   Build36-only: {len(set(B.cid)-set(A.cid))}")
# per-hour and per-regime
A["hour"] = (A.ep - W0) // 3600; B["hour"] = (B.ep - W0) // 3600
print("\nr6.4 by hour: fires / accuracy / PnL-per-fire (fee 0):")
g = A[np.isfinite(A.q10)].groupby("hour").apply(lambda d: pd.Series({"fires": len(d), "acc": 100 * d.win.mean(),
     "pnl_per_fire": np.where(d.win, 1 / cost(d.q10, 0.0) - 1, -1.0).mean()}), include_groups=False)
print(g.round(2).to_string())
if A.regime.notna().any():
    print("\nr6.4 by regime label (the classify_regime output at fire time):")
    gr = A[np.isfinite(A.q10)].groupby(A.regime.fillna("")).apply(lambda d: pd.Series({"fires": len(d), "acc": 100 * d.win.mean(),
         "avg_q": d.q10.mean(), "pnl_per_fire_f0": np.where(d.win, 1 / cost(d.q10, 0.0) - 1, -1.0).mean(),
         "pnl_per_fire_f7": np.where(d.win, 1 / cost(d.q10, 0.07) - 1, -1.0).mean()}), include_groups=False)
    print(gr.round(3).to_string())
print("\nr6.4 stats:", {k: ja["stats"][k] for k in ("events", "candles_settled", "ef_inputs_ready_ticks")})
print("r6.4 top blockers:", sorted(ja["blockers"].items(), key=lambda x: -x[1])[:6])
A.to_csv(pathlib.Path(__file__).resolve().parent / "r64_fires_repriced.csv", index=False)
print("\nLABEL: EF signal untouched in both builds. Fills are the real $10 ask-ladder VWAP at the 5 s grid point at or before the fire; outcomes are the market's own Chainlink resolution. One day.")
