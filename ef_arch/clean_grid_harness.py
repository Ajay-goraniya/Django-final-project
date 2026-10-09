#!/usr/bin/env python3
"""
clean_grid_harness.py -- the exact harness behind the "AUC 0.622" number,
made self-contained and extended with what the project actually needs:
a candle-level policy simulation reporting PnL per 100 candles.

Everything here is causal by construction:
  * a fixed wall-clock grid (1 s state, 5 s decision points), never a
    selected snapshot;
  * every feature at decision time t uses only data with timestamp <= t
    (rolling sums are trailing; volatility is shifted one step);
  * walk-forward: hour h is scored by a model trained on hours < h only,
    with train-only standardisation;
  * ONE coherent binary: P(candle closes contrarian to its current body).
    P_continuation = 1 - P_reversal exactly.

Reproduce:
    python3 clean_grid_harness.py            # uses ../btc_replay_2026-08-01_24h/normalized
    python3 clean_grid_harness.py --data <normalized dir>

Prints: walk-forward AUC (row-level, diagnostic), candle-clustered bootstrap
CI on AUC, top-third precision, then a POLICY SIMULATION: one reversal fire
per candle at most, admission by conservative edge, exact Predict fee
economics (P_BE = q/(1-fee)), under three synthetic pricing assumptions,
with a Pareto sweep of fires/100 vs PnL/100. All PnL is SYNTHETIC-PRICE
PnL and is labelled as such.
"""
import argparse, glob, math, pathlib, sys
import numpy as np

W0_MS, W1_MS = 1785542400_000, 1785628800_000
CAND = 300
FEE = 0.02


