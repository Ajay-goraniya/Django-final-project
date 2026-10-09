#!/usr/bin/env python3
"""Train EF to beat the price we GET, not the price it SEES. READ-ONLY. Zurich data only, London untouched.

Root cause per NC-10/NC-13: EF's edge is real at the decision ask and gone ~0.25 s later once the makers
have repriced. So the target is not "will this side win" but "will this side win at the ask that will
actually be there".

Signals: every decide_log pass with RAW EV >= 0.15 (this includes every fire, since the live bar is 0.25).
The engine writes ~4 rows/s, and consecutive rows for the same candle+side are p50 257 ms apart with 98.2%
under 300 ms, so the row ladder itself supplies the sub-second delays - no interpolation and no 1 Hz
fallback is needed on this window.

DELAYED ASK: for a row at t, the first same-candle row at ts >= t+D takes its `up_ask`/`dn_ask` for OUR
side. Using both-side columns rather than that row's own `ask` keeps the delayed price independent of
whatever side the later pass happened to choose. The ACHIEVED delay is recorded and reported, not assumed.

TARGET, V's definition, per $1 staked at the delayed ask q_d:
    per$1 = (win/q_d - cost(q_d)) / cost(q_d),   cost(q) = 1 + 0.07*(1-q)
Features are decision-time only: the engine's own 44 decide_log features minus absolute price levels,
plus logit(ask), logit(p_raw) and sec/300. Walk-forward by DAY, ridge, fit on prior days only.

This is NOT NC-12: nothing here ranks or selects by the existing calibrated edge. The model predicts the
delayed outcome directly and the rule is "predicted delayed EV >= theta".

Grading: gamma `btc-updown-5m` outcomePrices - the venue's own resolution (settlement rule, CLAUDE.md).
"""
import sqlite3, json, math, datetime as dt, collections, random, numpy as np

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
RATE = 0.07
EV_FLOOR = 0.15           # candidate set: every pass at or above this raw EV (so every fire is included)
EF_BAR = 0.25             # what EF actually does today on this box (raw_v10_live25)
DELAYS = (250, 500, 1000)
THETAS = (-0.10, -0.05, 0.0, 0.05, 0.10)
DROP = {'_price', '_ask_up', '_ask_dn', '_venue_ok', 'ref_now', 'ref_open', 'bn_line_now',
        'bn_line_open', 'ref_src', 'ref_inst', 'ref_inst_ok', 'sec_left'}

cost = lambda q: 1 + RATE * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)
be = lambda q: q * cost(q)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

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
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    # the archive copies research tables only, so the feature ORDER comes from the engine's own meta -
    # the same key list decide_log was written against. Reading it from anywhere else would risk
    # mislabelling 44 columns silently.
    a = sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    use = [i for i, k in enumerate(keys) if k not in DROP]
    names = [keys[i] for i in use]
    per_candle = collections.defaultdict(list)
    for t, ep, side, p, pr, ask, ua, da, fire, fs in c.execute(
            'SELECT ts_ms,epoch,side,p,p_raw,ask,up_ask,dn_ask,fire,feats FROM decide_log '
            'WHERE p IS NOT NULL AND ask IS NOT NULL AND side IS NOT NULL ORDER BY ts_ms'):
        if ep not in vo: continue
        if not (0.01 < ask < 0.99): continue
        if ua is None or da is None: continue
        v = None
        if fs:
            try:
                raw = json.loads(fs)
                if len(raw) == len(keys): v = [raw[i] for i in use]
            except Exception: v = None
        per_candle[ep].append(dict(t=t, ep=ep, side=side, p_raw=float(pr if pr is not None else p),
                                   ask=float(ask), ua=float(ua), da=float(da), fire=int(fire or 0),
                                   feats=v, win=int(side == vo[ep])))
    rows = []
    for ep, rs in per_candle.items():
        rs.sort(key=lambda r: r['t'])
        ts = [r['t'] for r in rs]
        for i, r in enumerate(rs):
            r['ev'] = r['p_raw'] / be(r['ask']) - 1
            if r['ev'] < EV_FLOOR or r['feats'] is None or any(x is None for x in r['feats']): continue
            r['sec'] = (r['t'] // 1000) - ep
            if not (0 <= r['sec'] <= 295): continue
            ok = True
            for D in DELAYS:
                j = np.searchsorted(ts, r['t'] + D, side='left')
                if j >= len(rs): ok = False; break
                q = rs[j]['ua'] if r['side'] == 'UP' else rs[j]['da']
                if not (0.01 < q < 0.99): ok = False; break
                r[f'ask{D}'] = q
                r[f'lag{D}'] = rs[j]['t'] - r['t']
            if not ok: continue
            r['day'] = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
            rows.append(r)
    return rows, names

def fit_ridge(X, y, l2=1.0):
    X = np.c_[np.ones(len(X)), X]
    R = np.eye(X.shape[1]) * l2; R[0, 0] = 0
    return np.linalg.solve(X.T @ X + R, X.T @ y)
pred = lambda w, X: np.c_[np.ones(len(X)), X] @ w

def featmat(rows, names):
    F = np.array([r['feats'] for r in rows], float)
    extra = np.array([[lg(r['ask']), lg(r['p_raw']), r['sec'] / 300.0] for r in rows], float)
    X = np.c_[F, extra]
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-12] = 1.0
    return (X - mu) / sd

