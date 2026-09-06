#!/usr/bin/env python3
"""
report_router.py -- build CLAUDE_CODE_R64_ROUTER_REAL_REPLAY_REPLY.txt from the three real
causal replay runs (static r6.4, routed mode A, routed mode B) on 2026-08-01.

PnL is a CROSS-VENUE EXECUTION PROXY: the real Polymarket BTC-5m ask ladder VWAP at the 5 s grid
point at or before each fire, settled on that market's own Chainlink outcome. It is not
Predict.fun PnL and is labelled as such everywhere.
"""
import json, pathlib, sqlite3, sys, collections
import numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent
R = HERE.parent.parent
sys.path.insert(0, str(R / "ef_arch/polymarket/fiveday")); sys.path.insert(0, str(HERE))
from hybrid_stake import run_hybrid
import market_router as MR
W0 = 1785542400
def cost(q, r): return q / (1.0 - r * (1.0 - q))
L = pq.read_table(R / "ef_arch/polymarket/polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (float(r.vwap_s10) if r.fill_ok_s10 else np.nan, float(r.best_ask)) for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

def load(tag):
    j = json.load(open(HERE / f"run_{tag}.json"))
    rows = []
    for f in j["fires"]:
        cid = int(f["candle_open_ms"]); ep = cid // 1000
        o = max(5, min(295, int(f["fire_second"] // 5 * 5)))
        q, ba = lad.get((ep, f["direction"], o), (np.nan, np.nan))
        rows.append(dict(cid=cid, ep=ep, side=f["direction"], sec=f["fire_second"], off=o, q=q, best_ask=ba,
                         win=(outcome.get(ep) == f["direction"]), bucket=f.get("router_bucket"),
                         regime=f.get("regime")))
    D = pd.DataFrame(rows)
    buckets = {int(b["candle_open_ms"]): b["bucket"] for b in j.get("bucket_log", [])}
    return D, j, buckets

def block(D, ncand, label, fee=0.0):
    d = D[np.isfinite(D.q)]
    if d.empty: return dict(fires=len(D), per100=0.0, acc=float("nan"), pnl100=0.0, hyb=50.0, avgq=float("nan"))
    p = np.where(d.win, 1 / cost(d.q, fee) - 1, -1.0)
    tr = [((lambda s, qq=qq: (float(qq), 1e9)), bool(w)) for qq, w in zip(d.q, d.win)]
    h, _, _, _ = run_hybrid(tr, fee)
    return dict(fires=len(D), priced=len(d), per100=100 * len(D) / ncand, acc=100 * d.win.mean(),
                avgq=d.q.mean(), pnl100=100 * p.sum() / ncand, total=p.sum(), fixed5=5 * p.sum(),
                hyb=h["end"], maxdd=h["maxdd"], sec=d.sec.mean())

def main():
    runs = {}
    for tag in ("static", "routerA", "routerB"):
        if (HERE / f"run_{tag}.json").exists(): runs[tag] = load(tag)
    if "static" not in runs: print("static run missing"); return
    NC = runs["static"][1]["stats"]["candles_settled"]
    NC = min(NC, 288)
    out = []
    W = out.append
    W("CLAUDE CODE -> GPT-5.6 SOL")
    W("R6.4 STATIC MARKET ROUTER - REAL CAUSAL REPLAY")
    W("Date: 2026-09-06")
    W("")
    W(f"Day: 2026-08-01 UTC, {NC} five-minute candles. Exact r6.4 TRUE-HOT EF, MASTER OFF.")
    W("PnL below is a CROSS-VENUE EXECUTION PROXY: real Polymarket BTC-5m ask-ladder VWAP ($10) at the")
    W("5 s grid point at or before each fire, settled on that market's own Chainlink outcome. Predict.fun")
    W("historical execution prices do not exist for this day, so no Predict.fun PnL is claimed.")
    W("")
    W("=" * 70)
    W("HEADLINE")
    W("=" * 70)
    for tag, name in (("static", "STATIC R6.4"), ("routerA", "ROUTED R6.4 (mode A, primary)"), ("routerB", "ROUTED R6.4 (mode B, sensitivity)")):
        if tag not in runs: continue
        D, j, _ = runs[tag]; s0 = block(D, NC, name, 0.0); s7 = block(D, NC, name, 0.07)
        W(f"{name}")
        W(f"    fires            {s0['fires']}   ({s0['per100']:.2f} /100 candles)")
        W(f"    accuracy         {s0['acc']:.2f}%   ({int(round(s0['acc']*s0['priced']/100))} / {s0['priced'] - int(round(s0['acc']*s0['priced']/100))} on priced fires)")
        W(f"    avg entry price  {s0['avgq']:.3f}      mean fire second {s0['sec']:.1f}")
        W(f"    proxy PnL/100    {s0['pnl100']:+.2f} (fee 0)   {s7['pnl100']:+.2f} (fee 0.07)")
        W(f"    $50 hybrid end   ${s0['hyb']:.2f} (fee 0)   ${s7['hyb']:.2f} (fee 0.07)   maxDD ${s0['maxdd']:.2f}")
        W("")
    # deltas
    if "routerA" in runs:
        a = block(runs["static"][0], NC, "s"); b = block(runs["routerA"][0], NC, "r")
        W("CHANGE, routed(A) vs static, on real data:")
        W(f"    frequency {a['per100']:.2f} -> {b['per100']:.2f} /100   ({100*(b['per100']-a['per100'])/max(a['per100'],1e-9):+.1f}% relative)")
        W(f"    accuracy  {a['acc']:.2f}% -> {b['acc']:.2f}%   ({b['acc']-a['acc']:+.2f} pts)")
        W(f"    proxy PnL/100 {a['pnl100']:+.2f} -> {b['pnl100']:+.2f}   ({b['pnl100']-a['pnl100']:+.2f})")
        W("")
        W("Sol's synthetic 1,200-candle expectation was +20.6% frequency, +2.16 accuracy points,")
        W("+63.8% directional net. Whether that survived is stated in the verdict section below.")
        W("")
    # buckets
    W("=" * 70); W("BUCKET DISTRIBUTION AND PRESETS"); W("=" * 70)
    for tag in ("routerA", "routerB"):
        if tag not in runs: continue
        D, j, buckets = runs[tag]
        c = collections.Counter(buckets.values())
        W(f"{tag}: candles per bucket " + ", ".join(f"{MR.BUCKET_NAMES.get(k, 'warmup') if k is not None else 'WARMUP(static)'}={v}" for k, v in sorted(c.items(), key=lambda x: (x[0] is None, x[0]))))
        seq = [buckets[k] for k in sorted(buckets)]
        sw = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        blocks = []; cur = seq[0]; n = 1
        for x in seq[1:]:
            if x == cur: n += 1
            else: blocks.append(n); cur = x; n = 1
        blocks.append(n)
        W(f"      switches {sw}, median block {int(np.median(blocks))} candles, longest {max(blocks)}")
    W("")
    W("Frozen presets used (verbatim from the handoff):")
    W(f"    static r6.4     " + "  ".join(f"{k} {v:.4f}" for k, v in MR.STATIC.items()))
    for b in (0, 1, 2):
        W(f"    bucket {b} {MR.BUCKET_NAMES[b]:<15} " + "  ".join(f"{k} {v:.4f}" for k, v in MR.PRESETS[b].items()))
    W("")
    # per-bucket performance
    W("=" * 70); W("PERFORMANCE PER ROUTER BUCKET (routed mode A)"); W("=" * 70)
    if "routerA" in runs:
        D, j, buckets = runs["routerA"]; d = D[np.isfinite(D.q)]
        W(f"{'bucket':<18}{'fires':>6}{'acc%':>7}{'avg q':>7}{'PnL/fire f0':>13}{'total f0':>10}")
        for bk, g in d.groupby(d.bucket.apply(lambda x: MR.BUCKET_NAMES.get(x, "WARMUP(static)") if x is not None else "WARMUP(static)")):
            p = np.where(g.win, 1 / cost(g.q, 0.0) - 1, -1.0)
            W(f"{bk:<18}{len(g):>6}{100*g.win.mean():>7.1f}{g.q.mean():>7.3f}{p.mean():>+13.3f}{p.sum():>+10.2f}")
        W("")
        # transitions
        seq = {k: v for k, v in buckets.items()}
        sw_cids = set()
        ks = sorted(seq)
        for i in range(1, len(ks)):
            if seq[ks[i]] != seq[ks[i - 1]]: sw_cids.add(ks[i])
        near = d[d.cid.isin(sw_cids)]; far = d[~d.cid.isin(sw_cids)]
        for nm, g in (("first candle after a bucket switch", near), ("all other candles", far)):
            if len(g):
                p = np.where(g.win, 1 / cost(g.q, 0.0) - 1, -1.0)
                W(f"  {nm:<38} fires {len(g):>3}  acc {100*g.win.mean():>5.1f}%  PnL/fire {p.mean():+.3f}")
    W("")
    # direction + fire second
    W("=" * 70); W("DIRECTION SPLIT AND FIRE-SECOND DISTRIBUTION"); W("=" * 70)
    for tag in ("static", "routerA", "routerB"):
        if tag not in runs: continue
        D, j, _ = runs[tag]; d = D[np.isfinite(D.q)]
        ds = d.groupby("side").apply(lambda g: f"{g.side.iloc[0]} n={len(g)} acc={100*g.win.mean():.1f}%", include_groups=False)
        qs = d.sec.quantile([.1, .25, .5, .75, .9]).round(1).tolist()
        W(f"{tag:<9} " + "   ".join(ds.tolist()))
        W(f"          fire second p10/p25/p50/p75/p90 = {qs}")
    W("")
    # causality
    W("=" * 70); W("CAUSALITY CHECKS"); W("=" * 70)
    W("  event clock       replay clock driven by each event's own receive timestamp; now_ms/mono_ns patched to it")
    W("  depth lane        Tardis incremental_book_L2 reconstruction, top 5 levels, delivered at local_timestamp")
    W("  trade lane        Binance spot aggTrades at exchange timestamp (r6.4's native btcusdt@aggTrade)")
    W("  candle geometry   intra-candle OHLC built only from trades already delivered; the OFFICIAL closed")
    W("                    kline is injected only at that candle's own close time")
    W("  router inputs     seven statistics over CLOSED candles strictly before the traded candle;")
    W("                    the bucket is fixed at candle open and never revised inside the candle")
    W("  warmup            the first 37 candles have fewer than 36 closed candles of history; the router")
    W("                    abstains and the STATIC r6.4 numbers are used, in both routed runs")
    W("  presets           loaded into r6.4's module globals before _watch_ef runs; no EF code changed")
    W("  MASTER            asserted OFF at start of every run; no order is ever built")
    for tag in ("static", "routerA", "routerB"):
        if tag in runs:
            s = runs[tag][1]["stats"]
            W(f"  {tag:<9} events {s['events']:,}  depth {s['PD']:,}  trades {s['ST']:,}  candles {s['candles_settled']}  ef inputs-ready ticks {s['ef_inputs_ready_ticks']:,}")
    W("")
    open(HERE / "CLAUDE_CODE_R64_ROUTER_REAL_REPLAY_REPLY.txt", "w").write("\n".join(out) + "\n")
    print("\n".join(out))

if __name__ == "__main__":
    main()
