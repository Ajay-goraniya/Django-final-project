"""Task R-9 item 1 (V, 09-15 19:2x): a STACKED second-stage brain on top of frozen v10.

User: "keep working on it, don't stop after a few tests fail." Goal unchanged - a trained brain
that knows when its own move is wrong. No gates, no hand thresholds.

Design. Frozen v10 keeps the DIRECTION; the stack only refines the CONFIDENCE:
    stage 1 : frozen v10 -> p_up -> side = UP if p_up >= 0.5, and ps = P(that side) as it believes
    stage 2 : a model trained on "did this fire actually win?" from fire-time inputs -
              ps, EV, ask, sec, rv60, taker ratio (R-7), last-3 and last-10 outcomes (causal,
              per lane), hour-of-day (sin/cos), and the rv60 regime bucket
    the EV rule is UNCHANGED: ps2 replaces ps, same cost model, same regime thresholds, one fire
    per candle at the first qualifying tick.
Walk-forward by day: train on days < d, test on d. Both arms V asked for: logit and lightgbm.

Everything is graded on `venues.outcome`; these are Polymarket fires. Paper fills at the quoted
ask, so per-$1 is an upper bound (R-3: the live book earned +0.004 against +0.038 quoted).
"""
import json, os, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
H1 = os.path.dirname(os.path.abspath(__file__))

S2 = ['ps', 'ev', 'ask', 'sec', 'rv60', 'taker', 'last3', 'last10', 'hod_sin', 'hod_cos', 'regime']


def build(rows, frozen):
    """Attach stage-1 output and the stage-2 inputs.

    THE STREAKS ARE PER CANDLE, NOT PER TICK, and this is not a detail. A first version appended
    every tick's outcome to the history, so the second and later ticks of a candle saw a "previous
    result" that was their OWN candle's label. That leaked the target into its own feature and
    printed an 83.8% hit rate and +414 PnL - a number far too good to be true, which is how it was
    caught. Streaks now use only candles STRICTLY EARLIER than the current one.
    """
    hist = {}                      # lane -> list of (epoch, y2) for COMPLETED earlier candles
    seen = {}                      # (lane, epoch) -> y2, so each candle contributes once
    for r in sorted(rows, key=lambda r: (r['ts'], r['ep'])):
        p = frozen.p_up(r['feat'])
        r['side1'] = 'UP' if p >= 0.5 else 'DOWN'
        r['ps'] = p if p >= 0.5 else 1 - p
        r['ev'] = R8.ev_of(r['ps'], r['ask'])
        h = [v for e, v in hist.setdefault(r['lane'], []) if e < r['ep']]
        r['last3'] = float(np.mean(h[-3:])) if len(h) >= 3 else 0.5
        r['last10'] = float(np.mean(h[-10:])) if len(h) >= 10 else 0.5
        f = r['feat']
        r['sec'], r['rv60'] = f['sec_left'], f['rv60']
        r['hod_sin'], r['hod_cos'] = f['hod_sin'], f['hod_cos']
        r['regime'] = (0 if f['rv60'] <= R8.RV_EDGES[0]
                       else (1 if f['rv60'] <= R8.RV_EDGES[1] else 2))
        r['y2'] = 1.0 if r['side1'] == r['actual'] else 0.0
        k = (r['lane'], r['ep'])
        if k not in seen:
            seen[k] = r['y2']
            hist[r['lane']].append((r['ep'], r['y2']))
    return rows


def fit_logit(X, y, groups):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GroupKFold
    mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
    inner = np.full(len(y), np.nan)
    for itr, ite in GroupKFold(n_splits=min(4, max(2, len(np.unique(groups))))).split(X, y, groups):
        inner[ite] = mk().fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
    iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip').fit(inner, y)
    m = mk().fit(X, y)
    return lambda Z: iso.predict(m.predict_proba(Z)[:, 1])


def fit_lgbm(X, y, groups):
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GroupKFold
    mk = lambda: lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=15,
                                    min_child_samples=60, subsample=0.8, subsample_freq=1,
                                    colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    inner = np.full(len(y), np.nan)
    for itr, ite in GroupKFold(n_splits=min(4, max(2, len(np.unique(groups))))).split(X, y, groups):
        inner[ite] = mk().fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
    iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip').fit(inner, y)
    m = mk().fit(X, y)
    return lambda Z: iso.predict(m.predict_proba(Z)[:, 1])


def fires_from(rows, ps_vec):
    """Same EV rule, side from stage 1, confidence from ps_vec."""
    by = {}
    for r, ps in sorted(zip(rows, ps_vec), key=lambda z: z[0]['ts']):
        if r['ep'] in by:
            continue
        if R8.ev_of(ps, r['ask']) >= R8.threshold(r['rv60']):
            by[r['ep']] = dict(r, ps_used=ps)
    return by


def book(fires):
    if not fires:
        return None
    pnl, wins = [], 0
    for t in fires.values():
        won = (t['side1'] == t['actual'])
        wins += won
        pnl.append(R8.per1(t['ask'], won))
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl), total=sum(pnl))


