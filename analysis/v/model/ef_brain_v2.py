"""EF brain v2, V's independent run (cross-check for H1's EF_BRAIN_V2): does a context-aware or a self-adjusting
probability correction beat the live pooled Platt, walk-forward by day?

Owner, 09-23 01:3x: "more accuracy, more pnl, less drawdowns and adjustable frequency (low frequency in
drawdowns/bad market)". No gates: frequency may only fall because the corrected p falls.

Rule fixed before any result: ev = p_cal / cost - 1 >= 0.15, ask <= 0.60, cost = ask/(1-0.07*(1-ask)) (the
engine's fee), $5 stake, graded on venues.outcome. Every arm is fitted on days BEFORE the test day only.
  A  pooled Platt refit on all prior days (the live method; the live pair is its all-days version)
  B  context-aware: logistic on logit(p), sec_left/300, rv60, |move_bps|, logit(p_venue), logit(p)*sec_left/300
  C  self-adjusting: Platt on the last N graded fires before the test day, N in {100, 200, 400, 800}
Whole grid printed; the owner's frequency question is answered by fires/day on arm A's 3 worst and 3 best days.
Usage: python3 ef_brain_v2.py --pnl poly_pnl.sqlite3 --venues venues.sqlite3
"""
import argparse, sqlite3, json, math, statistics as st
import numpy as np
from sklearn.linear_model import LogisticRegression

ap = argparse.ArgumentParser(); ap.add_argument('--pnl', required=True); ap.add_argument('--venues', required=True); a = ap.parse_args()
FEE, BAR, MAXASK, STAKE = 0.0167, 0.15, 0.60, 5.0
out = dict(sqlite3.connect(a.venues).execute('select epoch,actual from outcome'))
lg = lambda x: math.log(min(max(x, 1e-4), 1 - 1e-4) / (1 - min(max(x, 1e-4), 1 - 1e-4)))
R = []
for ep, ts, side, p, ask, sec, feat in sqlite3.connect(a.pnl).execute(
        'select candle_epoch,ts_ms,side,p,ask,sec,feat from trades where win is not null order by ts_ms'):
    act = out.get(int(ep))
    if act is None or not ask or not p or not feat: continue
    f = json.loads(feat); pv = f.get('p_venue')
    pv_side = (pv if side == 'UP' else 1 - pv) if isinstance(pv, (int, float)) else ask   # venue's p for OUR side
    sl = f.get('sec_left', 300 - (sec or 0))
    R.append(dict(day=int(ep) // 86400, ts=ts, p=float(p), ask=float(ask), win=int(str(act).upper() == side.upper()),
                  x=[lg(p), sl / 300.0, float(f.get('rv60') or 0), abs(float(f.get('move_bps') or 0)), lg(pv_side), lg(p) * sl / 300.0]))
days = sorted(set(r['day'] for r in R))
cost = lambda q: q / (1 - 0.07 * (1 - q))
per1 = lambda r: ((1 - FEE) / r['ask'] - 1) if r['win'] else (-1 - FEE)

def fit(rows, cols):
    X = np.array([[r['x'][c] for c in cols] for r in rows]); y = np.array([r['win'] for r in rows])
    return LogisticRegression(C=1.0, max_iter=2000).fit(X, y)

def run(pred):
    taken = []
    for d in days[1:]:
        tr = [r for r in R if r['day'] < d]; te = [r for r in R if r['day'] == d]
        pc = pred(tr, te)
        for r, q in zip(te, pc):
            if r['ask'] <= MAXASK and q / cost(r['ask']) - 1 >= BAR: taken.append(r)
    return taken

def stats(T, lab):
    cum = peak = dd = 0; run_ = worst = 0; byday = {}
    for r in sorted(T, key=lambda r: r['ts']):
        x = per1(r) * STAKE; cum += x; peak = max(peak, cum); dd = max(dd, peak - cum)
        run_ = 0 if r['win'] else run_ + 1; worst = max(worst, run_); byday.setdefault(r['day'], []).append(x)
    nd = len(days) - 1
    print(f"{lab:30s} n/day {len(T)/nd:5.1f} right {100*st.mean(r['win'] for r in T) if T else 0:5.1f}% "
          f"per$1 {st.mean(per1(r) for r in T) if T else 0:+.3f} total {cum:+7.1f} maxDD {dd:5.1f} run {worst:2d} "
          f"negdays {sum(sum(v)<0 for v in byday.values())}/{nd}")
    return byday

print(f'{len(R)} graded fires, {len(days)} days; walk-forward on days 2..{len(days)} (each day fitted on the days before it)')
arms = {}
arms['A pooled Platt (live method)'] = run(lambda tr, te: fit(tr, [0]).predict_proba(np.array([[r['x'][0]] for r in te]))[:, 1])
arms['B context-aware'] = run(lambda tr, te: fit(tr, [0, 1, 2, 3, 4, 5]).predict_proba(np.array([r['x'] for r in te]))[:, 1])
for N in (100, 200, 400, 800):
    arms[f'C self-adjusting N={N}'] = run(lambda tr, te, N=N: fit(sorted(tr, key=lambda r: r['ts'])[-N:], [0]).predict_proba(np.array([[r['x'][0]] for r in te]))[:, 1])
A_days = None; res = {}
for lab, T in arms.items():
    res[lab] = stats(T, lab)
    if A_days is None: A_days = res[lab]
order = sorted(A_days, key=lambda d: sum(A_days[d]))
worst3, best3 = order[:3], order[-3:]
print('\nfires/day on arm A\'s 3 worst days vs its 3 best days (the "low frequency in bad markets" question):')
for lab, bd in res.items():
    w = st.mean(len(bd.get(d, [])) for d in worst3); b = st.mean(len(bd.get(d, [])) for d in best3)
    wp = sum(sum(bd.get(d, [])) for d in worst3)
    print(f"  {lab:30s} worst-3 {w:5.1f}/day (pnl {wp:+6.1f}) | best-3 {b:5.1f}/day")
