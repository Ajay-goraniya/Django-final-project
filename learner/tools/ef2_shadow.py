"""EF2 forward shadow (candidate J): a second EF entry at t~120 s on EF's own side, only if that side's
LIVE Predict.fun ask is still <= CAP. Nothing is traded. Direction = twin C's EF fire for the candle
(c_thr1.sqlite3, EV scale 1.0 = Tokyo's setting); the ask is read from twin C's live websocket book
(/api/state on 8796) at 1 Hz between T0 and T1 seconds into the candle; the row closest to TARGET is
the entry. Graded at close from the candles table. Output: ef2_shadow.sqlite3 + a stats line per candle.
"""
import json, sqlite3, time, urllib.request, sys
D = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
TWIN_DB = f"{D}/v11/tests/c_thr1.sqlite3"
API = "http://127.0.0.1:8796/api/state"
T0, TARGET, T1 = 110, 120, 130
CAPS = (None, 0.60, 0.50)
FEE = 0.02
con = sqlite3.connect(f"{D}/ef2_shadow.sqlite3")
con.execute("""CREATE TABLE IF NOT EXISTS ef2(candle_id INTEGER PRIMARY KEY, direction TEXT, fire_sec REAL,
  ask REAL, size REAL, ask_sec REAL, age_ms INTEGER, samples INTEGER, actual TEXT, correct INTEGER)""")
con.commit()

def get(url, t=4):
    try:
        return json.load(urllib.request.urlopen(url, timeout=t))
    except Exception:
        return None

def twin_fire(cid):
    try:
        t = sqlite3.connect(TWIN_DB)
        r = t.execute("SELECT direction, ts_ms FROM ef_predictions WHERE candle_id=? ORDER BY ts_ms LIMIT 1", (cid,)).fetchone()
        t.close()
        return r
    except Exception:
        return None

def grade_pending():
    t = sqlite3.connect(TWIN_DB)
    for (cid, d) in con.execute("SELECT candle_id, direction FROM ef2 WHERE actual IS NULL").fetchall():
        a = t.execute("SELECT actual FROM candles WHERE candle_id=?", (cid,)).fetchone()
        if a and a[0] in ("UP", "DOWN"):
            con.execute("UPDATE ef2 SET actual=?, correct=? WHERE candle_id=?", (a[0], 1 if a[0] == d else 0, cid))
    con.commit(); t.close()

def stats():
    rows = con.execute("SELECT ask, correct FROM ef2 WHERE correct IS NOT NULL AND ask IS NOT NULL ORDER BY candle_id").fetchall()
    out = []
    for cap in CAPS:
        r = [(a, c) for a, c in rows if cap is None or a <= cap]
        if not r:
            out.append(f"cap {cap}: n=0"); continue
        pnl = [((1 / (a * (1 + FEE)) - 1) if c else -1.0) for a, c in r]
        h = len(pnl) // 2
        out.append(f"cap {cap}: n={len(r)} hit {sum(c for _, c in r) / len(r) * 100:.0f}% per-fire {sum(pnl) / len(pnl):+.3f} halves {sum(pnl[:h]):+.2f}/{sum(pnl[h:]):+.2f}")
    return " | ".join(out)

samples = {}
last_cid = None
while True:
    now = time.time(); cid = int(now // 300) * 300 * 1000; sec = now - cid / 1000
    if cid != last_cid:
        samples = {}; last_cid = cid
        grade_pending()
    if T0 <= sec <= T1:
        fire = twin_fire(cid)
        if fire:
            d, fire_ms = fire
            st = get(API)
            b = (st or {}).get("book") or {}
            side = b.get("up" if d == "UP" else "down") or {}
            if int(b.get("candle_id") or 0) == cid and side.get("price"):
                samples[round(sec)] = (float(side["price"]), float(side.get("size") or 0), sec, int(side.get("age_ms") or 0), d, (fire_ms - cid) / 1000.0)
        if sec >= T1 - 1 and samples and not con.execute("SELECT 1 FROM ef2 WHERE candle_id=?", (cid,)).fetchone():
            k = min(samples, key=lambda s: abs(s - TARGET)); a, sz, asec, age, d, fsec = samples[k]
            con.execute("INSERT OR IGNORE INTO ef2 VALUES(?,?,?,?,?,?,?,?,NULL,NULL)", (cid, d, fsec, a, sz, asec, age, len(samples)))
            con.commit()
            print(time.strftime("%H:%M:%S", time.gmtime()), f"cid {cid} {d} fired {fsec:.0f}s ask@{asec:.0f}s {a:.2f} size {sz:.0f} age {age}ms samples {len(samples)} | {stats()}", flush=True)
    time.sleep(1.0 if T0 - 2 <= sec <= T1 else 2.0)
