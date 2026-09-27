#!/usr/bin/env python3
"""A REVERSAL "brain" on the LIVE-ONLY inputs (V, 09-27, owner okayed). READ-ONLY, no engine touched.

The new part is the inputs: T1 and NC-8 had only Binance 1 s price and flow. `decide_log` carries the
engine's full live feature vector every pass (44 named features at meta `decide_log_features`), so at
each REVERSAL call we join the nearest feats row at or before that second and ask whether perp basis,
book depth, OFI and flow can tell a real move from a fake one.

Two model families, both fit walk-forward by day on prior days only:
  LOGIT  L2 logistic, Newton (same routine as V's lane_ev_replay)
  GBM    gradient boosting, logistic loss, depth 3, 150 trees, lr 0.05, 32-quantile split search
Rule: buy the first call per candle with p_model/(ask*cost(ask)) - 1 >= theta, theta 0 / .05 / .10.
NULL: the identical machinery on [logit ask, sec/300] only, so the null is strictly NESTED in the brain
and any gain is attributable to the live-only inputs rather than to the model class.

Feature choice, decided before any result was read:
  - the live-only inputs V named: basis_bps perp_n15 (perp), imb5 imb20 spread_bps (depth),
    ofi5 ofi15 ofi60 (OFI), spot_imb15 spot_imb60 (flow), plus the shape/return features.
  - ABSOLUTE PRICE LEVELS ARE EXCLUDED (_price, ref_now, ref_open, bn_line_now, bn_line_open). On a
    three-day sample a tree that splits on a raw BTC level is selecting a calendar day, not learning
    structure. p_venue, _ask_up, _ask_dn and _venue_ok are excluded from the brain too: p_venue is a
    transform of the venue ask, which is the null's own feature.
  - the venue ask and sec/300 ARE included in the brain, so null-nested-in-brain holds exactly.
  - feed_timing is NOT joinable: it lives in signals.decision, and decide_log's 44 keys carry no timing
    field. So the feed_timing part of the brief cannot be tested and is not claimed here.

Grading: results.actual. The venues snapshot on the branch ends 09-16 and covers none of this window.
Execution: the London model from analysis/v/model/lane_exec_sim.py - P(fill|win) 54.1%, P(fill|lose)
65.0%, slippage cents p10/p50/p90 -1/+2/+11, $10 stake, 1000 runs.
"""
import csv, sqlite3, bisect, json, math, random, collections, datetime as dt, numpy as np

DB = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
VEN = '/tmp/venues_zurich_0923.sqlite3'
CALLS = '/tmp/calls_rev.csv'
SEC_LO, SEC_HI, RUNS, SIMS = 0, 240, 1000, 500
DROP = {'_price', '_ask_up', '_ask_dn', '_venue_ok', 'p_venue', 'ref_now', 'ref_open',
        'bn_line_now', 'bn_line_open', 'ref_src', 'ref_inst', 'ref_inst_ok', 'sec_left'}

cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: (w / x - cost(x)) / cost(x)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

def load():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    keys = json.loads(c.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    use = [i for i, k in enumerate(keys) if k not in DROP]
    names = [keys[i] for i in use]
    dl = []
    for ts, fs in c.execute('SELECT ts_ms,feats FROM decide_log WHERE feats IS NOT NULL ORDER BY ts_ms'):
        v = json.loads(fs)
        if len(v) != len(keys): continue
        dl.append((int(ts // 1000), [v[i] for i in use]))
    seen = {}
    for s, v in dl: seen[s] = v                       # last row in a second wins
    dsec = sorted(seen)
    vq = sqlite3.connect(f'file:{VEN}?mode=ro', uri=True)
    Q = [(int(t), float(u), float(d)) for t, u, d in vq.execute('select ts,poly_up,poly_dn from q order by ts')
         if u is not None and d is not None]
    QT = [q[0] for q in Q]
    out = []
    for r in csv.DictReader(open(CALLS)):
        if r['kind'] != 'REVERSAL': continue
        ep, sec = int(r['epoch']), int(r['sec'])
        if not (SEC_LO <= sec <= SEC_HI): continue
        ts = ep + sec
        i = bisect.bisect_right(QT, ts) - 1
        if i < 0 or ts - QT[i] > 0: continue           # past-only, same second
        ask, opp = (Q[i][1], Q[i][2]) if r['side'] == 'UP' else (Q[i][2], Q[i][1])
        j = bisect.bisect_right(dsec, ts) - 1
        if j < 0: continue
        f = seen[dsec[j]]
        if any(x is None for x in f): continue
        out.append(dict(epoch=ep, sec=sec, day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'),
                        ask=ask, opp=opp, win=int(r['win']), feats=[float(x) for x in f],
                        join_age=ts - dsec[j]))
    return out, names

# ---------------------------------------------------------------- models
def fit_logit(X, y, l2=2.0, it=200):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30))); g = X.T @ (p - y)
        R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (p * (1 - p))[:, None]) + R + np.eye(len(w)) * 1e-6
        step = np.linalg.solve(H, g + R @ w)
        w -= step
        if np.max(np.abs(step)) < 1e-8: break
    return ('logit', w)

