"""Task R-5 (V, 09-15 02:2x): dynamic staking as a TRAINED model, not a bucket gate.

R-4 closed the fixed-bucket version: the buckets do not separate the win rate, and the one thing
that separates the money (EV) turned out to be the price paid, not the accuracy - it failed
verify.py's quote-age check. V's follow-up is the user's standing direction for EF applied here:
don't gate, train a brain.

Build: walk-forward model of per-$1 PnL from inputs known AT FIRE TIME (p, EV, ask, sec, rv60,
lane), fit on the FIRST half by time, used to size the SECOND half. Sizing = fractional Kelly on
the model's predicted edge, capped. Ship only if verify.py passes on the second half AND the sized
book beats fixed-3 on the same trades.

Two guards this task needs and R-4 earned:
  1. The model can only re-learn "cheap ask pays more per $1". So the ablation below refits with
     `ask` REMOVED and reports both. If the edge lives in `ask`, it is the R-4 artifact wearing a
     model, and the quote-age failure carries over unchanged.
  2. Paper fills at the quoted ask are an UPPER BOUND. Paper and live are pooled for fitting only
     where V asked, and scored SEPARATELY, always.
"""
import csv, json, os, sqlite3, statistics, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

H1 = os.path.dirname(os.path.abspath(__file__))
DB = '/tmp/claude-0/db'
RATE = 0.07
FIXED = 3.0            # the stake the lane uses today; the thing to beat
KELLY_FRAC = 0.25      # fractional Kelly
CAP = 3.0              # cap in units of the fixed stake, so sizing can never exceed 3x fixed
FEATS = ['p', 'ev', 'ask', 'sec', 'rv60']


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def net_odds(ask):
    return (1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0


def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def load_lane(name, cols, lane_id):
    c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
    out = []
    for ep, ts, side, p, ask, ev, sec, rv60, actual in c.execute(
            'select %s,actual from trades where actual is not null' % ','.join(cols)):
        if None in (ask, p, ev, sec, rv60):
            continue
        out.append(dict(ep=int(ep), ts=int(ts), side=side, p=float(p), ask=float(ask),
                        ev=float(ev), sec=float(sec), rv60=float(rv60), lane=lane_id))
    return out


def load_live(oc):
    """Live fills. No p, no EV, no rv60 recorded -> they cannot be scored by this model.
    Kept and reported separately so the limit is visible rather than hidden."""
    out = []
    for r in csv.DictReader(open(os.path.join(H1, 'r3_submissions.csv'))):
        if r['result'] != 'FILLED' or not r['avg_fill_price']:
            continue
        ep = int(r['candle_epoch'])
        if ep not in oc:
            continue
        out.append(dict(ep=ep, ts=int(r['ts_ms']), side=r['side'],
                        ask=float(r['avg_fill_price']),
                        sec=float(int(r['ts_ms']) / 1000 - ep)))
    return out


def design(rows, feats):
    X = np.array([[r[f] for f in feats] + [1.0 if r['lane'] == 'v10' else 0.0] for r in rows])
    return X


def fit_ridge(X, y, lam=1.0):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    A[-1, -1] -= lam                                  # do not penalise the intercept
    w = np.linalg.solve(A, Z.T @ y)
    return dict(mu=mu, sd=sd, w=w)


def predict(m, X):
    Z = np.hstack([(X - m['mu']) / m['sd'], np.ones((len(X), 1))])
    return Z @ m['w']


def score(rows, oc, stakes):
    """Total PnL and per-$1 for a vector of stakes over the same trades."""
    tot_pnl = tot_stake = 0.0
    per = []
    for r, s in zip(rows, stakes):
        a = oc.get(r['ep'])
        if a is None or s <= 0:
            continue
        v = per1(r['ask'], r['side'] == a)
        tot_pnl += s * v
        tot_stake += s
        per.append(v)
    if tot_stake == 0:
        return None
    return dict(n=len(per), pnl=tot_pnl, staked=tot_stake, per1=tot_pnl / tot_stake)


def kelly_stakes(rows, edge):
    out = []
    for r, e in zip(rows, edge):
        b = net_odds(r['ask'])
        f = KELLY_FRAC * (e / b) if b > 0 else 0.0
        out.append(float(np.clip(f, 0.0, 1.0)) * CAP * FIXED)
    return np.array(out)


def run(rows, oc, feats, label):
    rows = sorted(rows, key=lambda r: r['ts'])
    y = np.array([per1(r['ask'], r['side'] == oc.get(r['ep'])) for r in rows])
    h = len(rows) // 2
    tr, te = rows[:h], rows[h:]
    m = fit_ridge(design(tr, feats), y[:h])
    edge = predict(m, design(te, feats))
    sized = kelly_stakes(te, edge)
    flat = np.full(len(te), FIXED)
    s_dyn, s_flat = score(te, oc, sized), score(te, oc, flat)
    # paired per-trade difference on the SAME trades
    d = [(sz * per1(r['ask'], r['side'] == oc.get(r['ep']))) - (FIXED * per1(r['ask'], r['side'] == oc.get(r['ep'])))
         for r, sz in zip(te, sized) if oc.get(r['ep'])]
    pos = sum(1 for x in d if x > 0)
    neg = sum(1 for x in d if x < 0)
    print('  %-34s train %4d  test %4d' % (label, len(tr), len(te)))
    print('    fixed-%.0f : staked %8.1f  pnl %+9.2f  per $1 %+.3f'
          % (FIXED, s_flat['staked'], s_flat['pnl'], s_flat['per1']))
    print('    Kelly   : staked %8.1f  pnl %+9.2f  per $1 %+.3f   (%.2f of flat capital)'
          % (s_dyn['staked'], s_dyn['pnl'], s_dyn['per1'], s_dyn['staked'] / s_flat['staked']))
    print('    per-$1 delta %+.3f   total-pnl delta %+.2f   trades better/worse %d/%d'
          % (s_dyn['per1'] - s_flat['per1'], s_dyn['pnl'] - s_flat['pnl'], pos, neg))
    coef = dict(zip(feats + ['lane_v10'], np.round(m['w'][:-1], 3)))
    print('    what it learned (standardised weights): %s' % json.dumps(coef))
    print()
    return dict(te=te, sized=sized, flat=flat, dyn=s_dyn, fl=s_flat, edge=edge, model=m, d=d)


def main():
    oc = oracle()
    v10 = load_lane('v10_poly_long4',
                    ['candle_epoch', 'ts_ms', 'side', 'p', 'ask', 'ev', 'sec', 'rv60'], 'v10')
    v12 = (load_lane('v12_poly_lane',
                     ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec',
                      'rv60'], 'v12')
           + load_lane('v12_poly_weekend',
                       ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec',
                        'rv60'], 'v12'))
    live = load_live(oc)
    pooled = sorted(v10 + v12, key=lambda r: r['ts'])

    print('=' * 78)
    print('R-5  walk-forward trained sizing, %d paper trades (v10 %d + v12 %d), %d live fills'
          % (len(pooled), len(v10), len(v12), len(live)))
    print('     fit on the first half by TIME, sized on the second. Fractional Kelly %.2f, cap %.0fx.'
          % (KELLY_FRAC, CAP))
    print('=' * 78)
    print()
    print('  ALL PAPER FILLS AT THE QUOTED ASK - an upper bound, never a live number.')
    print()
    full = run(pooled, oc, FEATS, 'pooled paper, all features')
    abl = run(pooled, oc, [f for f in FEATS if f != 'ask'], 'pooled paper, ASK REMOVED (ablation)')
    v10r = run(v10, oc, FEATS, 'v10 only')
    v12r = run(v12, oc, FEATS, 'v12 only')

    print('=' * 78)
    print('LIVE FILLS: %d graded. The live journal records no p, no EV and no rv60, so this model'
          % len(live))
    print('CANNOT be scored on them at all. Not "did badly" - could not be run. Stated, not hidden.')
    print('=' * 78)
    print()

    print('=' * 78)
    print('VERIFICATION on the SECOND HALF only (the sized half), pooled paper')
    print('=' * 78)
    te = full['te']
    h = len(te) // 2
    a1 = score(te[:h], oc, full['sized'][:h]), score(te[:h], oc, full['flat'][:h])
    a2 = score(te[h:], oc, full['sized'][h:]), score(te[h:], oc, full['flat'][h:])
    f = Finding('R-5 Kelly sizing on a trained edge model (scored per $1 staked)',
                per_fire=full['dyn']['per1'] - full['fl']['per1'], n=len(te))
    f.sample({'test half': len(te)})
    f.halves(first=a1[0]['per1'] - a1[1]['per1'], second=a2[0]['per1'] - a2[1]['per1'])
    f.null(mine=full['dyn']['per1'], null_value=full['fl']['per1'], null_name='fixed-3 flat stake')
    f.quote_age(rule='ffill', max_age_s=10.0,
                source='the lanes\' own quote_age_ms/book_age_ms - unchanged from R-4')
    same = [True] * len(te)
    f.paired(mine_right=same, theirs_right=same)
    f.verdict()
    print('  On paired(): sizing NEVER changes which trades are right - both rules take the same')
    print('  trades and differ only in how much. So the paired accuracy test has no discordant')
    print('  pairs and no information here. It is run and reported failing for that reason, not')
    print('  because the two rules tie. The informative paired statistic is the per-trade PnL')
    print('  difference, printed above as better/worse.')
    print()
    print('=' * 78)
    print('V\'S SHIP CONDITION: does the sized book BEAT fixed-3 ON THE SAME TRADES?')
    print('=' * 78)
    print('  fixed-3 total PnL on the test half : %+9.2f  (staked %.0f)'
          % (full['fl']['pnl'], full['fl']['staked']))
    print('  Kelly   total PnL on the test half : %+9.2f  (staked %.0f)'
          % (full['dyn']['pnl'], full['dyn']['staked']))
    print('  -> NO. It is behind by %+.2f, and it gets there by staking %.0f%% of the capital.'
          % (full['dyn']['pnl'] - full['fl']['pnl'],
             100 * full['dyn']['staked'] / full['fl']['staked']))
    print()
    print('  The per-$1 number rises only because Kelly declines most of the book. Per $1 is the')
    print('  wrong scorecard for this lane: the binding constraint is the number of 5-minute')
    print('  candles, not capital, and the unused %.0f%% has nowhere else to go inside the same'
          % (100 * (1 - full['dyn']['staked'] / full['fl']['staked'])))
    print('  candles. On the metric V set - same trades, more money - it loses.')
    print()
    print('=' * 78)
    print('THE STEELMAN: give Kelly the SAME TOTAL CAPITAL and let it lever up')
    print('=' * 78)
    sc = full['fl']['staked'] / full['dyn']['staked']
    norm = full['sized'] * sc
    a, b = score(te, oc, norm), full['fl']
    worst = min(s * per1(r['ask'], r['side'] == oc.get(r['ep']))
                for r, s in zip(te, norm) if oc.get(r['ep']))
    print('  rescale x%.1f so both books stake %.0f in total:' % (sc, b['staked']))
    print('    normalised Kelly %+.2f  vs  fixed-3 %+.2f   -> Kelly wins by %+.2f ON PAPER'
          % (a['pnl'], b['pnl'], a['pnl'] - b['pnl']))
    print('  and here is what that costs:')
    print('    %d of %d trades get a ZERO stake - that is a GATE on %.0f%% of the book, the exact'
          % (int((norm == 0).sum()), len(norm), 100 * (norm == 0).mean()))
    print('      shape the standing rule bans, not a sizing curve.')
    print('    max single stake $%.0f vs $%.0f flat; largest single-trade loss $%.0f vs $%.0f.'
          % (norm.max(), FIXED, worst, -FIXED))
    print('    median stake $%.2f - most of the book is sized to almost nothing.' % np.median(norm))
    print()
    print('  ABLATION IS THE ONE THAT DECIDES: with `ask` removed the per-$1 delta goes')
    print('  %+.3f -> %+.3f.' % (full['dyn']['per1'] - full['fl']['per1'],
                                 abl['dyn']['per1'] - abl['fl']['per1']))
    print()


if __name__ == '__main__':
    main()
