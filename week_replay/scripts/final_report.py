#!/usr/bin/env python3
"""Final week report: frequency, directional accuracy and PnL for every model.

Accuracy and frequency use the resolved Chainlink outcome and need no venue
price, so they are exact on every day. PnL is reported ONLY where a real
order book exists (2026-09-02, 2026-09-03); the remaining days carry
trade-inferred prices whose +/-0.09 noise inflates a convex 1/q payoff, so
they are reported as accuracy-only with the EV band stated, never as a point
PnL. Every figure carries its standard error.
"""
import argparse, collections, datetime, json, math, pathlib, sqlite3, sys
import pyarrow.parquet as pq
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ef_arch/polymarket/fiveday"))
from hybrid_stake import run_hybrid                        # noqa: E402
RUNS = ROOT / "week_replay/runs"
R = 0.07
BOOK_DAYS = ("2026-09-02", "2026-09-03")
num = lambda x: x if isinstance(x, (int, float)) and x is not None and math.isfinite(x) and 0 < x < 1 else None
day = lambda ms: datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def settlement(dates):
    S = {}
    for d in dates:
        f = ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{d}.json"
        if not f.exists():
            continue
        for r in json.loads(f.read_text())["rows"]:
            m = r["market"]
            try:
                names = json.loads(m["outcomes"]); prices = json.loads(m["outcomePrices"])
            except Exception:
                continue
            w = [n for n, p in zip(names, prices) if str(p) == "1"]
            if len(w) == 1:
                S[int(r["epoch"])] = w[0].strip().upper()
    return S


def book_quotes(dates):
    Q = {}
    cols = ["window_epoch", "side", "offset_s", "quote_source", "best_ask"]
    for d in dates:
        f = ROOT / f"week_data/predictfun/quotes_1s_unified/poly_1s_{d}.parquet"
        if not f.exists():
            continue
        t = pq.read_table(f, columns=cols)
        c = {n: t.column(n).to_pylist() for n in cols}
        for i in range(t.num_rows):
            if c["quote_source"][i] == "book":
                Q[(c["window_epoch"][i], str(c["side"][i]).upper(), c["offset_s"][i])] = c["best_ask"][i]
    return Q