def _tree(X, g, h, bins, depth, lam=1.0, min_h=5.0):
    """One depth-limited regression tree on gradient/hessian. Returns a nested dict."""
    G, H = g.sum(), h.sum()
    leaf = {'leaf': -G / (H + lam)}
    if depth == 0 or len(g) < 20 or H < 2 * min_h: return leaf
    best = None
    for f in range(X.shape[1]):
        b = bins[f]
        if len(b) < 2: continue
        idx = np.searchsorted(b, X[:, f], side='right')
        gs = np.bincount(idx, weights=g, minlength=len(b) + 1)
        hs = np.bincount(idx, weights=h, minlength=len(b) + 1)
        cg, ch = np.cumsum(gs), np.cumsum(hs)
        for k in range(len(b)):
            hl, hr = ch[k], H - ch[k]
            if hl < min_h or hr < min_h: continue
            gl, gr = cg[k], G - cg[k]
            gain = gl * gl / (hl + lam) + gr * gr / (hr + lam) - G * G / (H + lam)
            if best is None or gain > best[0]: best = (gain, f, b[k])
    if best is None or best[0] <= 1e-9: return leaf
    _, f, thr = best; m = X[:, f] <= thr
    if m.sum() == 0 or (~m).sum() == 0: return leaf
    return {'f': f, 'thr': thr,
            'l': _tree(X[m], g[m], h[m], bins, depth - 1, lam, min_h),
            'r': _tree(X[~m], g[~m], h[~m], bins, depth - 1, lam, min_h)}

def _apply(t, X):
    if 'leaf' in t: return np.full(len(X), t['leaf'])
    out = np.empty(len(X)); m = X[:, t['f']] <= t['thr']
    if m.any(): out[m] = _apply(t['l'], X[m])
    if (~m).any(): out[~m] = _apply(t['r'], X[~m])
    return out

def fit_gbm(X, y, trees=150, lr=0.05, depth=3, nbins=32):
    base = math.log(max(1e-6, y.mean()) / max(1e-6, 1 - y.mean()))
    bins = [np.unique(np.quantile(X[:, f], np.linspace(0, 1, nbins + 1)[1:-1])) for f in range(X.shape[1])]
    F = np.full(len(y), base); ts = []
    for _ in range(trees):
        p = 1 / (1 + np.exp(-np.clip(F, -30, 30)))
        t = _tree(X, p - y, np.maximum(p * (1 - p), 1e-6), bins, depth)
        ts.append(t); F += lr * _apply(t, X)
    return ('gbm', (base, lr, ts))

def predict(m, X):
    kind, w = m
    if kind == 'logit': return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))
    base, lr, ts = w
    F = np.full(len(X), base)
    for t in ts: F += lr * _apply(t, X)
    return 1 / (1 + np.exp(-np.clip(F, -30, 30)))

# ---------------------------------------------------------------- scoring
SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def london(R):
    rng = random.Random(11); tots = []; spent = []
    for _ in range(RUNS):
        t = s = 0.0
        for c in R:
            if rng.random() > (0.541 if c['win'] else 0.650): continue
            px = min(0.99, max(0.01, c['ask'] + slip(rng))); sh = 10 / px
            fee = 0.07 * sh * px * (1 - px); s += 10 + fee
            t += (sh if c['win'] else 0) - 10 - fee
        tots.append(t); spent.append(s)
    return float(np.mean(tots)) / max(1e-9, float(np.mean(spent))), float(np.mean(tots))

def report(name, R, rng):
    if not R: print(f'  {name:42s} none'); return
    v = np.array([per1(c['win'], c['ask']) for c in R]); h = len(R) // 2
    sims = [np.mean([per1(1 - c['win'], c['opp']) if fl else per1(c['win'], c['ask'])
                     for c, fl in zip(R, rng.random(len(R)) < .5)]) for _ in range(SIMS)]
    pp = float(np.mean(np.array(sims) >= v.mean()))
    ex, tot = london(R)
    days = collections.Counter(c['day'] for c in R)
    print(f'  {name:42s} n{len(R):4d}{"*" if len(R) < 60 else " "} hit {100*np.mean([c["win"] for c in R]):5.1f}% '
          f'ask {np.median([c["ask"] for c in R]):.2f} paper {v.mean():+.3f} (H1 {v[:h].mean():+.3f} H2 {v[h:].mean():+.3f}) '
          f'LON {ex:+.3f}/$1 ${tot:+.0f} perm p {pp:.2f}  test days {len(days)} {dict(sorted(days.items()))}')

