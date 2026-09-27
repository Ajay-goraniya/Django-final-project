#!/usr/bin/env python3
"""ETH-only / SOL-only SHADOW EF (owner order 09-27 02:4x via V). Zurich shadow only.

SEPARATE PROCESS, SEPARATE DB, per coin. It never opens the engine's journal, never places a real order,
holds no credentials, and changes nothing about the BTC shadow. Public endpoints only.

The money path is the ENGINE'S, imported from the running module rather than re-derived:
`poly_core.order_plan` (tick-grid cap in Decimal, venue minimum, EV reference), `poly_core.walk_book`
(PaperBroker's fill: whatever the live ladder holds), `poly_core.fee`. That is deliberate - the three
09-12/13 errors in CLAUDE.md were all scratch re-implementations of exactly these.

Signal: arm (iv) of analysis/v/multi/ETH_SOL_EF.md, FROZEN on 14 days (09-13..09-26), no refitting here.
  line = mean of the 60 one-second Binance closes before the candle opens
  P    = close of the kline opening at ep+s-1
  sig  = stdev of the 900 one-second log-returns ending at that kline
  zt   = log(P/line) / (sig*sqrt(max(240-s,0)+20))
  p_up = sigmoid(b0 + b1*zt)
Rule: first second in 15..240 where max-side EV = p/(ask*(1+0.07*(1-ask))) - 1 >= 0.25 on the LIVE best
ask, one trade per candle, $5. The fill is taken from the live book AT THAT MOMENT, so depth and latency
are real rather than modelled.

Two EV references are recorded, not one. The rule above is V's spec, judged at the live ask. The engine's
own `order_plan` judges EV at ask + EV_REFERENCE_PAD (1 tick), which is strictly stricter; when it refuses
an order the rule wanted, that is recorded as `engine_ev_ref` instead of being hidden, because how often
the engine's own path would decline these trades is a fact the live decision will need.
"""
import asyncio, json, sqlite3, time, math, urllib.request, datetime as dt, argparse, sys, os, uuid
sys.path.insert(0, '/home/ubuntu/claude-work/repo/learner/v12_2')
import poly_core as PC

ap = argparse.ArgumentParser(); ap.add_argument('--coin', required=True, choices=('eth', 'sol'))
ap.add_argument('--stake', type=float, default=5.0); ap.add_argument('--theta', type=float, default=None)
ap.add_argument('--arm', default='frozen', choices=('frozen', 'platt'),
                help="frozen: the model-only logistic from ETH_SOL_EF.md arm (iv), theta 0.25, unchanged. "
                     "platt: a Platt fit on [logit(model p), logit(venue mid of that side)], theta 0.15.")
A = ap.parse_args()
COIN = A.coin; SYM = {'eth': 'ETHUSDT', 'sol': 'SOLUSDT'}[COIN]
ARM = A.arm
DB = f'/home/ubuntu/pm_multi/shadow_{COIN}.sqlite3' if ARM == 'frozen' else f'/home/ubuntu/pm_multi/shadow_{COIN}_platt.sqlite3'
FROZEN = {'eth': (-0.007173, 1.487533), 'sol': (-0.027489, 1.863596)}[COIN]
# Platt on [logit(model p), logit(venue mid of that side)], fitted on the 14-day panel and frozen here.
# Filled in by fit_platt_arm.py once the panel rebuild lands; None means the arm refuses to trade rather
# than trading an unfitted model.
# Fitted on the rebuilt 14-day panel (ETH 948,834 / SOL 451,625 taker prints, 4,031/4,032 markets, all
# with venue resolutions - matches ETH_SOL_EF.md's counts). Both slopes come out well BELOW 1, which is the
# whole correction: the frozen arm behaved as if the model p deserved weight 1.0 and the venue mid 0.
PLATT = {'eth': (0.0, 0.5573933489064047, 0.5151785355467882),
         'sol': (0.0, 0.7358928846160869, 0.30505139926240726)}[COIN]
if A.theta is None: A.theta = 0.25 if ARM == 'frozen' else 0.15
GAMMA = 'https://gamma-api.polymarket.com/events?slug=%s-updown-5m-%d'
BOOK = 'https://clob.polymarket.com/book?token_id=%s'
KL = 'https://data-api.binance.vision/api/v3/klines?symbol=%s&interval=1s&limit=1000'
KL_TAIL = 'https://data-api.binance.vision/api/v3/klines?symbol=%s&interval=1s&limit=30'
WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
UA = 'Mozilla/5.0 (X11; Linux x86_64) zurich-shadow/1.0'
SEC_LO, SEC_HI, RATE, EXP = 15, 240, 0.07, 1.0

