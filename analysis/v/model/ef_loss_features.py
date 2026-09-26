"""Is there ANY market signal - BTC volume, RSI, taker buy/sell, trend, volatility, order flow, book - that tells
EF's losing bets apart from its winning ones, beyond what the corrected probability already says?

Owner, 09-23 02:4x: "there should be something ... from btc side, volume, rsi, oi, buy sell or any other
parameters". Standing rule: no gates - so the question is asked the only honest way: (1) does any feature predict
the RESIDUAL (win - p_cal) at fire time, whole list, permutation p, Benjamini-Hochberg across the list; and
(2) a trained brain (gradient boosting on logit(p_cal) + every feature), walk-forward by day, under the SAME fixed
EV rule as live (ev >= 0.15, ask <= 0.60, $5), against arm A (pooled Platt, the live method).

Features: the 25 v10 fire-time features stored with each paper fire, plus computed from Binance 1 s klines at the
fire second: RSI14 on 1-min closes, volume last 60 s / median 60 s volume of the prior 30 min, taker-buy share over
60 s and 300 s, returns 5 m / 15 m / 60 m, 1-min ATR(14) in bps, candle-of-day volume rank. OI and funding are not
available to these containers (futures API geo-blocked), so they are not tested - stated, not assumed.
"""
import argparse, sqlite3, json, math, glob, bisect, statistics as st
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier

