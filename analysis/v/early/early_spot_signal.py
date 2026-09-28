#!/usr/bin/env python3
"""Early spot-only signal vs the venue's price, PUBLIC data only (V, 09-28). Independent of Zurich's decide_log.

Owner's direction: the model must fire EARLY and see what the crowd does not. The v10 model's second-biggest input is the
venue's own price (lv +1.551), so it agrees with the market by construction. Here: a walk-forward logistic on SPOT-ONLY
features (Binance 1 s klines) read at second S of the candle, scored against the venue's OWN resolution (gamma), and
priced at what takers actually PAID for that side within 3 s of S (Polymarket public trade tape).

Per S in {20,30,45,60}: AUC spot-only vs AUC of the venue's traded price alone; the full P x A grid of "disagreement"
cells (spot p_side >= P while the side's traded price <= A): n, win%, per $1 after the taker fee, halves, permutation
(the shuffled side is priced at ITS OWN traded price, never the other side's).

Line = TWAP60 before the open (R-16: the venue settles on TWAP60(open) vs the close). Labels = gamma outcomePrices.
usage: early_spot_signal.py <first 5m epoch> <last 5m epoch>
"""
import sys, json, math, collections, datetime as dt, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'twap'))
import arb_trades_check as A

S_LIST = tuple(int(x) for x in os.environ.get('EARLY_S', '20,30,45,60').split(','))
P_LIST = (0.55, 0.60, 0.65, 0.70)
A_LIST = (0.40, 0.45, 0.50, 0.55)
W = 3
fee = lambda p: 0.07 * p * (1 - p)
OUT = os.path.join(os.path.dirname(__file__), os.environ.get('EARLY_OUT', 'early_rows_btc.json'))


def feats(px, e, S, prev):
    """Spot-only features at second e+S. px: sec -> close. prev: list of prior candle returns (bps)."""
    line = [px[k] for k in range(e - 60, e) if k in px]
    if len(line) < 45: return None
    L = sum(line) / len(line)
    now = px.get(e + S)
    if now is None: return None
    g = lambda k: px.get(e + S - k)
    if any(g(k) is None for k in (5, 30, 60)): return None
    rets = [math.log(px[k] / px[k - 1]) for k in range(e + S - 59, e + S + 1) if k in px and k - 1 in px]
    if len(rets) < 40: return None
    rv60 = float(np.std(rets)) * 1e4
    seen = [px[k] for k in range(e, e + S + 1) if k in px]
    hi, lo = max(seen), min(seen)
    pos = 0.5 if hi == lo else (now - lo) / (hi - lo)
    hod = 2 * math.pi * ((e % 86400) / 86400.0)
    return dict(move=(now - L) / L * 1e4, ret5=(now / g(5) - 1) * 1e4, ret30=(now / g(30) - 1) * 1e4, ret60=(now / g(60) - 1) * 1e4,
                rv60=rv60, pos=pos, prev1=prev[0], prev2=prev[1], hs=math.sin(hod), hc=math.cos(hod), mv_sec=(now - L) / L * 1e4 * (300 - S) / 300.0)


