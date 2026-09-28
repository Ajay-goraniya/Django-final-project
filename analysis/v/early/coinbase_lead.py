#!/usr/bin/env python3
"""Does Coinbase LEAD Binance into the venue's settlement? Public data (V, 09-28).
Inputs: coinbase_1s_btc.json (fetch_coinbase_1s.py), Binance 1 s closes (data-api.binance.vision), candle labels + venue traded
prices from early_rows_btc*.json (early_spot_signal.py). Coinbase is a Chainlink BTC/USD source; the Polymarket crowd watches Binance.
1. Lead-lag on 1 s log returns: corr(ret_bn[t], ret_cb[t-k]) vs corr(ret_cb[t], ret_bn[t-k]), k = 1..10 s.
2. At sec S in {20,30,45,60}: walk-forward logistic, BASE = Binance-only (move, ret5, ret30, ret60, mv_sec) vs BASE + Coinbase
   (cb_div = (cb-bn)/bn bps, cb_ret5, cb_lead = cb_ret5 - bn_ret5, cb_move = Coinbase move from the Coinbase TWAP60 line). AUC each,
   AUC of the venue traded price, and disagreement cells (model p_side >= P while the side's traded price <= A): n, win%, per $1.
usage: coinbase_lead.py <first 5m epoch> <last 5m epoch>"""
import sys, os, json, glob, math
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'twap'))
import arb_trades_check as A
import early_spot_signal as E

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rows():
    rows = []
    for fn in sorted(glob.glob(os.path.join(HERE, 'early_rows_btc*.json'))): rows += json.load(open(fn))
    return sorted({r['e']: r for r in rows}.values(), key=lambda r: r['e'])


def ffill(px, a, b):
    out, last = {}, None
    for t in range(a, b + 1):
        if t in px: last = px[t]
        if last is not None: out[t] = last
    return out


def lead_lag(bn, cb, a, b):
    ts = [t for t in range(a + 1, b) if t in bn and t - 1 in bn and t in cb and t - 1 in cb]
    rb = np.array([math.log(bn[t] / bn[t - 1]) for t in ts]); rc = np.array([math.log(cb[t] / cb[t - 1]) for t in ts])
    print(f'\n1-s returns, {len(ts)} shared seconds. corr(bn_t, cb_t-k) = Coinbase leads; corr(cb_t, bn_t-k) = Binance leads')
    print(f'  k=0 same-second corr {np.corrcoef(rb, rc)[0,1]:+.3f}')
    for k in (1, 2, 3, 5, 10):
        print(f'  k={k:2d}  Coinbase leads {np.corrcoef(rb[k:], rc[:-k])[0,1]:+.4f}   Binance leads {np.corrcoef(rc[k:], rb[:-k])[0,1]:+.4f}')


def cb_feats(bn, cb, e, S):
    L_cb = [cb[k] for k in range(e - 60, e) if k in cb]
    if len(L_cb) < 45: return None
    Lc = sum(L_cb) / len(L_cb)
    t = e + S
    if any(k not in cb or k not in bn for k in (t, t - 5)): return None
    return dict(cb_div=(cb[t] - bn[t]) / bn[t] * 1e4, cb_ret5=(cb[t] / cb[t - 5] - 1) * 1e4,
                cb_lead=((cb[t] / cb[t - 5]) - (bn[t] / bn[t - 5])) * 1e4, cb_move=(cb[t] - Lc) / Lc * 1e4)


def main(a, b):
    rows = load_rows()
    print(f'candles with labels {len(rows)}')
    bn = A.closes(a - 700, b + 300); cb_raw = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'coinbase_1s_btc.json'))).items()}
    cb = ffill(cb_raw, a - 700, b + 300)
    print(f'binance 1 s {len(bn)}, coinbase raw {len(cb_raw)} ffilled {len(cb)}')
    lead_lag(bn, cb_raw, a, b)
    base_keys = ['move', 'ret5', 'ret30', 'ret60', 'mv_sec']; cb_keys = ['cb_div', 'cb_ret5', 'cb_lead', 'cb_move']
    days = sorted({r['day'] for r in rows}); rng = np.random.default_rng(3)
    for S in E.S_LIST:
        K = str(S); rs = []
        for r in rows:
            if K not in r['s']: continue
            f2 = cb_feats(bn, cb, r['e'], S)
            if f2 is None: continue
            rs.append((r, f2))
        y = np.array([r['up'] for r, _ in rs]).astype(int); d = np.array([r['day'] for r, _ in rs])
        Xb = np.array([[r['s'][K]['f'][k] for k in base_keys] for r, _ in rs]); Xc = np.array([[f2[k] for k in cb_keys] for _, f2 in rs])
        X2 = np.c_[Xb, Xc]
        def wf(X):
            p = np.full(len(rs), np.nan)
            for k in days[1:]:
                tr, te = d < k, d == k
                if tr.sum() < 100 or te.sum() == 0: continue
                mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
                f = E.fit_logit((X[tr] - mu) / sd, y[tr]); p[te] = f((X[te] - mu) / sd)
            return p
        pb, p2 = wf(Xb), wf(X2)
        mkt = np.array([(r['s'][K]['ask_up'] if r['s'][K]['ask_up'] is not None else (1 - r['s'][K]['ask_dn'] if r['s'][K]['ask_dn'] is not None else np.nan)) for r, _ in rs])
        ok = ~np.isnan(pb) & ~np.isnan(p2) & ~np.isnan(mkt)
        print(f'\n=== S={S}s  n {ok.sum()}   AUC Binance-only {E.auc(pb[ok], y[ok]):.3f}   +Coinbase {E.auc(p2[ok], y[ok]):.3f}   '
              f'venue price {E.auc(mkt[ok], y[ok]):.3f}   cb_lead alone {E.auc(Xc[ok, 2], y[ok]):.3f}   cb_div alone {E.auc(Xc[ok, 0], y[ok]):.3f}')
        for name, p in (('Binance-only', pb), ('+Coinbase', p2)):
            su = p >= 0.5; ps = np.where(su, p, 1 - p)
            ask = np.array([(r['s'][K]['ask_up'] if s_ else r['s'][K]['ask_dn']) or np.nan for (r, _), s_ in zip(rs, su)], dtype=float)
            win = np.where(su, y == 1, y == 0); half = np.array([r['e'] for r, _ in rs]) >= np.median([r['e'] for r, _ in rs])
            print(f'  {name}:  P>=  ask<=     n   win%   per$1      H1      H2')
            for P in (0.55, 0.60, 0.65):
                for Am in (0.45, 0.50, 0.55):
                    sel = ok & ~np.isnan(ask) & (ps >= P) & (ask <= Am); n = int(sel.sum())
                    if n == 0: print(f'    {P:.2f} {Am:.2f} {0:>6}'); continue
                    per = np.array([E.pnl(s_, a_, w_) for s_, a_, w_ in zip(su[sel], ask[sel], win[sel])])
                    h1 = per[~half[sel]].mean() if (~half[sel]).any() else float('nan'); h2 = per[half[sel]].mean() if half[sel].any() else float('nan')
                    print(f'    {P:.2f} {Am:.2f} {n:>6} {100*win[sel].mean():>5.1f}% {per.mean():>+7.3f} {h1:>+7.3f} {h2:>+7.3f}' + ('  *n<60' if n < 60 else ''))


if __name__ == '__main__':
    main(int(sys.argv[1]), int(sys.argv[2]))
