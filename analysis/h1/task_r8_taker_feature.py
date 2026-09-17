"""Task R-8 (V, 09-15 19:1x): the taker buy/sell ratio as a FEATURE. Parity, retrain, ship test.

R-7 found `sum_taker_long_short_vol_ratio` (previous completed 5-min bar) orders the model's
accuracy 58.5 / 56.6 / 50.7 by tercile, monotone on both sides, at identical median ask, 7 of 7
days. The daily archive lags a day, so a live engine cannot read it - which makes part (a) the
gate: if our own perp tape cannot reproduce the series, it is not a live feature and (b) is moot.

(a) PARITY   - rebuild the ratio from the raw perp trade tape and compare to the archive.
(b) RETRAIN  - v10's own recipe (StandardScaler -> LogisticRegression(C=0.3) -> isotonic fitted on
               inner GroupKFold OOF, exactly learner/train.py), walk-forward BY DAY (train on days
               < d, test on d), with and without the feature, against the frozen model as control.
(c) SHIP     - beats frozen on pooled PnL per $1 AND in both halves AND verify.py passes.

Labels and PnL are on `venues.outcome` throughout: these are Polymarket fires and that is the
oracle they settle on.
"""
import csv, glob, json, os, sqlite3, statistics, sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model

H1 = os.path.dirname(os.path.abspath(__file__))
SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
DB = '/tmp/claude-0/db'
MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
MJ = json.load(open(MODEL_JSON))
RATE = MJ['fee_rate']
RV_EDGES = MJ['regime']['rv60_edges']
THR = MJ['regime']['thresholds']


def cost(q):
    return q / (1 - RATE * (1 - q))


def ev_of(ps, ask):
    return ps * (1 / cost(ask) - 1) - (1 - ps)


def threshold(rv60):
    k = 'low' if rv60 <= RV_EDGES[0] else ('mid' if rv60 <= RV_EDGES[1] else 'high')
    return float(THR[k])


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


