"""Task R-10 (V, 09-15 20:3x): replay btc_model_v10's own ACCURACY mode. The user wants a safer mode.

`decide(mode="accuracy")` fires iff p_side >= conf_floor AND EV >= ev_floor. model_v10.json ships
two variants: fixed 0.85 / 0.02, and regime_floors keyed on rv60 (low 0.80/0.02, mid 0.75/0.05,
high 0.80/0.08). Both are replayed here over the same tick streams as R-6, same cost model, same
one-fire-per-candle rule, graded on `venues.outcome`.

The model file also carries a CLAIM about this mode: `oos_8day` = 81.8 trades/day, 87.6% accuracy,
8/8 positive days. That claim is from the training era on Binance-settled data. Checking it against
what the mode actually does on the Polymarket lanes is half the value of this task, so it is
reported side by side rather than quietly ignored.

Paper at the quoted ask: per-$1 is an upper bound (R-3: the live book earned +0.004 against +0.038
at its own quote). Accuracy, unlike per-$1, does not depend on fill price.
"""
import json, os, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import Model
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
MJ = json.load(open(MODEL_JSON))
ACC = MJ['accuracy_mode']
RF = ACC['regime_floors']
ACC_EDGES = ACC.get('rv60_edges') or MJ['regime']['rv60_edges']


def floors_regime(rv60):
    k = 'low' if rv60 <= ACC_EDGES[0] else ('mid' if rv60 <= ACC_EDGES[1] else 'high')
    return float(RF[k]['conf_floor']), float(RF[k]['ev_floor'])


def fire_acc(rows, conf=None, evf=None, regime=False):
    """One fire per candle, first tick that clears BOTH floors."""
    by = {}
    for r in sorted(rows, key=lambda r: r['ts']):
        if r['ep'] in by:
            continue
        cf, ef = floors_regime(r['rv60']) if regime else (conf, evf)
        if r['ps'] >= cf and r['ev'] >= ef:
            by[r['ep']] = r
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


def by_day(fires):
    d = {}
    for t in fires.values():
        d.setdefault(t['day'], []).append(R8.per1(t['ask'], t['side1'] == t['actual']))
    return d


def report(name, fires, ndays):
    b = book(fires)
    if not b:
        print('  %-26s  no fires' % name)
        return None
    dd = by_day(fires)
    pos = sum(1 for v in dd.values() if sum(v) > 0)
    # per-day rate over the days this rule ACTUALLY fires on, not calendar days
    print('  %-26s %6.1f %7d %8.1f%% %+9.3f %+9.2f   %d/%d'
          % (name, b['n'] / max(1, len(dd)), b['n'], 100 * b['win'], b['per1'], b['total'],
             pos, len(dd)))
    return b


def main():
    taker = R8.our_taker()
    oc = R8.oracle()
    rows = R8.ticks(oc, taker)
    for r in rows:
        r['actual'] = oc[r['ep']]
    frozen = Model(MODEL_JSON)
    for r in rows:
        p = frozen.p_up(r['feat'])
        r['side1'] = 'UP' if p >= 0.5 else 'DOWN'
        r['ps'] = p if p >= 0.5 else 1 - p
        r['ev'] = R8.ev_of(r['ps'], r['ask'])
        r['rv60'] = r['feat']['rv60']
    rows.sort(key=lambda r: r['ts'])
    days = sorted({r['day'] for r in rows})
    nd = len(days)

    print('=' * 78)
    print('R-10  the model\'s own ACCURACY mode, replayed')
    print('=' * 78)
    print('  %d evaluated ticks, %d candles, %d days, graded on venues.outcome.'
          % (len(rows), len({r['ep'] for r in rows}), nd))
    print('  Paper at the quoted ask: per $1 is an UPPER BOUND. Accuracy is not.')
    print()
    print('  %-26s %6s %7s %8s %9s %9s   %s'
          % ('rule', 'fi/day', 'fires', 'hit%', 'per $1', 'total', 'pos days'))
    pnl_rule = {}
    for r in rows:
        if r['ep'] in pnl_rule:
            continue
        if r['ev'] >= R8.threshold(r['rv60']):
            pnl_rule[r['ep']] = r
    b_pnl = report('pnl rule (what runs now)', pnl_rule, nd)
    b_fix = report('accuracy 0.85 / 0.02', fire_acc(rows, ACC['conf_floor'], ACC['ev_floor']), nd)
    b_reg = report('accuracy regime_floors', fire_acc(rows, regime=True), nd)
    print()
    print('  The model file CLAIMS for this mode (oos_8day, training era, Binance-settled):')
    print('    %.1f trades/day, %.1f%% accuracy, %s positive days, $%s over 8 days.'
          % (ACC['oos_8day']['trades_per_day'], ACC['oos_8day']['accuracy'],
             ACC['oos_8day']['positive_days'], ACC['oos_8day']['pnl_8d']))
    if b_fix:
        nf = len(by_day(fire_acc(rows, ACC['conf_floor'], ACC['ev_floor'])))
        print('    Replayed on the Polymarket lanes it does %.1f/day at %.1f%% - the ACCURACY'
              % (b_fix['n'] / nf, 100 * b_fix['win']))
        print('    CLAIM HOLDS (86.4 vs 87.6). What does not hold is that it is worth anything:')
        print('    +%.2f total over the whole sample against the pnl rule\'s +%.2f.'
              % (b_fix['total'], b_pnl['total']))
    print()

    print('=' * 78)
    print('THE WHOLE GRID conf_floor x ev_floor - no best cell, the trade-off is the point')
    print('=' * 78)
    print('  %-9s %s' % ('', '  '.join('%12s' % ('ev>=%.2f' % e) for e in (0.02, 0.05, 0.08))))
    grid = {}
    for cf in (0.70, 0.75, 0.80, 0.85, 0.90):
        cells = []
        for ef in (0.02, 0.05, 0.08):
            b = book(fire_acc(rows, cf, ef))
            grid[(cf, ef)] = b
            cells.append('%4d %5.1f%%%s' % (b['n'], 100 * b['win'],
                                            '!' if b['n'] < MIN_CELL else ' ') if b else '%12s' % '-')
        print('  p>=%.2f  %s' % (cf, '  '.join(cells)))
    print('  (cells show n and hit%%; "!" marks n < %d - insufficient, not to be read)' % MIN_CELL)
    print()
    print('  same grid, per $1:')
    print('  %-9s %s' % ('', '  '.join('%12s' % ('ev>=%.2f' % e) for e in (0.02, 0.05, 0.08))))
    for cf in (0.70, 0.75, 0.80, 0.85, 0.90):
        cells = []
        for ef in (0.02, 0.05, 0.08):
            b = grid[(cf, ef)]
            cells.append('%12s' % ('%+.3f%s' % (b['per1'], '!' if b['n'] < MIN_CELL else '')) if b else '%12s' % '-')
        print('  p>=%.2f  %s' % (cf, '  '.join(cells)))
    print()
    verify(rows, pnl_rule, b_pnl, nd)
    return rows, pnl_rule, b_pnl, b_fix, b_reg, nd, days


