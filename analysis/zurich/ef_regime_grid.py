#!/usr/bin/env python3
"""Is there a regime where fixed15 is robustly profitable UNDER LONDON EXECUTION? READ-ONLY.

Owner/V: London's Fixed EF made money 09-23..25 (weekdays) and lost 09-26..27 (weekend, quiet).

Buckets were fixed in V's brief BEFORE anything was looked at, and are implemented exactly as written:
  (a) trailing-60-minute realised vol tercile, cut on ALL fires
  (b) weekday vs weekend (UTC)
  (c) UTC session 00-08 / 08-16 / 16-24
  (d) 1 h trailing BTC range tercile
Both (a) and (d) use only the 60 minutes BEFORE the candle opens, so no bucket can see the outcome.

Re-profiling to fixed15, exactly as the engine judges it: q = platt(p_raw) with a=1.0677 b=-0.3208 and
q=min(p,q), and EV is taken at **ask + 1 tick** (poly_core.EV_REFERENCE_PAD), not at the raw ask -
  _px  = ceil(ask/tick)*tick + 1 tick,  f = 0.07*_px*(1-_px),  cost = max(_px+f, _px/(1-f/_px))
  fire when q/cost - 1 >= 0.15
That reference pad is why a naive ask-based EV admits trades the engine refuses; using the raw ask here
would have loosened the bar by ~0.02 and quietly changed which fires exist.

Grading: the venue's own gamma resolution. Execution: analysis/v/rawfixed/LONDON_EXEC_MODEL.md -
P(fill|would win) 0.541, P(fill|would lose) 0.650, slippage p10/p50/p90 -1/+2/+11c on top, fee
0.07*sh*p*(1-p), $10 stake, 1000 Monte Carlo runs.
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections, numpy as np
from decimal import Decimal, ROUND_CEILING

JOURNALS = ['/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3',
            '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3',
            '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3',
            '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3']
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
K1M = '/tmp/poly/btc1m.sqlite3'
A, B, RATE, TICK, PAD = 1.0677, -0.3208, 0.07, 0.01, 1
THETA, STAKE, RUNS, MIN_CELL = 0.15, 10.0, 1000, 60
D = lambda x: Decimal(str(x))

def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A * z + B)))))

def ev_at_pad(q, ask):
    """EV judged at ask + PAD ticks, the engine's own EV reference (poly_core.order_plan)."""
    px = float((D(ask) / D(TICK)).to_integral_value(rounding=ROUND_CEILING) * D(TICK) + D(PAD) * D(TICK))
    px = min(px, float(D(1) - D(TICK)))
    f = RATE * px * (1 - px)
    cost = max(px + f, px / (1 - f / px))
    return q / cost - 1

cost1 = lambda x: 1 + RATE * (1 - x)
per1 = lambda w, x: (w / x - cost1(x)) / cost1(x)

def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out

def klines():
    c = sqlite3.connect(f'file:{K1M}?mode=ro', uri=True)
    return {int(ts): (o, h, l, cl) for ts, o, h, l, cl in c.execute('SELECT ts,o,h,l,cl FROM k1m')}

