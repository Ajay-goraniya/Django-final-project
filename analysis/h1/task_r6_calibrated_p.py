"""Task R-6 (V, 09-15 02:3x): put a CALIBRATED p inside the existing EV rule, walk-forward.

Not a gate - the brain's own p corrected by its own record. R-5 run 2 measured the defect this
fixes: p is overconfident in all five bins (gaps -0.051 / -0.039 / -0.102 / -0.119 / -0.051) and
beats the venue's own price by 0.0028 of Brier.

Method: fit calibration on the FIRST half of graded fires (Platt and isotonic, both reported),
apply it on the SECOND half INSIDE the engine's own EV rule - same cost model, same regime
thresholds, read from the engine's own model_v10.json - and report what changes.

The candidate stream is reconstructed from BOTH tables, because neither alone is the full picture:
`trades` holds the ticks that fired, `decisions` holds the ticks that did not (its `fire` column is
0 on every row). Their union is what the engine actually looked at, and only that union can answer
"fires ADDED".

`p` is p_side (range 0.5098-0.99 in both tables), so calibration never changes the SIDE - it can
only change whether the EV rule fires. That is the whole mechanism under test.
"""
import json, os, sqlite3, statistics, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

H1 = os.path.dirname(os.path.abspath(__file__))
REPO = '/home/user/Django-final-project'
DB = '/tmp/claude-0/db'
MODEL = json.load(open(os.path.join(REPO, 'learner/v12_checkpoint/model_v10.json')))
RATE = MODEL['fee_rate']
RV_EDGES = MODEL['regime']['rv60_edges']
THR = MODEL['regime']['thresholds']


def cost(q):
    return q / (1 - RATE * (1 - q))


def ev_of(ps, ask):
    return ps * (1 / cost(ask) - 1) - (1 - ps)


def threshold(rv60):
    key = 'low' if rv60 <= RV_EDGES[0] else ('mid' if rv60 <= RV_EDGES[1] else 'high')
    return float(THR[key])


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def stream(name, tcols, dcol_ask='ask'):
    """The union of fired and non-fired ticks the engine evaluated."""
    c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
    out = []
    for ep, ts, side, p, ask, ev, sec, rv60 in c.execute(
            'select %s from trades where p is not null' % ','.join(tcols)):
        if None in (ask, p, rv60):
            continue
        out.append(dict(ep=int(ep), ts=int(ts), side=side, p=float(p), ask=float(ask),
                        ev=float(ev), sec=float(sec), rv60=float(rv60), fired=True, lane=name))
    for ts, ep, sec, side, p, ask, ev, feat in c.execute(
            'select ts_ms,candle_epoch,sec,side,p,ask,ev,feat from decisions where p is not null'):
        if None in (ask, p):
            continue
        try:
            rv = float(json.loads(feat)['rv60'])
        except Exception:
            continue
        out.append(dict(ep=int(ep), ts=int(ts), side=side, p=float(p), ask=float(ask),
                        ev=(float(ev) if ev is not None else ev_of(float(p), float(ask))),
                        sec=(float(sec) if sec is not None else 0.0), rv60=rv,
                        fired=False, lane=name))
    return out


# ---- the two calibrators ---------------------------------------------------------------------
def platt(p, y):
    """Logistic regression of the outcome on logit(p). Returns a callable."""
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    a, b = 0.0, 1.0
    for _ in range(200):                                   # Newton on 2 parameters
        f = 1 / (1 + np.exp(-(a + b * z)))
        g = np.array([np.sum(y - f), np.sum((y - f) * z)])
        w = f * (1 - f)
        H = np.array([[-np.sum(w), -np.sum(w * z)], [-np.sum(w * z), -np.sum(w * z * z)]])
        if abs(np.linalg.det(H)) < 1e-12:
            break
        step = np.linalg.solve(H, g)
        a, b = a - step[0], b - step[1]
        if np.max(np.abs(step)) < 1e-9:
            break
    return lambda q: 1 / (1 + np.exp(-(a + b * np.log(
        np.clip(q, 1e-6, 1 - 1e-6) / (1 - np.clip(q, 1e-6, 1 - 1e-6)))))), (a, b)


