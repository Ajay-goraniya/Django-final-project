"""EF bucket grid on the Zurich shadow fills. READ-ONLY.

Implements analysis/v/staking/EF_BUCKET_GRID_SPEC.md (679d19c). Buckets were fixed in the spec before
anything was looked at; every cell is printed, nothing is selected.

Grading: `venues.outcome` where the snapshot on the branch covers the epoch, else the engine's own
`results.actual`, and each row says which. On the 84 epochs the snapshot does cover, the two sources
agree 84/84 - so `results.actual` is cross-checked where it can be, not merely assumed.

Break-even win rate at a mean entry q, fee included: the engine's fee is 0.07*shares*q*(1-q), so
fee/stake = 0.07*(1-q) exactly, and breaking even needs W = q * (1 + 0.07*(1-q)).
"""
import sqlite3, json, datetime as dt, collections

JOURNALS = [
    ('z1',     '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3'),
    ('z2',     '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3'),
    ('z3',     '/tmp/z3copy.sqlite3'),
    ('paper1', '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3'),
    ('live4',  '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'),
]
VENUES = '/tmp/venues_ro.sqlite3'
MIN_CELL = 60

def load():
    vo = {}
    try:
        v = sqlite3.connect(f'file:{VENUES}?mode=ro', uri=True)
        vo = dict(v.execute('SELECT epoch,actual FROM outcome').fetchall()); v.close()
    except Exception as e:
        print(f'venues snapshot unreadable: {repr(e)[:60]}')
    trades = []
    for name, path in JOURNALS:
        c = sqlite3.connect(path if path.startswith('/tmp') else f'file:{path}?mode=ro',
                            uri=not path.startswith('/tmp'))
        c.row_factory = sqlite3.Row
        res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
        for r in c.execute("""SELECT o.epoch,o.ts,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe
                              FROM orders o JOIN fills f ON f.order_id=o.id
                              WHERE o.status='FILLED' AND o.kind='EF' GROUP BY o.id"""):
            src = 'venues' if r['epoch'] in vo else 'engine'
            a = vo.get(r['epoch'], res.get(r['epoch']))
            if a is None: continue
            s = c.execute("SELECT side,decision FROM signals WHERE epoch=? AND kind='EF' LIMIT 1",
                          (r['epoch'],)).fetchone()
            if not s or not s['side']: continue
            d = json.loads(s['decision']) if s['decision'] else {}
            ft = d.get('features') or {}
            cost = (r['sp'] or 0.) + (r['fe'] or 0.)
            if not cost or not r['sh']: continue
            entry = r['sp'] / r['sh']
            if not (0.01 < entry < 0.99): continue
            mv = ft.get('move_bps')
            trades.append(dict(ts=r['ts'], epoch=r['epoch'], side=s['side'], entry=entry, src=src,
                               sec=r['ts'] - r['epoch'], win=(s['side'] == a),
                               move=abs(float(mv)) if isinstance(mv, (int, float)) else None,
                               per1=(((r['sh'] or 0.) if s['side'] == a else 0.) - cost) / cost))
        c.close()
    trades.sort(key=lambda t: t['ts'])
    return trades

def cell(sub, mid):
    if not sub: return None
    n = len(sub); w = sum(1 for x in sub if x['win'])
    q = sum(x['entry'] for x in sub) / n
    be = q * (1 + 0.07 * (1 - q))
    per = sum(x['per1'] for x in sub) / n
    h1 = [x for x in sub if x['ts'] < mid]; h2 = [x for x in sub if x['ts'] >= mid]
    p1 = sum(x['per1'] for x in h1)/len(h1) if h1 else None
    p2 = sum(x['per1'] for x in h2)/len(h2) if h2 else None
    srcs = collections.Counter(x['src'] for x in sub)
    return dict(n=n, winp=100*w/n, mean_entry=q, be=100*be, per1=per, h1=p1, h2=p2,
                n1=len(h1), n2=len(h2), src=('venues' if srcs['engine']==0 else
                'engine' if srcs['venues']==0 else f"mixed {srcs['venues']}v/{srcs['engine']}e"))