def first_per_candle(rows, ok):
    seen = {}
    for r in sorted(rows, key=lambda r: (r['ep'], r['t'])):
        if r['ep'] not in seen and ok(r): seen[r['ep']] = r
    return [seen[e] for e in sorted(seen)]

def score(sel, D):
    """per$1 at the DELAYED ask - the price we would actually get."""
    if not sel: return None
    num = sum(per1(r['win'], r[f'ask{D}']) * cost(r[f'ask{D}']) for r in sel)
    den = sum(cost(r[f'ask{D}']) for r in sel)
    return num / den

def halves_of(sel, D):
    h = len(sel) // 2
    s = sorted(sel, key=lambda r: r['t'])
    return score(s[:h], D), score(s[h:], D)

def perm_p(sel, D, draws=1000, seed=11):
    """A flip pays the OPPOSITE side's delayed ask (c299e19), never our own."""
    if not sel: return float('nan')
    real = score(sel, D)
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        num = den = 0.
        for r in sel:
            flip = rng.random() < 0.5
            if flip:
                q = 1 - r[f'ask{D}']
                q = min(0.99, max(0.01, q)); w = 1 - r['win']
            else:
                q = r[f'ask{D}']; w = r['win']
            num += per1(w, q) * cost(q); den += cost(q)
        sims.append(num / den)
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), float(np.mean(sims)), sims[int(.95 * len(sims))]

