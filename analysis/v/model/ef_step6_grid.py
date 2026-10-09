"""EF step 6, every combination of its settings, replayed on the 9 recorded days (owner, 09-23 03:1x: "try making
different adjustments and everything and check" - "just do what I said").

Settings gridded (all combinations):
  calibration  raw p | pooled Platt (the live pair, fitted on these same days = in-sample) | walk-forward Platt
               (each day fitted only on earlier days; day 1 has no fit and is skipped for every arm)
  EV mode      fixed bar in {0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40} | regime (v10's own: rv60 low 0.15 / mid 0.25 /
               high 0.25) | regime scaled x0.6 / x1.4
  EV pad       0 / 1 (live) / 3 / 5 ticks of 0.001 above the ask
  max ask      0.50 / 0.60 (live) / 0.70
Exact venue fee (0.07 p(1-p) per share, inside the stake), $5, graded on Polymarket (venues.outcome), 8 test days.
Data limit: rows exist only where the old paper engine fired (raw EV >= 0.15 at its moment), so any combination
looser than raw 0.15 is a lower bound. The whole grid is written to CSV; the report shows the whole of the main
slice and ranks nothing as a finding.
"""
import argparse, sqlite3, math, json, csv, itertools, statistics as st
import numpy as np
from sklearn.linear_model import LogisticRegression

ap = argparse.ArgumentParser(); ap.add_argument('--pnl', required=True); ap.add_argument('--venues', required=True); ap.add_argument('--out', required=True)
a = ap.parse_args()
A_, B_ = 1.0677, -0.3208; EDGES = (0.1668167346880573, 0.3652950621790043); REG = dict(low=0.15, mid=0.25, high=0.25)
out = dict(sqlite3.connect(a.venues).execute('select epoch,actual from outcome'))
R = []
for ts, ep, side, p, ask, feat in sqlite3.connect(a.pnl).execute('select ts_ms,candle_epoch,side,p,ask,feat from trades where win is not null order by ts_ms'):
    act = out.get(int(ep))
    if not act or not ask or not p: continue
    f = json.loads(feat) if feat else {}
    R.append(dict(ts=ts, day=int(ep) // 86400, p=p, ask=ask, rv=float(f.get('rv60') or 0), win=act.upper() == side.upper()))
days = sorted(set(r['day'] for r in R)); TEST = [r for r in R if r['day'] > days[0]]
lg = lambda q: math.log(q / (1 - q)); fee = lambda q: 0.07 * q * (1 - q); cost = lambda q: max(q + fee(q), q / (1 - fee(q) / q))
pooled = {id(r): min(r['p'], 1 / (1 + math.exp(-(A_ * lg(r['p']) + B_)))) for r in R}
wf = {}
for d in days[1:]:
    tr = [r for r in R if r['day'] < d]; m = LogisticRegression(max_iter=2000).fit([[lg(r['p'])] for r in tr], [int(r['win']) for r in tr])
    for r in R:
        if r['day'] == d: wf[id(r)] = min(r['p'], float(m.predict_proba([[lg(r['p'])]])[0, 1]))
CAL = {'raw': lambda r: r['p'], 'pooled_platt': lambda r: pooled[id(r)], 'walkfwd_platt': lambda r: wf[id(r)]}
def bar_fn(mode):
    if mode.startswith('fixed'): v = float(mode.split('_')[1]); return lambda r: v
    k = {'regime': 1.0, 'regime_x0.6': 0.6, 'regime_x1.4': 1.4}[mode]
    return lambda r: k * REG['low' if r['rv'] <= EDGES[0] else ('mid' if r['rv'] <= EDGES[1] else 'high')]
MODES = [f'fixed_{b:.2f}' for b in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)] + ['regime', 'regime_x0.6', 'regime_x1.4']
rows = []
for cal, mode, pad, mx in itertools.product(CAL, MODES, (0, 1, 3, 5), (0.50, 0.60, 0.70)):
    bf = bar_fn(mode); cum = peak = dd = 0; n = w = 0; bd = {}; run = worst = 0
    for r in TEST:
        q = CAL[cal](r); px = min(0.999, r['ask'] + pad * 0.001)
        if r['ask'] > mx or q / cost(px) - 1 < bf(r): continue
        x = 5 * ((1 / (r['ask'] + fee(r['ask'])) - 1) if r['win'] else -1.0)
        n += 1; w += r['win']; cum += x; peak = max(peak, cum); dd = max(dd, peak - cum); bd[r['day']] = bd.get(r['day'], 0) + x
        run = 0 if r['win'] else run + 1; worst = max(worst, run)
    rows.append(dict(calibration=cal, ev_mode=mode, pad_ticks=pad, max_ask=mx, trades_per_day=round(n / (len(days) - 1), 1),
                     right_pct=round(100 * w / n, 1) if n else None, profit=round(cum, 1), max_dd=round(dd, 1),
                     profit_per_dd=round(cum / dd, 2) if dd else None, losing_days=sum(v < 0 for v in bd.values()), longest_losing_run=worst))
with open(a.out, 'w', newline='') as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
print(f'{len(rows)} combinations, {len(TEST)} fires on {len(days)-1} test days -> {a.out}')
print('\nMAIN SLICE (pad 1, max ask 0.60 = live), every calibration x EV mode:')
print(f"{'calibration':15s} {'EV mode':13s} {'/day':>5s} {'right':>6s} {'profit':>7s} {'maxDD':>6s} {'p/DD':>5s} {'losedays':>8s} {'run':>4s}")
for r in rows:
    if r['pad_ticks'] == 1 and r['max_ask'] == 0.60:
        print(f"{r['calibration']:15s} {r['ev_mode']:13s} {r['trades_per_day']:5.1f} {r['right_pct'] or 0:5.1f}% {r['profit']:+7.0f} {r['max_dd']:6.0f} {r['profit_per_dd'] or 0:5.1f} {r['losing_days']:8d} {r['longest_losing_run']:4d}")
print('\nEFFECT OF PAD and MAX ASK on the live combination (pooled Platt, fixed 0.15):')
for r in rows:
    if r['calibration'] == 'pooled_platt' and r['ev_mode'] == 'fixed_0.15':
        print(f"  pad {r['pad_ticks']} max_ask {r['max_ask']:.2f}: {r['trades_per_day']:5.1f}/day right {r['right_pct'] or 0:5.1f}% profit {r['profit']:+6.0f} maxDD {r['max_dd']:5.0f} losing days {r['losing_days']}")
print('\nSAME, walk-forward Platt (honest version of the live fix):')
for r in rows:
    if r['calibration'] == 'walkfwd_platt' and r['ev_mode'] == 'fixed_0.15':
        print(f"  pad {r['pad_ticks']} max_ask {r['max_ask']:.2f}: {r['trades_per_day']:5.1f}/day right {r['right_pct'] or 0:5.1f}% profit {r['profit']:+6.0f} maxDD {r['max_dd']:5.0f} losing days {r['losing_days']}")