DDL = [
    """CREATE TABLE IF NOT EXISTS orders(epoch INTEGER PRIMARY KEY, ts REAL, sec INTEGER, side TEXT,
       token TEXT, p_up REAL, p_side REAL, zt REAL, sig REAL, line REAL, spot REAL,
       ask REAL, ask_sz REAL, ev REAL, cap REAL, amount REAL, tick REAL,
       shares REAL, spent REAL, fees REAL, fill_price REAL, slip REAL,
       book_age_s REAL, decide_ms REAL, depth_at_cap REAL, engine_ok INTEGER, reason TEXT, spot_age_s REAL)""",
    """CREATE TABLE IF NOT EXISTS skips(epoch INTEGER, sec INTEGER, reason TEXT, detail TEXT,
       PRIMARY KEY(epoch, sec, reason))""",
    # post-fire drift on LIVE books: what the side's ask was 1 s and 2 s after we fired. On the frozen
    # arm's first 6 h the slippage at the fill was +0.00c, so the question is not what we paid but what
    # the book did next - that is the number that says whether the fire moment was any good.
    """CREATE TABLE IF NOT EXISTS drift(epoch INTEGER PRIMARY KEY, sec INTEGER, side TEXT,
       ask0 REAL, ask1 REAL, ask2 REAL, sz0 REAL, sz1 REAL, sz2 REAL)""",
    """CREATE TABLE IF NOT EXISTS results(epoch INTEGER PRIMARY KEY, actual TEXT, src TEXT, ts REAL,
       payout REAL, pnl REAL)""",
    """CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)""",
    """CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)""",
]
books, toks, terms, fired, kl = {}, {}, {}, set(), {}
errs = {}

def log(db, s):
    try: db.execute('INSERT OR REPLACE INTO health VALUES(?,?)', (time.time(), s[:400])); db.commit()
    except Exception: pass
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} [{COIN}/{ARM}] {s}', flush=True)

def gj(url, timeout=12):
    r = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(r, timeout=timeout) as f: return json.load(f)

def discover(ep):
    for e in gj(GAMMA % (COIN, ep)) or []:
        for m in e.get('markets', []):
            if m.get('slug') == f'{COIN}-updown-5m-{ep}':
                t = json.loads(m['clobTokenIds']); return str(t[0]), str(t[1])
    return None