ap = argparse.ArgumentParser(); ap.add_argument('--pnl', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--klines', nargs='+', required=True); ap.add_argument('--perms', type=int, default=500); a = ap.parse_args()
FEE, BAR, MAXASK, STAKE, A_, B_ = 0.0167, 0.15, 0.60, 5.0, 1.0677, -0.3208
rng = np.random.default_rng(7)

K = {}
for p in a.klines:
    for ts, cl, v, tb in sqlite3.connect(p).execute('select ts,cl,v,tb from k1s'):
        K[int(ts // 1000)] = (cl, v, tb)
KT = np.array(sorted(K)); KC = np.array([K[t][0] for t in KT]); KV = np.array([K[t][1] for t in KT]); KB = np.array([K[t][2] for t in KT])
def idx(t): return int(np.searchsorted(KT, t, side='right')) - 1

def kfeat(t):
    i = idx(t)
    if i < 3700 or KT[i] < t - 5: return None
    c = KC[i]
    def ret(s):
        j = idx(t - s); return (c / KC[j] - 1) * 1e4 if j >= 0 and KC[j] > 0 else 0.0
    mins = [KC[idx(t - 60 * k)] for k in range(15, -1, -1)]          # 16 one-minute closes
    d = np.diff(mins); up = np.clip(d, 0, None).mean(); dn = np.clip(-d, 0, None).mean()
    rsi = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    v60 = KV[max(0, i - 59):i + 1].sum()
    prior = [KV[max(0, i - 60 * (k + 1) + 1):i - 60 * k + 1].sum() for k in range(1, 31)]
    b60 = KB[max(0, i - 59):i + 1].sum(); b300 = KB[max(0, i - 299):i + 1].sum(); v300 = KV[max(0, i - 299):i + 1].sum()
    hi = [KC[max(0, idx(t - 60 * k) - 59):idx(t - 60 * k) + 1] for k in range(14)]
    atr = np.mean([(x.max() - x.min()) / c * 1e4 for x in hi if len(x)])
    return dict(k_rsi14=rsi, k_vol_ratio=v60 / (st.median(prior) or 1e-9), k_buy60=b60 / (v60 or 1e-9), k_buy300=b300 / (v300 or 1e-9),
                k_ret5m=ret(300), k_ret15m=ret(900), k_ret60m=ret(3600), k_atr1m=atr)

out = dict(sqlite3.connect(a.venues).execute('select epoch,actual from outcome'))
FE = ['move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'rv60', 'range_bps', 'pos_in_range', 'dist_hi_bps', 'dist_lo_bps', 'spot_imb15',
      'spot_imb60', 'ofi5', 'ofi15', 'ofi60', 'perp_n15', 'basis_bps', 'spread_bps', 'imb5', 'imb20', 'micro_bps', 'prev1_bps', 'prev2_bps', 'sec_left', 'p_venue']
R = []
for ep, ts, side, p, ask, feat in sqlite3.connect(a.pnl).execute('select candle_epoch,ts_ms,side,p,ask,feat from trades where win is not null order by ts_ms'):
    act = out.get(int(ep))
    if act is None or not ask or not p or not feat: continue
    f = json.loads(feat); kf = kfeat(int(ts // 1000))
    if kf is None: continue
    sgn = 1.0 if side == 'UP' else -1.0          # direction-signed: positive = the move/flow is WITH our side
    x = {}
    for k in FE:
        v = f.get(k); v = float(v) if isinstance(v, (int, float)) and math.isfinite(v) else 0.0
        x[k] = v * sgn if k in ('move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'spot_imb15', 'spot_imb60', 'ofi5', 'ofi15', 'ofi60', 'imb5', 'imb20',
                                 'micro_bps', 'prev1_bps', 'prev2_bps', 'pos_in_range', 'basis_bps') else v
    x['p_venue'] = f['p_venue'] if side == 'UP' else 1 - f['p_venue']
    for k, v in kf.items():
        x[k] = (v - 50) * sgn if k == 'k_rsi14' else ((v - 0.5) * sgn if k.startswith('k_buy') else (v * sgn if k.startswith('k_ret') else v))
    pc = min(p, 1 / (1 + math.exp(-(A_ * math.log(p / (1 - p)) + B_))))
    R.append(dict(day=int(ep) // 86400, ts=ts, p=p, pc=pc, ask=ask, win=int(act.upper() == side.upper()), x=x))
names = list(R[0]['x'])
print(f'{len(R)} graded fires with klines, {len(set(r["day"] for r in R))} days, {len(names)} features (signed so + = with our side)')

# (1) does anything predict the residual? whole list, permutation p, BH
res = np.array([r['win'] - r['pc'] for r in R])
rows = []
for k in names:
    v = np.array([r['x'][k] for r in R]); rk = np.argsort(np.argsort(v)); rr = np.argsort(np.argsort(res))
    obs = np.corrcoef(rk, rr)[0, 1]
    null = [abs(np.corrcoef(rk, rng.permutation(rr))[0, 1]) for _ in range(a.perms)]
    rows.append((k, obs, (1 + sum(n >= abs(obs) for n in null)) / (1 + a.perms)))
rows.sort(key=lambda t: t[2]); m = len(rows)
print('\n(1) Spearman(feature, win - p_cal), whole list, permutation p, BH-adjusted q:')
for i, (k, c, pv) in enumerate(rows):
    q = min(1.0, min(pv2 * m / (j + 1) for j, (_, _, pv2) in enumerate(rows) if j >= i))
    print(f'  {k:14s} rho {c:+.3f}  p {pv:.3f}  q {q:.3f}')

# (2) trained brain, walk-forward, same fixed rule
cost = lambda q: q / (1 - 0.07 * (1 - q)); per1 = lambda r: ((1 - FEE) / r['ask'] - 1) if r['win'] else (-1 - FEE)
days = sorted(set(r['day'] for r in R)); lg = lambda q: math.log(q / (1 - q))
def run(pred):
    T = []
    for d in days[1:]:
        tr = [r for r in R if r['day'] < d]; te = [r for r in R if r['day'] == d]
        for r, q in zip(te, pred(tr, te)):
            if r['ask'] <= MAXASK and q / cost(r['ask']) - 1 >= BAR: T.append(r)
    return T
def stats(T, lab):
    cum = peak = dd = 0; run_ = worst = 0; bd = {}
    for r in sorted(T, key=lambda r: r['ts']):
        x = per1(r) * STAKE; cum += x; peak = max(peak, cum); dd = max(dd, peak - cum); run_ = 0 if r['win'] else run_ + 1; worst = max(worst, run_); bd.setdefault(r['day'], 0); bd[r['day']] += x
    print(f'  {lab:34s} n/day {len(T)/(len(days)-1):5.1f} right {100*st.mean(r["win"] for r in T):5.1f}% per$1 {st.mean(per1(r) for r in T):+.3f} '
          f'total {cum:+7.1f} maxDD {dd:5.1f} run {worst:2d} negdays {sum(v<0 for v in bd.values())}/{len(days)-1}')
def platt(tr, te):
    m_ = LogisticRegression(max_iter=2000).fit(np.array([[lg(r['p'])] for r in tr]), [r['win'] for r in tr])
    return m_.predict_proba(np.array([[lg(r['p'])] for r in te]))[:, 1]
def brain(tr, te, cols):
    X = lambda S: np.array([[lg(r['pc'])] + [r['x'][k] for k in cols] for r in S])
    g = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    g.fit(X(tr), [r['win'] for r in tr]); return g.predict_proba(X(te))[:, 1]
kl = [k for k in names if k.startswith('k_')]
print('\n(2) walk-forward by day, rule ev >= 0.15, ask <= 0.60, $5:')
stats(run(platt), 'A pooled Platt (live method)')
stats(run(lambda tr, te: brain(tr, te, kl)), 'brain: p_cal + BTC kline features')
stats(run(lambda tr, te: brain(tr, te, names)), 'brain: p_cal + all features')

# (3) the two features that survive BH in (1), as a plain logistic next to logit(p) - walk-forward, same rule
def logi(tr, te, cols):
    X = lambda S: np.array([[lg(r['p'])] + [(lg(min(max(r['x'][k], .01), .99)) if k == 'p_venue' else r['x'][k]) for k in cols] for r in S])
    m_ = LogisticRegression(max_iter=4000).fit(X(tr), [r['win'] for r in tr]); return m_.predict_proba(X(te))[:, 1]
print('\n(3) logistic on logit(p) + the BH survivors, walk-forward, same rule:')
stats(run(lambda tr, te: logi(tr, te, ['p_venue'])), 'logit(p) + logit(p_venue)')
stats(run(lambda tr, te: logi(tr, te, ['pos_in_range'])), 'logit(p) + pos_in_range')
stats(run(lambda tr, te: logi(tr, te, ['p_venue', 'pos_in_range'])), 'logit(p) + p_venue + pos_in_range')
