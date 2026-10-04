#!/usr/bin/env python3
"""PARITY: V's engine-side EF6Lane vs Zurich's ef3_shadow arm E3, on one full day. READ-ONLY. Master OFF.

Replays every decide_log pass of a day through learner/v12_2/ef6_lane.EF6Lane, loaded with that day's
engine-format model, and diffs the fires (candle / side / second) against what ef3_shadow recorded for
E3_trail_1h_q90. Two runs:

  as-written  ef6_lane exactly as V pushed it
  +shim       with `_ask_up` / `_ask_dn` added to the row from the up_ask / dn_ask the lane already
              receives. Measured: _ask_up == up_ask and _ask_dn == dn_ask EXACTLY on 39,997 of 40,000
              rows (the 3 exceptions are NULL on both sides). This is the one-line fix ef6_lane needs.
"""
import sys, os, json, sqlite3, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/ubuntu/claude-work/repo/learner/v12_2')
from ef6_lane import EF6Lane, StumpModel

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
SHADOW = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
EDIR = '/home/ubuntu/claude-work/repo/learner/v12_2/ef6'


def replay(day, year, shim, mday=None):
    mp = f'{EDIR}/ef6_{year}-{day}.json'
    if not os.path.exists(mp): sys.exit(f'no engine model at {mp}')
    lane = EF6Lane(cfg=dict(enabled=True, model_dir=EDIR))
    # load THROUGH load_day_model so the seed file is picked up the way the engine would do it
    if not lane.load_day_model(f'{year}-{mday or day}'): sys.exit('load_day_model failed')
    print(f'    seed rows loaded into the trailing window: {len(lane.tq.rows):,}')
    L = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(L.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    fires = {}; npass = 0; nscored = 0
    for ts, ep, side, p, ua, da, fs in c.execute(
            'SELECT ts_ms,epoch,side,p,up_ask,dn_ask,feats FROM decide_log '
            'WHERE p IS NOT NULL AND side IS NOT NULL AND up_ask IS NOT NULL AND dn_ask IS NOT NULL '
            'AND feats IS NOT NULL ORDER BY ts_ms'):
        d = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        if d != day: continue
        sec = (ts // 1000) - ep
        if not (15 <= sec <= 240): continue
        try: v = json.loads(fs)
        except Exception: continue
        if len(v) != len(keys): continue
        feats = dict(zip(keys, v))
        if shim: feats['_ask_up'], feats['_ask_dn'] = float(ua), float(da)
        npass += 1
        before = len(lane.fired)
        r = lane.decide(ep, ts / 1000.0, sec, feats, float(ua), float(da), side, float(p))
        if len(lane.tq.rows) > 0: nscored += 1
        if r: fires[int(ep)] = (r['side'], int(r['sec']))
    return fires, npass, nscored


if __name__ == '__main__':
    day = sys.argv[1] if len(sys.argv) > 1 else '09-27'
    year = '2026'
    s = sqlite3.connect(f'file:{SHADOW}?mode=ro', uri=True)
    mine = {int(e): ('UP' if u else 'DOWN', int(sc)) for e, u, sc in s.execute(
        "SELECT epoch, up, sec FROM fires WHERE arm='E4_trail_1h_q90_strict' AND day=?", (day,))}
    print(f'day {day}: ef3_shadow E3 fired in {len(mine)} candles')

    for shim in (False, True):
        f, npass, nsc = replay(day, year, shim)
        tag = 'ef6_lane +shim' if shim else 'ef6_lane as-written'
        print(f'\n{tag}: {npass:,} passes replayed, fired in {len(f)} candles')
        both = set(mine) & set(f)
        same = [e for e in both if mine[e] == f[e]]
        dside = [e for e in both if mine[e][0] != f[e][0]]
        dsec = [e for e in both if mine[e][0] == f[e][0] and mine[e][1] != f[e][1]]
        print(f'  candles in BOTH {len(both)}  | identical (side+second) {len(same)}'
              f'  | side differs {len(dside)}  | second differs {len(dsec)}')
        print(f'  shadow only {len(set(mine) - set(f))}   lane only {len(set(f) - set(mine))}')
        if dsec[:3]:
            for e in dsec[:3]: print(f'    sec diff  epoch {e}: shadow {mine[e]}  lane {f[e]}')
        if (set(mine) - set(f)) and len(set(mine) - set(f)) <= 6:
            for e in sorted(set(mine) - set(f))[:4]: print(f'    shadow-only epoch {e}: {mine[e]}')
        if (set(f) - set(mine)) and len(set(f) - set(mine)) <= 6:
            for e in sorted(set(f) - set(mine))[:4]: print(f'    lane-only  epoch {e}: {f[e]}')
        if not shim and len(f) == 0:
            print('  -> zero fires as predicted: the trees split on _ask_up/_ask_dn, ef6_lane does not put'
                  ' them in the row, so StumpModel.predict returns None on EVERY row.')