def collect(a, b):
    px = A.closes(a - 700, b + 300)
    print(f'binance 1 s closes: {len(px)}', flush=True)
    rows, rep = [], collections.Counter()
    for e in range(a, b + 1, 300):
        m = A.market(f'btc-updown-5m-{e}')
        if not m or not m[2]: rep['no_market'] += 1; continue
        cid, toks, outp = m
        up_win = float(outp[0]) > 0.5
        prev = []
        for k in (1, 2):
            o, c = px.get(e - 300 * k), px.get(e - 300 * k + 299)
            prev.append((c / o - 1) * 1e4 if o and c else 0.0)
        tr = A.trades(cid, e)
        last = {0: collections.defaultdict(list), 1: collections.defaultdict(list)}
        for t in tr:
            if t['side'] != 'BUY' or not (e <= t['timestamp'] < e + 300): continue
            i = 0 if t['asset'] == toks[0] else 1 if t['asset'] == toks[1] else None
            if i is not None: last[i][t['timestamp']].append(float(t['price']))
        per_s = {}
        for S in S_LIST:
            f = feats(px, e, S, prev)
            if f is None: continue
            pr = {}
            for i in (0, 1):
                v = [p for k in range(e + S - W, e + S + 1) for p in last[i].get(k, [])]
                pr[i] = max(v) if v else None            # what the unlucky taker paid, not the min
            per_s[str(S)] = dict(f=f, ask_up=pr[0], ask_dn=pr[1])
        if per_s:
            rows.append(dict(e=e, day=(e // 86400), up=up_win, s=per_s)); rep['ok'] += 1
        if rep['ok'] % 100 == 0: print(f'  {rep["ok"]} candles', flush=True)
    json.dump(rows, open(OUT, 'w'))
    print(f'candles {rep["ok"]} (no market/outcome {rep["no_market"]})', flush=True)
    return rows


def fit_logit(X, y, l2=1.0, it=50):
    """Plain IRLS logistic with ridge, standardised inputs. No sklearn dependency needed but used if present."""
    try:
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(C=1.0 / l2, max_iter=500).fit(X, y)
        return lambda Z: m.predict_proba(Z)[:, 1]
    except Exception:
        Xb = np.c_[np.ones(len(X)), X]; w = np.zeros(Xb.shape[1])
        for _ in range(it):
            p = 1 / (1 + np.exp(-Xb @ w)); Wd = p * (1 - p) + 1e-9
            H = Xb.T @ (Xb * Wd[:, None]) + l2 * np.eye(len(w)); g = Xb.T @ (y - p) - l2 * w
            w += np.linalg.solve(H, g)
        return lambda Z: 1 / (1 + np.exp(-(np.c_[np.ones(len(Z)), Z] @ w)))


def auc(score, y):
    s, y = np.asarray(score), np.asarray(y).astype(int)
    if y.sum() == 0 or y.sum() == len(y): return float('nan')
    order = np.argsort(s); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    return float((ranks[y == 1].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (len(y) - y.sum())))


def pnl(side_up, ask, win):
    """per $1 staked, taker fee, payout 1/share."""
    c = ask + fee(ask); return (1.0 / c - 1.0) if win else -1.0


def analyse(rows):
    keys = ['move', 'ret5', 'ret30', 'ret60', 'rv60', 'pos', 'prev1', 'prev2', 'hs', 'hc', 'mv_sec']
    days = sorted({r['day'] for r in rows})
    rng = np.random.default_rng(7)
    print(f'\ncandles {len(rows)}, days {len(days)} ({dt.datetime.fromtimestamp(days[0]*86400, dt.timezone.utc):%m-%d}..'
          f'{dt.datetime.fromtimestamp(days[-1]*86400, dt.timezone.utc):%m-%d}); walk-forward: day k fitted on days < k, day 1 unscored')
    for S in S_LIST:
        K = str(S); rs = [r for r in rows if K in r['s']]
        X = np.array([[r['s'][K]['f'][k] for k in keys] for r in rs]); y = np.array([r['up'] for r in rs]).astype(int)
        d = np.array([r['day'] for r in rs])
        p = np.full(len(rs), np.nan)
        for k in days[1:]:
            tr, te = d < k, d == k
            if tr.sum() < 100 or te.sum() == 0: continue
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            f = fit_logit((X[tr] - mu) / sd, y[tr]); p[te] = f((X[te] - mu) / sd)
        ok = ~np.isnan(p)
        mkt_up = np.array([(r['s'][K]['ask_up'] if r['s'][K]['ask_up'] is not None else (1 - r['s'][K]['ask_dn'] if r['s'][K]['ask_dn'] is not None else np.nan)) for r in rs])
        both = ok & ~np.isnan(mkt_up)
        print(f'\n=== S={S}s  scored {ok.sum()}  with a venue trade within {W}s: {both.sum()}')
        print(f'  AUC spot-only {auc(p[both], y[both]):.3f}   AUC venue traded price {auc(mkt_up[both], y[both]):.3f}   '
              f'AUC of ask-vs-line move alone {auc(X[both, 0], y[both]):.3f}')
        # disagreement grid: our side by spot p; ask = that side's own traded price (max within 3 s)
        side_up = p >= 0.5; ps = np.where(side_up, p, 1 - p)
        ask = np.array([(r['s'][K]['ask_up'] if su else r['s'][K]['ask_dn']) or np.nan for r, su in zip(rs, side_up)], dtype=float)
        win = np.where(side_up, y == 1, y == 0)
        half = np.array([r['e'] for r in rs]) >= np.median([r['e'] for r in rs])
        print(f'  {"P>=":>5} {"ask<=":>6} {"n":>5} {"n/day":>6} {"win%":>6} {"per$1":>7} {"H1":>7} {"H2":>7} {"permP":>6} {"ask":>5}')
        for P in P_LIST:
            for Amax in A_LIST:
                sel = ok & ~np.isnan(ask) & (ps >= P) & (ask <= Amax)
                n = int(sel.sum())
                if n == 0: print(f'  {P:>5.2f} {Amax:>6.2f} {0:>5}'); continue
                per = np.array([pnl(su, a, w) for su, a, w in zip(side_up[sel], ask[sel], win[sel])])
                h1 = per[~half[sel]].mean() if (~half[sel]).any() else float('nan'); h2 = per[half[sel]].mean() if half[sel].any() else float('nan')
                # permutation: shuffle WHICH candles we call UP, price the called side at ITS OWN traded price
                idx = np.where(sel)[0]; base = per.mean(); cnt = 0; tot = 0
                au = np.array([r['s'][K]['ask_up'] or np.nan for r in rs], dtype=float); ad = np.array([r['s'][K]['ask_dn'] or np.nan for r in rs], dtype=float)
                for _ in range(300):
                    sh = rng.permutation(side_up[idx]); a2 = np.where(sh, au[idx], ad[idx]); w2 = np.where(sh, y[idx] == 1, y[idx] == 0)
                    m = ~np.isnan(a2)
                    if m.sum() < max(5, n // 2): continue
                    v = np.array([pnl(s_, a_, w_) for s_, a_, w_ in zip(sh[m], a2[m], w2[m])]).mean(); tot += 1; cnt += v >= base
                permp = cnt / tot if tot else float('nan')
                print(f'  {P:>5.2f} {Amax:>6.2f} {n:>5} {n/max(1,len(days)-1):>6.1f} {100*win[sel].mean():>5.1f}% {base:>+7.3f} {h1:>+7.3f} {h2:>+7.3f} {permp:>6.2f} {ask[sel].mean():>5.2f}'
                      + ('  *n<60' if n < 60 else ''))
        # the crowd's own bet at the same second, for reference: buy the venue favourite
        fav_up = mkt_up >= 0.5; fask = np.where(fav_up, np.array([r['s'][K]['ask_up'] or np.nan for r in rs], dtype=float), np.array([r['s'][K]['ask_dn'] or np.nan for r in rs], dtype=float))
        fsel = both & ~np.isnan(fask)
        fw = np.where(fav_up, y == 1, y == 0)
        fper = np.array([pnl(s_, a_, w_) for s_, a_, w_ in zip(fav_up[fsel], fask[fsel], fw[fsel])])
        print(f'  null (buy the venue favourite at its traded price): n {fsel.sum()} win {100*fw[fsel].mean():.1f}% per$1 {fper.mean():+.3f}')


if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3] == 'cached':
        import glob; rows = []
        for fn in sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'early_rows_btc*.json'))): rows += json.load(open(fn))
        rows = sorted({r['e']: r for r in rows}.values(), key=lambda r: r['e'])
        analyse(rows)
    else:
        rows = collect(a, b)
        if os.environ.get('EARLY_OUT') is None: analyse(rows)
