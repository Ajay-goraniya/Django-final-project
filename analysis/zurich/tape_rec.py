#!/usr/bin/env python3
"""Public-tape recorder for the btc5 markets - the missing input for arm PFAV.

WHY THIS EXISTS. PFAV fills off the PUBLIC TAPE: "first print after our post at price <= our bid, with
>= N shares in that second". Zurich had no live tape. The only `tr` tables on the box are in /tmp/poly,
they are another session's, they stopped on 09-27/09-28, and they carry no maker/taker split - so they
cannot answer "was this a MAKER fill", which is the whole premise of a passive arm.

MAKER IS DERIVED, NOT REPORTED. data-api has no maker flag: takerOnly=false returns ALL prints and
takerOnly=true returns the taker subset, so maker = all MINUS taker, keyed on the fields that identify
one print (tx hash, asset, wallet, size, price). That is exactly how analysis/v/maker2/passive_fav.py
does it, and it is copied rather than reinvented so PFAV's fills match V's study.

TIMESTAMPS: data-api ts runs ~2.2 s ahead of candle seconds (LAG in passive_fav.py). This module stores
the RAW ts; the lag is applied by the consumer, so if V ever re-measures it nothing here has to change.

READ-ONLY on everything else. Writes only its own database.
"""
import json, sqlite3, sys, time, urllib.request, datetime as dt

DB    = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
UA    = {'User-Agent': 'curl/8.5.0'}
BACK  = 3          # candles back to (re)poll - late prints keep landing after a candle closes
MAXOFF = 2000


def g(u, tries=4):
    for a in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25))
        except Exception:
            if a == tries - 1: return None
            time.sleep(1.5 * (a + 1))


def pull(cond):
    """(all_rows, taker_keys). Paged; data-api caps out, so MAXOFF bounds a runaway."""
    out = {}
    tk = set()
    for taker in ('false', 'true'):
        off = 0
        while off < MAXOFF:
            d = g(f'https://data-api.polymarket.com/trades?market={cond}&limit=500&offset={off}&takerOnly={taker}')
            if not d: break
            for t in d:
                k = (t.get('transactionHash'), t.get('asset'), t.get('proxyWallet'),
                     str(t.get('size')), str(t.get('price')))
                if taker == 'true': tk.add(k)
                else: out[k] = t
            off += len(d)
            if len(d) < 500: break
            time.sleep(0.05)
    return out, tk


db = sqlite3.connect(DB)
db.execute('''CREATE TABLE IF NOT EXISTS tape(
  epoch INT, ts INT, asset TEXT, wallet TEXT, side TEXT, price REAL, size REAL,
  is_taker INT, txh TEXT, PRIMARY KEY(txh, asset, wallet, size, price))''')
db.execute('CREATE INDEX IF NOT EXISTS tape_ep ON tape(epoch)')
db.execute('CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)')

gm = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)
now = int(time.time()); cur = (now // 300) * 300
eps = [cur - 300 * i for i in range(BACK + 1)]
n_new = 0
for ep in eps:
    r = gm.execute("SELECT cond FROM mkt WHERE asset='btc' AND epoch=?", (ep,)).fetchone()
    if not r or not r[0]: continue
    allr, tk = pull(r[0])
    if not allr: continue
    rows = []
    for k, t in allr.items():
        rows.append((ep, int(t['timestamp']), t.get('asset'), t.get('proxyWallet'), t.get('side'),
                     float(t.get('price')), float(t.get('size')), 1 if k in tk else 0,
                     t.get('transactionHash')))
    before = db.execute('SELECT count(*) FROM tape').fetchone()[0]
    db.executemany('INSERT OR REPLACE INTO tape VALUES(?,?,?,?,?,?,?,?,?)', rows)
    db.commit()
    n_new += db.execute('SELECT count(*) FROM tape').fetchone()[0] - before
db.execute('INSERT OR REPLACE INTO health VALUES(?,?)',
           (time.time(), f'{n_new} new rows over {len(eps)} candles'))
db.commit()
tot, mk = db.execute('SELECT count(*), sum(1-is_taker) FROM tape').fetchone()
print(f'{dt.datetime.now(dt.UTC):%H:%M:%S} tape: +{n_new} new, {tot:,} total, {mk or 0:,} maker rows')