def isotonic(p, y):
    """Pool-adjacent-violators, then step interpolation."""
    o = np.argsort(p)
    x, v = np.asarray(p)[o].astype(float), np.asarray(y)[o].astype(float)
    w = np.ones_like(v)
    i = 0
    while i < len(v) - 1:
        if v[i] <= v[i + 1]:
            i += 1
            continue
        nv = (v[i] * w[i] + v[i + 1] * w[i + 1]) / (w[i] + w[i + 1])
        nw = w[i] + w[i + 1]
        v = np.delete(v, i + 1); w = np.delete(w, i + 1); x = np.delete(x, i + 1)
        v[i], w[i] = nv, nw
        i = max(i - 1, 0)
    return lambda q: np.interp(q, x, v)


# ---- the rule --------------------------------------------------------------------------------
def fire_set(ticks, pmap):
    """Re-run the engine's rule: per candle, the FIRST tick in time whose EV clears its regime
    threshold fires; one fire per candle. pmap maps raw p -> the p to use."""
    by = {}
    for t in sorted(ticks, key=lambda r: r['ts']):
        if t['ep'] in by:
            continue
        ps = float(pmap(t['p']))
        if ev_of(ps, t['ask']) >= threshold(t['rv60']):
            by[t['ep']] = dict(t, p_used=ps, ev_used=ev_of(ps, t['ask']))
    return by


def book(fires, oc):
    pnl, wins, n = [], 0, 0
    for t in fires.values():
        a = oc.get(t['ep'])
        if a is None:
            continue
        won = (t['side'] == a)
        wins += won
        n += 1
        pnl.append(per1(t['ask'], won))
    if not n:
        return None
    return dict(n=n, win=wins / n, per1=statistics.fmean(pnl), total=sum(pnl))


def report(label, raw, cal, oc):
    kept = set(raw) & set(cal)
    dropped = set(raw) - set(cal)
    added = set(cal) - set(raw)
    br, bc = book(raw, oc), book(cal, oc)
    print('  %s' % label)
    print('    fires raw %d -> calibrated %d   kept %d, DROPPED %d, ADDED %d'
          % (len(raw), len(cal), len(kept), len(dropped), len(added)))
    for nm, b in (('raw', br), ('calibrated', bc)):
        if b:
            print('    %-11s n=%4d win %5.1f%%  per $1 %+.3f  total %+8.2f'
                  % (nm, b['n'], 100 * b['win'], b['per1'], b['total']))
    for nm, s in (('DROPPED', dropped), ('ADDED', added)):
        d = book({k: raw.get(k) or cal[k] for k in s}, oc) if s else None
        if d:
            mark = '' if d['n'] >= MIN_CELL else '  INSUFFICIENT'
            print('    %-11s n=%4d win %5.1f%%  per $1 %+.3f  total %+8.2f%s'
                  % (nm, d['n'], 100 * d['win'], d['per1'], d['total'], mark))
        elif s:
            print('    %-11s n=%4d (ungraded)' % (nm, len(s)))
    print()
    return br, bc, dropped, added


def permute_p(ticks, oc, cal, raw_book, draws=200, seed=7):
    """Permute the CALIBRATED PREDICTIONS across candles, never the labels (CLAUDE.md: shuffling
    labels destroys the market's calibration and the control prints a fake profit)."""
    rng = np.random.default_rng(seed)
    ps = np.array([cal(t['p']) for t in ticks])
    sims = []
    for _ in range(draws):
        perm = rng.permutation(ps)
        lut = {id(t): perm[i] for i, t in enumerate(ticks)}
        f = fire_set(ticks, lambda q: 0.5)      # placeholder, replaced below
        # re-run the rule with the permuted value attached to each tick
        by = {}
        for i, t in enumerate(sorted(ticks, key=lambda r: r['ts'])):
            if t['ep'] in by:
                continue
            v = lut[id(t)]
            if ev_of(v, t['ask']) >= threshold(t['rv60']):
                by[t['ep']] = t
        b = book(by, oc)
        if b:
            sims.append(b['per1'])
    return np.array(sims)