async def gamma_loop(db):
    while True:
        try:
            now = int(time.time())
            for ep in (now // 300 * 300, now // 300 * 300 + 300):
                if ep in toks: continue
                r = await asyncio.to_thread(discover, ep)
                if r: toks[ep] = r; log(db, f'market {ep} up={r[0][:10]}.. dn={r[1][:10]}..')
        except Exception as e: errs['gamma'] = repr(e)[:110]
        await asyncio.sleep(20)

async def ws_loop(db):
    import websockets
    while True:
        want = sorted({t for ep, (u, d) in toks.items() if ep >= int(time.time()) // 300 * 300 - 300 for t in (u, d)})
        if not want: await asyncio.sleep(3); continue
        try:
            async with websockets.connect(WS, ping_interval=20, close_timeout=5, max_size=None) as w:
                await w.send(json.dumps({'assets_ids': want, 'type': 'market'}))
                log(db, f'ws subscribed {len(want)} tokens')
                end = time.time() + 300
                while time.time() < end:
                    raw = await asyncio.wait_for(w.recv(), timeout=30)
                    # The venue sends `book` as a LIST but price_change / last_trade_price as a BARE
                    # DICT (measured: 2,496 dict price_change vs 2 list book in 50 s). Iterating the
                    # dict walks its KEYS, so every delta was being dropped silently - the books were
                    # only as fresh as the REST resync. Normalise the payload before iterating.
                    _p = raw if isinstance(raw, (list, dict)) else json.loads(raw)
                    for e in (_p if isinstance(_p, list) else [_p]):
                        if not isinstance(e, dict): continue
                        k = e.get('event_type'); tk = str(e.get('asset_id') or '')
                        if k == 'book':
                            b = {s: {float(x['price']): float(x['size']) for x in e.get(s, [])
                                     if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s in ('asks', 'bids')}
                            b['snapshot'] = time.monotonic(); b['seq'] = books.get(tk, {}).get('seq', 0) + 1
                            books[tk] = b
                        elif k == 'price_change':
                            for c in e.get('price_changes', []):
                                b = books.get(str(c.get('asset_id')))
                                if not b or c.get('side') not in ('BUY', 'SELL'): continue
                                p, q = float(c['price']), float(c['size'])
                                if not (0 < p < 1 and q >= 0 and math.isfinite(q)): continue
                                sd = b['asks' if c['side'] == 'SELL' else 'bids']
                                if q: sd[p] = q
                                else: sd.pop(p, None)
                                b['seq'] = b.get('seq', 0) + 1
                        elif k == 'tick_size_change':
                            terms.pop(tk, None)
        except Exception as e:
            errs['ws'] = repr(e)[:110]; await asyncio.sleep(1)

async def resync_loop(db):
    """REST /book every 5 s for the live tokens. A price_change delta does not resync the book and the
    venue sends a full `book` only on subscribe, so without this the decision reads a book tens of
    seconds old - and a stale ask would manufacture the lead this test exists to measure. Two tokens
    every 5 s is negligible against the venue's limits; tick_size / min_order_size come along free,
    and the venue does move them intra-candle."""
    while True:
        await asyncio.sleep(5)
        try:
            now = int(time.time())
            for tk in sorted({t for ep, (u, d) in toks.items() if ep >= now // 300 * 300 for t in (u, d)}):
                try: d = await asyncio.to_thread(gj, BOOK % tk, 10)
                except Exception: continue
                b = {s: {float(x['price']): float(x['size']) for x in (d.get(s) or [])
                         if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s in ('asks', 'bids')}
                b['snapshot'] = time.monotonic(); b['seq'] = books.get(tk, {}).get('seq', 0) + 1
                books[tk] = b
                try: terms[tk] = (float(d['tick_size']), float(d['min_order_size']), RATE, EXP)
                except Exception: pass
        except Exception as e: errs['resync'] = repr(e)[:110]

async def kl_loop(db):
    first = True
    while True:
        try:
            url = (KL % SYM) if (first or len(kl) < 960) else (KL_TAIL % SYM)
            for x in await asyncio.to_thread(gj, url, 20):
                kl[int(x[0]) // 1000] = float(x[4])
            first = False
            if len(kl) > 6000:                       # keep the buffer bounded
                for t in sorted(kl)[:len(kl) - 4000]: kl.pop(t, None)
            errs.pop('kl', None)
        except Exception as e: errs['kl'] = repr(e)[:110]
        await asyncio.sleep(2)

MAX_SPOT_AGE = 3          # the newest CLOSED 1 s kline is always ~1 s old; 3 s allows one miss, no more
def close_at(t, limit=None):
    """Last close at or before t. `limit` caps the forward-fill; None means unbounded, which is what
    build_panel.py does for the history. The CURRENT price is fetched with limit=MAX_SPOT_AGE instead,
    because a stale spot would be the signal itself going stale - a different error from a gap in the
    volatility window."""
    lo = 0 if limit is None else 0
    hi = 3600 if limit is None else limit
    for k in range(lo, hi + 1):
        if (t - k) in kl: return kl[t - k]
    return None

def signal(ep, s):
    """Frozen arm (iv). Returns (p_up, zt, sig, line, spot) or None if the 960 s of history is incomplete."""
    line_px = [close_at(ep - 60 + i) for i in range(60)]
    if any(v is None for v in line_px): return None
    line = sum(line_px) / 60.0
    ipt = ep + s - 1
    if close_at(ipt, MAX_SPOT_AGE) is None: return None      # spot itself is stale: no signal, not a guess
    seq = [close_at(ipt - 900 + i) for i in range(901)]
    if any(v is None for v in seq) or line <= 0: return None
    lr = [math.log(seq[i + 1] / seq[i]) for i in range(900)]
    m = sum(lr) / 900.0
    v = sum(x * x for x in lr) / 900.0 - m * m
    sig = math.sqrt(max(v, 1e-12))
    spot = seq[-1]
    zt = math.log(spot / line) / (sig * math.sqrt(max(240 - s, 0) + 20))
    b0, b1 = FROZEN
    spot_age = next((k for k in range(MAX_SPOT_AGE + 1) if (ipt - k) in kl), None)
    return 1 / (1 + math.exp(-max(-30, min(30, b0 + b1 * zt)))), zt, sig, line, spot, spot_age

def quote_of(tk):
    b = books.get(tk)
    if not b: return None
    asks = sorted(b.get('asks') or {})
    bids = sorted(b.get('bids') or {}, reverse=True)
    if not asks or not bids: return None
    age = time.monotonic() - b.get('snapshot', time.monotonic())
    # order_plan reads age_ms and seq off the quote, so the dict has to be the shape Books.quote
    # returns - not a lookalike. Getting that wrong is how the first smoke run died.
    return dict(ask=asks[0], ask_sz=b['asks'][asks[0]], bid=bids[0],
                asks=[(p, b['asks'][p]) for p in asks], bids=[(p, b['bids'][p]) for p in bids],
                age=age, age_ms=age * 1000.0, seq=b.get('seq', 0))

ev_of = lambda p, a: p / (a * (1 + RATE * (1 - a))) - 1
lgt = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

async def decide_loop(db):
    last = 0
    while True:
        await asyncio.sleep(0.1)
        now = int(time.time())
        if now == last: continue
        last = now
        ep = now // 300 * 300; s = now - ep
        if not (SEC_LO <= s <= SEC_HI) or ep in fired or ep not in toks: continue
        t0 = time.monotonic()
        try: sg = signal(ep, s)
        except Exception as ex:
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)',
                       (ep, s, 'signal_error', f'{type(ex).__name__}: {str(ex)[:90]}')); db.commit(); continue
        if sg is None:
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)',
                       (ep, s, 'no_klines', f'buffer {len(kl)}')); db.commit(); continue
        p_up, zt, sig, line, spot, spot_age = sg
        up, dn = toks[ep]
        best = None
        qs = {t: quote_of(t) for t in (up, dn)}
        for tk, side, ps in ((up, 'UP', p_up), (dn, 'DOWN', 1 - p_up)):
            q = qs.get(tk)
            if not q: continue
            if ARM == 'platt':
                # venue mid of the UP side, exactly as build_panel/analyze define it: (ask_up + 1-ask_dn)/2.
                qu, qd = qs.get(up), qs.get(dn)
                if not (qu and qd): continue
                mid_up = (qu['ask'] + (1 - qd['ask'])) / 2.0
                m = mid_up if side == 'UP' else 1 - mid_up
                if PLATT is None:
                    db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)',
                               (ep, s, 'platt_unfitted', 'coefficients not yet frozen')); db.commit()
                    return
                c0, c1, c2 = PLATT
                z = c0 + c1 * lgt(ps) + c2 * lgt(m)
                ps = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = ev_of(ps, q['ask'])
            if best is None or e > best[0]: best = (e, tk, side, ps, q)
        if best is None:
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)', (ep, s, 'no_book', '')); db.commit(); continue
        ev, tk, side, p_side, q = best
        if ev < A.theta: continue
        tm = terms.get(tk)
        if not tm:
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)', (ep, s, 'no_terms', '')); db.commit(); continue
        d = dict(p=p_side, threshold=A.theta)
        engine_ok, plan, reason = 1, None, ''
        try:
            plan = PC.order_plan(q, tm, A.stake, d, pad=1, band=False, require_depth=False)
        except ValueError as ex:
            engine_ok = 0; reason = f'engine_ev_ref: {ex}'
        if plan is None:  # the rule wanted it, the engine's ask+1-tick reference refused: record, do not trade
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)', (ep, s, 'engine_ev_ref', reason[:120]))
            db.commit(); fired.add(ep)
            log(db, f'{ep} s{s} {side} ev {ev:+.3f} ask {q["ask"]:.2f} REFUSED by the engine reference')
            continue
        f = PC.walk_book(q, plan)
        dms = (time.monotonic() - t0) * 1000
        depth = sum(p * n for p, n in q['asks'] if p <= plan['cap'])
        if not f or not f['shares']:
            db.execute('INSERT OR IGNORE INTO skips VALUES(?,?,?,?)', (ep, s, 'fak_not_filled', '')); db.commit()
            fired.add(ep); continue
        db.execute('INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (ep, time.time(), s, side, tk, p_up, p_side, zt, sig, line, spot,
                    q['ask'], q['ask_sz'], ev, plan['cap'], plan['amount'], tm[0],
                    f['shares'], f['spent'], f['fees'], f['price'], (f['price'] - q['ask']),
                    q['age'], dms, depth, engine_ok, reason[:120], spot_age))
        db.commit(); fired.add(ep)
        asyncio.create_task(drift(db, ep, s, side, tk, q['ask'], q['ask_sz']))
        log(db, f'{ep} s{s} {side} p {p_side:.3f} ask {q["ask"]:.2f} ev {ev:+.3f} -> {f["shares"]:.1f} sh '
                f'@ {f["price"]:.4f} slip {100*(f["price"]-q["ask"]):+.2f}c age {q["age"]:.2f}s')