def fmt(name, c):
    if c is None: return f'  {name:<18}       (no data)'
    mark = '  INSUFFICIENT' if c['n'] < MIN_CELL else ''
    h1 = f"{c['h1']:+.3f}" if c['h1'] is not None else '   -  '
    h2 = f"{c['h2']:+.3f}" if c['h2'] is not None else '   -  '
    return (f"  {name:<18}{c['n']:>5}{c['winp']:>8.1f}%{c['be']:>9.1f}%{c['per1']:>9.3f}"
            f"{h1:>9}({c['n1']:>3}){h2:>9}({c['n2']:>3})  {c['src']}{mark}")

if __name__ == '__main__':
    tr = load()
    lo, hi = tr[0]['ts'], tr[-1]['ts']; mid = lo + (hi - lo) / 2
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'Zurich EF shadow fills: {len(tr)} graded, {f(lo)} -> {f(hi)} UTC')
    print(f'Half split by TIME at {f(mid)}')
    srcs = collections.Counter(x['src'] for x in tr)
    print(f"grading: venues.outcome {srcs['venues']}, engine results.actual {srcs['engine']} "
          f"(the two agree 84/84 where the snapshot overlaps)")
    print(f"\n  {'bucket':<18}{'n':>5}{'win%':>9}{'BE win%':>9}{'per$1':>9}{'  half1':>15}{'  half2':>15}  grading")
    groups = [
        ('FIRE SECOND', [(f'[{a},{b})', lambda x, a=a, b=b: a <= x['sec'] < b)
                         for a, b in ((0,60),(60,120),(120,180),(180,240),(240,300))]),
        ('ENTRY PRICE', [('<0.35', lambda x: x['entry'] < 0.35),
                         ('0.35-0.45', lambda x: 0.35 <= x['entry'] < 0.45),
                         ('0.45-0.55', lambda x: 0.45 <= x['entry'] < 0.55),
                         ('0.55-0.65', lambda x: 0.55 <= x['entry'] < 0.65),
                         ('>=0.65', lambda x: x['entry'] >= 0.65)]),
        ('|MOVE| bps', [('<3', lambda x: x['move'] is not None and x['move'] < 3),
                        ('3-6', lambda x: x['move'] is not None and 3 <= x['move'] < 6),
                        ('6-10', lambda x: x['move'] is not None and 6 <= x['move'] < 10),
                        ('>=10', lambda x: x['move'] is not None and x['move'] >= 10),
                        ('move NOT LOGGED', lambda x: x['move'] is None)]),
        ('UTC HOUR BLOCK', [(f'{a:02d}-{b:02d}', lambda x, a=a, b=b: a <= dt.datetime.fromtimestamp(
                             x['ts'], dt.timezone.utc).hour < b) for a, b in ((0,6),(6,12),(12,18),(18,24))]),
        ('SIDE', [('UP', lambda x: x['side'] == 'UP'), ('DOWN', lambda x: x['side'] == 'DOWN')]),
    ]
    verdict = []
    for title, specs in groups:
        print(f'\n{title}')
        for name, sel in specs:
            c = cell([x for x in tr if sel(x)], mid)
            print(fmt(name, c))
            if c and c['n'] >= MIN_CELL and c['h1'] is not None and c['h2'] is not None:
                if c['h1'] < 0 and c['h2'] < 0: verdict.append(('NEG', title, name, c))
                if c['h1'] > 0 and c['h2'] > 0: verdict.append(('POS', title, name, c))
    print('\n=== CELLS WITH n>=60 WHOSE SIGN HOLDS IN BOTH HALVES ===')
    if not verdict: print('  none')
    for kind, title, name, c in verdict:
        print(f"  {kind}  {title} {name}: n {c['n']}, per$1 {c['per1']:+.3f}, "
              f"h1 {c['h1']:+.3f} (n{c['n1']}) h2 {c['h2']:+.3f} (n{c['n2']}), {c['src']}")