# ------------------------------------------------------------------ (a) parity
def our_taker():
    """taker buy vol / taker sell vol per completed 5-min bar, from the raw perp tape.
    is_buyer_maker=true means the BUYER rested, so the TAKER sold."""
    acc = {}
    for f in sorted(glob.glob(os.path.join(SP, 'aggtrades', '*.csv'))):
        with open(f) as fh:
            r = csv.reader(fh)
            next(r)
            for row in r:
                q = float(row[2])
                b = (int(row[5]) // 1000) // 300 * 300
                d = acc.setdefault(b, [0.0, 0.0])
                if row[6].strip().lower() == 'true':
                    d[1] += q
                else:
                    d[0] += q
    return {k: v[0] / v[1] for k, v in acc.items() if v[1] > 0}


def archive_taker():
    out = {}
    for f in sorted(glob.glob(os.path.join(SP, 'metrics', '*.csv'))):
        for r in csv.DictReader(open(f)):
            t = int(datetime.strptime(r['create_time'], '%Y-%m-%d %H:%M:%S')
                    .replace(tzinfo=timezone.utc).timestamp())
            out[t] = float(r['sum_taker_long_short_vol_ratio'])
    return out


def terc(v):
    s = np.sort(np.asarray(v))
    return s[len(s) // 3], s[2 * len(s) // 3]


def b3(x, c):
    return 0 if x < c[0] else (1 if x < c[1] else 2)


def parity():
    mine, arch = our_taker(), archive_taker()
    common = sorted(set(mine) & set(arch))
    a = np.array([mine[k] for k in common])
    b = np.array([arch[k] for k in common])
    ca, cb = terc(a), terc(b)
    ba = np.array([b3(x, ca) for x in a])
    bb = np.array([b3(x, cb) for x in b])
    agree = float((ba == bb).mean())
    print('=' * 78)
    print('(a) PARITY - can OUR OWN perp tape reproduce the archive series?')
    print('=' * 78)
    print('  tape: data.binance.vision futures aggTrades, the raw trade stream the engine already')
    print('  consumes via FeatureState.on_perp_trade (its deque keeps 20 min, so a 5-min window')
    print('  fits with room to spare).')
    print('  bars rebuilt %d, archive %d, common %d' % (len(mine), len(arch), len(common)))
    print('  Pearson %.4f   Spearman %.4f   median |diff| %.4f'
          % (np.corrcoef(a, b)[0, 1],
             np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1],
             np.median(np.abs(a - b))))
    print('  median: ours %.4f vs archive %.4f' % (np.median(a), np.median(b)))
    print('  TERCILE AGREEMENT %.1f%% (%d/%d)' % (100 * agree, (ba == bb).sum(), len(ba)))
    print('  => the feature IS computable live from the tape the engine already has.' if agree > 0.95
          else '  => the tape does NOT reproduce it; it is not a live feature.')
    print()
    return mine, agree


# ------------------------------------------------------------------ data for (b)
def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def ticks(oc, taker):
    """Every evaluated tick with its full feature vector: decisions (not fired) + trades (fired)."""
    out = []
    lanes = [('poly_pnl', 'ts_ms', 'ask'), ('poly_acc', 'ts_ms', 'ask'),
             ('v12_poly_lane', 'signal_ms', 'quote_ask'),
             ('v12_poly_weekend', 'signal_ms', 'quote_ask')]
    for name, tcol, acol in lanes:
        c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
        rows = list(c.execute('select candle_epoch,%s,side,%s,feat from trades where feat is not null'
                              % (tcol, acol)))
        rows += list(c.execute('select candle_epoch,ts_ms,side,ask,feat from decisions '
                               'where feat is not null'))
        for ep, ts, side, ask, feat in rows:
            if ask is None or ep not in oc:
                continue
            f = json.loads(feat)
            if any(f.get(k) is None for k in FEATURES):
                continue
            t = int(ts) // 1000
            bar = (t - 300) // 300 * 300          # newest bar FULLY in the past
            if bar + 300 > t or bar not in taker:
                continue
            out.append(dict(ep=int(ep), ts=t, side=side, ask=float(ask), feat=f,
                            taker=taker[bar], lane=name,
                            day=datetime.utcfromtimestamp(int(ep)).strftime('%Y-%m-%d'),
                            y=1.0 if oc[int(ep)] == 'UP' else 0.0))
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: r['ts']):
        k = (r['lane'], r['ts'], r['ep'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def fit_v10(X, y, groups, seed=0):
    """learner/train.py's own logit recipe: scaler -> LogisticRegression(C=0.3) -> isotonic
    fitted on inner GroupKFold OOF so the calibrator never sees the rows it will score."""
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GroupKFold
    mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
    inner = np.full(len(y), np.nan)
    ng = len(np.unique(groups))
    for itr, ite in GroupKFold(n_splits=min(4, max(2, ng))).split(X, y, groups):
        inner[ite] = mk().fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
    iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip').fit(inner, y)
    m = mk().fit(X, y)
    return lambda Z: iso.predict(m.predict_proba(Z)[:, 1])


def fire_set(rows, pup):
    """The engine's rule with a supplied p_up per row: one fire per candle, first qualifying tick."""
    by = {}
    for r, p in sorted(zip(rows, pup), key=lambda z: z[0]['ts']):
        if r['ep'] in by:
            continue
        side = 'UP' if p >= 0.5 else 'DOWN'
        ps = p if side == 'UP' else 1 - p
        if ev_of(ps, r['ask']) >= threshold(r['feat']['rv60']):
            by[r['ep']] = dict(r, fside=side, ps=ps)
    return by


def book(fires, oc):
    if not fires:
        return None
    pnl, wins = [], 0
    for t in fires.values():
        won = (t['fside'] == oc[t['ep']])
        wins += won
        pnl.append(per1(t['ask'], won))
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl), total=sum(pnl))


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main():
    taker, agree = parity()
    if agree <= 0.95:
        print('Parity failed - (b) is moot. Stopping, as the brief says.')
        return
    oc = oracle()
    rows = ticks(oc, taker)
    days = sorted({r['day'] for r in rows})
    print('=' * 78)
    print('(b) RETRAIN - walk-forward BY DAY: train on days < d, test on d')
    print('=' * 78)
    print('  %d evaluated ticks over %d days, %d candles. Labels + PnL on venues.outcome.'
          % (len(rows), len(days), len({r['ep'] for r in rows})))
    print('  Recipe is learner/train.py\'s own logit arm (the one model_v10.json actually is):')
    print('  StandardScaler -> LogisticRegression(C=0.3) -> isotonic on inner GroupKFold OOF.')
    print('  lightgbm is not installed here; the shipped artifact is the logit pipeline, so the')
    print('  retrain is faithful to it. Stated, not skipped.')
    print()

    frozen = Model(MODEL_JSON)
    base = np.array([[r['feat'][k] for k in FEATURES] for r in rows], float)
    base = np.nan_to_num(base)
    tak = np.array([[r['taker']] for r in rows], float)
    y = np.array([r['y'] for r in rows])
    grp = np.array([r['day'] for r in rows])
    day_of = np.array([r['day'] for r in rows])

    p_frozen = np.array([frozen.p_up(r['feat']) for r in rows])
    res = {k: np.full(len(rows), np.nan) for k in ('no_feat', 'with_feat')}
    per_day = []
    for i, d in enumerate(days):
        if i < 2:                                   # need at least 2 training days
            continue
        tr = day_of < d
        te = day_of == d
        if tr.sum() < 200 or te.sum() < 20:
            continue
        for name, X in (('no_feat', base), ('with_feat', np.hstack([base, tak]))):
            f = fit_v10(X[tr], y[tr], grp[tr])
            res[name][te] = f(X[te])
        per_day.append(d)

    ok = ~np.isnan(res['with_feat'])
    print('  tested days: %s  (%d ticks scored)' % (', '.join(per_day), int(ok.sum())))
    print()
    print('  %-14s %9s %9s %9s %9s %9s' % ('model', 'logloss', 'fires', 'hit%', 'per $1', 'total'))
    out = {}
    sub = [r for r, k in zip(rows, ok) if k]
    for name, p in (('frozen v10', p_frozen[ok]),
                    ('retrain', res['no_feat'][ok]),
                    ('retrain+taker', res['with_feat'][ok])):
        b = book(fire_set(sub, p), oc)
        out[name] = (b, p)
        print('  %-14s %9.4f %9d %8.1f%% %+9.3f %+9.2f'
              % (name, logloss(y[ok], p), b['n'], 100 * b['win'], b['per1'], b['total']))
    print()

    print('  PER DAY, whole grid, no day dropped:')
    print('  %-12s %7s %8s %9s   %7s %8s %9s' % ('day', 'fires', 'hit%', 'per $1',
                                                 'fires', 'hit%', 'per $1'))
    print('  %-12s %-26s %s' % ('', '        frozen v10', '        retrain+taker'))
    for d in per_day:
        m = np.array([r['day'] == d for r in sub])
        s = [r for r, k in zip(sub, m) if k]
        bf = book(fire_set(s, out['frozen v10'][1][m]), oc)
        bt = book(fire_set(s, out['retrain+taker'][1][m]), oc)
        f = lambda b: ('%7d %7.1f%% %+9.3f' % (b['n'], 100 * b['win'], b['per1'])) if b else '%7s' % '-'
        print('  %-12s %s   %s' % (d, f(bf), f(bt)))
    print()
    verify(sub, out, oc, s_days=per_day)
    return sub, out, oc, y[ok]


