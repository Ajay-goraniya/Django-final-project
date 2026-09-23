"""Run the standing verify gates on the Zurich raw_v10_live25 shadow arm now that it has cleared n=60."""
import sqlite3, json, sys
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding

DB='/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
WINDOWS=[(1790127365.0,1790170418.0),(1790172444.0,float('inf'))]
in_arm=lambda t: any(a<=t<b for a,b in WINDOWS)
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True); c.row_factory=sqlite3.Row
res={r['epoch']:r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
rows=[]
for r in c.execute("""SELECT o.epoch,o.ts,o.plan,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe FROM orders o
                      JOIN fills f ON f.order_id=o.id WHERE o.kind='EF' AND o.status='FILLED'
                      GROUP BY o.id ORDER BY o.ts"""):
    if not in_arm(r['ts']): continue
    a=res.get(r['epoch'])
    if a is None: continue
    pl=json.loads(r['plan']) or {}
    side=pl.get('side') or (c.execute("SELECT side FROM signals WHERE epoch=? AND kind='EF' LIMIT 1",(r['epoch'],)).fetchone() or [None])[0]
    if side is None: continue
    price=pl.get('quote') or (r['sp']/r['sh'] if r['sh'] else None)
    cost=(r['sp'] or 0)+(r['fe'] or 0)
    rows.append(dict(epoch=r['epoch'],side=side,actual=a,price=float(price),shares=r['sh'],cost=cost,
                     win=(side==a),pnl=((r['sh'] or 0) if side==a else 0)-cost))
n=len(rows); spent=sum(x['cost'] for x in rows); pnl=sum(x['pnl'] for x in rows)
per=pnl/spent
print(f'ARM raw_v10_live25 stitched: n {n}, right {sum(x["win"] for x in rows)} ({sum(x["win"] for x in rows)/n*100:.1f}%), per$1 {per:+.4f}, pnl {pnl:+.2f}')
f=Finding('Zurich raw_v10_live25 shadow arm', per_fire=per, n=n)

# 1. grading provenance: results.actual vs the venues outcome table if we have it
alt={}
try:
    v=sqlite3.connect('file:/tmp/venues_ro.sqlite3?mode=ro',uri=True)
    for e,o in v.execute('SELECT epoch,actual FROM outcome'): alt[e]=o   # the column is `actual`, not `outcome`
except Exception as ex: print('venues snapshot unreadable:', repr(ex)[:80])
eng={x['epoch']:x['actual'] for x in rows}
overlap=sorted(set(eng) & set(alt))
print(f'grading cross-check: venues snapshot has {len(alt)} epochs, overlap with this arm = {len(overlap)}')
if overlap:
    f.grading(results_actual=eng, venues_outcome={k:alt[k] for k in overlap})
else:
    print('  -> venues.sqlite3.gz on the branch is stale (09-08..09-16); this arm is 09-23, ZERO overlap.')
    print('  -> the grading gate CANNOT be run here. It needs a fresh venues snapshot covering 09-23.')
    f.grading(results_actual=eng)

# 2. sample
f.sample(cells={'raw arm': n})
# 3. halves, chronological
h=n//2
first=sum(x['pnl'] for x in rows[:h])/sum(x['cost'] for x in rows[:h])
second=sum(x['pnl'] for x in rows[h:])/sum(x['cost'] for x in rows[h:])
f.halves(first=first, second=second)
# 4. permutation: shuffle the SIDE the model picked, keep outcome<->price paired
# verify.permutation is numeric (it calls np.isnan on pred), so encode the side UP=1.0 / DOWN=0.0
enc=lambda v: 1.0 if v=='UP' else 0.0
y=[enc(x['actual']) for x in rows]; pred=[enc(x['side']) for x in rows]; price=[x['price'] for x in rows]
def pnl_fn(y_, pred_, price_):
    tot=cost=0.
    for a,s,p in zip(y_,pred_,price_):
        sh=5.0/p; fee=0.07*sh*p*(1-p)
        cost+=5.0+fee; tot+=(sh if s==a else 0)
    return (tot-cost)/cost
f.permutation(y, pred, price, pnl_fn)
# 5. costs: haircut the ask
def per_at(h_):
    tot=cost=0.
    for x in rows:
        p=min(0.99,x['price']+h_); sh=5.0/p; fee=0.07*sh*p*(1-p)
        cost+=5.0+fee; tot+=(sh if x['win'] else 0)
    return (tot-cost)/cost
f.costs({0.0:per_at(0.0), 0.02:per_at(0.02), 0.05:per_at(0.05)})
# 6. null: always buy the cheaper side at the same moments
tot=cost=0.
for x in rows:
    p=x['price'] if x['price']<0.5 else 1-x['price']
    cheap_side=x['side'] if x['price']<0.5 else ('UP' if x['side']=='DOWN' else 'DOWN')
    sh=5.0/p; fee=0.07*sh*p*(1-p); cost+=5.0+fee; tot+=(sh if cheap_side==x['actual'] else 0)
f.null(per, (tot-cost)/cost, null_name='buy the cheap side at the same moments')
print(); ok=f.verdict(); print('\nVERDICT:', 'holds' if ok else 'DOES NOT HOLD')
