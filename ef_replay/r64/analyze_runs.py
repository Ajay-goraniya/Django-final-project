#!/usr/bin/env python3
"""
analyze_runs.py -- static r6.4 vs routed r6.4 on the real causal 2026-08-01 replay.
Reads the run databases directly (runs may be stopped early), recomputes each candle's router
bucket offline from the same closed-candle inputs the live router used (the router is a pure
function of completed candles, so this reproduces it exactly), joins every fire to the real
Polymarket BTC-5m ask ladder, and settles on that market's own Chainlink outcome.
"""
import sqlite3, pathlib, sys, collections
import numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent; R = HERE.parents[1]
sys.path.insert(0, str(R / "ef_arch/polymarket/fiveday")); sys.path.insert(0, str(HERE))
from hybrid_stake import run_hybrid
import market_router as MR
W0 = 1785542400
def cost(q, r): return q / (1.0 - r * (1.0 - q))

L = pq.read_table(R / "ef_arch/polymarket/polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (float(r.vwap_s10) if r.fill_ok_s10 else np.nan, float(r.best_ask)) for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

# ---- offline reproduction of each router's per-candle bucket ----
CS = pd.read_parquet(HERE / "candle_stats_2026-08-01.parquet")
kl = pq.read_table(R / "btc_replay_2026-08-01_24h/normalized/spot_klines_5m.parquet").to_pandas()
def buckets_clean6():
    r = MR.Clean6Router(); out = {}
    for row in CS.itertuples():
        b, _, _ = r.bucket(); out[int(row.cid)] = b
        r.add_closed_candle(row.rv, row.eff, row.wick, row.crosses, getattr(row, "dir"), row.body, getattr(row, "range"))
    return out
def buckets_ab(mode):
    r = MR.MarketRouter(); out = {}
    for row in kl.itertuples():
        b, _, _ = r.bucket(mode); out[int(row.open_time // 1000)] = b
        r.add_closed_candle(row.open, row.high, row.low, row.close, row.volume)
    return out
BUCK = {"routerA": buckets_ab("A"), "routerB": buckets_ab("B"), "clean6": buckets_clean6(), "static": {}}

def load(tag):
    db = HERE / f"run_{tag}.sqlite3"
    if not db.exists(): return None, None
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ncand = c.execute("select count(*) from candles").fetchone()[0]
    rows = []
    for cid, side, ts, corr in c.execute("select candle_id, direction, ts_ms, correct from ef_predictions order by ts_ms"):
        ep = cid // 1000; sec = (ts - cid) / 1000.0
        o = max(5, min(295, int(sec // 5 * 5)))
        q, ba = lad.get((ep, side, o), (np.nan, np.nan))
        rows.append(dict(cid=cid, ep=ep, side=side, sec=sec, off=o, q=q, best_ask=ba,
                         win=(outcome.get(ep) == side), binance_ok=corr,
                         bucket=BUCK[tag].get(cid) if tag in BUCK else None))
    return pd.DataFrame(rows), ncand

runs = {t: load(t) for t in ("static", "routerA", "routerB", "clean6")}
runs = {k: v for k, v in runs.items() if v[0] is not None}
import os
NC = int(os.environ.get("NCAND", min(v[1] for v in runs.values())))
LAST = W0 + 300 * (NC - 1)
print("=" * 112)
print(f"R6.4 STATIC vs ROUTED - REAL CAUSAL REPLAY 2026-08-01 - common window: first {NC} candles (00:00-{(NC*5)//60:02d}:{(NC*5)%60:02d} UTC)")
print("=" * 112)
hdr = f"{'run':<10}{'fires':>6}{'/100':>7}{'PM acc%':>9}{'Bin acc%':>9}{'avg q':>7}{'avg s':>7}{'PnL/100 f0':>12}{'PnL/100 f7':>12}{'fix$5':>9}{'hyb$50 f0':>11}{'hyb f7':>9}{'maxDD':>8}"
print(hdr)
S = {}
for tag in ("static", "routerA", "routerB", "clean6"):
    if tag not in runs: continue
    D = runs[tag][0]; D = D[D.ep <= LAST]; d = D[np.isfinite(D.q)]
    if d.empty: continue
    tr = [((lambda s, qq=qq: (float(qq), 1e9)), bool(w)) for qq, w in zip(d.q, d.win)]
    p0 = np.where(d.win, 1 / cost(d.q, 0.0) - 1, -1.0); p7 = np.where(d.win, 1 / cost(d.q, 0.07) - 1, -1.0)
    h0, _, _, _ = run_hybrid(tr, 0.0); h7, _, _, _ = run_hybrid(tr, 0.07)
    bacc = 100 * D.binance_ok.dropna().mean() if D.binance_ok.notna().any() else float("nan")
    S[tag] = dict(D=D, d=d, fires=len(D), per100=100 * len(D) / NC, pmacc=100 * d.win.mean(), binacc=bacc,
                  q=d.q.mean(), sec=d.sec.mean(), p0=100 * p0.sum() / NC, p7=100 * p7.sum() / NC,
                  fix=5 * p0.sum(), h0=h0["end"], h7=h7["end"], dd=h0["maxdd"])
    r = S[tag]
    print(f"{tag:<10}{r['fires']:>6}{r['per100']:>7.1f}{r['pmacc']:>9.1f}{r['binacc']:>9.1f}{r['q']:>7.3f}{r['sec']:>7.1f}"
          f"{r['p0']:>+12.2f}{r['p7']:>+12.2f}{r['fix']:>+9.2f}{r['h0']:>11.2f}{r['h7']:>9.2f}{r['dd']:>8.2f}")
print("\nPM acc = accuracy against the market's own Chainlink outcome. Bin acc = r6.4's own grading vs the Binance close.")
print("PnL = CROSS-VENUE EXECUTION PROXY at the real Polymarket $10 ask-ladder VWAP. Not Predict.fun PnL.")
if "static" in S:
    for tag in ("clean6", "routerA", "routerB"):
        if tag in S:
            a, b = S["static"], S[tag]
            print(f"\n{tag} vs static: frequency {a['per100']:.1f} -> {b['per100']:.1f} /100 ({100*(b['per100']-a['per100'])/a['per100']:+.1f}%)   "
                  f"PM accuracy {a['pmacc']:.1f}% -> {b['pmacc']:.1f}% ({b['pmacc']-a['pmacc']:+.2f} pts)   "
                  f"proxy PnL/100 {a['p0']:+.2f} -> {b['p0']:+.2f} ({b['p0']-a['p0']:+.2f})")
# warmup identity check
print("\n" + "=" * 112); print("WARMUP IDENTITY CHECK (router not ready -> static thresholds -> fires must be identical)"); print("=" * 112)
for tag, ready in (("routerA", 37), ("routerB", 37), ("clean6", 8)):
    if tag not in S or "static" not in S: continue
    lim = W0 + 300 * ready
    a = set(map(tuple, S["static"]["D"].loc[S["static"]["D"].ep < lim, ["cid", "side"]].values))
    b = set(map(tuple, S[tag]["D"].loc[S[tag]["D"].ep < lim, ["cid", "side"]].values))
    print(f"  {tag:<9} first {ready:>2} candles: static {len(a)} fires, routed {len(b)} fires, identical: {a == b}")
# per bucket
print("\n" + "=" * 112); print("PERFORMANCE BY ROUTER BUCKET"); print("=" * 112)
for tag in ("clean6", "routerA", "routerB"):
    if tag not in S: continue
    d = S[tag]["d"]
    print(f"\n{tag}:  {'bucket':<18}{'fires':>6}{'PM acc%':>9}{'avg q':>7}{'PnL/fire f0':>13}{'total':>9}")
    for bk, g in d.groupby(d.bucket.apply(lambda x: MR.BUCKET_NAMES.get(x, "WARMUP(static)") if x is not None else "WARMUP(static)")):
        p = np.where(g.win, 1 / cost(g.q, 0.0) - 1, -1.0)
        print(f"{'':<10}{bk:<18}{len(g):>6}{100*g.win.mean():>9.1f}{g.q.mean():>7.3f}{p.mean():>+13.3f}{p.sum():>+9.2f}")
# bucket occupancy + switching
print("\n" + "=" * 112); print("BUCKET OCCUPANCY AND SWITCHING over the common window"); print("=" * 112)
for tag in ("clean6", "routerA", "routerB"):
    if tag not in BUCK or not BUCK[tag]: continue
    seq = [BUCK[tag][c] for c in sorted(BUCK[tag]) if c // 1000 <= LAST]
    act = [x for x in seq if x is not None]
    sw = sum(1 for i in range(1, len(act)) if act[i] != act[i - 1])
    blocks = []; cur = act[0]; n = 1
    for x in act[1:]:
        if x == cur: n += 1
        else: blocks.append(n); cur = x; n = 1
    blocks.append(n)
    cnt = collections.Counter(act)
    print(f"  {tag:<9} warmup {len(seq)-len(act):>2}  " + "  ".join(f"{MR.BUCKET_NAMES[k]}={v}" for k, v in sorted(cnt.items()))
          + f"   switches {sw}, median block {int(np.median(blocks))}, longest {max(blocks)}")
# direction + fire second
print("\n" + "=" * 112); print("DIRECTION SPLIT AND FIRE SECOND"); print("=" * 112)
for tag in ("static", "clean6", "routerA", "routerB"):
    if tag not in S: continue
    d = S[tag]["d"]
    ds = "  ".join(f"{s} n={len(g)} PMacc={100*g.win.mean():.1f}%" for s, g in d.groupby("side"))
    qs = d.sec.quantile([.1, .5, .9]).round(1).tolist()
    print(f"  {tag:<9} {ds}    fire second p10/p50/p90 {qs}")
for tag in S: S[tag]["D"].to_csv(HERE / f"fires_{tag}.csv", index=False)
print("\nLABEL: r6.4 EF source untouched in every run; only the six Early-EF thresholds are swapped by the external router.")
