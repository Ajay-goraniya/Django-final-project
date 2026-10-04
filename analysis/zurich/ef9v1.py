#!/usr/bin/env python3
"""EF-9 v1: the sequence model with the inputs it was actually supposed to have. READ-ONLY. Master OFF.

V, 09-28: the missing inputs did not need a recorder. data.binance.vision publishes daily aggTrades for
spot AND um-futures and both are reachable, so perp flow exists historically even though fstream's
websocket is blocked here. Bids/sizes stay out on V's measurement that book size/age add nothing beyond
price (NC-19 BOOK_SIZE_INFO), so their absence is a decision, not a gap.

10 channels at 250 ms over the last 30 s (120 steps), no hand features:
  own_ask, opp_ask, spot bps-from-line, spot signed flow, spot trade count,
  perp bps-from-line, perp signed flow, perp trade count, line distance bps, sec
Signed flow = taker-buy minus taker-sell notional; is_buyer_maker True means the TAKER SOLD.

Sequences are NOT materialised - 1.48M x 10 x 120 float32 is 7.1 GB. Per-candle grids are held (1201 x 10
per candle, 49 MB for the lot) and batches are gathered on the fly.

TEST DAYS ARE 09-25/26/27. 09-28 is excluded: the daily aggTrades zip for a day is published after that
day closes, so today has no Binance history and a sequence for it cannot be built. Said rather than
quietly padded with zeros.
"""
import sys, os, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1
from ef3 import platt, pad_cost, STAKE
from ef3_shadow import outcomes
from ef9 import CNN, gradcheck

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
BNH = '/home/ubuntu/pm_bnhist'
STEP_MS, WIN, TICK, DELAY_MS, NCH = 250, 120, 0.01, 250, 10
GRIDN = 1 + 300 * 1000 // STEP_MS
CACHE = '/home/ubuntu/pm_ef3/ef9v1_grids.npz'


def bn_load(days):
    """250 ms buckets -> dict ts_ms -> (px, signed notional, count), per stream."""
    out = {}
    for s in ('spot', 'perp'):
        T, P, F, N = [], [], [], []
        for d in days:
            p = f'{BNH}/{s}_{d}.npz'
            if not os.path.exists(p): continue
            z = np.load(p)
            T.append(z['ts']); P.append(z['px']); F.append(z['buy'] - z['sell']); N.append(z['n'])
        if not T: continue
        t = np.concatenate(T); o = np.argsort(t, kind='stable')
        out[s] = (t[o], np.concatenate(P)[o], np.concatenate(F)[o], np.concatenate(N)[o].astype(float))
    return out


