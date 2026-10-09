#!/usr/bin/env python3
"""Can EF be made STABLE - few good trades a day instead of many - by selectivity and staking?
READ-ONLY backtest. No config change, nothing live. Kelly/dynamic staking live still needs the
owner's two separate confirmations (CLAUDE.md); this is research only.

Owner (09-27 11:3x): "work on staking or removing loss... stable version... fine with 5 winning trades a
day instead of 50 at 50% win rate... then I can use hybrid staking."

Fires are rebuilt from the engine's own `diagnostics` pnl rows, the same source raw_vs_fixed_london_exec
uses, so both profiles exist on the SAME candles over the whole EF history rather than only where
decide_log reaches:
    RAW    first pass with ev(p_raw)        >= 0.25
    FIXED  first pass with ev(platt(p_raw)) >= 0.15,  platt a=1.0677 b=-0.3208, q=min(p,q)
    ev = p/(ask*(1+0.07*(1-ask))) - 1;  the ask is the executor's own read at that pass, so past-only.

RANKING STATISTIC, fixed before looking, as V specified: the CALIBRATED EDGE
    edge = platt(p_raw) - ask*(1 + 0.07*(1-ask))
i.e. probability minus break-even probability. Tiers keep the top X% of fires WITHIN EACH DAY, so the bar
adapts day by day instead of being a fixed threshold fitted to the sample.

Grading: the venue's own resolution from gamma (`btc-updown-5m-<epoch>` outcomePrices), fetched for this
window; engine `results.actual` only where gamma has no row, and the split is printed.
London execution: the lane_exec_sim model - P(fill|would win) 54.1%, P(fill|would lose) 65.0%, slippage
p10/p50/p90 -1/+2/+11c on top, fee 0.07*sh*p*(1-p).
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections, numpy as np

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
OTHERS = ['/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3',
          '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3']
BTC5 = '/tmp/poly/btc5.sqlite3'
A, B = 1.0677, -0.3208
RATE = 0.07
BASE = 10.0
RUNS = 400
TIERS = (0.05, 0.10, 0.20, 0.40, 1.00)

be = lambda q: q * (1 + RATE * (1 - q))
per1 = lambda w, q: (w / q - (1 + RATE * (1 - q))) / (1 + RATE * (1 - q))
def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A * z + B)))))
ev = lambda p, q: (p / be(q) - 1) if be(q) > 0 else -1

def outcomes():
    out, src = {}, 'gamma'
    try:
        c = sqlite3.connect(f'file:{BTC5}?mode=ro', uri=True)
        out = {int(e): o for e, o in c.execute("SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")}
    except Exception as e:
        print(f'gamma btc outcomes unavailable ({repr(e)[:50]}) - falling back to results.actual only')
    return out

def load():
    vo = outcomes()
    cands = {}
    for path in [LIVE] + OTHERS:
        try: c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        except Exception: continue
        try: res = dict(c.execute('SELECT epoch,actual FROM results').fetchall())
        except Exception: continue
        rows = collections.defaultdict(list)
        for ts, d in c.execute('SELECT ts,detail FROM diagnostics ORDER BY ts'):
            try: j = json.loads(d)
            except Exception: continue
            if j.get('mode') != 'pnl' or 'breakeven' not in j: continue
            p, ask, side = j.get('p'), j.get('ask'), j.get('side')
            if not isinstance(p, (int, float)) or not isinstance(ask, (int, float)) or not side: continue
            if not (0.01 < ask < 0.99): continue
            pr = j.get('p_raw')
            rows[int(ts // 300) * 300].append((ts, float(pr if isinstance(pr, (int, float)) else p), float(ask), side))
        for ep, rs in rows.items():
            gsrc = 'gamma' if ep in vo else 'engine'
            act = vo.get(ep, res.get(ep))
            if act is None: continue
            rs.sort()
            for arm, tr, thr in (('RAW', lambda x: x, 0.25), ('FIXED', platt, 0.15)):
                for ts, pr, ask, side in rs:
                    if ev(tr(pr), ask) >= thr:
                        k = (arm, ep)
                        if k in cands: break
                        cands[k] = dict(arm=arm, epoch=ep, ts=ts, sec=ts - ep, ask=ask, side=side,
                                        p_raw=pr, p_cal=platt(pr), win=int(side == act), gsrc=gsrc,
                                        day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'))
                        break
        c.close()
    for v in cands.values(): v['edge'] = v['p_cal'] - be(v['ask'])
    return sorted(cands.values(), key=lambda x: x['ts'])

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def london(rows, stakes):
    rng = random.Random(17); tot = []; spent = []
    for _ in range(RUNS):
        t = s = 0.
        for r, stk in zip(rows, stakes):
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r['ask'] + slip(rng))); sh = stk / px
            fee = RATE * sh * px * (1 - px); s += stk + fee
            t += (sh if r['win'] else 0) - stk - fee
        tot.append(t); spent.append(s)
    return (np.mean(tot) / max(1e-9, np.mean(spent))), float(np.mean(tot))

def curve(rows, stakes):
    pnl = [stk * per1(r['win'], r['ask']) for r, stk in zip(rows, stakes)]
    cum = peak = mdd = 0.
    for x in pnl:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    day = collections.defaultdict(float)
    for r, x in zip(rows, pnl): day[r['day']] += x
    ds = list(day.values())
    worst3h = 0.
    for i in range(len(rows)):
        s = 0.
        for j in range(i, len(rows)):
            if rows[j]['ts'] - rows[i]['ts'] > 3 * 3600: break
            s += pnl[j]
        worst3h = min(worst3h, s)
    return dict(pnl=cum, mdd=mdd, ratio=(cum / mdd if mdd > 0 else float('inf')),
                spent=sum(stakes) + sum(RATE * (stk / r['ask']) * r['ask'] * (1 - r['ask'])
                                        for r, stk in zip(rows, stakes)),
                days=len(ds), pos_days=sum(1 for v in ds if v > 0), worst_day=min(ds) if ds else 0.,
                day_std=(st.pstdev(ds) if len(ds) > 1 else 0.), worst3h=worst3h, seq=pnl)

def halves(rows, stakes):
    h = len(rows) // 2
    a = curve(rows[:h], stakes[:h]); b = curve(rows[h:], stakes[h:])
    f = lambda c: (c['pnl'] / c['spent']) if c['spent'] else 0.
    return f(a), f(b)

def top_per_day(rows, frac, key='edge'):
    by = collections.defaultdict(list)
    for r in rows: by[r['day']].append(r)
    keep = []
    for d, rs in by.items():
        rs = sorted(rs, key=lambda x: -x[key])
        k = max(1, int(round(frac * len(rs)))) if frac < 1.0 else len(rs)
        keep += rs[:k]
    return sorted(keep, key=lambda x: x['ts'])

# ------------------------------------------------------------------ staking arms
def kelly_frac(p, q):
    """Binary Kelly at price q: stake S buys S/q shares, so net odds b=(1-q)/q and f* = (p-q)/(1-q)."""
    if not (0 < q < 1): return 0.
    return max(0., (p - q) / (1 - q))

def stakes_for(rows, arm, bankroll=500.0, fit_days=None):
    """Every arm is normalised to deploy the SAME total as fixed-$10 so per$1 and maxDD are comparable
    per dollar risked, not just per trade. Terciles and the MA window use PRIOR DAYS ONLY."""
    n = len(rows)
    if arm == 'A fixed $10':
        raw = [BASE] * n
    elif arm == 'B tiered 5/10/20 by edge tercile':
        raw = []
        seen = []
        for r in rows:
            hist = [x['edge'] for x in seen if x['day'] < r['day']]
            if len(hist) < 30: raw.append(BASE)
            else:
                lo, hi = np.percentile(hist, [33.3, 66.7])
                raw.append(5.0 if r['edge'] <= lo else (20.0 if r['edge'] > hi else 10.0))
            seen.append(r)
    elif arm == 'C half-Kelly on calibrated p (cap 3x)':
        raw = [min(3 * BASE, bankroll * kelly_frac(r['p_cal'], r['ask']) / 2.0) for r in rows]
        raw = [max(3.0, x) for x in raw]
    elif arm.startswith('F de-risk below MA'):
        k = int(arm.split('(')[1].split(')')[0])
        raw = []; eq = 0.; hist = []
        for r in rows:
            ma = st.mean(hist[-k:]) if len(hist) >= k else None
            raw.append(BASE * (0.5 if (ma is not None and eq < ma) else 1.0))
            eq += BASE * per1(r['win'], r['ask']); hist.append(eq)
    else:
        raise ValueError(arm)
    tot = sum(raw)
    scale = (BASE * n / tot) if tot > 0 else 1.0
    return [max(3.0, x * scale) for x in raw]

def fit_F(rows):
    """k chosen on the FIRST HALF of the days only."""
    days = sorted({r['day'] for r in rows})
    if len(days) < 4: return 20
    cut = days[len(days) // 2]
    first = [r for r in rows if r['day'] < cut]
    best, bk = -1e18, 20
    for k in (10, 20, 40):
        s = curve(first, stakes_for(first, f'F de-risk below MA({k})'))
        v = s['ratio'] if s['mdd'] > 0 else -1e9
        if v > best: best, bk = v, k
    return bk

def line(name, rows, stakes=None, show_lon=True):
    if not rows:
        print(f'  {name:36s}      (none)'); return None
    stakes = stakes or [BASE] * len(rows)
    c = curve(rows, stakes)
    p1 = c['pnl'] / c['spent'] if c['spent'] else 0.
    h1, h2 = halves(rows, stakes)
    lon = london(rows, stakes) if show_lon else (float('nan'), float('nan'))
    days = c['days']
    mark = '' if len(rows) >= 60 else ' *'
    print(f'  {name:36s}{len(rows):5d}{mark:2s}{len(rows)/max(days,1):6.1f}{100*np.mean([r["win"] for r in rows]):7.1f}%'
          f'{p1:+8.3f}{lon[0]:+9.3f}{c["day_std"]:8.1f}{c["worst_day"]:+9.1f}{c["mdd"]:8.1f}'
          f'{100*c["pos_days"]/max(days,1):7.0f}%{h1:+8.3f}{h2:+8.3f}')
    return dict(name=name, n=len(rows), per1=p1, lon=lon[0], lon_tot=lon[1], **c, h1=h1, h2=h2)

HDR = (f'  {"cell":36s}{"n":>5}{"":2s}{"/day":>6}{"win%":>8}{"paper":>8}{"LONDON":>9}'
       f'{"dayStd":>8}{"worstDay":>9}{"maxDD":>8}{"pos%":>8}{"H1":>8}{"H2":>8}')

# ------------------------------------------------------------------ main
if __name__ == '__main__':
    rows = load()
    gs = collections.Counter(r['gsrc'] for r in rows)
    print(f'EF fires rebuilt from diagnostics: {len(rows)} across both profiles, '
          f'{len({r["epoch"] for r in rows})} candles, {len({r["day"] for r in rows})} days')
    print(f'grading: gamma venue resolution {gs["gamma"]}, engine results.actual {gs["engine"]}')
    for arm in ('RAW', 'FIXED'):
        sub = [r for r in rows if r['arm'] == arm]
        print(f'  {arm:5s} {len(sub)} fires, {len({r["day"] for r in sub})} days, '
              f'win {100*np.mean([r["win"] for r in sub]):.1f}%, ask p50 {np.median([r["ask"] for r in sub]):.2f}, '
              f'edge p50 {np.median([r["edge"] for r in sub]):+.4f}')

    for arm in ('RAW', 'FIXED'):
        sub = [r for r in rows if r['arm'] == arm]
        if not sub: continue
        print(f'\n{"="*140}\n1. SELECTIVITY by calibrated edge, top X% WITHIN EACH DAY - {arm}\n{"="*140}')
        print(HDR)
        for f in TIERS:
            line(f'top {int(f*100):>3}% by edge', top_per_day(sub, f))
        print(f'\n  context: ASK BUCKET ({arm})')
        for lo, hi in ((0, .25), (.25, .35), (.35, .45), (.45, .55), (.55, 1.0)):
            line(f'ask {lo:.2f}-{hi:.2f}', [r for r in sub if lo <= r['ask'] < hi])
        print(f'\n  context: FIRE SECOND ({arm})')
        for lo, hi in ((0, 60), (60, 120), (120, 180), (180, 240), (240, 300)):
            line(f'sec {lo}-{hi}', [r for r in sub if lo <= r['sec'] < hi])

    # ---- staking, on the tier the owner's "5 a day" implies and on all fires, both profiles
    print(f'\n{"="*140}\n2. HYBRID STAKING. Every arm normalised to deploy the same total as fixed $10.\n{"="*140}')
    results = []
    for arm in ('RAW', 'FIXED'):
        sub = [r for r in rows if r['arm'] == arm]
        if not sub: continue
        for tier_name, tier in (('all fires', 1.00), ('top 20%/day', 0.20), ('top 10%/day', 0.10)):
            R = top_per_day(sub, tier)
            if not R: continue
            k = fit_F(R)
            print(f'\n  --- {arm}, {tier_name}: {len(R)} fires, {len(R)/max(len({r["day"] for r in R}),1):.1f}/day ---')
            print(HDR.replace('cell', 'staking arm'))
            for name in ('A fixed $10', 'B tiered 5/10/20 by edge tercile',
                         'C half-Kelly on calibrated p (cap 3x)', f'F de-risk below MA({k})'):
                stk = stakes_for(R, name)
                res = line(name, R, stk)
                if res:
                    res.update(arm=arm, tier=tier_name, staking=name,
                               ret_mdd=(res['pnl'] / res['mdd'] if res['mdd'] > 0 else float('inf')))
                    results.append(res)
                    print(f'       total ${res["pnl"]:+.2f} on ${res["spent"]:.0f} deployed | maxDD ${res["mdd"]:.2f} '
                          f'| return/maxDD {res["ret_mdd"]:+.2f} | worst 3 h ${res["worst3h"]:+.2f} '
                          f'| London total ${res["lon_tot"]:+.1f}')

    print(f'\n{"="*140}\n3. RANKED ON STABILITY, not total PnL: share of positive days first, then return/maxDD\n{"="*140}')
    ok = [r for r in results if r['days'] >= 3]
    ok.sort(key=lambda r: (-(r['pos_days'] / max(r['days'], 1)), -(r['ret_mdd'] if r['ret_mdd'] != float('inf') else 1e9)))
    print(f'  {"arm":58s}{"n":>5}{"pos%":>7}{"ret/DD":>9}{"paper":>8}{"LONDON":>9}{"worst3h":>10}{"maxDD":>8}')
    for r in ok:
        nm = f'{r["arm"]} {r["tier"]} / {r["staking"]}'
        rd = f'{r["ret_mdd"]:+.2f}' if r['ret_mdd'] != float('inf') else '  inf'
        print(f'  {nm:58s}{r["n"]:5d}{100*r["pos_days"]/r["days"]:6.0f}%{rd:>9}{r["per1"]:+8.3f}'
              f'{r["lon"]:+9.3f}{r["worst3h"]:+10.2f}{r["mdd"]:8.1f}'
              + ('  *n<60' if r['n'] < 60 else ''))
    print('\n  * = under 60 fires, not a reading. Ranked on stability as ordered; nothing here is selected')
    print('    as "the best cell" - the whole grid is above and the London column is the one that matters.')

    # ------------------------------------------------------------------ 4. verify.py on the arm I'd recommend
    print(f'\n{"="*140}\n4. verify.py on the arm I would put forward: RAW, top 20% by edge per day\n{"="*140}')
    import sys as _sys, os as _os
    # absolute, not 'analysis/h1': this is a STANDING re-run job, and a relative path made it work only
    # when launched from the repo root - it died with ModuleNotFoundError on the 09-28 re-run from
    # analysis/zurich, after every table above had already been computed.
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'h1'))
    import verify as V
    R = top_per_day([r for r in rows if r['arm'] == 'RAW'], 0.20)
    # grading: the venue's resolution vs the engine's own label, on the epochs where both exist
    vo = outcomes()
    lc = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    eng = {int(e): a for e, a in lc.execute('SELECT epoch,actual FROM results WHERE actual IS NOT NULL')}
    ep_set = {r['epoch'] for r in R}
    g = {e: vo[e] for e in ep_set if e in vo}; h = {e: eng[e] for e in ep_set if e in eng}
    F = V.Finding('EF RAW, top 20% by calibrated edge per day', per_fire=None, n=len(R))
    F.grading(gamma_venue_resolution=g, engine_results_actual=h)
    # 'same-instant': the ask in a diagnostics pnl row is the executor's own book read at the very pass
    # that decided, not a forward-filled collector sample. My first call passed a prose string, which
    # verify correctly refused - the literal matters because this check exists to catch exactly the
    # stale-quote trap that turned a 0.00 edge into +0.27/fire on Task 20.
    F.quote_age(rule='same-instant', max_age_s=0.0, source='diagnostics pnl rows (executor read)')
    F.sample({'top 20% by edge per day': len(R)})
    hh = len(R) // 2
    st_ = [BASE] * len(R)
    F.halves(curve(R[:hh], st_[:hh])['pnl'] / max(curve(R[:hh], st_[:hh])['spent'], 1e-9),
             curve(R[hh:], st_[hh:])['pnl'] / max(curve(R[hh:], st_[hh:])['spent'], 1e-9))
    y = [r['win'] for r in R]; pred = [r['p_cal'] for r in R]; price = [r['ask'] for r in R]
    orig = [r['side'] for r in R]
    def pnl_fn(y_, pred_, price_):
        """A flipped side pays ITS OWN ask (1-q), never the original side's - the c299e19 correction."""
        tot = cost = 0.
        for a_, s_, q_, o_ in zip(y_, pred_, price_, orig):
            flipped = (s_ != o_) if isinstance(s_, str) else False
            qq = min(0.99, 1 - q_ + 0.01) if flipped else q_
            sh = BASE / qq; fee = RATE * sh * qq * (1 - qq)
            cost += BASE + fee; tot += (sh if a_ else 0.)
        return (tot - cost) / cost
    # The claim is that the EDGE RANKING picks the good fires, so the control has to break the ranking:
    # keep the same number of fires per day, chosen at RANDOM instead of by edge. My first attempt passed
    # a pnl_fn that ignored the shuffled predictions, so real and permuted were identical at p=1.000 -
    # a control that cannot fail. This one can.
    allraw = [r for r in rows if r['arm'] == 'RAW']
    byday = collections.defaultdict(list)
    for r in allraw: byday[r['day']].append(r)
    want = {d: len([x for x in R if x['day'] == d]) for d in byday}
    real_p1 = curve(R, [BASE] * len(R))
    real_v = real_p1['pnl'] / max(real_p1['spent'], 1e-9)
    rng = random.Random(7); sims = []
    for _ in range(1000):
        pick = []
        for d, rs in byday.items():
            k = want.get(d, 0)
            if k: pick += rng.sample(rs, min(k, len(rs)))
        pick.sort(key=lambda x: x['ts'])
        c_ = curve(pick, [BASE] * len(pick))
        sims.append(c_['pnl'] / max(c_['spent'], 1e-9))
    sims.sort()
    pv = sum(1 for x in sims if x >= real_v) / len(sims)
    F._add('permutation control', pv <= 0.01,
           'edge-ranked %+.3f vs SAME COUNT PER DAY chosen at random: mean %+.3f (p95 %+.3f), p=%.3f '
           'over 1000 draws' % (real_v, st.mean(sims), sims[int(.95 * len(sims))], pv))
    def at_cost(c):
        num = sum(BASE * per1(r['win'], min(0.99, r['ask'] + c)) for r in R)
        den = sum(BASE * (1 + RATE * (1 - min(0.99, r['ask'] + c))) for r in R)
        return num / max(den, 1e-9)
    F.costs({c: at_cost(c) for c in (0.0, 0.02, 0.05)})
    cheap = sum(BASE * per1(1 - r['win'], min(0.99, 1 - r['ask'] + 0.01)) for r in R) / \
            max(sum(BASE * (1 + RATE * (1 - min(0.99, 1 - r['ask'] + 0.01))) for r in R), 1e-9)
    F.null(curve(R, st_)['pnl'] / max(curve(R, st_)['spent'], 1e-9), cheap, 'buy the other side instead')
    sw = []
    for f in TIERS:
        T = top_per_day([r for r in rows if r['arm'] == 'RAW'], f)
        c_ = curve(T, [BASE] * len(T))
        sw.append(c_['pnl'] / max(c_['spent'], 1e-9))
    print(f'  sweep over tiers {[int(f*100) for f in TIERS]}%: ' + ' '.join(f'{x:+.3f}' for x in sw))
    F.sweep(sw)
    print(f'\n  verdict(): {F.verdict()}')