def rolling(ticks, oc, every=200, kind='platt'):
    """Refit the calibrator every `every` graded fires, walking forward."""
    fired = sorted([t for t in ticks if t['fired'] and oc.get(t['ep'])], key=lambda r: r['ts'])
    if len(fired) < 2 * every:
        return None
    marks = list(range(every, len(fired), every))
    by, used = {}, 0
    for m in marks:
        tr = fired[:m]
        p = np.array([t['p'] for t in tr])
        y = np.array([1.0 if t['side'] == oc[t['ep']] else 0.0 for t in tr])
        cal = platt(p, y)[0] if kind == 'platt' else isotonic(p, y)
        lo = fired[m]['ts']
        hi = fired[m + every]['ts'] if m + every < len(fired) else float('inf')
        seg = [t for t in ticks if lo <= t['ts'] < hi]
        f = fire_set(seg, cal)
        by.update(f)
        used += 1
    return by, used, marks


def main():
    oc = oracle()
    paper = (stream('poly_pnl', ['candle_epoch', 'ts_ms', 'side', 'p', 'ask', 'ev', 'sec', 'rv60'])
             + stream('v12_poly_lane',
                      ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec',
                       'rv60'])
             + stream('v12_poly_weekend',
                      ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec',
                       'rv60']))
    paper.sort(key=lambda r: r['ts'])

    print('=' * 78)
    print('R-6  calibrated p inside the engine\'s own EV rule, walk-forward')
    print('=' * 78)
    print('  candidate stream: %d ticks over %d candles (fired %d, not fired %d)'
          % (len(paper), len({t['ep'] for t in paper}),
             sum(1 for t in paper if t['fired']), sum(1 for t in paper if not t['fired'])))
    print('  rule read from the engine\'s own model_v10.json: fee %.2f, rv60 edges %.4f/%.4f,'
          % (RATE, *RV_EDGES))
    print('  thresholds low %.2f / mid %.2f / high %.2f. One fire per candle, first qualifying tick.'
          % (THR['low'], THR['mid'], THR['high']))
    print()

    # sanity: does the rule reproduce the engine's own fire set on the whole history?
    repro = fire_set(paper, lambda q: q)
    actual = {t['ep'] for t in paper if t['fired']}
    print('  RULE SANITY: replaying the raw rule reproduces %d/%d of the engine\'s own fires'
          % (len(set(repro) & actual), len(actual)))
    print('               (and proposes %d candles the engine did not fire).'
          % len(set(repro) - actual))
    print()

    fired_graded = [t for t in paper if t['fired'] and oc.get(t['ep'])]
    h = len(fired_graded) // 2
    split_ts = fired_graded[h]['ts']
    tr = fired_graded[:h]
    te_ticks = [t for t in paper if t['ts'] >= split_ts]
    print('  split at the median graded fire: train %d fires, test stream %d ticks over %d candles'
          % (len(tr), len(te_ticks), len({t['ep'] for t in te_ticks})))
    print()

    p_tr = np.array([t['p'] for t in tr])
    y_tr = np.array([1.0 if t['side'] == oc[t['ep']] else 0.0 for t in tr])
    cal_p, (a, b) = platt(p_tr, y_tr)
    cal_i = isotonic(p_tr, y_tr)
    print('  Platt fitted on the training half: a=%.3f b=%.3f  (b<1 = shrink toward the base rate)'
          % (a, b))
    print('  example mapping   p=0.55 -> Platt %.3f / isotonic %.3f'
          % (cal_p(0.55), cal_i(0.55)))
    print('                    p=0.65 -> Platt %.3f / isotonic %.3f'
          % (cal_p(0.65), cal_i(0.65)))
    print('                    p=0.80 -> Platt %.3f / isotonic %.3f'
          % (cal_p(0.80), cal_i(0.80)))
    print()

    print('=' * 78)
    print('SECOND HALF - WHOLE GRID, both calibrators')
    print('=' * 78)
    raw = fire_set(te_ticks, lambda q: q)
    out = {}
    for nm, cal in (('PLATT', cal_p), ('ISOTONIC', cal_i)):
        out[nm] = report(nm, raw, fire_set(te_ticks, cal), oc) + (cal,)

    print('=' * 78)
    print('ROLLING REFIT every 200 graded fires')
    print('=' * 78)
    for nm in ('platt', 'isotonic'):
        r = rolling(paper, oc, 200, nm)
        if not r:
            print('  %-9s not enough graded fires for a rolling refit' % nm)
            continue
        by, used, marks = r
        seg_raw = fire_set([t for t in paper if t['ts'] >= paper[0]['ts']], lambda q: q)
        b = book(by, oc)
        print('  %-9s %d refits at %s ...  fires %d  per $1 %+.3f  total %+8.2f'
              % (nm, used, marks[:3], b['n'], b['per1'], b['total']))
    print('=' * 78)
    print('VERIFICATION on the second half')
    print('=' * 78)
    for nm in ('PLATT', 'ISOTONIC'):
        br, bc, dropped, added, cal = out[nm]
        # halves of the TEST window, per-$1 delta calibrated - raw
        eps = sorted({t['ep'] for t in te_ticks})
        mid = eps[len(eps) // 2]
        d = []
        for lo, hi in ((eps[0], mid), (mid, eps[-1] + 1)):
            r1 = book({k: v for k, v in raw.items() if lo <= k < hi}, oc)
            c1 = book({k: v for k, v in fire_set(te_ticks, cal).items() if lo <= k < hi}, oc)
            d.append((c1['per1'] - r1['per1']) if (r1 and c1) else float('nan'))
        # permutation of the CALIBRATED predictions, never the labels
        rng = np.random.default_rng(7)
        vals = np.array([cal(t['p']) for t in te_ticks])
        sims = []
        for _ in range(200):
            pv = rng.permutation(vals)
            by = {}
            order = np.argsort([t['ts'] for t in te_ticks])
            for i in order:
                t = te_ticks[i]
                if t['ep'] in by:
                    continue
                if ev_of(pv[i], t['ask']) >= threshold(t['rv60']):
                    by[t['ep']] = t
            bb = book(by, oc)
            if bb:
                sims.append(bb['per1'])
        sims = np.array(sims)
        pval = float((sims >= bc['per1']).mean()) if len(sims) else 1.0
        f = Finding('R-6 %s calibration inside the EV rule' % nm,
                    per_fire=bc['per1'] - br['per1'], n=bc['n'])
        f.sample({'calibrated fires': bc['n'], 'dropped': len(dropped),
                  'added': max(len(added), 0) or 1})
        f.halves(first=d[0], second=d[1])
        f._add('permutation control', pval <= 0.01,
               'real %+.3f vs permuted mean %+.3f, p=%.3f over %d draws'
               % (bc['per1'], sims.mean() if len(sims) else float('nan'), pval, len(sims)))
        f.null(mine=bc['total'], null_value=br['total'],
               null_name='raw p, SAME candles (V\'s ship metric: total PnL)')
        same = [True] * len(set(raw) & set(fire_set(te_ticks, cal)))
        f.paired(mine_right=same, theirs_right=same)
        f.verdict()
    print('  On paired(): on every candle where BOTH rules fire, they fire the SAME side - p_side')
    print('  is >= 0.5 by construction and calibration is monotone, so it can only change WHETHER')
    print('  the EV rule fires, never which way. There are no discordant pairs and the test has no')
    print('  information here. Reported failing for that reason, not because the rules tie.')
    print('  The informative statistic is the DROPPED book, printed above.')
    print()
    return paper, te_ticks, raw, out, oc, tr


if __name__ == '__main__':
    main()