def build():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}
    L = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    ref = {int(t): float(p) for t, p in L.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL')}
    vo = outcomes()
    bn = bn_load(['2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27'])
    have = {s: (v[0].min(), v[0].max()) for s, v in bn.items()}
    print(f'  binance buckets: ' + '  '.join(f'{s} {len(v[0]):,}' for s, v in bn.items()))
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    by = collections.defaultdict(list)
    for ts, ep, side, p, ua, da in c.execute(
            'SELECT ts_ms,epoch,side,p,up_ask,dn_ask FROM decide_log WHERE p IS NOT NULL AND side IS NOT NULL '
            'AND up_ask IS NOT NULL AND dn_ask IS NOT NULL ORDER BY ts_ms'):
        if ep not in vo: continue
        by[ep].append((int(ts), side, float(p), float(ua), float(da)))
    G, ROW = [], []
    for ep, rs in sorted(by.items()):
        line = ref.get(ep)
        if line is None: continue
        t0 = ep * 1000
        # `have` holds (min_ts, max_ts) per stream; bn[s][0] is the whole timestamp ARRAY, and indexing
        # that instead was an ambiguous-truth ValueError on the first candle.
        if not all(lo <= t0 and t0 + 300000 <= hi for lo, hi in have.values()): continue
        g = np.zeros((GRIDN, NCH), np.float32)
        gu = np.full(GRIDN, np.nan); gd = np.full(GRIDN, np.nan)
        for ts, side, p, ua, da in rs:
            i = (ts - t0) // STEP_MS
            if 0 <= i < GRIDN: gu[i], gd[i] = ua, da
        for arr in (gu, gd):
            m = np.isnan(arr)
            if m.all(): break
            idx = np.where(~m, np.arange(GRIDN), 0); np.maximum.accumulate(idx, out=idx); arr[:] = arr[idx]
            f0 = int(np.argmax(~np.isnan(arr)))
            if f0 > 0: arr[:f0] = arr[f0]
        if np.isnan(gu).any() or np.isnan(gd).any(): continue
        g[:, 0], g[:, 1] = gu, gd
        gts = t0 + np.arange(GRIDN) * STEP_MS
        for si, s in enumerate(('spot', 'perp')):
            t, px, fl, n = bn[s]
            j = np.searchsorted(t, gts, 'right') - 1
            ok = j >= 0
            pv = np.where(ok, px[np.clip(j, 0, len(px) - 1)], line)
            g[:, 2 + si * 3] = (pv - line) / line * 1e4
            hit = (j >= 0) & (t[np.clip(j, 0, len(t) - 1)] == gts)      # flow only in its own bucket
            g[:, 3 + si * 3] = np.where(hit, fl[np.clip(j, 0, len(fl) - 1)], 0.0) / 1e4
            g[:, 4 + si * 3] = np.where(hit, n[np.clip(j, 0, len(n) - 1)], 0.0) / 10.0
        for s_ in range(301):
            v = ref.get(ep + s_)
            if v is not None:
                i = s_ * 1000 // STEP_MS
                if i < GRIDN: g[i, 8] = (v - line) / line * 1e4
        nz = g[:, 8] != 0
        if nz.any():
            idx = np.where(nz, np.arange(GRIDN), 0); np.maximum.accumulate(idx, out=idx); g[:, 8] = g[idx, 8]
        g[:, 9] = np.arange(GRIDN) * STEP_MS / 1000.0 / 240.0
        gi = len(G); G.append(g)
        ts_a = np.array([r[0] for r in rs]); ua_a = np.array([r[3] for r in rs]); da_a = np.array([r[4] for r in rs])
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        out = vo[ep]
        for i2, (ts, side_l, p_l, ua, da) in enumerate(rs):
            sec = ts // 1000 - ep
            if not (15 <= sec <= 240): continue
            k = (ts - t0) // STEP_MS
            if k < WIN: continue
            j = int(np.searchsorted(ts_a, ts + DELAY_MS, 'left'))
            for up_, own, oa in ((1, ua, ua_a), (0, da, da_a)):
                if not (0.01 < own < 0.99): continue
                q = np.nan
                if j < len(rs):
                    lat = float(oa[j])
                    if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q = lat
                sd_ = 'UP' if up_ else 'DOWN'
                # p_side: compare the SIDE STRINGS. The first version compared sd_ ('UP'/'DOWN') to
                # an int, which is silently always False, so every row got 1 - p and `ps >= 0.5` was
                # true on ZERO of 1,456,364 rows - the rule fired nothing and looked like a flat result.
                ROW.append((gi, k, up_, 1.0 if sd_ == out else 0.0, q, ep, ts,
                            p_l if sd_ == side_l else 1.0 - p_l, day))
    ps_arr = np.array([r[7] for r in ROW], np.float32)
    frac = float((ps_arr >= 0.5).mean())
    print(f'  p_side >= 0.5 on {100*frac:.1f}% of rows (expect ~50%: the engine logs its favoured side, '
          f'so exactly one side of each pass qualifies)')
    assert 0.30 < frac < 0.70, f'p_side pin is broken: {100*frac:.1f}% of rows qualify'
    Ga = np.stack(G)
    d = dict(G=Ga, gi=np.array([r[0] for r in ROW], np.int32), k=np.array([r[1] for r in ROW], np.int16),
             up=np.array([r[2] for r in ROW], np.int8), y=np.array([r[3] for r in ROW], np.float32),
             q=np.array([r[4] for r in ROW], np.float32), ep=np.array([r[5] for r in ROW], np.int64),
             ts=np.array([r[6] for r in ROW], np.int64), ps=np.array([r[7] for r in ROW], np.float32),
             day=np.array([r[8] for r in ROW]))
    np.savez(CACHE, **d)
    return d


def gather(G, gi, k, up, idx, mu, sd):
    n = len(idx)
    x = np.empty((n, NCH, WIN), np.float32)
    for a, i in enumerate(idx):
        w = G[gi[i], k[i] - WIN + 1:k[i] + 1].T
        x[a] = w
        if not up[i]: x[a, 0], x[a, 1] = w[1], w[0]
    return (x - mu) / sd


if __name__ == '__main__':
    if not gradcheck(): sys.exit('gradcheck FAILED')
    D = build()
    G, gi, k, up, y, q, ep, ts, ps, day = (D[x] for x in ('G', 'gi', 'k', 'up', 'y', 'q', 'ep', 'ts', 'ps', 'day'))
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(y, np.where(filled, q, 0.5)), 0.0).astype(np.float32)
    days = sorted(set(day.tolist()))
    print(f'EF-9 v1. candles {len(G):,}  rows {len(gi):,}  {NCH} channels x {WIN} x {STEP_MS} ms = 30 s')
    print(f'  days {days}  fill {100*filled.mean():.1f}%  target mean {tgt.mean():+.4f}')
    flat = G.reshape(-1, NCH)
    mu = flat.mean(0).astype(np.float32)[None, :, None]
    sd = (flat.std(0) + 1e-6).astype(np.float32)[None, :, None]
    pred = np.full(len(gi), np.nan, np.float32)
    rng = np.random.default_rng(0)
    for i, dcur in enumerate(days):
        if i == 0: continue
        tr = np.where(np.isin(day, days[:i]))[0]; te = np.where(day == dcur)[0]
        if len(tr) < 20000: continue
        sub = rng.choice(tr, size=min(len(tr), 120000), replace=False)
        net = CNN(cin=NCH)
        B = 4096
        for _ in range(4):
            rng.shuffle(sub)
            for a in range(0, len(sub) - B + 1, B):
                b = sub[a:a + B]
                yh, ca = net.fwd(gather(G, gi, k, up, b, mu, sd))
                net.step(net.bwd(ca, (2.0 / len(b)) * (yh - tgt[b])))
        o = np.empty(len(te), np.float32)
        for a in range(0, len(te), 8192):
            bb = te[a:a + 8192]
            o[a:a + len(bb)] = net.fwd(gather(G, gi, k, up, bb, mu, sd))[0]
        pred[te] = o
        print(f'  day {dcur}: train {len(sub):,} test {len(te):,}  corr {np.corrcoef(pred[te], tgt[te])[0,1]:+.4f}')
    np.save('/home/ubuntu/pm_ef3/ef9v1_pred.npy', pred)
    np.savez('/home/ubuntu/pm_ef3/ef9v1_meta.npz', y=y, q=q, ep=ep, ts=ts, ps=ps, day=day,
             own=np.array([G[gi[i], k[i], 0 if up[i] else 1] for i in range(len(gi))], np.float32))
    print('  saved ef9v1_pred.npy + ef9v1_meta.npz')
