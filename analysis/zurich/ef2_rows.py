#!/usr/bin/env python3
"""EF-2 step 1: build the training rows. NC-17, owner order 09-28 11:1x. READ-ONLY. Master OFF.

EF-2 is ONE model of P(win | buy THIS side at THIS ask at THIS second) - no direction model plus a gate. So
every pass contributes TWO candidate rows, one per side, and the model has to learn that buying the expensive
side of a decided market is a bad trade rather than being told so by a separate rule.

ROWS
  one per (pass, side) for passes at sec 15-240 with a usable own-side ask, in gamma-graded candles.
LABEL
  1 if that side is the side the venue resolved to. The outcome is binary and exhaustive, so the two rows of
  a pass carry complementary labels by construction.
p PER SIDE
  decide_log stores the EF decision's own side and p, and p >= 0.5 on 100.0% of 785,924 passes, so the logged
  side is the model-favoured one. For the other side p = 1 - p, forced by the outcome being binary rather
  than assumed about the engine's internals.
FEATURES
  all 44 engine features as logged (nothing dropped - ef_persist's DROP set is for a different question)
  + own_ask, opp_ask
  + ask dynamics: d1/d5/d30 = own ask now minus own ask ~1/5/30 s ago, and dip30 = own ask minus its own
    30 s MINIMUM. dip30 is the selected-dip detector: EF_VETO_V2 measured the same-source ask +6.02c higher
    one row after a fire, so "how far is this ask below where it has just been" is the private history of
    being picked off, which is the thing the engine has never been allowed to see.
  + sec, p_side.
PRICE AND FILL
  ef_persist's simulator, per side: a FAK at ask+1 tick fills iff that side's ask on the first row at
  >= t+250 ms is within one tick, and it fills AT that later ask.

A sampling note that belongs with the row counts: _decide_log throttles to one row per 250 ms but exempts a
candle's FIRST fire row, so fire moments are very slightly over-represented. Fires are ~325 of 785,924
passes, so the bias is ~0.04% of rows and is recorded here rather than corrected.
"""
import sys, sqlite3, json, time, datetime as dt, numpy as np

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
OUT = '/home/ubuntu/pm_ef2/ef2_rows.npz'
SEC_LO, SEC_HI, TICK, DELAY_MS = 15, 240, 0.01, 250
DYN = (1000, 5000, 30000)


def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out


def main():
    t0 = time.time()
    vo = outcomes()
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    nk = len(keys)
    print(f'engine feature keys: {nk}')
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)

    cand = {}
    bad_feat = 0
    for ts, ep, side, p, ask, ua, da, fire, fs in c.execute(
            'SELECT ts_ms,epoch,side,p,ask,up_ask,dn_ask,fire,feats FROM decide_log '
            'WHERE p IS NOT NULL AND side IS NOT NULL AND up_ask IS NOT NULL AND dn_ask IS NOT NULL '
            'ORDER BY ts_ms'):
        if ep not in vo: continue
        sec = (ts // 1000) - ep
        if not (SEC_LO <= sec <= SEC_HI): continue
        v = None
        if fs:
            try:
                raw = json.loads(fs)
                if len(raw) == nk: v = raw
            except Exception: pass
        if v is None: bad_feat += 1; continue
        cand.setdefault(ep, []).append((ts, side, float(p), float(ua), float(da), int(fire or 0), v))
    print(f'candles {len(cand)}, passes {sum(len(v) for v in cand.values())}, '
          f'passes dropped for unusable feats {bad_feat}   [{time.time()-t0:.0f}s]')

    X, Y, Q, F, EP, TS, SD, SEC_, DAY = [], [], [], [], [], [], [], [], []
    nfire = 0
    for ep, rs in cand.items():
        rs.sort(key=lambda r: r[0])
        ts_a = np.array([r[0] for r in rs])
        ua_a = np.array([r[3] for r in rs]); da_a = np.array([r[4] for r in rs])
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        out = vo[ep]
        for i, (ts, side_l, p_l, ua, da, fire, v) in enumerate(rs):
            nfire += fire
            j = int(np.searchsorted(ts_a, ts + DELAY_MS, side='left'))
            lo30 = int(np.searchsorted(ts_a, ts - DYN[2], side='left'))
            back = [int(np.searchsorted(ts_a, ts - d, side='right')) - 1 for d in DYN]
            for side in ('UP', 'DOWN'):
                own = ua if side == 'UP' else da
                opp = da if side == 'UP' else ua
                if not (0.01 < own < 0.99): continue
                oa = ua_a if side == 'UP' else da_a
                dyn = []
                for b in back:
                    dyn.append(own - oa[b] if 0 <= b < len(oa) else 0.0)
                w = oa[lo30:i + 1]
                dip = own - float(w.min()) if len(w) else 0.0
                q = None
                if j < len(rs):
                    lat = float(ua_a[j] if side == 'UP' else da_a[j])
                    if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q = lat
                X.append(v + [own, opp, dyn[0], dyn[1], dyn[2], dip, float((ts // 1000) - ep),
                              (p_l if side == side_l else 1.0 - p_l)])
                Y.append(1 if side == out else 0)
                Q.append(q if q is not None else np.nan)
                F.append(1 if q is not None else 0)
                EP.append(ep); TS.append(ts); SD.append(1 if side == 'UP' else 0)
                SEC_.append((ts // 1000) - ep); DAY.append(day)

    names = list(keys) + ['own_ask', 'opp_ask', 'd_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30', 'sec', 'p_side']
    X = np.array(X, dtype=np.float32)
    Y = np.array(Y, dtype=np.int8); Q = np.array(Q, dtype=np.float32); F = np.array(F, dtype=np.int8)
    EP = np.array(EP, dtype=np.int64); TS = np.array(TS, dtype=np.int64); SD = np.array(SD, dtype=np.int8)
    SEC_ = np.array(SEC_, dtype=np.int16); DAY = np.array(DAY)
    import os; os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, X=X, y=Y, q=Q, filled=F, ep=EP, ts=TS, is_up=SD, sec=SEC_, day=DAY,
                        names=np.array(names))
    print(f'\nsaved {OUT}  [{time.time()-t0:.0f}s]')
    print(f'  rows {len(Y):,}  features {X.shape[1]} ({nk} engine + 8 added)  '
          f'candles {len(cand)}  fire rows in source {nfire}')
    print(f'  base rate  P(this side wins) = {Y.mean():.4f}')
    print(f'  sim FILL rate over all candidate rows = {F.mean():.4f}')
    fq = Q[F == 1]
    print(f'  fill price: p10 {np.percentile(fq,10):.3f} p50 {np.percentile(fq,50):.3f} '
          f'p90 {np.percentile(fq,90):.3f}')
    print(f'  base rate among FILLED rows = {Y[F==1].mean():.4f}   among unfilled = {Y[F==0].mean():.4f}')
    print(f'\n  per day:')
    for d in sorted(set(DAY.tolist())):
        m = DAY == d
        print(f'    {d}  rows {int(m.sum()):>9,}  candles {len(set(EP[m].tolist())):>5}  '
              f'win {Y[m].mean():.4f}  fill {F[m].mean():.4f}')
    print(f'\n  ask dynamics (own side), cents:')
    for k in ('d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30'):
        v = X[:, names.index(k)]
        print(f'    {k:9s} mean {100*v.mean():+7.3f}  p10 {100*np.percentile(v,10):+7.2f}  '
              f'p50 {100*np.percentile(v,50):+7.2f}  p90 {100*np.percentile(v,90):+7.2f}')


if __name__ == '__main__':
    main()
