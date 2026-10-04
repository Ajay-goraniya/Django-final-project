#!/usr/bin/env python3
"""Split replayed EF fires by how the fill could be priced (real book vs
trade-inferred) and report accuracy, EV per $1 with its standard error, and
the hybrid-staking result for each bucket separately. The two buckets are
NOT interchangeable: only the book bucket is an executable price."""
import argparse, json, math, pathlib, sqlite3, sys
import pyarrow.parquet as pq
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ef_arch/polymarket/fiveday"))
from hybrid_stake import run_hybrid                       # noqa: E402
R = 0.07
COLS = ["window_epoch", "side", "offset_s", "quote_source", "best_ask", "ask_inferred"]
num = lambda x: x if isinstance(x, (int, float)) and x is not None and math.isfinite(x) and 0 < x < 1 else None

def load(dates):
    Q, S = {}, {}
    for d in dates:
        f = ROOT / f"week_data/predictfun/quotes_1s_unified/poly_1s_{d}.parquet"
        if f.exists():
            t = pq.read_table(f, columns=COLS)
            c = {n: t.column(n).to_pylist() for n in COLS}
            for i in range(t.num_rows):
                if c["quote_source"][i] != "none":
                    Q[(c["window_epoch"][i], str(c["side"][i]).upper(), c["offset_s"][i])] = (
                        c["quote_source"][i], c["best_ask"][i], c["ask_inferred"][i])
        m = ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{d}.json"
        if m.exists():
            for r in json.loads(m.read_text())["rows"]:
                mk = r["market"]
                try:
                    names = json.loads(mk["outcomes"]); prices = json.loads(mk["outcomePrices"])
                except Exception:
                    continue
                w = [n for n, p in zip(names, prices) if str(p) == "1"]
                if len(w) == 1:
                    S[int(r["epoch"])] = w[0].strip().upper()
    return Q, S

def report(tag, db, dates):
    Q, S = load(dates)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    buckets = {"book": [], "trade_inferred": []}
    for cid, d, ts in con.execute(
            "SELECT candle_id,direction,ts_ms FROM trades WHERE kind='EF' "
            "AND direction IN ('UP','DOWN') ORDER BY ts_ms"):
        a = S.get(cid // 1000)
        if a is None:
            continue
        r = Q.get((cid // 1000, d, int(round((ts - cid) / 1000.0))))
        if not r:
            continue
        src, ba, ai = r
        q = num(ba) if src == "book" else num(ai)
        if q is not None:
            buckets[src].append((q, d == a))
    out = []
    for src, rows in buckets.items():
        if not rows:
            continue
        n = len(rows); w = sum(1 for _q, x in rows if x)
        pay = [(1.0 / (q / (1 - R * (1 - q))) - 1.0) if x else -1.0 for q, x in rows]
        ev = sum(pay) / n
        se = ((sum((p - ev) ** 2 for p in pay) / max(n - 1, 1)) ** 0.5) / n ** 0.5
        res, _s, _e, _l = run_hybrid(
            [((lambda qq: (lambda s: (qq, float("inf"))))(q), x) for q, x in rows], R)
        out.append(dict(model=tag, pricing=src, n=n, acc=round(100 * w / n, 1),
                        mean_ask=round(sum(q for q, _x in rows) / n, 3),
                        ev=round(ev, 4), se=round(se, 4), t=round(ev / se, 2) if se else None,
                        hybrid_pnl=round(res["pnl"], 2), hybrid_ret=round(res["ret_pct"], 1),
                        maxdd=round(res["maxdd"], 2), bankrupt=res["bankrupt"]))
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbs", nargs="+", required=True, help="tag=path")
    ap.add_argument("--dates", nargs="+", required=True)
    a = ap.parse_args()
    rows = [r for p in a.dbs for r in report(*p.split("=", 1), a.dates)]
    print(f"{'model':6}{'pricing':16}{'n':>5}{'acc':>7}{'ask':>7}{'EV/$1':>9}{'+/-':>8}{'t':>7}"
          f"{'hybrid$':>10}{'ret%':>8}{'maxDD':>8}")
    for r in rows:
        print(f"{r['model']:6}{r['pricing']:16}{r['n']:5}{r['acc']:6.1f}%{r['mean_ask']:7.3f}"
              f"{r['ev']:+9.4f}{r['se']:8.4f}{r['t']:+7.2f}{r['hybrid_pnl']:+10.2f}"
              f"{r['hybrid_ret']:+8.1f}{r['maxdd']:8.2f}")
