import sys, json, sqlite3, math, statistics as st
sys.path.insert(0,'/home/user/Django-final-project/analysis/h1')
from verify import Finding
SP='/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
live=sorted([r for r in json.load(open('/home/user/Django-final-project/learner/live_backup/tokyo_orders.json'))
             if r.get('filled') and r.get('fill_price') is not None and r.get('quoted_price') is not None],
            key=lambda r:r['ts_ms'])
ef=[r for r in live if r['kind']=='EF']; h=len(ef)//2
g=lambda s:[r['fill_price']-r['quoted_price'] for r in s]
mean=lambda x:sum(x)/len(x)
# engine labels only; the crossing number is an execution measurement, graded on the venue that paid
eng={}
for f in ('build11','predict_pnl','twin_c_thr1'):
    c=sqlite3.connect(f'{SP}/{f}.sqlite3')
    for cid,o,cl in c.execute('select candle_id,open,close from candles'):
        if o: eng[cid//1000]='UP' if cl>=o else 'DOWN'
tokyo={}
for r in live:
    if r.get('financial_result') in ('WIN','LOSS'):
        tokyo[r['candle_id']//1000]= r['direction'] if r['financial_result']=='WIN' else ('DOWN' if r['direction']=='UP' else 'UP')
F=Finding('Task 21b - Predict.fun crossing cost on real fills', per_fire=mean(g(ef)), n=len(ef))
F.grading(engine_candles_actual=eng, tokyo_financial_result=tokyo)
F.quote_age('same-instant', 0.0, 'Tokyo order book_age_ms, median 151 ms at the order')
F.sample({'EF fills': len(ef), 'all fills': len(live)})
F.halves(mean(g(ef[:h])), mean(g(ef[h:])))
print()
print('VERDICT', F.verdict())
