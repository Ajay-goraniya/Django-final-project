#!/usr/bin/env python3
"""V 09-28 17:1x: why does London's E3 replay lose where Zurich's EF-6 wins? READ-ONLY. Master OFF.

Same model json, same ef6_lane, three price/cadence regimes on Zurich's decide_log:
  (1) full 250 ms cadence, price = quoted ask, NO fill sim
  (2) as (1) but one pass per 15 s      <- London's diag cadence
  (3) as (2) plus Zurich's +250 ms FAK sim
If (2) loses, E3 depends on 250 ms timing. If (1) loses, on the fill sim. If all three win, the difference
is in London's feature values, and the next step is to diff the 18 split features on shared seconds.
"""
import sys, os, json, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/ubuntu/claude-work/repo/learner/v12_2')
from ef6_lane import EF6Lane
from ef2_model import per1
from ef3_shadow import outcomes

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
EDIR = '/home/ubuntu/claude-work/repo/learner/v12_2/ef6'
MODEL_DAY = '2026-09-27'
STAKE, TICK, DELAY_MS = 10.0, 0.01, 250


def load():
    L = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(L.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    by = collections.defaultdict(list)
    for ts, ep, side, p, ua, da, fs in c.execute(
            'SELECT ts_ms,epoch,side,p,up_ask,dn_ask,feats FROM decide_log '
            'WHERE p IS NOT NULL AND side IS NOT NULL AND up_ask IS NOT NULL AND dn_ask IS NOT NULL '
            'AND feats IS NOT NULL ORDER BY ts_ms'):
        sec = (ts // 1000) - ep
        if not (15 <= sec <= 240): continue
        try: v = json.loads(fs)
        except Exception: continue
        if len(v) != len(keys): continue
        by[ep].append((ts, sec, dict(zip(keys, v)), float(ua), float(da), side, float(p)))
    return by, keys


def run(by, vo, mode, per_day_model=False):
    """per_day_model=True reloads each day's OWN walk-forward model, as EF-6's backtest did. That is the
    fourth regime V's three do not cover, and it is the one that separates 'the arm works' from 'the model
    London was given works'."""
    lane = EF6Lane(cfg=dict(enabled=True, model_dir=EDIR))
    lane.load_day_model(MODEL_DAY)
    fires = []; curday = None
    for ep in sorted(by):
        rows = by[ep]
        d0 = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        if per_day_model and d0 != curday:
            curday = d0
            if not lane.load_day_model(f'2026-{d0}'):
                lane.model = None
            lane.fired = set()
        if mode in (2, 3):
            seen = set(); sub = []
            for r in rows:
                b = r[0] // 15000
                if b in seen: continue
                seen.add(b); sub.append(r)
            use = sub
        else: use = rows
        ts_a = np.array([r[0] for r in rows]); ua = np.array([r[3] for r in rows]); da = np.array([r[4] for r in rows])
        for ts, sec, feats, u, d, side, p in use:
            r = lane.decide(ep, ts / 1000.0, sec, feats, u, d, side, p)
            if not r: continue
            own = r['ask']; q = own
            if mode == 3:
                j = int(np.searchsorted(ts_a, ts + DELAY_MS, side='left'))
                q = float('nan')
                if j < len(rows):
                    lat = float(ua[j] if r['side'] == 'UP' else da[j])
                    if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q = lat
            fires.append(dict(ep=ep, day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'),
                              side=r['side'], sec=r['sec'], ask=own, q=q,
                              win=(1.0 if vo.get(ep) == r['side'] else 0.0)))
            break
    return fires


def report(tag, fires, days):
    fl = [f for f in fires if f['q'] == f['q']]
    if not fl:
        print(f'  {tag:34s} NO FILLS ({len(fires)} fires)'); return
    tot = sum(STAKE * per1(f['win'], f['q']) for f in fl)
    byd = collections.defaultdict(float); nbyd = collections.Counter()
    for f in fl: byd[f['day']] += STAKE * per1(f['win'], f['q']); nbyd[f['day']] += 1
    print(f'  {tag:34s} $ {tot:+8.1f}  n {len(fires):4d} fills {len(fl):4d}  '
          f'win {100*np.mean([f["win"] for f in fl]):5.1f}%  mean ask {np.mean([f["ask"] for f in fl]):.3f}')
    print(f'  {"":34s} per day $ ' + '  '.join(f'{d} {byd.get(d, 0.0):+7.1f}' for d in days))
    print(f'  {"":34s} per day n ' + '  '.join(f'{d} {nbyd.get(d, 0):7d}' for d in days))


if __name__ == '__main__':
    by, keys = load()
    vo = outcomes()
    by = {e: r for e, r in by.items() if e in vo}
    days = sorted({dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime('%m-%d') for e in by})
    print(f'candles {len(by)}, days {days}, model {MODEL_DAY} (09-24/25/26 are IN-sample for it)')
    print(f'passes: full {sum(len(v) for v in by.values()):,}')
    for mode, tag in ((1, '(1) 250 ms, quoted ask, no fill'),
                      (2, '(2) 15 s subsample, quoted ask'),
                      (3, '(3) 15 s subsample + FAK sim')):
        report(tag, run(by, vo, mode), days)
    print()
    report('(4) 250 ms, per-DAY walk-forward model', run(by, vo, 1, per_day_model=True), days)