def ctx(km, ep):
    """Trailing-60-min realised vol and range, both ending at the minute BEFORE the candle opens."""
    m0 = (ep // 60) * 60
    win = [km.get(m0 - 60 * k) for k in range(1, 61)]
    if any(v is None for v in win): return None, None
    win = win[::-1]
    cl = [w[3] for w in win]
    rets = [math.log(b / a) for a, b in zip(cl, cl[1:]) if a > 0 and b > 0]
    if len(rets) < 50: return None, None
    vol = st.pstdev(rets)
    hi = max(w[1] for w in win); lo = min(w[2] for w in win); mid = (hi + lo) / 2
    rng = 1e4 * (hi - lo) / mid if mid > 0 else None
    return vol, rng

def load():
    vo = outcomes(); km = klines()
    fires = {}
    for path in JOURNALS:
        try: c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        except Exception: continue
        rows = collections.defaultdict(list)
        try: it = c.execute('SELECT ts,detail FROM diagnostics ORDER BY ts')
        except Exception: continue
        for ts, d in it:
            try: j = json.loads(d)
            except Exception: continue
            if j.get('mode') != 'pnl' or 'breakeven' not in j: continue
            p, ask, side = j.get('p'), j.get('ask'), j.get('side')
            if not isinstance(p, (int, float)) or not isinstance(ask, (int, float)) or not side: continue
            if not (0.01 < ask < 0.99): continue
            pr = j.get('p_raw')
            rows[int(ts // 300) * 300].append((ts, float(pr if isinstance(pr, (int, float)) else p), float(ask), side))
        for ep, rs in rows.items():
            if ep in fires or ep not in vo: continue
            rs.sort()
            for ts, pr, ask, side in rs:
                q = platt(pr)
                if ev_at_pad(q, ask) < THETA: continue
                vol, rng = ctx(km, ep)
                if vol is None: break
                t = dt.datetime.fromtimestamp(ep, dt.timezone.utc)
                fires[ep] = dict(epoch=ep, ts=ts, sec=ts - ep, ask=ask, side=side, p_cal=q, p_raw=pr,
                                 win=int(side == vo[ep]), vol=vol, rng=rng, day=t.strftime('%m-%d'),
                                 dow=t.weekday(), hour=t.hour,
                                 ev=ev_at_pad(q, ask))
                break
        c.close()
    return sorted(fires.values(), key=lambda r: r['ts'])

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def london(rows, seed=17, runs=RUNS):
    if not rows: return None, None, None
    rng = random.Random(seed); tots = []; spent = []; posd = []
    for _ in range(runs):
        t = s = 0.; day = collections.defaultdict(float)
        for r in rows:
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r['ask'] + slip(rng))); sh = STAKE / px
            fee = RATE * sh * px * (1 - px); s += STAKE + fee
            g = (sh if r['win'] else 0) - STAKE - fee
            t += g; day[r['day']] += g
        tots.append(t); spent.append(s)
        if day: posd.append(sum(1 for v in day.values() if v > 0) / len(day))
    return (np.mean(tots) / max(1e-9, np.mean(spent))), float(np.mean(tots)), (np.mean(posd) if posd else None)

def halves_london(rows):
    h = len(rows) // 2
    s = sorted(rows, key=lambda r: r['ts'])
    a = london(s[:h], runs=300)[0] if h else None
    b = london(s[h:], runs=300)[0] if len(s) - h else None
    return a, b

def cell(name, rows, cuts=None):
    if not rows:
        print(f'  {name:30s}     0        (none)'); return None
    lon, tot, posd = london(rows)
    a, b = halves_london(rows)
    days = collections.defaultdict(float)
    for r in rows: days[r['day']] += per1(r['win'], r['ask'])
    pos_paper = sum(1 for v in days.values() if v > 0)
    paper = sum(per1(r['win'], r['ask']) * cost1(r['ask']) for r in rows) / sum(cost1(r['ask']) for r in rows)
    flag = '' if len(rows) >= MIN_CELL else ' *'
    both = (a is not None and b is not None and a > 0 and b > 0)
    print(f'  {name:30s}{len(rows):6d}{flag:2s}{100*np.mean([r["win"] for r in rows]):6.1f}%'
          f'{paper:+9.3f}{lon:+11.3f}{(a if a is not None else 0):+9.3f}{(b if b is not None else 0):+9.3f}'
          f'{pos_paper:>5}/{len(days):<4}{100*(posd or 0):6.0f}%{tot:+9.1f}'
          + ('   <- both halves +' if both else ''))
    return dict(name=name, n=len(rows), lon=lon, h1=a, h2=b, rows=rows, both=both, paper=paper,
                days=len(days), pos=pos_paper)

HDR = (f'  {"bucket":30s}{"n":>6}{"":2s}{"win%":>7}{"paper":>9}{"LONDON":>11}{"H1":>9}{"H2":>9}'
       f'{"posDays":>10}{"posD%exec":>9}{"total$":>9}')

if __name__ == '__main__':
    rows = load()
    if not rows:
        print('no fires'); raise SystemExit
    days = sorted({r['day'] for r in rows})
    print(f'fixed15 re-profiled fires (EV>=0.15 at ask+{PAD} tick), gamma-graded: {len(rows)} on '
          f'{len(days)} days {days[0]}..{days[-1]}')
    print(f'  overall win {100*np.mean([r["win"] for r in rows]):.1f}%, ask p50 {np.median([r["ask"] for r in rows]):.2f}, '
          f'sec p50 {int(np.median([r["sec"] for r in rows]))}')
    vols = np.array([r['vol'] for r in rows]); rngs = np.array([r['rng'] for r in rows])
    v1, v2 = np.percentile(vols, [33.333, 66.667]); r1, r2 = np.percentile(rngs, [33.333, 66.667])
    print(f'  tercile cuts on ALL fires: vol {v1:.6f} / {v2:.6f} (1 m realised sd); '
          f'range {r1:.1f} / {r2:.1f} bps')
    keep = []
    print(f'\n{"="*124}\nFULL GRID. LONDON = London-exec per$1. posDays = paper days positive. '
          f'posD%exec = mean share of days positive under execution.\n{"="*124}')
    print('\n(a) TRAILING-60-MIN REALISED VOL TERCILE'); print(HDR)
    for lab, sel in (('vol LOW', lambda r: r['vol'] <= v1), ('vol MID', lambda r: v1 < r['vol'] <= v2),
                     ('vol HIGH', lambda r: r['vol'] > v2)):
        c_ = cell(lab, [r for r in rows if sel(r)]);  keep.append(c_)
    print('\n(b) WEEKDAY vs WEEKEND (UTC)'); print(HDR)
    for lab, sel in (('weekday Mon-Fri', lambda r: r['dow'] < 5), ('weekend Sat-Sun', lambda r: r['dow'] >= 5)):
        keep.append(cell(lab, [r for r in rows if sel(r)]))
    print('\n(c) UTC SESSION'); print(HDR)
    for lab, lo, hi in (('00-08 UTC', 0, 8), ('08-16 UTC', 8, 16), ('16-24 UTC', 16, 24)):
        keep.append(cell(lab, [r for r in rows if lo <= r['hour'] < hi]))
    print('\n(d) 1 H TRAILING BTC RANGE TERCILE'); print(HDR)
    for lab, sel in (('range LOW', lambda r: r['rng'] <= r1), ('range MID', lambda r: r1 < r['rng'] <= r2),
                     ('range HIGH', lambda r: r['rng'] > r2)):
        keep.append(cell(lab, [r for r in rows if sel(r)]))
    print('\nALL FIRES (reference)'); print(HDR)
    keep.append(cell('all fires', rows))

    cands = [c for c in keep if c and c['both'] and c['n'] >= MIN_CELL]
    print(f'\n{"="*124}\nCELLS POSITIVE IN BOTH HALVES WITH n>={MIN_CELL}: '
          + (', '.join(c['name'] for c in cands) if cands else 'NONE') + f'\n{"="*124}')
    if not cands:
        print('  Nothing to run verify.py on. That is the answer to the owner\'s question on this sample:')
        print('  no bucket is both large enough and stable enough under London execution to be worth testing.')
    else:
        import sys as _s; _s.path.insert(0, 'analysis/h1'); import verify as V
        vo = outcomes()
        lc = sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro', uri=True)
        eng = {int(e): a for e, a in lc.execute('SELECT epoch,actual FROM results WHERE actual IS NOT NULL')}
        for c_ in cands:
            R = c_['rows']
            F = V.Finding(f'fixed15 under London execution, {c_["name"]}', per_fire=c_['lon'], n=c_['n'])
            eps = {r['epoch'] for r in R}
            F.grading(gamma_venue_resolution={e: vo[e] for e in eps if e in vo},
                      engine_results_actual={e: eng[e] for e in eps if e in eng})
            F.quote_age(rule='same-instant', max_age_s=0.0, source='diagnostics pnl row (executor read)')
            F.sample({c_['name']: c_['n']})
            F.halves(c_['h1'], c_['h2'])
            orig = [r['side'] for r in R]
            def pnl_fn(y_, pred_, price_):
                tot = ct = 0.
                for a_, s_, q_, o_ in zip(y_, pred_, price_, orig):
                    flip = (s_ != o_) if isinstance(s_, str) else False
                    qq = min(0.99, 1 - q_ + 0.01) if flip else q_
                    sh = STAKE / qq; fee = RATE * sh * qq * (1 - qq)
                    ct += STAKE + fee; tot += (sh if a_ else 0.)
                return (tot - ct) / ct
            rng = random.Random(5); sims = []
            real = c_['lon']
            for _ in range(400):
                flipped = [dict(r, win=(1 - r['win']), ask=min(0.99, max(0.01, 1 - r['ask'] + 0.01)))
                           if rng.random() < 0.5 else r for r in R]
                sims.append(london(flipped, seed=rng.randint(1, 10**6), runs=60)[0])
            sims.sort()
            F._add('permutation control', (sum(1 for x in sims if x >= real) / len(sims)) <= 0.01,
                   'London-exec %+.3f vs coin-flip sides priced at the OPPOSITE ask: mean %+.3f (p95 %+.3f), '
                   'p=%.3f over 400 draws' % (real, st.mean(sims), sims[int(.95 * len(sims))],
                                              sum(1 for x in sims if x >= real) / len(sims)))
            def at(c):
                s2 = [dict(r, ask=min(0.99, r['ask'] + c)) for r in R]
                return london(s2, runs=200)[0]
            F.costs({0.0: real, 0.02: at(0.02), 0.05: at(0.05)})
            cheap = london([dict(r, win=1 - r['win'], ask=min(0.99, max(0.01, 1 - r['ask'] + 0.01))) for r in R],
                           runs=300)[0]
            F.null(real, cheap, 'buy the other side instead')
            F.verdict()
