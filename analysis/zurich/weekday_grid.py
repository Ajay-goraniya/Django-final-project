"""MAIN / REVERSAL / EF by UTC weekday and weekend-vs-weekday, across every Zurich shadow journal.

Buckets fixed before looking: Mon..Sun individually, then Sat+Sun vs Mon-Fri. Full grid printed, every
cell marked, no cell selected. Read-only: zurich_3 is byte-copied first because it carries a stale
-journal and refuses a read-only open.
"""
import sqlite3, json, datetime as dt, collections, sys

JOURNALS = [
    ('live_zurich',  '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3'),
    ('live_zurich_2','/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3'),
    ('live_zurich_3','/tmp/z3copy.sqlite3'),                      # byte copy, original untouched
    ('zurich_live4', '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'),
    ('zurich_paper1','/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3'),
]
DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
MIN_CELL = 60
rows = []
for name, path in JOURNALS:
    try:
        c = sqlite3.connect(f'file:{path}?mode=ro', uri=True) if not path.startswith('/tmp') else sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
        for r in c.execute("""SELECT o.epoch,o.ts,o.kind,o.plan,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe
                              FROM orders o JOIN fills f ON f.order_id=o.id
                              WHERE o.status='FILLED' AND o.kind IN ('MAIN','REVERSAL','EF') GROUP BY o.id"""):
            a = res.get(r['epoch'])
            if a is None: continue
            side = (json.loads(r['plan']) or {}).get('side') or (c.execute(
                "SELECT side FROM signals WHERE epoch=? AND kind=? LIMIT 1", (r['epoch'], r['kind'])).fetchone() or [None])[0]
            if side is None: continue
            d = dt.datetime.fromtimestamp(r['epoch'], dt.timezone.utc)
            cost = (r['sp'] or 0.) + (r['fe'] or 0.); win = (side == a)
            rows.append(dict(journal=name, kind=r['kind'], day=d.strftime('%a'), date=d.strftime('%Y-%m-%d'),
                             win=win, pnl=((r['sh'] or 0.) if win else 0.) - cost, cost=cost))
        c.close()
    except Exception as e:
        print(f'  {name}: UNREADABLE ({repr(e)[:60]})')

def cell(sub):
    if not sub: return '     -        -         -   (no data)'
    n = len(sub); w = sum(1 for x in sub if x['win'])
    cost = sum(x['cost'] for x in sub); pnl = sum(x['pnl'] for x in sub)
    per = pnl / cost if cost else float('nan')
    mark = '  INSUFFICIENT' if n < MIN_CELL else ''
    return f'{n:6d} {w/n*100:7.1f}% {per:+9.3f}{mark}'

print('Zurich shadow journals, all lanes, graded on results.actual (see the note in the file header)')
print(f'total graded rows: {len(rows)}\n')
print(f"{'bucket':<22}{'MAIN':>34}{'REVERSAL':>34}{'EF':>34}")
print(f"{'':22}" + ''.join(f"{'n    right%     per$1':>34}" for _ in range(3)))
for day in DAYS + ['--', 'WEEKEND Sat+Sun', 'WEEKDAY Mon-Fri']:
    if day == '--': print('-' * 124); continue
    if day.startswith('WEEKEND'): sel = lambda x: x['day'] in ('Sat','Sun')
    elif day.startswith('WEEKDAY'): sel = lambda x: x['day'] in ('Mon','Tue','Wed','Thu','Fri')
    else: sel = lambda x, d=day: x['day'] == d
    line = f'{day:<22}'
    for k in ('MAIN','REVERSAL','EF'):
        line += f"{cell([x for x in rows if x['kind']==k and sel(x)]):>34}"
    print(line)

print('\nWEEKEND DATES PRESENT (each Sat/Sun date that has any graded row):')
wd = collections.Counter(x['date'] for x in rows if x['day'] in ('Sat','Sun'))
if not wd: print('  none')
for d in sorted(wd):
    day = dt.datetime.strptime(d, '%Y-%m-%d').strftime('%a')
    print(f'  {d} {day}: {wd[d]} graded rows')
    for k in ('MAIN','REVERSAL','EF'):
        print(f'      {k:<9}{cell([x for x in rows if x["kind"]==k and x["date"]==d])}')
print(f'\nDISTINCT CALENDAR WEEKENDS (a Sat and its Sun both present): ', end='')
sats = {d for d in wd if dt.datetime.strptime(d,'%Y-%m-%d').strftime('%a')=='Sat'}
pairs = [s for s in sats if (dt.datetime.strptime(s,'%Y-%m-%d')+dt.timedelta(days=1)).strftime('%Y-%m-%d') in wd]
print(len(pairs), pairs if pairs else '(none)')
