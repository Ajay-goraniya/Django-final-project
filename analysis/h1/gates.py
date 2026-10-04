#!/usr/bin/env python3
"""H1 Task 2: hour-of-day, realised-vol and ask gates on the EF/runner fires.

Reproduces analysis/h1/2026-09-10_1130_task1_task2_results.md.
Usage: python3 gates.py [dir_with_sqlite3_gz]   (default: learner/live_backup)

PnL is reported at $1 with V's fee model: win = (1/quote)*0.98 - 1, loss = -1.
poly_pnl stores pnl at $10, so it is divided by 10.
"""
import datetime, gzip, os, shutil, sqlite3, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "..", "..", "learner", "live_backup")
utc = lambda ms: datetime.datetime.utcfromtimestamp(ms / 1000)


def conn(d, name):
    src = os.path.join(d, name + ".sqlite3.gz")
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    with gzip.open(src, "rb") as f:
        shutil.copyfileobj(f, tmp)
    tmp.close()
    c = sqlite3.connect(tmp.name)
    c.row_factory = sqlite3.Row
    return c


def fee_pnl(quote, win):
    if quote is None or win is None:
        return None
    return (1.0 / quote) * 0.98 - 1.0 if win else -1.0


def load_kind(c, kind):
    """predict_pnl / build11 style: trades(kind, quoted_price, correct, ...)."""
    return [{"ts": r["ts_ms"], "ask": r["quoted_price"], "win": r["correct"],
             "sec": r["seconds_into_candle"], "rv": None,
             "candle": r["candle_id"], "dir": r["direction"],
             "vp": fee_pnl(r["quoted_price"], r["correct"])}
            for r in c.execute("select * from trades where kind=? and correct is not null "
                               "order by ts_ms", (kind,))]


def load_runner(c):
    """poly_pnl style: trades(ask, win, sec, rv60, pnl at $10)."""
    return [{"ts": r["ts_ms"], "ask": r["ask"], "win": r["win"], "sec": r["sec"],
             "rv": r["rv60"], "candle": r["candle_epoch"], "dir": r["side"],
             "vp": (r["pnl"] or 0.0) / 10.0}
            for r in c.execute("select * from trades where win is not null order by ts_ms")]


def gate(rows, name, keep):
    """Report a gate: what it keeps, what it removes, and each half of the kept run."""
    k = [x for x in rows if keep(x)]
    rm = [x for x in rows if not keep(x)]
    if not k:
        return
    mid = rows[len(rows) // 2]["ts"]
    n, w = len(k), sum(x["win"] for x in k)
    p = sum(x["vp"] for x in k)
    h1 = sum(x["vp"] for x in k if x["ts"] < mid)
    h2 = sum(x["vp"] for x in k if x["ts"] >= mid)
    rw = sum(x["win"] for x in rm)
    print(f"  {name:22} keep {n:3} {w/n*100:3.0f}% {p:>+7.2f} | "
          f"removed {len(rm):3} {rw}/{len(rm)-rw} {sum(x['vp'] for x in rm):>+7.2f} | "
          f"h1 {h1:>+6.2f} h2 {h2:>+6.2f}")


def by_hour(runs):
    print("\n=== fires by UTC hour, per run (disagreement => not a real hour effect) ===")
    for h in range(24):
        cells, tot, any_ = [], 0.0, False
        for name, rows in runs.items():
            s = [x for x in rows if utc(x["ts"]).hour == h]
            if s:
                n, w = len(s), sum(x["win"] for x in s)
                pp = sum(x["vp"] for x in s)
                cells.append(f"{n:>3}f {w:>2}/{n-w:<2} {pp:>+7.2f}")
                tot += pp
                any_ = True
            else:
                cells.append(f"{'.':>19}")
        if any_:
            print(f"  {h:>3} " + " ".join(f"{c:>19}" for c in cells) + f" {tot:>+8.2f}")


def by_day(rows, hours, label):
    print(f"  window {label}:")
    for d in sorted({utc(x["ts"]).strftime("%m-%d") for x in rows}):
        s = [x for x in rows if utc(x["ts"]).hour in hours
             and utc(x["ts"]).strftime("%m-%d") == d]
        if s:
            n, w = len(s), sum(x["win"] for x in s)
            print(f"    {d}: n={n:3} {w}/{n-w} ({w/n*100:3.0f}%) "
                  f"pnl={sum(x['vp'] for x in s):+7.2f}")


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    runs = {"predict_pnl EF": load_kind(conn(d, "predict_pnl"), "EF"),
            "build11 twinA EF": load_kind(conn(d, "build11"), "EF"),
            "poly_pnl runner": load_runner(conn(d, "poly_pnl"))}
    print("=== run totals @ $1 ===")
    for k, v in runs.items():
        w = sum(x["win"] for x in v)
        print(f"  {k:20} n={len(v):4} hit={w/len(v)*100:3.0f}% "
              f"pnl={sum(x['vp'] for x in v):+8.2f}")
    by_hour(runs)
    print("\n=== (a) suspect windows split by day (predict_pnl) ===")
    by_day(runs["predict_pnl EF"], (4, 5, 6), "04-06")
    by_day(runs["predict_pnl EF"], (9, 10, 11), "09-11")

    T = runs["poly_pnl runner"]
    print("\n=== (b) realised-vol gate (poly_pnl rv60) ===")
    gate(T, "baseline", lambda x: True)
    for t in (0.2, 0.3, 0.4, 0.5, 0.6):
        gate(T, f"rv60 >= {t}", lambda x, t=t: x["rv"] is not None and x["rv"] >= t)
    print("\n=== (c) ask gates ===")
    for lo in (0.40, 0.45):
        gate(T, f"ask >= {lo}", lambda x, t=lo: x["ask"] is not None and x["ask"] >= t)
    for hi in (0.60, 0.55):
        gate(T, f"ask <= {hi}", lambda x, t=hi: x["ask"] is not None and x["ask"] <= t)
