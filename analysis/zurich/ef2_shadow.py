#!/usr/bin/env python3
"""EF-2 LIVE SHADOW ARM - PAPER ONLY, beside the engine's own fixed15 paper lane. Own sqlite, no engine change.

THERE IS NO ORDER PATH IN THIS FILE. Standard library only, no poly_live, no credentials, master never read
or written. Every row it produces is a simulation.

DESIGN. It tails the engine's `decide_log` READ-ONLY rather than recomputing features. That is the whole
point: the 44 engine features are the engine's own, so a shadow that recomputed them would be measuring my
re-implementation instead of EF-2's rule. Reading the engine's stream means the shadow and the offline
walk-forward see byte-identical inputs, and any difference between them is the rule, not the plumbing.

Consequence, stated rather than hidden: decide_log is written in batches (DECIDE_LOG_BATCH=40 at ~4 rows/s),
so this shadow trails real time by ~10 s. It is therefore a faithful shadow of the RULE and of the SIMULATED
fill, not a test of live latency - the same limitation the offline work has, kept identical on purpose.

ALL FOUR MARGINS run as separate arms in one process. Picking one in advance would be choosing a cell before
seeing the data, which is the thing this whole session keeps refusing to do.
"""
import json, math, os, sqlite3, sys, time, datetime as dt

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
DB = '/home/ubuntu/pm_ef2shadow/ef2_shadow.sqlite3'
MODEL = '/home/ubuntu/claude-work/repo/learner/v12_2/ef2/ef2_model.json'
sys.path.insert(0, '/home/ubuntu/claude-work/repo/learner/v12_2/ef2')
GAMMA = 'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}'
MARGINS = (0.0, 0.02, 0.03, 0.05)
SEC_LO, SEC_HI, TICK, DELAY_MS, STAKE, RATE = 15, 240, 0.01, 250, 10.0, 0.07
DYN = (1000, 5000, 30000)

DDL = [
    """CREATE TABLE IF NOT EXISTS fires(margin REAL, epoch INTEGER, ts_ms INTEGER, sec INTEGER, side TEXT,
       p_win REAL, p_engine REAL, ask REAL, opp_ask REAL, ev REAL, later_ask REAL, filled INTEGER,
       fill_price REAL, slip REAL, dip30 REAL, d1 REAL, d5 REAL, d30 REAL,
       outcome TEXT, win INTEGER, graded_ts REAL, PRIMARY KEY(margin, epoch))""",
    """CREATE TABLE IF NOT EXISTS seen(epoch INTEGER PRIMARY KEY, passes INTEGER, cands INTEGER, ts REAL)""",
    """CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)""",
]


def log(db, note):
    try:
        db.execute('INSERT OR REPLACE INTO health VALUES(?,?)', (time.time(), note[:400])); db.commit()
    except Exception: pass
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {note}', flush=True)


def be(a): return a * (1 + RATE * (1 - a))


