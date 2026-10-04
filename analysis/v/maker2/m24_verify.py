"""Run analysis/h1/verify.py's gate on M24 (frozen calm-FAV, 09-11..16 real asks)."""
import sys, json, glob, gzip, sqlite3, collections, random
import numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding
ROOT = sys.argv[1]
exec(open('/home/user/Django-final-project/analysis/v/maker2/m24_fav_oos.py').read().split("pnl = lambda")[0]
     .replace('sys.argv[1]', repr(ROOT + '/book1s.sqlite3')).replace('sys.argv[2]', repr(ROOT + '/hist/bin1s_0911_0926.json'))
     .replace('sys.argv[3]', repr(ROOT + '/hist/lean*.json.gz')))
pnl = lambda a, w: (1 if w else 0) - a - fee(a)
# grading: tape up_won vs Polymarket venues.outcome
ven = {}
for db in glob.glob(ROOT + '/*venues.sqlite3') + glob.glob(ROOT + '/*/venues.sqlite3'):
    try:
        for ep, o in sqlite3.connect(db).execute('select epoch, actual from outcome'): ven[int(ep)] = str(o).upper()
    except Exception as ex: print('skip', db, ex)
tape = {e: ('UP' if UP[e] == 1 else 'DOWN') for e, _, _ in T}
venl = {e: ('UP' if ven[e] in ('UP', '1', 'U') else 'DOWN') for e in tape if e in ven}
print('labels: tape', len(tape), 'venue overlap', len(venl), 'sample venue values', list(set(ven.values()))[:5])
f = Finding('M24 frozen calm-FAV taker, 09-11..16 real asks', per_fire=sum(pnl(a, w) for _, a, w in T) / len(T), n=len(T))
f.grading(tape={e: tape[e] for e in venl}, venue=venl)
f.sample(cells={'all': len(T)})
k = len(T) // 2
f.halves(first=np.mean([pnl(a, w) for _, a, w in T[:k]]), second=np.mean([pnl(a, w) for _, a, w in T[k:]]))
f.costs({h: np.mean([pnl(a + h, w) for _, a, w in T]) for h in (0.0, 0.01, 0.02)})
f.null(np.mean([pnl(a, w) for _, a, w in T]), np.mean([pnl(a, w) if random.random() < .5 else (pnl(ao, wo) if ao else 0) for a, w, ao, wo in NUL]), 'coin-flip side at its own ask')
f.verdict()