def first(C, ok):
    seen = {}
    for c in sorted(C, key=lambda c: (c['epoch'], c['sec'])):
        if c['epoch'] not in seen and ok(c): seen[c['epoch']] = c
    return [seen[e] for e in sorted(seen)]

if __name__ == '__main__':
    C, names = load()
    days = sorted({c['day'] for c in C})
    cpd = {d: len({c['epoch'] for c in C if c['day'] == d}) for d in days}
    print(f'REV calls joined to decide_log: {len(C)} on {len({c["epoch"] for c in C})} candles, days {days}')
    print(f'candles per day: {cpd}   join age p50 {int(np.median([c["join_age"] for c in C]))}s '
          f'max {max(c["join_age"] for c in C)}s')
    print(f'brain features ({len(names)}): {", ".join(names)}')
    print(f'\nPOWER, stated before the grid: a one-trade-per-candle rule can score at most '
          f'{sum(cpd[d] for d in days[1:])} trades on {len(days)-1} test days '
          f'({", ".join(f"{d}:{cpd[d]}" for d in days[1:])}), because the first day is training-only.')
    print(f'Training rows are CALLS, not candles: day 1 has {sum(1 for c in C if c["day"]==days[0])} call rows '
          f'from {cpd[days[0]]} candles, and every call in a candle shares one label - so the effective '
          f'training size is the candle count, not the row count.\n')
    idx = {}
    for lab, sel in (('BRAIN (live-only inputs + ask + sec)', lambda c: c['feats'] + [lg(c['ask']), c['sec'] / 300]),
                     ('NULL  (venue ask + sec only)', lambda c: [lg(c['ask']), c['sec'] / 300])):
        for mname, fitter in (('LOGIT', fit_logit), ('GBM d3', fit_gbm)):
            pc = {}
            for d in days[1:]:
                tr = [c for c in C if c['day'] < d]; te = [c for c in C if c['day'] == d]
                if not tr or not te: continue
                m = fitter(np.array([sel(c) for c in tr], float), np.array([c['win'] for c in tr], float))
                for c, p in zip(te, predict(m, np.array([sel(c) for c in te], float))): pc[id(c)] = float(p)
            print(f'{lab} / {mname}   (scored on {len({c["day"] for c in C if id(c) in pc})} test days)')
            rng = np.random.default_rng(7)
            for th in (0.0, 0.05, 0.10):
                report(f'ev>={th:.2f}', first([c for c in C if id(c) in pc],
                       lambda c: c['ask'] <= .90 and pc[id(c)] / (c['ask'] * cost(c['ask'])) - 1 >= th), rng)
            report('reference: every candle, first call ask<=0.90',
                   first([c for c in C if id(c) in pc], lambda c: c['ask'] <= .90), rng)
            print()

# ---------------------------------------------------------------- discrimination, separate from PnL
def auc(y, s):
    y = np.asarray(y); s = np.asarray(s)
    if y.min() == y.max(): return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def discrimination():
    """AUC on the walk-forward test days. PnL cells here are 30-60 trades; AUC uses every call and every
    candle, so it is the more honest read on whether the inputs carry any signal at all."""
    C, names = load(); days = sorted({c['day'] for c in C})
    print('\n=== DISCRIMINATION on the test days (AUC 0.50 = no signal) ===')
    for lab, sel in (('BRAIN', lambda c: c['feats'] + [lg(c['ask']), c['sec'] / 300]),
                     ('NULL ', lambda c: [lg(c['ask']), c['sec'] / 300])):
        for mname, fitter in (('LOGIT ', fit_logit), ('GBM d3', fit_gbm)):
            pc = {}
            for d in days[1:]:
                tr = [c for c in C if c['day'] < d]; te = [c for c in C if c['day'] == d]
                if not tr or not te: continue
                m = fitter(np.array([sel(c) for c in tr], float), np.array([c['win'] for c in tr], float))
                for c, p in zip(te, predict(m, np.array([sel(c) for c in te], float))): pc[id(c)] = float(p)
            T = [c for c in C if id(c) in pc]
            a_call = auc([c['win'] for c in T], [pc[id(c)] for c in T])
            byc = {}
            for c in T: byc.setdefault(c['epoch'], []).append(c)
            cy = [v[0]['win'] for v in byc.values()]
            cs = [float(np.mean([pc[id(x)] for x in v])) for v in byc.values()]
            print(f'  {lab} / {mname}  AUC per call {a_call:.3f} (n {len(T)})   '
                  f'per candle {auc(cy, cs):.3f} (n {len(byc)}, {sum(cy)} wins)')