def main():
    taker, agree = R8.our_taker(), None
    oc = R8.oracle()
    rows = R8.ticks(oc, taker)
    for r in rows:
        r['actual'] = oc[r['ep']]
    frozen = Model(MODEL_JSON)
    rows = build(rows, frozen)
    rows.sort(key=lambda r: r['ts'])
    days = sorted({r['day'] for r in rows})

    print('=' * 78)
    print('R-9 item 1  STACKED BRAIN on frozen v10 - stage 1 keeps the side, stage 2 the confidence')
    print('=' * 78)
    print('  %d evaluated ticks, %d candles, %d days. Stage-2 inputs: %s'
          % (len(rows), len({r['ep'] for r in rows}), len(days), ', '.join(S2)))
    print('  EV rule unchanged (same cost model, same regime thresholds, one fire per candle).')
    print('  Paper at the quoted ask - per $1 is an upper bound (R-3: live +0.004 vs +0.038).')
    print()

    X = np.array([[r[k] for k in S2] for r in rows], float)
    y = np.array([r['y2'] for r in rows])
    day = np.array([r['day'] for r in rows])
    grp = day

    pred = {k: np.full(len(rows), np.nan) for k in ('logit', 'lgbm')}
    tested = []
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 300 or te.sum() < 20:
            continue
        for name, fit in (('logit', fit_logit), ('lgbm', fit_lgbm)):
            pred[name][te] = fit(X[tr], y[tr], grp[tr])(X[te])
        tested.append(d)
    ok = ~np.isnan(pred['logit'])
    sub = [r for r, k in zip(rows, ok) if k]
    print('  tested days: %s  (%d ticks scored)' % (', '.join(tested), int(ok.sum())))
    print()

    base_ps = np.array([r['ps'] for r in sub])
    arms = {'frozen v10': base_ps,
            'stack logit': pred['logit'][ok],
            'stack lgbm': pred['lgbm'][ok]}
    res = {}
    print('  %-13s %9s %9s %9s %9s %9s' % ('arm', 'brier', 'fires', 'hit%', 'per $1', 'total'))
    for name, ps in arms.items():
        b = book(fires_from(sub, ps))
        res[name] = (b, ps)
        br = float(np.mean((ps - y[ok]) ** 2))
        print('  %-13s %9.4f %9d %8.1f%% %+9.3f %+9.2f'
              % (name, br, b['n'], 100 * b['win'], b['per1'], b['total']))
    print()

    print('  PER DAY, whole grid, no day dropped (per $1):')
    print('  %-12s %10s %10s %10s' % ('day', 'frozen', 'logit', 'lgbm'))
    for d in tested:
        m = np.array([r['day'] == d for r in sub])
        s = [r for r, k in zip(sub, m) if k]
        out = []
        for name in arms:
            b = book(fires_from(s, res[name][1][m]))
            out.append('%+10.3f' % b['per1'] if b else '%10s' % '-')
        print('  %-12s %s' % (d, ' '.join(out)))
    print()

    print('=' * 78)
    print('VERIFICATION - each arm against frozen, on the same candles')
    print('=' * 78)
    h = len(sub) // 2
    idx = {id(r): i for i, r in enumerate(sub)}
    for name in ('stack logit', 'stack lgbm'):
        hv = []
        for lab, half in (('h1', sub[:h]), ('h2', sub[h:])):
            m = np.array([idx[id(r)] for r in half])
            a = book(fires_from(half, res[name][1][m]))
            f0 = book(fires_from(half, res['frozen v10'][1][m]))
            hv.append((a['per1'] - f0['per1']) if (a and f0) else float('nan'))
        fz = fires_from(sub, res['frozen v10'][1])
        st = fires_from(sub, res[name][1])
        shared = sorted(set(fz) & set(st))
        rng = np.random.default_rng(7)
        real = res[name][0]['per1']
        sims = []
        for _ in range(200):
            b = book(fires_from(sub, rng.permutation(res[name][1])))
            if b:
                sims.append(b['per1'])
        sims = np.array(sims)
        f = Finding('R-9 %s vs frozen v10' % name,
                    per_fire=res[name][0]['per1'] - res['frozen v10'][0]['per1'],
                    n=res[name][0]['n'])
        f.sample({'%s fires' % name: res[name][0]['n']})
        f.halves(first=hv[0], second=hv[1])
        f.paired(mine_right=[st[e]['side1'] == st[e]['actual'] for e in shared],
                 theirs_right=[fz[e]['side1'] == fz[e]['actual'] for e in shared])
        f._add('permutation control', float((sims >= real).mean()) <= 0.01,
               'real %+.3f vs permuted mean %+.3f, p=%.3f over %d draws'
               % (real, sims.mean(), float((sims >= real).mean()), len(sims)))
        f.null(mine=res[name][0]['total'], null_value=res['frozen v10'][0]['total'],
               null_name='frozen v10 TOTAL PnL on the same candles')
        f.verdict()
    return sub, res, tested


if __name__ == '__main__':
    main()
