"""REVERSAL <240 s on the 8-day Polymarket replay, through analysis/h1/verify.py's gates (V, 09-23).
Input: lanes_twap60.csv (replay_lanes_1s.py --open twap60) + venues.sqlite3 (q = both asks at 1 Hz, outcome = Polymarket
resolution). Exact fee 0.07p(1-p) inside the stake; $1 per fire."""
import sys, csv, sqlite3, bisect, argparse, numpy as np, datetime as dt
sys.path.insert(0, 'analysis/h1'); import verify as V
ap = argparse.ArgumentParser(); ap.add_argument('--rows', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--lo', type=float, default=0); ap.add_argument('--hi', type=float, default=240); a = ap.parse_args()
vc = sqlite3.connect(a.venues); Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')]; QT = [q[0] for q in Q]
OUT = {int(e): x.upper() for e, x in vc.execute('select epoch,actual from outcome') if x}
def asks(ts):
    i = bisect.bisect_left(QT, ts - 5); best = None
    for j in range(i, min(len(Q), i + 11)):
        if abs(Q[j][0] - ts) <= 5 and Q[j][1] is not None and Q[j][2] is not None and (best is None or abs(Q[j][0] - ts) < abs(best[0] - ts)): best = Q[j]
    return (float(best[1]), float(best[2])) if best else None
R = []
for r in csv.DictReader(open(a.rows)):
    if r['kind'] != 'REVERSAL' or r['win'] in ('', 'None') or not (a.lo <= float(r['sec']) < a.hi): continue
    q = asks(int(r['ts']))
    if not q: continue
    R.append(dict(ep=int(r['epoch']), ts=int(r['ts']), side=r['side'], ask=float(r['ask']), up=q[0], dn=q[1], act=r['actual'].upper(), win=int(r['win'])))
R.sort(key=lambda r: r['ts'])
pay = lambda ask, win: (1 / (ask * (1 + 0.07 * (1 - ask))) - 1) if win else -1.0
per = np.array([pay(r['ask'], r['win']) for r in R]); n = len(R); h = n // 2
F = V.Finding(f'REVERSAL {a.lo:.0f}-{a.hi:.0f}s, Polymarket 8-day replay', per.mean(), n)
F.grading(replay_actual={r['ep']: r['act'] for r in R}, venues_outcome={r['ep']: OUT[r['ep']] for r in R if r['ep'] in OUT})
days = {}
for r, x in zip(R, per): days.setdefault(dt.datetime.utcfromtimestamp(r['ep']).strftime('%m-%d'), []).append(x)
F.sample({'all': n}); F.halves(per[:h].mean(), per[h:].mean())
y = np.array([1 if r['act'] == 'UP' else 0 for r in R]); pred = np.array([1.0 if r['side'] == 'UP' else 0.0 for r in R])
AU = np.array([r['up'] for r in R]); AD = np.array([r['dn'] for r in R])
def pnl(y_, p_, _):
    ask = np.where(p_ == 1, AU, AD); win = (p_ == y_)
    return float(np.mean(np.where(win, 1 / (ask * (1 + 0.07 * (1 - ask))) - 1, -1.0)))
F.permutation(y, pred, np.zeros(n), pnl, draws=1000)
F.costs({k: np.mean([pay(min(.999, r['ask'] + k), r['win']) for r in R]) for k in (0, .01, .02, .05)})
cheap = np.mean([pay(min(r['up'], r['dn']), (r['act'] == 'UP') == (r['up'] <= r['dn'])) for r in R])
F.null(per.mean(), cheap, 'buy the cheaper side at the same second')
opp = np.mean([pay(r['dn'] if r['side'] == 'UP' else r['up'], r['act'] != r['side']) for r in R])
F.null(per.mean(), opp, 'buy the OTHER side at the same second')
top = np.sort(per)[::-1]
print('concentration: all %+.3f | w/o top1 %+.3f | w/o top3 %+.3f | w/o top10 %+.3f' % (per.mean(), top[1:].mean(), top[3:].mean(), top[10:].mean()))
print('by day (n, per$1):', ' '.join(f'{d} {len(v)} {np.mean(v):+.3f}' for d, v in sorted(days.items())), '| losing days', sum(np.mean(v) < 0 for v in days.values()), '/', len(days))
F.verdict()