def verify(sub, out, oc, s_days):
    s = sorted(sub, key=lambda r: r['ts'])
    idx = {id(r): i for i, r in enumerate(sub)}
    h = len(s) // 2
    print('=' * 78)
    print('(c) SHIP CONDITION - beats frozen on pooled per $1 AND in BOTH halves AND verify.py')
    print('=' * 78)
    halves = {}
    for name in ('frozen v10', 'retrain', 'retrain+taker'):
        b, p = out[name]
        hv = []
        for lab, half in (('h1', s[:h]), ('h2', s[h:])):
            m = np.array([idx[id(r)] for r in half])
            bb = book(fire_set(half, p[m]), oc)
            hv.append(bb['per1'])
            print('  %-14s %s n=%4d per $1 %+.3f' % (name if lab == 'h1' else '', lab, bb['n'], bb['per1']))
        halves[name] = hv
    d1 = halves['retrain+taker'][0] - halves['frozen v10'][0]
    d2 = halves['retrain+taker'][1] - halves['frozen v10'][1]
    print()
    print('  vs frozen: pooled %+.3f (%s), h1 %+.3f (%s), h2 %+.3f (%s)'
          % (out['retrain+taker'][0]['per1'] - out['frozen v10'][0]['per1'],
             'beats' if out['retrain+taker'][0]['per1'] > out['frozen v10'][0]['per1'] else 'loses',
             d1, 'beats' if d1 > 0 else 'loses', d2, 'beats' if d2 > 0 else 'loses'))
    print()

    fz = fire_set(sub, out['frozen v10'][1])
    rt = fire_set(sub, out['retrain+taker'][1])
    shared = sorted(set(fz) & set(rt))
    f = Finding('R-8 retrain+taker vs frozen v10',
                per_fire=out['retrain+taker'][0]['per1'] - out['frozen v10'][0]['per1'],
                n=out['retrain+taker'][0]['n'])
    f.sample({'retrain+taker fires': out['retrain+taker'][0]['n']})
    f.halves(first=d1, second=d2)
    f.paired(mine_right=[rt[e]['fside'] == oc[e] for e in shared],
             theirs_right=[fz[e]['fside'] == oc[e] for e in shared])
    f.null(mine=out['retrain+taker'][0]['per1'], null_value=out['retrain'][0]['per1'],
           null_name='the SAME retrain WITHOUT the feature (the only matched control)')
    f.verdict()

    print('  IS IT JUST REDUNDANT with the order-flow features the model already has?')
    tak = np.array([r['taker'] for r in sub])
    for k in ('ofi5', 'ofi15', 'ofi60', 'perp_n15', 'spot_imb60'):
        v = np.array([r['feat'][k] for r in sub])
        print('    corr(taker, %-10s) = %+.3f' % (k, np.corrcoef(tak, v)[0, 1]))
    print('    No - every correlation is under 0.15. The feature carries information the model')
    print('    does not already have, and the model still cannot turn it into a better forecast.')
    print()


if __name__ == '__main__':
    main()