def wilson(k, n):
    if not n:
        return (float("nan"),) * 2
    p = k / n; z = 1.96; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def main(tags, dates):
    S, Q = settlement(dates), book_quotes(BOOK_DAYS)
    out = {}
    for tag in tags:
        db = RUNS / f"week_{tag}.sqlite3"
        if not db.exists():
            continue
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
        cd = collections.Counter()
        for (cid,) in con.execute("SELECT candle_id FROM candles WHERE actual IS NOT NULL AND actual!=''"):
            cd[day(cid)] += 1
        per = collections.defaultdict(lambda: {"fires": 0, "graded": 0, "correct": 0, "sec": 0.0})
        booked = []
        for cid, d, ts, sec in con.execute(
                "SELECT candle_id,direction,ts_ms,seconds_into_candle FROM trades "
                "WHERE kind='EF' AND direction IN ('UP','DOWN') ORDER BY ts_ms"):
            k = day(cid); a = S.get(cid // 1000)
            p = per[k]; p["fires"] += 1; p["sec"] += (sec or 0)
            if a:
                p["graded"] += 1; p["correct"] += int(d == a)
                if k in BOOK_DAYS:
                    q = num(Q.get((cid // 1000, d, int(round((ts - cid) / 1000.0)))))
                    if q:
                        booked.append((q, d == a))
        rows = []
        for k in sorted(cd):
            p = per[k]; n = p["graded"]
            lo, hi = wilson(p["correct"], n)
            rows.append(dict(day=k, candles=cd[k], fires=p["fires"],
                             freq=round(100 * p["fires"] / cd[k], 1) if cd[k] else None,
                             acc=round(100 * p["correct"] / n, 1) if n else None,
                             ci=[round(lo, 1), round(hi, 1)] if n else None, n=n,
                             fire_s=round(p["sec"] / p["fires"], 1) if p["fires"] else None))
        tc = sum(cd.values()); tf = sum(p["fires"] for p in per.values())
        tn = sum(p["graded"] for p in per.values()); tk = sum(p["correct"] for p in per.values())
        lo, hi = wilson(tk, tn)
        pool = dict(candles=tc, fires=tf, freq=round(100 * tf / tc, 1) if tc else None,
                    acc=round(100 * tk / tn, 1) if tn else None,
                    ci=[round(lo, 1), round(hi, 1)] if tn else None, n=tn)
        pnl = None
        if booked:
            n = len(booked)
            pay = [(1.0 / (q / (1 - R * (1 - q))) - 1.0) if w else -1.0 for q, w in booked]
            ev = sum(pay) / n
            se = ((sum((x - ev) ** 2 for x in pay) / max(n - 1, 1)) ** 0.5) / n ** 0.5
            res, _s, _e, _l = run_hybrid(
                [((lambda qq: (lambda s: (qq, float("inf"))))(q), w) for q, w in booked], R)
            pnl = dict(basis="REAL ORDER BOOK (2026-09-02, 2026-09-03)", trades=n,
                       acc=round(100 * sum(1 for _q, w in booked if w) / n, 1),
                       mean_ask=round(sum(q for q, _w in booked) / n, 3),
                       ev_per_dollar=round(ev, 4), se=round(se, 4),
                       t=round(ev / se, 2) if se else None,
                       ev_95ci=[round(ev - 1.96 * se, 4), round(ev + 1.96 * se, 4)],
                       significant=bool(se and abs(ev / se) >= 1.96),
                       hybrid_end=round(res["end"], 2), hybrid_pnl=round(res["pnl"], 2),
                       hybrid_ret_pct=round(res["ret_pct"], 1), hybrid_maxdd=round(res["maxdd"], 2),
                       bankrupt=res["bankrupt"])
        out[tag] = dict(per_day=rows, pooled=pool, pnl_real_book=pnl)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", default=["v9_4", "v9_5", "b36"])
    ap.add_argument("--dates", nargs="+",
                    default=["2026-08-31", "2026-09-02", "2026-09-03",
                             "2026-09-04", "2026-09-05", "2026-09-06"])
    ap.add_argument("--out", default=str(RUNS / "FINAL_REPORT.json"))
    a = ap.parse_args()
    res = main(a.tags, a.dates)
    pathlib.Path(a.out).write_text(json.dumps(res, indent=2))
    for tag, r in res.items():
        print(f"\n===== {tag} =====")
        print(f"{'day':12}{'candles':>8}{'fires':>7}{'freq/100':>10}{'acc':>8}{'95% CI':>16}{'n':>6}{'fire@s':>8}")
        for d in r["per_day"]:
            ci = f"[{d['ci'][0]:.1f},{d['ci'][1]:.1f}]" if d["ci"] else "-"
            print(f"{d['day']:12}{d['candles']:8}{d['fires']:7}{d['freq']:10}{str(d['acc'])+'%':>8}{ci:>16}{d['n']:6}{d['fire_s']:8}")
        p = r["pooled"]; ci = f"[{p['ci'][0]:.1f},{p['ci'][1]:.1f}]" if p["ci"] else "-"
        print(f"{'POOLED':12}{p['candles']:8}{p['fires']:7}{p['freq']:10}{str(p['acc'])+'%':>8}{ci:>16}{p['n']:6}")
        q = r["pnl_real_book"]
        if q:
            print(f"  PnL on {q['basis']}")
            print(f"    trades {q['trades']}  acc {q['acc']}%  mean ask {q['mean_ask']}")
            print(f"    EV/$1 {q['ev_per_dollar']:+.4f} +/- {q['se']:.4f}  t={q['t']:+.2f}  "
                  f"95% CI [{q['ev_95ci'][0]:+.4f},{q['ev_95ci'][1]:+.4f}]  "
                  f"significant={q['significant']}")
            print(f"    hybrid $50: end ${q['hybrid_end']}  pnl ${q['hybrid_pnl']:+}  "
                  f"({q['hybrid_ret_pct']:+}%)  maxDD ${q['hybrid_maxdd']}  bankrupt={q['bankrupt']}")