if __name__ == '__main__':
    rows, names = load()
    days = sorted({r['day'] for r in rows})
    print(f'candidate passes (raw EV>={EV_FLOOR}, graded on gamma, all delays available): {len(rows)} '
          f'on {len({r["ep"] for r in rows})} candles, days {days}')
    for D in DELAYS:
        lags = np.array([r[f'lag{D}'] for r in rows])
        print(f'  delay +{D} ms: ACHIEVED lag p10 {np.percentile(lags,10):.0f} p50 {np.percentile(lags,50):.0f} '
              f'p90 {np.percentile(lags,90):.0f} ms   ask moved {100*np.mean([r[f"ask{D}"]-r["ask"] for r in rows]):+.2f}c mean')
    print(f'  features: {len(names)+3} ({len(names)} engine feats + logit ask, logit p_raw, sec/300)')

    X = featmat(rows, names)
    dayarr = np.array([r['day'] for r in rows])
    ef_today = first_per_candle(rows, lambda r: r['ev'] >= EF_BAR)
    print(f'\ntoday\'s EF (first pass with raw EV>={EF_BAR}) fires on {len(ef_today)} of '
          f'{len({r["ep"] for r in rows})} candles')

    for D in DELAYS:
        y = np.array([per1(r['win'], r[f'ask{D}']) for r in rows])
        print(f'\n{"="*126}\nDELAY +{D} ms — target = per$1 at the delayed ask. Walk-forward by day, fit on prior days only.\n{"="*126}')
        p = np.full(len(rows), np.nan)
        for d in days[1:]:
            tr, te = dayarr < d, dayarr == d
            if tr.sum() < 500 or te.sum() == 0: continue
            p[te] = pred(fit_ridge(X[tr], y[tr]), X[te])
        scored = ~np.isnan(p)
        for r, pv, s in zip(rows, p, scored): r['pred'], r['scored'] = pv, s
        sub = [r for r in rows if r['scored']]
        eft = [r for r in ef_today if r['scored']]
        print(f'  scored on {len({r["day"] for r in sub})} test days, {len(sub)} passes, '
              f'{len({r["ep"] for r in sub})} candles')
        base = score(eft, D)
        h1, h2 = halves_of(eft, D) if eft else (None, None)
        pp, pm, p95 = perm_p(eft, D) if eft else (float('nan'),) * 3
        print(f'  {"arm":38s}{"n":>5}{"hit":>7}{"per$1@delay":>12}{"H1":>9}{"H2":>9}{"permP":>8}{"permMean":>10}')
        print(f'  {"EF TODAY (raw EV>=0.25), delayed ask":38s}{len(eft):5d}'
              f'{100*np.mean([r["win"] for r in eft]):6.1f}%{base:+12.3f}{(h1 or 0):+9.3f}{(h2 or 0):+9.3f}'
              f'{pp:8.3f}{pm:+10.3f}' + ('  *n<60' if len(eft) < 60 else ''))
        for th in THETAS:
            sel = first_per_candle(sub, lambda r: r['pred'] >= th)
            if not sel: print(f'  {"BRAIN pred>=%+.2f" % th:38s}    0        (no fires)'); continue
            v = score(sel, D); a, b = halves_of(sel, D)
            pv, mn, _ = perm_p(sel, D)
            print(f'  {"BRAIN pred>=%+.2f" % th:38s}{len(sel):5d}{100*np.mean([r["win"] for r in sel]):6.1f}%'
                  f'{v:+12.3f}{(a or 0):+9.3f}{(b or 0):+9.3f}{pv:8.3f}{mn:+10.3f}'
                  + ('  *n<60' if len(sel) < 60 else ''))
        # paired vs today's EF on the candles BOTH trade, at the same delayed ask
        sel0 = first_per_candle(sub, lambda r: r['pred'] >= 0.0)
        A = {r['ep']: r for r in sel0}; B = {r['ep']: r for r in eft}
        both = sorted(set(A) & set(B))
        disc = [e for e in both if A[e]['t'] != B[e]['t']]
        if both:
            va = score([A[e] for e in both], D); vb = score([B[e] for e in both], D)
            print(f'  PAIRED on the {len(both)} candles both trade: brain {va:+.3f} vs EF today {vb:+.3f}; '
                  f'{len(disc)} at a DIFFERENT second (only those carry information)')
            if disc:
                da = score([A[e] for e in disc], D); db = score([B[e] for e in disc], D)
                print(f'    on the {len(disc)} discordant: brain {da:+.3f} vs EF today {db:+.3f}'
                      + ('  *n<60' if len(disc) < 60 else ''))
            onlyA = sorted(set(A) - set(B)); onlyB = sorted(set(B) - set(A))
            # Where does the brain's number actually come from? If the shared candles favour EF, the answer
            # is "the extra candles", which is a different claim from "it picks better moments".
            va2 = score([A[e] for e in onlyA], D) if onlyA else None
            vb2 = score([B[e] for e in onlyB], D) if onlyB else None
            print(f'  brain-ONLY candles {len(onlyA)}: {va2:+.3f}' + ('  *n<60' if len(onlyA) < 60 else '')
                  + f'   |   EF-ONLY candles {len(onlyB)}: '
                  + (f'{vb2:+.3f}' + ('  *n<60' if len(onlyB) < 60 else '') if vb2 is not None else 'n/a'))

    # ---------------------------------------------------------------- the veto, which is where the value is
    print(f'\n{"="*126}\nTHE VETO: split TODAY\'S EF fires by what the delay model says about them\n{"="*126}')
    print(f'  {"cell":44s}{"n":>5}{"hit":>7}' + ''.join(f'{"+"+str(D)+"ms":>11}' for D in DELAYS)
          + f'{"H1@250":>9}{"H2@250":>9}{"permP@250":>11}')
    for D in DELAYS:
        y = np.array([per1(r['win'], r[f'ask{D}']) for r in rows])
        p = np.full(len(rows), np.nan)
        for d in days[1:]:
            tr, te = dayarr < d, dayarr == d
            if tr.sum() < 500 or te.sum() == 0: continue
            p[te] = pred(fit_ridge(X[tr], y[tr]), X[te])
        for r, pv in zip(rows, p): r[f'pred{D}'] = pv
    eft = [r for r in ef_today if not np.isnan(r.get('pred250', np.nan))]
    for lab, sel in (('EF fires the model KEEPS (pred>=0 @250ms)', [r for r in eft if r['pred250'] >= 0]),
                     ('EF fires the model VETOES (pred<0 @250ms)', [r for r in eft if r['pred250'] < 0]),
                     ('EF fires, all', eft)):
        if not sel: continue
        vals = ''.join(f'{score(sel, D):+11.3f}' for D in DELAYS)
        a, b = halves_of(sel, 250)
        pv, _, _ = perm_p(sel, 250)
        print(f'  {lab:44s}{len(sel):5d}{100*np.mean([r["win"] for r in sel]):6.1f}%{vals}'
              f'{(a or 0):+9.3f}{(b or 0):+9.3f}{pv:11.3f}' + ('  *n<60' if len(sel) < 60 else ''))
    print('  The veto is the actionable half: it does not need the brain to CHOOSE a moment, only to refuse one.')

    print(f'\n  SWEEP of the veto threshold on today\'s EF fires (the rule keeps a fire when pred >= th).')
    print(f'  A monotone sweep is a real regularity; one peaking at the value I happened to pick is noise.')
    print(f'  {"keep when pred >=":22s}{"n":>5}{"hit":>7}' + ''.join(f'{"+"+str(D)+"ms":>11}' for D in DELAYS))
    for th in (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20):
        sel = [r for r in eft if r['pred250'] >= th]
        if not sel: print(f'  {th:+22.2f}    0   (none)'); continue
        print(f'  {th:+22.2f}{len(sel):5d}{100*np.mean([r["win"] for r in sel]):6.1f}%'
              + ''.join(f'{score(sel, D):+11.3f}' for D in DELAYS) + ('  *n<60' if len(sel) < 60 else ''))
