#!/usr/bin/env python3
"""EF fires on a transient ask DIP in its own read. Does WAITING for the dip to persist fix the fills?
READ-ONLY, Zurich decide_log, gamma-graded. Nothing live.

EF_VETO_V2 measured the mechanism: on raw25 fires the same-source ask is +6.02c HIGHER one decide row
later, against a market-wide drift of only +0.43c. The fire moment is a selected dip, so a FAK priced off
it often has nothing to hit. The direct fix is to require the dip to still be there.

FILL SIMULATOR (V's spec): a FAK at ask_t + 1 tick fills iff OUR side's ask on the first same-candle row at
>= t+250 ms is <= ask_t + 0.01, and it fills AT that later ask. Otherwise no fill at all. Validated against
London's real 31% first-attempt fill rate before anything is concluded from it.

PERSISTENCE: fire on the K-th CONSECUTIVE qualifying pass (K = 1..4), where "qualifying" is the profile's
own EV bar evaluated at that pass's own ask:
  raw25    raw EV >= 0.25 at the ask
  fixed15  platt(p_raw) EV >= 0.15 taken at ask + 1 tick (poly_core.EV_REFERENCE_PAD, as the engine does)
A run breaks the moment a pass does not qualify, so K counts genuine persistence, not elapsed time.
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections, numpy as np
from decimal import Decimal, ROUND_CEILING

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
RATE, TICK, PAD, STAKE = 0.07, 0.01, 1, 10.0
DELAY_MS, LONDON_REAL_FILL = 250, 0.31
KS = (1, 2, 3, 4)
MIN_CELL = 60
DROP = {'_price', '_ask_up', '_ask_dn', '_venue_ok', 'ref_now', 'ref_open', 'bn_line_now',
        'bn_line_open', 'ref_src', 'ref_inst', 'ref_inst_ok', 'sec_left'}
A_P, B_P = 1.0677, -0.3208
Dc = lambda x: Decimal(str(x))
cost = lambda q: 1 + RATE * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)
be = lambda q: q * cost(q)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))

def pad_cost(ask):
    px = float((Dc(ask) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))

qual_raw = lambda pr, ask: (pr / be(ask) - 1) >= 0.25
qual_fix = lambda pr, ask: (platt(pr) / pad_cost(ask) - 1) >= 0.15

def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out

def load():
    vo = outcomes()
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    use = [i for i, k in enumerate(keys) if k not in DROP]
    names = [keys[i] for i in use]
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    cand = collections.defaultdict(list)
    for t, ep, side, p, pr, ask, ua, da, fs in c.execute(
            'SELECT ts_ms,epoch,side,p,p_raw,ask,up_ask,dn_ask,feats FROM decide_log '
            'WHERE p IS NOT NULL AND ask IS NOT NULL AND side IS NOT NULL ORDER BY ts_ms'):
        if ep not in vo or ua is None or da is None: continue
        if not (0.01 < ask < 0.99): continue
        v = None
        if fs:
            try:
                raw = json.loads(fs)
                if len(raw) == len(keys): v = [raw[i] for i in use]
            except Exception: v = None
        cand[ep].append(dict(t=t, ep=ep, side=side, p_raw=float(pr if pr is not None else p),
                             ask=float(ask), ua=float(ua), da=float(da), feats=v,
                             win=int(side == vo[ep]), sec=(t // 1000) - ep))
    out = {}
    for ep, rs in cand.items():
        rs.sort(key=lambda r: r['t'])
        ts = [r['t'] for r in rs]
        for i, r in enumerate(rs):
            r['day'] = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
            j = np.searchsorted(ts, r['t'] + DELAY_MS, side='left')
            if j < len(rs):
                q = rs[j]['ua'] if r['side'] == 'UP' else rs[j]['da']
                r['later'] = q if 0.01 < q < 0.99 else None
                r['later_lag'] = rs[j]['t'] - r['t']
            else: r['later'] = None
        out[ep] = rs
    return out, names

def fill(r):
    """FAK at ask+1 tick: fills iff the later ask is within a tick, AT that later ask."""
    if r.get('later') is None: return None
    return r['later'] if r['later'] <= r['ask'] + TICK + 1e-12 else None

def runs(rs, qual):
    """Mark each pass with the length of the consecutive qualifying run ending there."""
    n = 0
    for r in rs:
        ok = qual(r['p_raw'], r['ask'])
        n = (n + 1) if ok else 0
        r['run'] = n
    return rs

def fire_at_k(rs, qual, K):
    runs(rs, qual)
    for r in rs:
        if r['run'] == K: return r
    return None

def score(sel):
    """sel = list of (row, fill_price). Only FILLED entries carry money."""
    fl = [(r, q) for r, q in sel if q is not None]
    if not fl: return None
    num = sum(per1(r['win'], q) * cost(q) for r, q in fl)
    den = sum(cost(q) for r, q in fl)
    tot = sum(STAKE * per1(r['win'], q) for r, q in fl)
    return dict(n=len(sel), nf=len(fl), fillpct=len(fl) / len(sel), win=np.mean([r['win'] for r, _ in fl]),
                per1=num / den, total=tot, days=len({r['day'] for r, _ in fl}))

def halves(sel):
    fl = sorted([(r, q) for r, q in sel if q is not None], key=lambda x: x[0]['t'])
    h = len(fl) // 2
    f = lambda s: (sum(per1(r['win'], q) * cost(q) for r, q in s) / sum(cost(q) for r, q in s)) if s else None
    return f(fl[:h]), f(fl[h:])

def perm(sel, draws=500, seed=13):
    fl = [(r, q) for r, q in sel if q is not None]
    if not fl: return float('nan'), float('nan')
    real = sum(per1(r['win'], q) * cost(q) for r, q in fl) / sum(cost(q) for r, q in fl)
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        num = den = 0.
        for r, q in fl:
            if rng.random() < 0.5:
                qq = min(0.99, max(0.01, 1 - q + TICK)); w = 1 - r['win']
            else: qq, w = q, r['win']
            num += per1(w, qq) * cost(qq); den += cost(qq)
        sims.append(num / den)
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), st.mean(sims)

def line(lab, sel):
    s = score(sel)
    if not s: print(f'  {lab:30s}{len(sel):5d}      (no fills)'); return None
    a, b = halves(sel); pp, pm = perm(sel)
    print(f'  {lab:30s}{s["n"]:5d}{s["nf"]:6d}{100*s["fillpct"]:7.1f}%{100*s["win"]:7.1f}%'
          f'{s["per1"]:+9.3f}{s["total"]:+9.1f}{(a or 0):+8.3f}{(b or 0):+8.3f}{pp:7.3f}{pm:+8.3f}'
          f'{s["days"]:>5}' + ('  *n<60' if s['nf'] < MIN_CELL else ''))
    return dict(lab=lab, sel=sel, **s)

HDR = (f'  {"arm":30s}{"fires":>5}{"fills":>6}{"fill%":>8}{"win%":>8}{"per$1":>9}{"total$":>9}'
       f'{"H1":>8}{"H2":>8}{"permP":>7}{"permM":>8}{"days":>5}')

if __name__ == '__main__':
    cand, names = load()
    allrows = [r for rs in cand.values() for r in rs]
    days = sorted({r['day'] for r in allrows})
    print(f'decide_log candles graded: {len(cand)}, passes {len(allrows)}, days {days}')
    have = [r for r in allrows if r.get('later') is not None]
    lags = np.array([r['later_lag'] for r in have])
    print(f'  +{DELAY_MS} ms row available on {len(have)}/{len(allrows)} passes; achieved lag p50 '
          f'{np.percentile(lags,50):.0f} p90 {np.percentile(lags,90):.0f} ms')

    # ---- (1) validate the fill simulator on today's fires (raw25 K=1) ----
    base = {}
    for ep, rs in cand.items():
        r = fire_at_k(rs, qual_raw, 1)
        if r is not None: base[ep] = r
    sim = [(r, fill(r)) for r in base.values()]
    nf = sum(1 for _, q in sim if q is not None)
    print(f'\n(1) FILL SIMULATOR VALIDATION - raw25 first qualifying pass, n {len(sim)}')
    print(f'    simulated first-attempt fill rate {100*nf/max(len(sim),1):.1f}%  vs London REAL '
          f'{100*LONDON_REAL_FILL:.0f}% per attempt')
    d = abs(nf / max(len(sim), 1) - LONDON_REAL_FILL)
    print(f'    absolute difference {100*d:.1f} pp -> '
          + ('CLOSE ENOUGH to use' if d <= 0.10 else 'NOT a match; read every fill number below with that in mind'))
    fx = {}
    for ep, rs in cand.items():
        r = fire_at_k(rs, qual_fix, 1)
        if r is not None: fx[ep] = r
    simf = [(r, fill(r)) for r in fx.values()]
    nff = sum(1 for _, q in simf if q is not None)
    print(f'    fixed15 first qualifying pass: n {len(simf)}, simulated fill {100*nff/max(len(simf),1):.1f}%')

    # ---- v1 veto, refit here so it can score ANY row ----
    tr_rows = [r for r in allrows if r['feats'] is not None and all(x is not None for x in r['feats'])
               and r.get('later') is not None and (r['p_raw'] / be(r['ask']) - 1) >= 0.15]
    def mat(rs):
        return np.c_[np.array([r['feats'] for r in rs], float),
                     np.array([[lg(r['ask']), lg(r['p_raw']), r['sec'] / 300.0] for r in rs], float)]
    Xt = mat(tr_rows); yt = np.array([per1(r['win'], r['later']) for r in tr_rows])
    dt_ = np.array([r['day'] for r in tr_rows])
    models = {}
    for d in days[1:]:
        m = dt_ < d
        if m.sum() < 500: continue
        mu, sd = Xt[m].mean(0), Xt[m].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
        X = np.c_[np.ones(int(m.sum())), (Xt[m] - mu) / sd]
        R = np.eye(X.shape[1]); R[0, 0] = 0
        models[d] = (mu, sd, np.linalg.solve(X.T @ X + R, X.T @ yt[m]))
    def keep(r):
        mdl = models.get(r['day'])
        if mdl is None or r['feats'] is None or any(x is None for x in r['feats']): return None
        mu, sd, w = mdl
        x = (mat([r])[0] - mu) / sd
        return float(np.r_[1.0, x] @ w) >= 0

    for pname, qual in (('raw25', qual_raw), ('fixed15', qual_fix)):
        print(f'\n{"="*136}\n(2) PERSISTENCE - {pname}. Fire on the K-th CONSECUTIVE qualifying pass.\n{"="*136}')
        print(HDR)
        cells = {}
        for K in KS:
            sel = []
            for ep, rs in cand.items():
                r = fire_at_k(rs, qual, K)
                if r is not None: sel.append((r, fill(r)))
            cells[K] = sel
            line(f'K={K}', sel)
        print(f'\n  PAIRED vs K=1 on the candles BOTH trade (filled in both), {pname}:')
        b1 = {r['ep']: (r, q) for r, q in cells[1]}
        for K in KS[1:]:
            bk = {r['ep']: (r, q) for r, q in cells[K]}
            both = [e for e in sorted(set(b1) & set(bk)) if b1[e][1] is not None and bk[e][1] is not None]
            if not both: print(f'    K={K}: no candle filled in both'); continue
            v1 = sum(per1(b1[e][0]['win'], b1[e][1]) * cost(b1[e][1]) for e in both) / sum(cost(b1[e][1]) for e in both)
            vk = sum(per1(bk[e][0]['win'], bk[e][1]) * cost(bk[e][1]) for e in both) / sum(cost(bk[e][1]) for e in both)
            disc = [e for e in both if b1[e][0]['t'] != bk[e][0]['t']]
            print(f'    K={K}: {len(both)} candles filled in both, {len(disc)} at a DIFFERENT pass; '
                  f'K=1 {v1:+.3f} vs K={K} {vk:+.3f}' + ('  *n<60' if len(both) < MIN_CELL else ''))
        print(f'\n  PER DAY fill% / per$1, {pname}:')
        print(f'    {"day":8s}' + ''.join(f'{"K="+str(K):>18}' for K in KS))
        for d in days:
            row = f'    {d:8s}'
            for K in KS:
                s = [(r, q) for r, q in cells[K] if r['day'] == d]
                f_ = sum(1 for _, q in s if q is not None)
                v = score(s)
                row += f'{(f"{100*f_/len(s):.0f}%/{v['per1']:+.2f}" if s and v else "-"):>18}'
            print(row)
        print(f'\n(3) THE SAME WITH THE v1 VETO ON TOP - {pname}')
        print(HDR)
        for K in KS:
            sel = [(r, q) for r, q in cells[K] if keep(r) is True]
            line(f'K={K} + veto', sel)
