#!/usr/bin/env python3
"""Liveness watcher. Checks what the runs actually PRODUCE, not that a pid exists.
Improvement #19: on 09-11 a process-count watcher missed two runners whose
websockets were dead for an hour. Prints ALERT lines only; silence means healthy."""
import sqlite3, time, subprocess, sys, urllib.request

S = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
V12 = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/results/v12_poly_weekend.sqlite3"

# (label, db, table, time column, max age seconds)
FEEDS = [
    ("book1s Predict.fun 1Hz", f"{S}/book1s.sqlite3",   "b1", "ts_ms", 120),
    ("poly1s Polymarket 1Hz",  f"{S}/polybook.sqlite3", "pb", "ts_ms", 120),
    ("venue_collect",          f"{S}/venues.sqlite3",   "q",  "ts",    300),
]
PORTS = [8794, 8795, 8796, 8798, 8790]

def row_age(db, table, col):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    v = c.execute(f"select max({col}) from {table}").fetchone()[0]
    c.close()
    if v is None:
        return None
    v = float(v)
    if v > 1e12:
        v /= 1000.0
    return time.time() - v

def main():
    bad = {}
    while True:
        alerts = []
        for label, db, table, col, limit in FEEDS:
            try:
                a = row_age(db, table, col)
                if a is None:
                    alerts.append(f"{label}: no rows")
                elif a > limit:
                    alerts.append(f"{label}: last row {a:.0f}s ago (limit {limit}s)")
            except Exception as e:
                alerts.append(f"{label}: {type(e).__name__} {e}")
        n = len(subprocess.run(["bash", "-c",
              "ps -eo pid,args | awk '$2==\"python3\"{print $1}'"],
              capture_output=True, text=True).stdout.split())
        if n < 8:
            alerts.append(f"only {n} python processes (expected 12)")
        for p in PORTS:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{p}/api/state", timeout=8).read(1)
            except Exception as e:
                alerts.append(f"port {p} unreachable: {type(e).__name__}")
        # only report a condition once per 10 minutes so the log stays readable
        now = time.time()
        for a in alerts:
            key = a.split(":")[0]
            if now - bad.get(key, 0) > 600:
                bad[key] = now
                print(f"ALERT {time.strftime('%H:%M:%S')} {a}", flush=True)
        for key in list(bad):
            if not any(a.split(":")[0] == key for a in alerts):
                del bad[key]
        time.sleep(60)

if __name__ == "__main__":
    main()
