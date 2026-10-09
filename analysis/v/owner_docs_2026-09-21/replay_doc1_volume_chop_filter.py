"""Replay doc 1's FROZEN filter on the repo's own build11-family journals.

Condition, verbatim from the doc: 0.346 <= volume_ratio <= 1.396 AND ef_chop <= 0.539.
Rows: kind=EF, forbidden=0, financial_result in (WIN, LOSS). PnL: financial_pnl.
Features come from ef_predictions.features (same candle_id + ef_attempt_seq as the trade).
Thresholds are NOT touched. Every db is reported on its own; a pooled line is given but
the lanes run on the same tape, so pooled n is inflated by correlated rows.
"""
import sqlite3, json, random, statistics as st
from collections import defaultdict

VLO, VHI, CHOP = 0.346, 1.396, 0.539
DBS = ['build11','predict_pnl','predict_acc','twin_b_guard','twin_c_thr1','twin_d_auto','twin_e_combo','v11_paper_1630-2100']

def load(name):
    c = sqlite3.connect(f'/tmp/livecheck/{name}.sqlite3'); c.row_factory = sqlite3.Row
    feats = defaultdict(list)   # candle_id -> [(ts_ms, features)]
    for r in c.execute("SELECT candle_id, ts_ms, features FROM ef_predictions"):
        try: f = json.loads(r['features']) if isinstance(r['features'], str) else r['features']
        except Exception: continue
        feats[r['candle_id']].append((r['ts_ms'], f))
    rows = []
    miss = 0
    for t in c.execute("SELECT candle_id, ts_ms, financial_pnl, financial_result, execution_mode "
                       "FROM trades WHERE kind='EF' AND forbidden=0 AND financial_result IN ('WIN','LOSS') ORDER BY ts_ms"):
        cands = feats.get(t['candle_id'])
        if not cands: miss += 1; continue
        f = min(cands, key=lambda x: abs((x[0] or 0) - (t['ts_ms'] or 0)))[1]   # nearest prediction to the trade
        vr, ch, ev = f.get('volume_ratio'), f.get('ef_chop'), f.get('ef_v11_ev')
        if vr is None or ch is None: miss += 1; continue
        rows.append(dict(ts=t['ts_ms'], pnl=float(t['financial_pnl']), win=int(t['financial_result']=='WIN'),
                         vr=float(vr), chop=float(ch), ev=(float(ev) if ev is not None else None), mode=t['execution_mode']))
    return rows, miss

def summ(rs):
    n = len(rs); w = sum(r['win'] for r in rs); p = sum(r['pnl'] for r in rs)
    return n, w, (100.0*w/n if n else 0.0), p

def keep(r, vlo=VLO, vhi=VHI, chop=CHOP):
    return vlo <= r['vr'] <= vhi and r['chop'] <= chop

def line(label, rs):
    n,w,acc,p = summ(rs)
    return f'{label:34s} n={n:5d} W={w:4d} acc={acc:5.1f}% pnl={p:+8.2f}'

allrows = []
print('=== per db: raw vs frozen filter ===')
for name in DBS:
    rs, miss = load(name)
    if not rs: print(f'{name}: no settled EF rows with features (missing={miss})'); continue
    filt = [r for r in rs if keep(r)]
    n,w,acc,p = summ(rs); fn,fw,facc,fp = summ(filt)
    print(f'{name:22s} raw n={n:4d} acc={acc:4.1f}% pnl={p:+7.2f} | filt n={fn:4d} ({100*fn/n:4.1f}%) acc={facc:4.1f}% pnl={fp:+7.2f} | delta={fp-p:+7.2f} | unmatched={miss}')
    for r in rs: r['db'] = name
    allrows += rs

print('\n=== pooled (correlated lanes, n inflated) ===')
filt = [r for r in allrows if keep(r)]
print(line('raw', allrows)); print(line('frozen filter', filt))

print('\n=== halves (chronological, per db, filtered set pnl and delta-vs-raw) ===')
for name in DBS:
    rs = [r for r in allrows if r['db']==name]
    if len(rs) < 120: continue
    h = len(rs)//2; a, b = rs[:h], rs[h:]
    fa, fb = [r for r in a if keep(r)], [r for r in b if keep(r)]
    print(f'{name:22s} H1 raw {summ(a)[3]:+7.2f} filt {summ(fa)[3]:+7.2f} (n={len(fa)}) | H2 raw {summ(b)[3]:+7.2f} filt {summ(fb)[3]:+7.2f} (n={len(fb)}) | delta H1 {summ(fa)[3]-summ(a)[3]:+6.2f} H2 {summ(fb)[3]-summ(b)[3]:+6.2f}')

print('\n=== sweep, one threshold at a time, others frozen (pooled) ===')
for lbl, vals, fn in [('vol_lo', [0.15,0.20,0.25,0.30,0.346,0.40,0.45,0.50,0.60], lambda v: lambda r: keep(r, vlo=v)),
                      ('vol_hi', [1.0,1.1,1.2,1.3,1.396,1.5,1.7,2.0,3.0], lambda v: lambda r: keep(r, vhi=v)),
                      ('chop_max',[0.35,0.40,0.45,0.50,0.539,0.60,0.70,0.80,1.0], lambda v: lambda r: keep(r, chop=v))]:
    out = []
    for v in vals:
        s = [r for r in allrows if fn(v)(r)]
        out.append(f'{v}:{summ(s)[3]:+.1f}/n{summ(s)[0]}')
    print(f'{lbl:9s} ' + '  '.join(out))

print('\n=== nulls at the SAME retention (pooled) ===')
ret = len(filt)/len(allrows)
k = len(filt)
with_ev = [r for r in allrows if r['ev'] is not None]
topev = sorted(with_ev, key=lambda r: -r['ev'])[:int(ret*len(with_ev))]
print(line(f'frozen filter ({100*ret:.1f}% kept)', filt))
print(line(f'top-EV null, same retention', topev))
random.seed(7); draws = []
for _ in range(500):
    s = random.sample(allrows, k); draws.append(summ(s)[3])
draws.sort()
print(f'random-retention null (500 draws, k={k}): median {st.median(draws):+.2f}  p5 {draws[25]:+.2f}  p95 {draws[475]:+.2f}  -> filter pnl {summ(filt)[3]:+.2f} sits at pct {100*sum(d<summ(filt)[3] for d in draws)/500:.0f}')

print('\n=== what the filter removes: volume_ratio bands (pooled raw) ===')
bands = [(0,0.346),(0.346,1.396),(1.396,99)]
for lo,hi in bands:
    s = [r for r in allrows if lo <= r['vr'] < hi]
    print(line(f'vr in [{lo},{hi})', s))
for lo,hi in [(0,0.539),(0.539,99)]:
    s = [r for r in allrows if lo <= r['chop'] < hi]
    print(line(f'chop in [{lo},{hi})', s))

print('\n=== cold-start confound: rows in first 2h of each db, and their volume_ratio ===')
for name in DBS:
    rs = [r for r in allrows if r['db']==name]
    if not rs: continue
    t0 = rs[0]['ts']; cold = [r for r in rs if r['ts'] - t0 < 2*3600*1000]
    if cold:
        vrs = [r['vr'] for r in cold]
        print(f'{name:22s} first-2h n={len(cold):3d} pnl={summ(cold)[3]:+6.2f} vr median={st.median(vrs):.2f} kept-by-filter={sum(keep(r) for r in cold)}')
