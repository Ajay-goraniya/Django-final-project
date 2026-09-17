#!/usr/bin/env python3
"""H1: REVERSAL/EF profile from a build11-style engine DB.

Reproduces analysis/h1/2026-09-10_1115_reversal_hour_and_depth.md.
Usage: python3 reversal_profile.py [path/to/build11.sqlite3]
Default reads the committed backup, decompressing it to a temp file.
"""
import gzip, os, shutil, sqlite3, sys, tempfile, datetime

DEFAULT = os.path.join(os.path.dirname(__file__), "..", "..",
                       "learner", "live_backup", "build11.sqlite3.gz")


def open_db(path):
    if path.endswith(".gz"):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        with gzip.open(path, "rb") as f:
            shutil.copyfileobj(f, tmp)
        tmp.close()
        path = tmp.name
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def lane_totals(c):
    print("=== lane totals (graded, $1) ===")
    for k in ("REVERSAL", "MAIN", "EF"):
        r = c.execute(
            "select count(*), sum(correct), round(sum(coalesce(pnl,0)),2) "
            "from trades where kind=? and correct is not null", (k,)).fetchone()
        n, w, p = r[0], r[1] or 0, r[2] or 0.0
        if n:
            print(f"  {k:9} n={n:4} W={w:4} hit={w/n*100:3.0f}%  pnl={p:+8.2f}")


def distributions(c, kind="REVERSAL"):
    print(f"\n=== {kind} fire conditions ===")
    for col in ("seconds_into_candle", "book_size", "spread", "quoted_price"):
        s = sorted(r[0] for r in c.execute(
            f"select {col} from trades where kind=? and {col} is not null", (kind,)))
        if not s:
            continue
        q = lambda f: s[min(int(len(s) * f), len(s) - 1)]
        print(f"  {col:20} n={len(s):3} min={s[0]:8.2f} p25={q(.25):8.2f} "
              f"med={q(.5):8.2f} p75={q(.75):8.2f} max={s[-1]:8.2f}")


def price_buckets(c, kind="REVERSAL", edges=(0.45, 0.60)):
    print(f"\n=== {kind} by entry price ===")
    lo, hi = edges
    buckets = {f"<={lo}": [], f"{lo}-{hi}": [], f">{hi}": []}
    for p, corr, pnl in c.execute(
            "select quoted_price, correct, pnl from trades "
            "where kind=? and correct is not null and quoted_price is not null", (kind,)):
        k = f"<={lo}" if p <= lo else (f"{lo}-{hi}" if p <= hi else f">{hi}")
        buckets[k].append((corr, pnl or 0.0))
    for k, v in buckets.items():
        if not v:
            continue
        n, w, p = len(v), sum(a for a, _ in v), sum(b for _, b in v)
        print(f"  {k:10} n={n:3} W={w:3} hit={w/n*100:3.0f}%  "
              f"pnl={p:+7.2f}  per-fire={p/n:+.3f}")


def by_hour(c, kind):
    print(f"\n=== {kind} by UTC hour ===")
    hr = lambda ms: datetime.datetime.utcfromtimestamp(ms / 1000).hour
    agg = {}
    for r in c.execute("select ts_ms, correct, pnl, quoted_price from trades "
                       "where kind=? and correct is not null", (kind,)):
        d = agg.setdefault(hr(r["ts_ms"]), [0, 0, 0.0, []])
        d[0] += 1
        d[1] += r["correct"]
        d[2] += r["pnl"] or 0.0
        if r["quoted_price"]:
            d[3].append(r["quoted_price"])
    print(f"  {'UTC':>4} {'n':>3} {'W':>3} {'hit':>5} {'pnl':>8} {'avg buy':>8}")
    for h in sorted(agg):
        n, w, p, pr = agg[h]
        print(f"  {h:>4} {n:>3} {w:>3} {w/n*100:>4.0f}% {p:>+8.2f} "
              f"{sum(pr)/len(pr) if pr else 0:>8.2f}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    c = open_db(path)
    lane_totals(c)
    distributions(c)
    price_buckets(c)
    for k in ("REVERSAL", "EF"):
        by_hour(c, k)
