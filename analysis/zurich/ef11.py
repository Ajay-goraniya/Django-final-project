#!/usr/bin/env python3
"""EF-11: EF-9 v1's architecture at 1 s on the LONG tape. READ-ONLY. PAPER. Master OFF.

Owner: 3 test days is too few. tape1s turns out to carry everything already - spot_px/spot_buy/spot_sell,
perp_px/perp_buy/perp_sell, ref_px, up_ask, dn_ask - 516,302 rows over 09-22 19:30 .. now = 6.05 d. So no
Binance download was needed for this: the engine's own tape has had the signed flow all along.

CHANNELS (8): own_ask, opp_ask, spot bps-from-line, spot signed flow, perp bps-from-line, perp signed
flow, line distance bps, sec. tape1s carries notional but NOT trade counts, so v1's two count channels
have no 1 s equivalent and are absent rather than faked. Book depth (bid5/ask5/bid20/ask20) is present in
the tape but stays out on V's BOOK_SIZE_INFO measurement.

THE ONE SUBSTITUTION, and it is not cosmetic: EF-9 v1 pins to the engine's p_side >= 0.5, and tape1s does
NOT carry the engine's p - decide_log only goes back to 09-24. Pinning on p would throw away the extra
history this test exists to get. So the side is pinned to THE MODEL'S OWN preference: score both sides,
take the higher predicted after-fill $. That is a different rule from v1's, stated here rather than
buried, and it means EF-11 and EF-9 v1 are not the same arm measured over more days.

FILL: the same-side ask 1 s later <= ask + 1 tick, filling AT that later ask. The 1 s tape cannot express
the +250 ms sim, so this is a slower, more forgiving fill than every other table in this repo.
"""
import sys, os, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1
from ef3 import platt, pad_cost, STAKE
from ef3_shadow import outcomes
from ef9 import CNN, gradcheck

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
WIN, NCH, TICK = 30, 8, 0.01
Q, ANCHORS, G_MS, W_MS = 0.90, (0, 15, 30, 45), 60_000, 3600_000
CACHE = '/home/ubuntu/pm_ef3/ef11.npz'


def build():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True); return {k: z[k] for k in z.files}
    c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    cols = 'ts,spot_px,spot_buy,spot_sell,perp_px,perp_buy,perp_sell,ref_px,up_ask,dn_ask'
    raw = np.array(c.execute(f'SELECT {cols} FROM tape1s ORDER BY ts').fetchall(), dtype=object)
    ts = raw[:, 0].astype(np.int64)
    f = lambda j: np.array([np.nan if v is None else float(v) for v in raw[:, j]])
    sp, sb, ss, pp_, pb, psl, rf, ua, da = (f(j) for j in range(1, 10))
    def ff(a):
        m = np.isnan(a)
        if m.all(): return np.zeros_like(a)
        i = np.where(~m, np.arange(len(a)), 0); np.maximum.accumulate(i, out=i); a = a[i]
        k = int(np.argmax(~np.isnan(a)))
        if k: a[:k] = a[k]
        return a
    sp, pp_, rf, ua, da = (ff(x) for x in (sp, pp_, rf, ua, da))
    sb, ss, pb, psl = (np.nan_to_num(x) for x in (sb, ss, pb, psl))
    idx = {int(t): i for i, t in enumerate(ts)}
    vo = outcomes()
    G, ROW = [], []
    for ep in sorted(vo):
        if ep + 300 > ts.max() or ep < ts.min(): continue
        base = idx.get(ep)
        if base is None: continue
        sl = slice(base, base + 301)
        if base + 301 > len(ts) or ts[base + 300] != ep + 300: continue
        line = rf[base]
        if not np.isfinite(line) or line <= 0: continue
        g = np.zeros((301, NCH), np.float32)
        g[:, 0] = ua[sl]; g[:, 1] = da[sl]
        g[:, 2] = (sp[sl] - line) / line * 1e4
        g[:, 3] = (sb[sl] - ss[sl]) / 1e4
        g[:, 4] = (pp_[sl] - line) / line * 1e4
        g[:, 5] = (pb[sl] - psl[sl]) / 1e4
        g[:, 6] = (rf[sl] - line) / line * 1e4
        g[:, 7] = np.arange(301) / 240.0
        if not np.isfinite(g).all(): continue
        gi = len(G); G.append(g)
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'); out = vo[ep]
        for s in range(WIN, 241):
            u0, d0 = ua[base + s], da[base + s]
            u1, d1 = ua[base + s + 1], da[base + s + 1]
            for up_, own, nxt in ((1, u0, u1), (0, d0, d1)):
                if not (0.01 < own < 0.99): continue
                q = nxt if (0.01 < nxt < 0.99 and nxt <= own + TICK + 1e-12) else np.nan
                sd_ = 'UP' if up_ else 'DOWN'
                ROW.append((gi, s, up_, 1.0 if sd_ == out else 0.0, q, ep, (ep + s) * 1000, day, own))
    d = dict(G=np.stack(G), gi=np.array([r[0] for r in ROW], np.int32),
             k=np.array([r[1] for r in ROW], np.int16), up=np.array([r[2] for r in ROW], np.int8),
             y=np.array([r[3] for r in ROW], np.float32), q=np.array([r[4] for r in ROW], np.float32),
             ep=np.array([r[5] for r in ROW], np.int64), ts=np.array([r[6] for r in ROW], np.int64),
             day=np.array([r[7] for r in ROW]), own=np.array([r[8] for r in ROW], np.float32))
    np.savez(CACHE, **d); return d