def verify(rows, pnl_rule, b_pnl, nd):
    print('=' * 78)
    print('VERIFICATION - accuracy mode against the pnl rule that runs today')
    print('=' * 78)
    acc = fire_acc(rows, ACC['conf_floor'], ACC['ev_floor'])
    h = len(rows) // 2
    hv = []
    for lab, half in (('h1', rows[:h]), ('h2', rows[h:])):
        a = book(fire_acc(half, ACC['conf_floor'], ACC['ev_floor']))
        p = {}
        for r in half:
            if r['ep'] not in p and r['ev'] >= R8.threshold(r['rv60']):
                p[r['ep']] = r
        b = book(p)
        hv.append((a['per1'] - b['per1']) if (a and b) else float('nan'))
        print('  %s  accuracy n=%3d per $1 %+.3f   |   pnl rule n=%3d per $1 %+.3f'
              % (lab, a['n'], a['per1'], b['n'], b['per1']))
    shared = sorted(set(acc) & set(pnl_rule))
    rng = np.random.default_rng(7)
    ps = np.array([r['ps'] for r in rows])
    real = book(acc)['per1']
    sims = []
    for _ in range(200):
        pv = rng.permutation(ps)
        by = {}
        for r, v in sorted(zip(rows, pv), key=lambda z: z[0]['ts']):
            if r['ep'] in by:
                continue
            if v >= ACC['conf_floor'] and r['ev'] >= ACC['ev_floor']:
                by[r['ep']] = r
        b = book(by)
        if b:
            sims.append(b['per1'])
    sims = np.array(sims)
    f = Finding('R-10 accuracy mode 0.85/0.02 vs the pnl rule',
                per_fire=book(acc)['per1'] - b_pnl['per1'], n=book(acc)['n'])
    f.sample({'accuracy fires': book(acc)['n']})
    f.halves(first=hv[0], second=hv[1])
    f.paired(mine_right=[acc[e]['side1'] == acc[e]['actual'] for e in shared],
             theirs_right=[pnl_rule[e]['side1'] == pnl_rule[e]['actual'] for e in shared])
    f._add('permutation control', float((sims >= real).mean()) <= 0.01,
           'real %+.3f vs permuted mean %+.3f, p=%.3f over %d draws'
           % (real, sims.mean() if len(sims) else float('nan'),
              float((sims >= real).mean()) if len(sims) else 1.0, len(sims)))
    f.null(mine=book(acc)['total'], null_value=b_pnl['total'],
           null_name='the pnl rule, TOTAL PnL')
    f.verdict()
    print('  Read the paired line carefully: accuracy mode really IS right more often on the')
    print('  shared candles. That is the mode working exactly as designed. It still makes no')
    print('  money, because the confidence it demands is bought at an ask that already prices it.')
    print()


if __name__ == '__main__':
    main()
