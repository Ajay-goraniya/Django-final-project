#!/usr/bin/env python3
"""
join_pnl.py -- join replayed EF fires to the REAL Polymarket per-second quotes
and the REAL Chainlink settlement, then run the user's hybrid staking.

Nothing here is synthetic. Every fill price is either a real order-book ask
ladder (quote_source="book") or a real executed taker print (trade_inferred).
Rows with neither are reported as unexecutable, never imputed.
"""
import argparse, json, math, pathlib, sqlite3, sys
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ef_arch/polymarket/fiveday"))
from hybrid_stake import run_hybrid                      # noqa: E402

QDIR = ROOT / "week_data/predictfun/quotes_1s_unified"
MDIR = ROOT / "ef_arch/polymarket/fiveday/data/markets"
FEE_RATE = 0.07                                          # venue feeSchedule.rate, takerOnly
CANDLE_MS = 300_000
VWAP_TIERS = [(2, "vwap_s2"), (5, "vwap_s5"), (10, "vwap_s10"), (100, "vwap_s100")]


def load_settlement(dates):
    """window_epoch -> 'UP'|'DOWN' from the resolved Gamma/Chainlink outcome."""
    out = {}
    for d in dates:
        f = MDIR / f"btc5m_markets_{d}.json"
        if not f.exists():
            continue
        for r in json.loads(f.read_text())["rows"]:
            m = r.get("market") or {}
            try:
                names = json.loads(m["outcomes"]); prices = json.loads(m["outcomePrices"])
            except Exception:
                continue
            win = [n for n, p in zip(names, prices) if str(p) == "1"]
            if len(win) == 1:
                out[int(r["epoch"])] = win[0].strip().upper()
    return out


def load_quotes(dates):
    """(window_epoch, side, offset_s) -> quote dict, real rows only."""
    q = {}
    cols = ["window_epoch", "side", "offset_s", "quote_source", "best_ask",
            "ask_inferred", "vwap_s2", "shares_s2", "fill_ok_s2",
            "vwap_s5", "shares_s5", "fill_ok_s5", "vwap_s10", "shares_s10",
            "fill_ok_s10", "vwap_s100", "shares_s100", "fill_ok_s100"]
    for d in dates:
        f = QDIR / f"poly_1s_{d}.parquet"
        if not f.exists():
            print(f"  no quotes for {d}", file=sys.stderr); continue
        t = pq.read_table(f, columns=cols)
        c = {n: t.column(n).to_pylist() for n in cols}
        for i in range(t.num_rows):
            if c["quote_source"][i] == "none":
                continue
            q[(c["window_epoch"][i], str(c["side"][i]).upper(), c["offset_s"][i])] = {
                k: c[k][i] for k in cols[3:]}
    return q


def _num(x):
    return x if isinstance(x, (int, float)) and x is not None and math.isfinite(x) else None


def make_fill(row, mode):
    """Return f(stake)->(price, shares). Ladder VWAP sized to the stake when the
    book exists; touch otherwise. Never invents a price."""
    src = row["quote_source"]

    def f(stake):
        if src == "book" and mode != "touch":
            best = None
            for _cap, key in VWAP_TIERS:
                v = _num(row.get(key)); sh = _num(row.get("shares_" + key.split("_")[1]))
                if v is None or sh is None or not row.get("fill_ok_" + key.split("_")[1]):
                    continue
                if sh * v >= stake:            # this tier can absorb the whole clip
                    return v, sh
                best = (v, sh)                 # remember deepest tier that filled
            if best:
                return best[0], best[1]
            a = _num(row.get("best_ask"))
            return (a, 0.0) if a else (None, 0.0)
        a = _num(row.get("best_ask")) if src == "book" else _num(row.get("ask_inferred"))
        return (a, float("inf")) if a else (None, 0.0)
    return f


def fires_from_db(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    rows = con.execute(
        "SELECT candle_id, direction, ts_ms FROM trades WHERE kind='EF' "
        "AND direction IN ('UP','DOWN') ORDER BY ts_ms").fetchall()
    con.close()
    return rows


def run(tag, db, dates, mode, shift):
    settle, quotes = load_settlement(dates), load_quotes(dates)
    fires = fires_from_db(db)
    seq, miss_q, miss_s, per_day = [], 0, 0, {}
    for cid, direction, ts in fires:
        epoch = cid // 1000
        off = int(round((ts - cid) / 1000.0))
        if off < 0 or off > 299:
            continue
        actual = settle.get(epoch)
        if actual is None:
            miss_s += 1; continue
        row = quotes.get((epoch, direction, off))
        if row is None:
            miss_q += 1; continue
        q = _num(row.get("best_ask") if row["quote_source"] == "book" else row.get("ask_inferred"))
        if q is not None and shift:
            row = dict(row)
            for k in ("best_ask", "ask_inferred", "vwap_s2", "vwap_s5", "vwap_s10", "vwap_s100"):
                if _num(row.get(k)) is not None:
                    row[k] = min(0.99, max(0.01, row[k] + shift))
        seq.append((make_fill(row, mode), direction == actual, row["quote_source"], epoch))
    res, _st, eq, log = run_hybrid([(f, w) for f, w, _s, _e in seq], FEE_RATE)
    book_n = sum(1 for _f, _w, s, _e in seq if s == "book")
    return {"model": tag, "fires_total": len(fires), "joined": len(seq),
            "book_priced": book_n, "inferred_priced": len(seq) - book_n,
            "no_quote": miss_q, "no_settlement": miss_s,
            "wins_joined": sum(1 for _f, w, _s, _e in seq if w),
            "acc_joined": round(100 * sum(1 for _f, w, _s, _e in seq if w) / len(seq), 2) if seq else None,
            "hybrid": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbs", nargs="+", required=True, help="tag=path pairs")
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--mode", default="ladder", choices=["ladder", "touch"])
    ap.add_argument("--shift", type=float, default=0.0,
                    help="add this to every ask (error-band sensitivity, e.g. +/-0.04)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = [run(*p.split("=", 1), a.dates, a.mode, a.shift) for p in a.dbs]
    print(json.dumps({"dates": a.dates, "mode": a.mode, "ask_shift": a.shift,
                      "fee_rate": FEE_RATE, "results": res}, indent=2))
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(res, indent=2))