async def drift(db, ep, sec, side, tk, ask0, sz0):
    """Record the same side's best ask 1 s and 2 s after the fire."""
    out = [ask0, None, None]; szs = [sz0, None, None]
    for k in (1, 2):
        await asyncio.sleep(1.0)
        qq = quote_of(tk)
        if qq: out[k] = qq['ask']; szs[k] = qq['ask_sz']
    try:
        db.execute('INSERT OR REPLACE INTO drift VALUES(?,?,?,?,?,?,?,?,?)',
                   (ep, sec, side, out[0], out[1], out[2], szs[0], szs[1], szs[2])); db.commit()
    except Exception as e: errs['drift'] = repr(e)[:110]

def resolve(ep):
    for e in gj(GAMMA % (COIN, ep)) or []:
        for m in e.get('markets', []):
            if m.get('slug') != f'{COIN}-updown-5m-{ep}': continue
            op = m.get('outcomePrices')
            if not op: return None
            try: op = json.loads(op) if isinstance(op, str) else op
            except Exception: return None
            if len(op) < 2: return None
            a, b = float(op[0]), float(op[1])
            if max(a, b) < 0.99: return None
            return 'UP' if a > b else 'DOWN'
    return None

async def resolve_loop(db):
    while True:
        try:
            now = int(time.time())
            for (ep, side, sh, sp, fe) in db.execute(
                    "SELECT o.epoch,o.side,o.shares,o.spent,o.fees FROM orders o "
                    "LEFT JOIN results r ON r.epoch=o.epoch WHERE r.epoch IS NULL AND o.epoch<?",
                    (now - 420,)).fetchall():
                a = await asyncio.to_thread(resolve, ep)
                if not a: continue
                payout = sh if side == a else 0.0
                db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?)',
                           (ep, a, 'gamma.outcomePrices', time.time(), payout, payout - (sp + fe)))
                db.commit()
        except Exception as e: errs['resolve'] = repr(e)[:110]
        await asyncio.sleep(90)