def gather(G, gi, k, up, idx, mu, sd):
    x = np.empty((len(idx), NCH, WIN), np.float32)
    for a, i in enumerate(idx):
        w = G[gi[i], k[i] - WIN + 1:k[i] + 1].T
        x[a] = w
        if not up[i]: x[a, 0], x[a, 1] = w[1], w[0]
    return (x - mu) / sd


def strict_thr(sv, qq):
    if len(sv) < 500: return np.inf
    qv = float(np.quantile(sv, qq)); i = int(np.searchsorted(sv, qv, 'right'))
    return float(sv[i]) if i < len(sv) else np.inf


def dd_run(seq):
    cum = peak = mdd = 0.
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    return cum, mdd


if __name__ == '__main__':
    if not gradcheck(): sys.exit('gradcheck FAILED')
    D = build()
    G, gi, k, up, y, q, ep, ts, day, own = (D[x] for x in
                                            ('G', 'gi', 'k', 'up', 'y', 'q', 'ep', 'ts', 'day', 'own'))
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(y, np.where(filled, q, 0.5)), 0.0).astype(np.float32)
    days = sorted(set(day.tolist()))
    print(f'EF-11 1 s. candles {len(G):,}  rows {len(gi):,}  {NCH}ch x {WIN}s  days {days}')
    print(f'  fill {100*filled.mean():.1f}%  target mean {tgt.mean():+.4f}')
    flat = G.reshape(-1, NCH)
    mu = flat.mean(0).astype(np.float32)[None, :, None]
    sd = (flat.std(0) + 1e-6).astype(np.float32)[None, :, None]
    pred = np.full(len(gi), np.nan, np.float32)
    rng = np.random.default_rng(0)
    for i, dcur in enumerate(days):
        if i < 2: continue                                   # walk-forward from the THIRD day
        tr = np.where(np.isin(day, days[:i]))[0]; te = np.where(day == dcur)[0]
        if len(tr) < 20000 or not len(te): continue
        sub = rng.choice(tr, size=min(len(tr), 150000), replace=False)
        net = CNN(cin=NCH)
        for _ in range(5):
            rng.shuffle(sub)
            for a in range(0, len(sub) - 4096 + 1, 4096):
                b = sub[a:a + 4096]
                yh, ca = net.fwd(gather(G, gi, k, up, b, mu, sd))
                net.step(net.bwd(ca, (2.0 / len(b)) * (yh - tgt[b])))
        o = np.empty(len(te), np.float32)
        for a in range(0, len(te), 8192):
            bb = te[a:a + 8192]; o[a:a + len(bb)] = net.fwd(gather(G, gi, k, up, bb, mu, sd))[0]
        pred[te] = o
        print(f'  day {dcur}: train {len(sub):,} test {len(te):,}  corr {np.corrcoef(pred[te], tgt[te])[0,1]:+.4f}')
    np.savez('/home/ubuntu/pm_ef3/ef11_pred.npz', pred=pred)
    print('  saved')
