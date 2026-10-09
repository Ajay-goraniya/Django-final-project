#!/usr/bin/env python3
"""Zurich's OWN gamma outcome mirror (V authorised 09-28, research box).

WHY. /tmp/poly/btc5*.sqlite3 froze at 09-28 01:42 and the forward shadow, which grades every arm off
those files, scored nothing after the 01:30 candle. Zurich does not own that collector, so rather than
write into another session's database this keeps a separate mirror that ef3_shadow.py reads ALONGSIDE
them. Same table shape (mkt), so it is a drop-in extra source and the frozen files stay untouched.

The outcome derivation is COPIED from V's analysis/v/multi/fetch_poly.py add_event(), deliberately
character for character: closed, both outcomePrices in {'0','1'}, and the two differ. If that rule ever
changes, these labels must change with it - so it is not reimplemented from the API docs, it is copied
from the collector whose labels every earlier result was graded on.

Outcomes ONLY. V's script also pulls every taker trade per market, which is a large download this does
not need. usage: gamma_outcomes.py [start_epoch] [end_epoch]
"""
import json, sqlite3, sys, time, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

DB    = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
PEERS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
UA    = {'User-Agent': 'curl/8.5.0'}
ASSET = 'btc'
now   = int(time.time()) // 300 * 300
T0    = int(sys.argv[1]) if len(sys.argv) > 1 else now - 3 * 86400
T1    = int(sys.argv[2]) if len(sys.argv) > 2 else now


def get(u, tries=5):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
        except Exception:
            time.sleep(1.2 * (i + 1))
    return None


db = sqlite3.connect(DB, check_same_thread=False)
db.execute('create table if not exists mkt(asset, epoch integer, cond, tok_up, tok_dn, outcome,'
           ' primary key(asset, epoch))')


def add_event(e):
    if not e.get('markets'): return None
    m = e['markets'][0]
    try:
        ep = int(e['slug'].rsplit('-', 1)[1])
    except Exception:
        return None
    if not (T0 <= ep <= T1): return ep
    toks = json.loads(m['clobTokenIds']); outs = json.loads(m['outcomes'])
    px = json.loads(m.get('outcomePrices') or '[]')
    iu = outs.index('Up'); idn = 1 - iu
    oc = None
    if m.get('closed') and px and px[iu] in ('1', '0') and px[idn] in ('1', '0') and px[iu] != px[idn]:
        oc = 'UP' if px[iu] == '1' else 'DOWN'
    db.execute('insert or replace into mkt values(?,?,?,?,?,?)',
               (ASSET, ep, m['conditionId'], toks[iu], toks[idn], oc))
    return ep


have = {r[0] for r in db.execute('select epoch from mkt where asset=? and outcome is not null', (ASSET,))}
want = sorted(set(range(T0, T1 + 1, 300)) - have)
print(f'range {dt.datetime.fromtimestamp(T0, dt.UTC):%m-%d %H:%M} .. '
      f'{dt.datetime.fromtimestamp(T1, dt.UTC):%m-%d %H:%M}  already have {len(have)}  fetching {len(want)}')

off = 0
while want and off < 2000:
    d = get(f'https://gamma-api.polymarket.com/events?series_slug={ASSET}-up-or-down-5m'
            f'&closed=true&limit=100&offset={off}&order=startTime&ascending=false', tries=2)
    if not d: break
    eps = [x for x in (add_event(e) for e in d) if x]
    want = [w for w in want if w not in set(eps)]
    off += 100
    if eps and min(eps) < T0: break
    time.sleep(0.2)
db.commit()

if want:
    def one(ep):
        d = get(f'https://gamma-api.polymarket.com/events?slug={ASSET}-updown-5m-{ep}')
        if d: add_event(d[0])
        time.sleep(0.05)
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, want))
    db.commit()

mine = {int(e): o for e, o in db.execute(
    "select epoch, outcome from mkt where asset=? and outcome is not null", (ASSET,))}
print(f'mirror now holds {len(mine)} outcomes')

# CROSS-CHECK against the frozen peers before anything grades on this. A new label source that
# disagrees with the one every earlier result was graded on is a silent regrade, not a fix.
peer = {}
for p in PEERS:
    try:
        c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        peer.update({int(e): o for e, o in c.execute(
            "select epoch, outcome from mkt where asset='btc' and outcome is not null")})
    except Exception:
        pass
ov = [e for e in mine if e in peer]
dis = [e for e in ov if mine[e] != peer[e]]
print(f'cross-check vs /tmp/poly: overlap {len(ov)}, disagree {len(dis)}'
      + (f'  *** {dis[:5]} ***' if dis else '  (identical)'))
sys.exit(1 if dis else 0)