async def status_loop(db):
    while True:
        await asyncio.sleep(600)
        n = db.execute('SELECT count(*) FROM orders').fetchone()[0]
        g = db.execute('SELECT count(*) FROM results').fetchone()[0]
        log(db, f'alive orders {n} graded {g} books {len(books)} size {os.path.getsize(DB)/1048576:.1f}MB errs {errs}')

async def main():
    db = sqlite3.connect(DB, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    for x in DDL: db.execute(x)
    db.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)', [
        ('coin', COIN), ('arm', ARM), ('stake', str(A.stake)), ('theta', str(A.theta)),
        ('platt', json.dumps(PLATT)),
        ('frozen', json.dumps(dict(b0=FROZEN[0], b_zt=FROZEN[1], source='ETH_SOL_EF.md arm (iv), 14 days 09-13..09-26, no refit'))),
        ('money_path', 'poly_core.order_plan + walk_book + fee, imported from learner/v12_2'),
        ('started', dt.datetime.now(dt.timezone.utc).isoformat())])
    db.commit()
    log(db, f'shadow start arm={ARM} stake ${A.stake} theta {A.theta} '
        f'frozen p=sigmoid({FROZEN[0]:+.6f}{FROZEN[1]:+.6f}*zt)' + (f' platt={PLATT}' if ARM=='platt' else ''))
    async def guard(fn):
        """A shadow that dies silently is worse than one that logs and carries on: restart each loop."""
        while True:
            try: await fn(db)
            except asyncio.CancelledError: raise
            except Exception as ex:
                log(db, f'LOOP {fn.__name__} died: {type(ex).__name__}: {str(ex)[:160]} - restarting')
                await asyncio.sleep(3)
    await asyncio.gather(*(guard(f) for f in (gamma_loop, ws_loop, resync_loop, kl_loop,
                                              decide_loop, resolve_loop, status_loop)))

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