# ----------------------------------------------------------------- grid build
def build_grid(data_dir):
    import pyarrow.parquet as pq
    SEC = (W1_MS - W0_MS) // 1000
    mid = np.full(SEC, np.nan); micro = np.full(SEC, np.nan)
    b15 = np.full(SEC, np.nan); b610 = np.full(SEC, np.nan); b1120 = np.full(SEC, np.nan)
    spr = np.full(SEC, np.nan); flow = np.zeros(SEC); tcnt = np.zeros(SEC); spot = np.full(SEC, np.nan)
    for h in range(24):
        f = data_dir / f"perp_depth20_{h:02d}.parquet"
        if f.exists():
            cols = ["timestamp", "bid_px_0", "ask_px_0"] + [f"bid_qty_{i}" for i in range(20)] + [f"ask_qty_{i}" for i in range(20)]
            t = pq.read_table(f, columns=cols)
            ts = (np.asarray(t.column("timestamp")) // 1000 - W0_MS) // 1000
            bq = np.vstack([np.asarray(t.column(f"bid_qty_{i}"), float) for i in range(20)])
            aq = np.vstack([np.asarray(t.column(f"ask_qty_{i}"), float) for i in range(20)])
            bp = np.asarray(t.column("bid_px_0"), float); ap = np.asarray(t.column("ask_px_0"), float)
            def imb(lo, hi):
                b = np.nansum(bq[lo:hi], 0); a = np.nansum(aq[lo:hi], 0); s = b + a
                return np.where(s > 0, (b - a) / np.where(s > 0, s, 1), 0.0)
            ok = (ts >= 0) & (ts < SEC); idx = ts[ok]
            mid[idx] = ((bp + ap) / 2)[ok]
            micro[idx] = ((ap * bq[0] + bp * aq[0]) / np.maximum(bq[0] + aq[0], 1e-9))[ok]
            b15[idx] = imb(0, 5)[ok]; b610[idx] = imb(5, 10)[ok]; b1120[idx] = imb(10, 20)[ok]
            spr[idx] = (ap - bp)[ok]
        f = data_dir / f"perp_trades_{h:02d}.parquet"
        if f.exists():
            t = pq.read_table(f, columns=["timestamp", "signed_quote_notional"])
            ts = (np.asarray(t.column("timestamp")) // 1000 - W0_MS) // 1000
            ok = (ts >= 0) & (ts < SEC); idx = ts[ok]
            np.add.at(flow, idx, np.asarray(t.column("signed_quote_notional"), float)[ok]); np.add.at(tcnt, idx, 1)
        f = data_dir / f"spot_aggtrades_{h:02d}.parquet"
        if f.exists():
            t = pq.read_table(f, columns=["timestamp", "price"])
            ts = (np.asarray(t.column("timestamp")) // 1000 - W0_MS) // 1000
            ok = (ts >= 0) & (ts < SEC); spot[ts[ok]] = np.asarray(t.column("price"), float)[ok]
    def ffill(a):
        idx = np.where(~np.isnan(a))[0]
        if len(idx) == 0: return a
        f = np.maximum.accumulate(np.where(~np.isnan(a), np.arange(len(a)), 0))
        out = a[f]; out[:idx[0]] = a[idx[0]]; return out
    return dict(mid=ffill(mid), micro=ffill(micro), b15=ffill(b15), b610=ffill(b610), b1120=ffill(b1120),
                spr=ffill(spr), flow=flow, tcnt=tcnt, spot=ffill(spot))


def roll_sum(a, w):
    c = np.concatenate([[0.0], np.cumsum(a)]); idx = np.arange(len(a)); lo = np.maximum(0, idx - w + 1)
    return c[idx + 1] - c[lo]


def NORM(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


# ------------------------------------------------------------ decision points
def decision_points(g):
    spot, mid, micro, spr = g["spot"], g["mid"], g["micro"], g["spr"]
    b15, b610, b1120, flow, tcnt = g["b15"], g["b610"], g["b1120"], g["flow"], g["tcnt"]
    SEC = len(spot); NC = SEC // CAND
    logret = np.zeros(SEC); logret[1:] = np.diff(np.log(np.maximum(spot, 1e-9)))
    sig = np.sqrt(np.maximum(roll_sum(logret ** 2, 600), 1e-18) / 600.0)
    sig = np.concatenate([[sig[0]], sig[:-1]])                # strictly past
    f5 = roll_sum(flow, 5); f30 = roll_sum(flow, 30); n30 = roll_sum(np.abs(flow), 30)
    fnorm5 = f5 / np.maximum(n30, 1e-9); fnorm30 = f30 / np.maximum(n30, 1e-9); tc5 = roll_sum(tcnt, 5)
    rows = []
    for c in range(NC):
        s0 = c * CAND; op = spot[s0]; cl = spot[s0 + CAND - 1]
        for off in range(5, 300, 5):
            i = s0 + off; left = CAND - off; px = spot[i]; s = max(sig[i], 1e-9)
            z = (px - op) / max(px * s * math.sqrt(left), 1e-12)
            rows.append((c, i, off, left, op, px, cl, z, s))
    A = np.array(rows, float)
    ci = A[:, 0].astype(int); ii = A[:, 1].astype(int); off = A[:, 2]; left = A[:, 3]
    op = A[:, 4]; px = A[:, 5]; cl = A[:, 6]; z = A[:, 7]; sg = A[:, 8]
    upc = cl > op; cur_up = px > op; contr_up = ~cur_up
    fair_up = NORM(z)
    fair_contr = np.where(contr_up, fair_up, 1 - fair_up)
    win_contr = (contr_up == upc)
    X = np.column_stack([b15[ii], b610[ii], b1120[ii], fnorm5[ii], fnorm30[ii],
                         (micro[ii] - mid[ii]) / np.maximum(spr[ii], 1e-9),
                         np.tanh(z), left / 300.0, np.log1p(tc5[ii]),
                         np.sign(px - op) * np.tanh(np.abs(px - op) / np.maximum(px * sg * np.sqrt(off), 1e-12))])
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    hour = (ii // 3600).astype(int)
    return dict(ci=ci, off=off, left=left, z=z, fair_contr=fair_contr, contr_up=contr_up,
                win_contr=win_contr, X=X, hour=hour, NC=NC)


# ---------------------------------------------------------------- modelling
def walk_forward(X, y, hour, l2=0.01, iters=300, lr=1.0, min_rows=2000):
    P = np.zeros(len(y))
    for h in range(24):
        tr = hour < h; te = hour == h
        if tr.sum() < min_rows:
            P[te] = y[tr].mean() if tr.sum() else 0.5; continue
        mu = X[tr].mean(0); sd = np.maximum(X[tr].std(0), 1e-9)
        A = np.column_stack([np.ones(tr.sum()), (X[tr] - mu) / sd]); yt = y[tr].astype(float); w = np.zeros(A.shape[1])
        for _ in range(iters):
            p = 1 / (1 + np.exp(-A @ w)); w += lr * (A.T @ (yt - p) / len(yt) - l2 * w)
        P[te] = 1 / (1 + np.exp(-(np.column_stack([np.ones(te.sum()), (X[te] - mu) / sd]) @ w)))
    return P


def auc(p, y):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    npos = y.sum(); nneg = len(y) - npos
    return (r[y == 1].sum() - npos * (npos + 1) / 2) / max(npos * nneg, 1)


def clustered_auc_ci(p, y, cl, n=1000, seed=1):
    """Bootstrap CANDLES, not rows (Sol section 35)."""
    rs = np.random.default_rng(seed); cands = np.unique(cl); idx_by = {c: np.where(cl == c)[0] for c in cands}
    vals = []
    for _ in range(n):
        pick = rs.choice(cands, len(cands), replace=True)
        sel = np.concatenate([idx_by[c] for c in pick]); vals.append(auc(p[sel], y[sel]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


# ------------------------------------------------------------- economics
def market(p_fair, compress, spread):
    """Synthetic quote: favourite-longshot compression toward 0.5 + half spread."""
    return np.clip(0.5 + (p_fair - 0.5) * (1 - compress) + spread / 2, 0.02, 0.98)


def ret_per_stake(win, q, fee=FEE):
    """EXACT Build36 accounting: payout shares = shares*(1-fee)."""
    return np.where(win, (1.0 - fee) / q - 1.0, -1.0)


def policy_sim(d, P, q, margin, buffer=0.0, fee=FEE):
    """One reversal fire per candle at most; first admissible decision point
    in time order. P is P(reversal wins). Returns per-candle pnl array."""
    ci, win = d["ci"], d["win_contr"]
    p_be = q / (1.0 - fee)
    p_safe = np.clip(P - buffer, 0.01, 0.99)
    edge = p_safe - p_be
    fire = edge >= margin
    pnl = np.zeros(d["NC"]); fired = np.zeros(d["NC"], bool); hit = np.zeros(d["NC"])
    for k in np.where(fire)[0]:
        c = ci[k]
        if fired[c]: continue
        fired[c] = True; pnl[c] = ret_per_stake(win[k], q[k], fee); hit[c] = win[k]
    return pnl, fired, hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(pathlib.Path(__file__).resolve().parent.parent / "btc_replay_2026-08-01_24h" / "normalized"))
    ap.add_argument("--cache", default=str(pathlib.Path(__file__).resolve().parent / "grid.npz"))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache)
    if cache.exists():
        g = dict(np.load(cache)); g = {k: g[k] for k in ("mid", "micro", "b15", "b610", "b1120", "spr", "flow", "tcnt", "spot")}
    else:
        g = build_grid(pathlib.Path(args.data)); np.savez_compressed(cache, **g)
    d = decision_points(g)
    X, y, hour, ci = d["X"], d["win_contr"].astype(float), d["hour"], d["ci"]
    P = walk_forward(X, y, hour)
    m = hour >= 4                                     # first 4 h have no prior training data
    a = auc(P[m], y[m]); lo, hi = clustered_auc_ci(P[m], y[m], ci[m])
    print("=" * 72); print("CLEAN FIXED-GRID HARNESS  (2026-08-01, 5 s decision points, walk-forward)"); print("=" * 72)
    print(f"decision rows {int(m.sum()):,}   distinct candles {len(np.unique(ci[m]))}   distinct days 1")
    print(f"P(reversal wins) walk-forward AUC = {a:.3f}   candle-clustered 95% CI [{lo:.3f}, {hi:.3f}]")
    for frac in (1 / 3, 0.10):
        k = int(m.sum() * frac); top = np.argsort(-P[m])[:k]
        print(f"   top {int(frac*100):>2}% precision (reversal) = {100*y[m][top].mean():5.1f}%   base {100*y[m].mean():.1f}%")
    print("   (P_continuation = 1 - P_reversal; one coherent binary)")

    print("\n" + "=" * 72); print("POLICY SIMULATION -- SYNTHETIC PRICE PnL, one reversal fire per candle max"); print("=" * 72)
    print("economics: P_BE = q/(1-fee), win return = (1-fee)/q - 1, fee = 0.02, $1 stake")
    print(f"{'pricing':<16}{'margin':>7}{'buffer':>7}{'fires/100':>10}{'acc%':>7}{'PnL/100':>9}{'worstHr':>9}{'maxDD':>7}")
    pareto = {}
    for cname, comp, sprd in (("no-bias c=0", 0.0, 0.01), ("base c=0.15", 0.15, 0.01), ("strong c=0.25", 0.25, 0.01)):
        q = market(d["fair_contr"], comp, sprd)
        for margin in (0.00, 0.03, 0.06, 0.10, 0.15):
            for buffer in (0.00, 0.03):
                pnl, fired, hit = policy_sim(d, P, q, margin, buffer)
                mm = np.zeros(d["NC"], bool); mm[np.unique(ci[m])] = True      # evaluated candles only
                nf = fired[mm].sum(); ncand = mm.sum()
                if nf == 0:
                    print(f"{cname:<16}{margin:>7.2f}{buffer:>7.2f}{0:>10.1f}{'-':>7}{0:>9.2f}{0:>9.2f}{0:>7.2f}"); continue
                hourly = np.array([pnl[mm & ((np.arange(d['NC']) * CAND) // 3600 == h)].sum() for h in range(24)])
                eq = np.cumsum(pnl[mm]); dd = float((np.maximum.accumulate(eq) - eq).max())
                acc = 100 * hit[mm & fired].mean()
                print(f"{cname:<16}{margin:>7.2f}{buffer:>7.2f}{100*nf/ncand:>10.1f}{acc:>7.1f}{100*pnl[mm].sum()/ncand:>9.2f}{hourly.min():>9.2f}{dd:>7.2f}")
                pareto.setdefault(cname, []).append((100 * nf / ncand, 100 * pnl[mm].sum() / ncand, margin, buffer))
    print("\nPARETO (fires/100 -> PnL/100), per pricing assumption, best PnL at each frequency band:")
    for cname, pts in pareto.items():
        pts = sorted(pts); best = {}
        for f, p, mg, bf in pts:
            band = int(f // 10) * 10
            if band not in best or p > best[band][0]: best[band] = (p, f, mg, bf)
        print(f"  {cname:<16}" + "  ".join(f"[{b}-{b+10}) {v[0]:+.2f}@m{v[2]:.2f}/b{v[3]:.2f}" for b, v in sorted(best.items())))
    print("\nALL PnL ABOVE IS SYNTHETIC-PRICE PnL. It becomes quotable only with real Predict.fun books (V3).")


if __name__ == "__main__":
    main()