def main():
    from ef2_scorer import Scorer
    sc = Scorer(MODEL)
    db = sqlite3.connect(DB)
    for q in DDL: db.execute(q)
    db.commit()
    log(db, f'ef2 shadow start - PAPER ONLY, no order path. {len(sc.names)} features, margins {MARGINS}')
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    a.close()
    done = {int(e) for (e,) in db.execute('SELECT epoch FROM seen')}
    last_ep = None
    while True:
        try:
            time.sleep(20)
            now = int(time.time())
            cur = now // 300 * 300
            # only work on candles that have fully elapsed, so the +250 ms row always exists
            for ep in sorted({cur - 300, cur - 600}):
                if ep in done or ep >= cur: continue
                a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
                rows = a.execute('SELECT ts_ms,side,p,up_ask,dn_ask,feats FROM decide_log '
                                 'WHERE epoch=? ORDER BY ts_ms', (ep,)).fetchall()
                a.close()
                rows = [r for r in rows if r[2] is not None and r[3] is not None and r[4] is not None and r[5]]
                if len(rows) < 20: continue
                ts_a = [r[0] for r in rows]
                ua_a = [float(r[3]) for r in rows]; da_a = [float(r[4]) for r in rows]
                cands, ncand, nmiss = [], 0, 0
                for i, (tms, side_l, p_l, ua, da, fs) in enumerate(rows):
                    sec = (tms // 1000) - ep
                    if not (SEC_LO <= sec <= SEC_HI): continue
                    try:
                        v = json.loads(fs)
                        if len(v) != len(keys): continue
                    except Exception: continue
                    j = next((k for k in range(i, len(ts_a)) if ts_a[k] >= tms + DELAY_MS), None)
                    lo30 = next((k for k in range(len(ts_a)) if ts_a[k] >= tms - DYN[2]), 0)
                    back = [max([k for k in range(len(ts_a)) if ts_a[k] <= tms - d] or [-1]) for d in DYN]
                    for side in ('UP', 'DOWN'):
                        own = float(ua) if side == 'UP' else float(da)
                        oppa = float(da) if side == 'UP' else float(ua)
                        if not (0.01 < own < 0.99): continue
                        oa = ua_a if side == 'UP' else da_a
                        dyn = [own - oa[b] if b >= 0 else 0.0 for b in back]
                        w = oa[lo30:i + 1]
                        dip = own - min(w) if w else 0.0
                        row = dict(zip(keys, [float(x) if x is not None else float('nan') for x in v]))
                        row.update(own_ask=own, opp_ask=oppa, d_ask_1s=dyn[0], d_ask_5s=dyn[1],
                                   d_ask_30s=dyn[2], dip30=dip, sec=float(sec),
                                   p_side=(float(p_l) if side == side_l else 1.0 - float(p_l)))
                        if sc.missing(row): nmiss += 1; continue
                        lat = None
                        if j is not None:
                            lv = (ua_a if side == 'UP' else da_a)[j]
                            if 0.01 < lv < 0.99: lat = lv
                        ncand += 1
                        # Scorer.score returns (p, info) since the London imputation change - taking the
                        # tuple as a float is what raised "bad operand type for unary -" on the first pass.
                        pv, pinfo = sc.score(row)
                        cands.append(dict(t=tms, sec=sec, side=side, ask=own, opp=oppa, later=lat,
                                          pe=row['p_side'], p=pv, dip=dip, imp=pinfo['n_imputed'],
                                          d1=dyn[0], d5=dyn[1], d30=dyn[2]))
                cands.sort(key=lambda c: (c['t'], -c['p']))
                for m in MARGINS:
                    hit = next((c for c in cands if c['p'] / be(c['ask']) - 1 >= m), None)
                    if hit is None: continue
                    fp = hit['later'] if (hit['later'] is not None
                                          and hit['later'] <= hit['ask'] + TICK + 1e-12) else None
                    db.execute('INSERT OR REPLACE INTO fires(margin,epoch,ts_ms,sec,side,p_win,p_engine,ask,'
                               'opp_ask,ev,later_ask,filled,fill_price,slip,dip30,d1,d5,d30,outcome,win,'
                               'graded_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (m, ep, hit['t'], hit['sec'], hit['side'], hit['p'], hit['pe'], hit['ask'],
                                hit['opp'], hit['p'] / be(hit['ask']) - 1, hit['later'],
                                1 if fp else 0, fp, (fp - hit['ask']) if fp else None,
                                hit['dip'], hit['d1'], hit['d5'], hit['d30'], None, None, None))
                db.execute('INSERT OR REPLACE INTO seen VALUES(?,?,?,?)', (ep, len(rows), ncand, time.time()))
                db.commit(); done.add(ep)
                fired = db.execute('SELECT count(*) FROM fires WHERE epoch=?', (ep,)).fetchone()[0]
                log(db, f'{ep} passes {len(rows)} candidates {ncand} skipped-for-missing-features '
                        f'{nmiss} -> {fired}/{len(MARGINS)} margins fired')
            # grade anything old enough
            import urllib.request
            for (e2,) in db.execute('SELECT DISTINCT epoch FROM fires WHERE outcome IS NULL AND ?-epoch>420',
                                    (now,)).fetchall():
                try:
                    rq = urllib.request.Request(GAMMA.format(e2), headers={'User-Agent': 'zurich-ef2-shadow/1.0'})
                    with urllib.request.urlopen(rq, timeout=12) as r: data = json.loads(r.read().decode())
                except Exception: continue
                for ev in data or []:
                    for mk in ev.get('markets', []):
                        if mk.get('slug') != f'btc-updown-5m-{e2}': continue
                        pr = mk.get('outcomePrices')
                        if not pr: continue
                        pr = json.loads(pr) if isinstance(pr, str) else pr
                        out = 'UP' if float(pr[0]) > 0.5 else 'DOWN'
                        db.execute('UPDATE fires SET outcome=?,win=(side=?),graded_ts=? WHERE epoch=?',
                                   (out, out, time.time(), e2)); db.commit()
        except Exception as e:
            try: log(db, f'loop error {repr(e)[:140]}')
            except Exception: pass
            time.sleep(5)


if __name__ == '__main__':
    main()
