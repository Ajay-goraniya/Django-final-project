"""Backtest doc 2's adaptive-EV penalty, verbatim, on every row that carries the v10 features
(LIVE 158 + PAPER 3,044 from all_trades.csv). No 3-second lookback exists in the journal, so this
is the penalty_now form; the doc's 3s rule can only make it veto MORE, never less.

Also: are the doc's normalising constants just this sample's own statistics? (in-sample check)
"""
import csv, math, statistics as st
from collections import defaultdict

rows = []
with open('/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/live_trades_export/all_trades.csv') as fh:
    for r in csv.DictReader(fh):
        if r['kind'] != 'EF' or r['data_class'] not in ('LIVE','PAPER'): continue
        try:
            f = {k: float(r['f_'+k]) for k in ('rv60','ret15','ret60','spot_imb60')}
            ev = float(r['ev']); thr = float(r['threshold']) if r['threshold'] else None
            pnl = float(r['pnl_local']); win = int(r['win'])
        except (ValueError, TypeError): continue
        rows.append(dict(cls=r['data_class'], db=r['source_db'], ev=ev, thr=thr, pnl=pnl, win=win, spent=float(r['spent'] or 0), **f))

print(f'rows with full features + ev + outcome: {len(rows)}  LIVE={sum(r["cls"]=="LIVE" for r in rows)} PAPER={sum(r["cls"]=="PAPER" for r in rows)}')

# ---- in-sample check on the constants ----
print('\n=== doc constants vs this sample\'s statistics ===')
for k, c in [('rv60',0.327249),('ret15',2.303539),('ret60',4.757087)]:
    a = [abs(r[k]) for r in rows]
    print(f'{k:6s} doc normaliser {c:.6f} | sample mean|x| {st.mean(a):.6f} std {st.pstdev(a):.6f} median {st.median(a):.6f}')
fw = [abs(r['ret60'])/(abs(r['spot_imb60'])+0.10) for r in rows]
ac = [math.sqrt((r['rv60']/0.327249)**2 + (abs(r['ret15'])/2.303539)**2 + (abs(r['ret60'])/4.757087)**2) for r in rows]
print(f'flow_weakness  doc activation 0.9113 scale 5.7734 | sample median {st.median(fw):.4f} mean {st.mean(fw):.4f} std {st.pstdev(fw):.4f}')
print(f'activity_stress doc activation 1.0450 scale 1.6664 | sample median {st.median(ac):.4f} mean {st.mean(ac):.4f} std {st.pstdev(ac):.4f}')

# ---- the penalty, verbatim ----
def penalty(r):
    fw = abs(r['ret60'])/(abs(r['spot_imb60'])+0.10)
    ac = math.sqrt((r['rv60']/0.327249)**2 + (abs(r['ret15'])/2.303539)**2 + (abs(r['ret60'])/4.757087)**2)
    return 0.08*max((fw-0.9113)/5.7734, 0) + 0.08*max((ac-1.0450)/1.6664, 0)

def summ(rs):
    n=len(rs); w=sum(r['win'] for r in rs); p=sum(r['pnl'] for r in rs); s=sum(r['spent'] for r in rs)
    return n, w, (100*w/n if n else 0), p, (p/s if s else 0)

def report(label, rs):
    # threshold: use the row's own recorded threshold; fall back 0.25 (the regime default)
    kept  = [r for r in rs if (r['ev'] - penalty(r)) >= (r['thr'] if r['thr'] is not None else 0.25)]
    veto  = [r for r in rs if r not in kept]
    for tag, s in [('all fires', rs), ('KEPT by adaptive EV', kept), ('VETOED by adaptive EV', veto)]:
        n,w,acc,p,pd = summ(s)
        print(f'  {label:6s} {tag:22s} n={n:5d} W={w:4d} acc={acc:5.1f}% pnl={p:+9.2f} per$1={pd:+.4f}')
    pens = [penalty(r) for r in rs]
    print(f'  {label:6s} penalty>0 on {100*sum(p>0 for p in pens)/len(pens):.1f}% of fires; median penalty {st.median(pens):.4f}, p90 {sorted(pens)[int(.9*len(pens))]:.4f}')

print('\n=== doc 2 adaptive-EV veto, replayed at fire time ===')
report('LIVE',  [r for r in rows if r['cls']=='LIVE'])
report('PAPER', [r for r in rows if r['cls']=='PAPER'])

print('\n=== what it targets: HIGH-vol / large-move fires, pnl by rv60 tercile (PAPER, the readable sample) ===')
paper = sorted([r for r in rows if r['cls']=='PAPER'], key=lambda r: r['rv60'])
t = len(paper)//3
for lbl, s in [('rv60 LOW', paper[:t]), ('rv60 MID', paper[t:2*t]), ('rv60 HIGH', paper[2*t:])]:
    n,w,acc,p,pd = summ(s); v = sum(1 for r in s if (r['ev']-penalty(r)) < (r['thr'] or 0.25))
    print(f'  {lbl:9s} n={n} acc={acc:.1f}% per$1={pd:+.4f}  vetoed-by-doc2={v} ({100*v/n:.0f}%)')
