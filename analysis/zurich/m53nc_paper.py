#!/usr/bin/env python3
"""M53-NC: not-calm-only follow-the-taker with LIVE-FILL REALISM. PAPER ONLY - no key is loaded and
no CLOB write endpoint is ever called. Frozen by PREREG_M53 amendment 3224c11.

Differences from the legacy M53 arm (which keeps running untouched):
  * NOT-CALM only, by the frozen FAV definition called from ef3_shadow (vol >= FAV_CUT_LOW 0.304,
    needing >=240 of the 300 s before the open). Insufficient data => SKIP and log, never a fallback.
  * Fires at websocket receipt + a 250 ms order round-trip and snapshots the book AT THAT MOMENT,
    not at print+3 s. 250 ms is the owner's conservative figure: this box has NO measured London
    order-placement latency (M19 measured a READ round trip, p50 44 ms; the probe could only bound
    the write path at "under ~1 s").
  * $5 FAK, limit = the ask we SAW at receipt + 0.01 capped 0.99, walked against the book as it
    stands 250 ms later. Partial fills count at the dollars actually spent; under 5 shares = no
    trade. Fee 0.07*p*(1-p) per share at EACH level's own price.
  * Bankroll $50, $5 a stake, skip the candle when cash < $5.
Depth comes from a live book maintained off the same socket (`book` snapshots + `price_change`
deltas), because the 1 Hz books table is level-1 only and cannot be walked.
"""
import asyncio, io, json, contextlib, socket, sqlite3, sys, time, datetime as dt, websockets

DB   = '/home/ubuntu/m53/m53.sqlite3'
BOOK = '/home/ubuntu/pm_multi/multi_market.sqlite3'
WS   = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
STAKE, FEE, START_CASH = 5.0, 0.07, 50.0
SEC0, SEC1, LO, HI = 60, 180, 0.60, 0.80
RTT = 0.250                      # order round-trip, conservative; see the prereg amendment
MIN_SHARES = 5.0
START = int(open('/home/ubuntu/m53/nc_start_epoch').read().strip())
fee_sh = lambda p: FEE * p * (1 - p)

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
with contextlib.redirect_stdout(io.StringIO()):
    import ef3_shadow as S
    S.ALL52, S.STRICT = None, None

# BUG FIX 16:2x: the 1 s series MUST be reloaded as the process runs. Loading it once at start meant
# every candle after startup had no data for its own [open-300, open) window, so _vol_bn returned
# None and the arm logged skipped-no-data - it lost the 16:15 and 16:20 candles (real vols 0.3516
# and 0.5651, both NOT-CALM and both tradeable). A reload costs 2.5 s, which is nothing against the
# 60 s of slack before the window opens. The frozen DEFINITION is untouched; it was being starved of
# data, not redefined.
_BN = {'t': 0.0, 'v': None}
def bn():
    if time.time() - _BN['t'] > 120:
        with contextlib.redirect_stdout(io.StringIO()):
            _BN['v'] = S._bn_1s()
        _BN['t'] = time.time()
    return _BN['v']

DDL = """CREATE TABLE IF NOT EXISTS nc(
 epoch INT PRIMARY KEY, print_ts REAL, print_sec INT, print_px REAL, side TEXT,
 detect_ts REAL, latency_ms INT, vol REAL, seen_ask REAL, lim REAL,
 levels INT, shares REAL, spent REAL, vwap REAL, slip REAL,
 status TEXT, cash_before REAL, cash_after REAL, win INT, pnl REAL, graded_ts INT)"""

def db():
    d = sqlite3.connect(DB, timeout=30); d.execute('PRAGMA journal_mode=WAL'); d.execute(DDL); return d

def toks(ep):
    return sqlite3.connect(f'file:{BOOK}?mode=ro', uri=True).execute(
        "select token_up,token_dn from markets where market='btc5' and epoch=?", (ep,)).fetchone()

def cash_now(d):
    r = d.execute('select cash_after from nc where cash_after is not null order by epoch desc limit 1').fetchone()
    return r[0] if r else START_CASH

def walk(asks, lim, budget):
    """FAK walk, cheapest level first, levels at or below the limit. Returns (shares, spent, levels).
    Budget is dollars INCLUDING the per-share fee charged at each level's own price."""
    sh = sp = 0.0; lv = 0
    for px in sorted(asks):
        if px > lim + 1e-9 or px >= 0.99: break
        avail = asks[px]
        if avail <= 0: continue
        unit = px + fee_sh(px)                      # cost of one share at this level, fee included
        want = (budget - sp) / unit
        if want <= 1e-9: break
        take = min(avail, want)
        sh += take; sp += take * unit; lv += 1
        if sp >= budget - 1e-9: break
    return sh, sp, lv

def record(d, ep, pts, px, sd, now, vol, seen, asks):
    cash = cash_now(d)
    row = dict(epoch=ep, print_ts=pts, print_sec=int(pts-ep), print_px=px, side=sd,
               detect_ts=now, latency_ms=int((now-pts)*1000), vol=vol, seen_ask=seen,
               lim=None, levels=0, shares=0.0, spent=0.0, vwap=None, slip=None,
               status=None, cash_before=cash, cash_after=cash)
    if cash < STAKE:
        row['status'] = 'skipped-cash'
    elif seen is None or not asks:
        row['status'] = 'missed-nobook'
    else:
        lim = min(round(seen + 0.01, 4), 0.99)
        sh, sp, lv = walk(asks, lim, STAKE)
        row['lim'] = lim
        if sh < MIN_SHARES:
            row['status'] = 'missed-size'; row['shares'] = sh; row['levels'] = lv
        else:
            vwap = sp / sh
            row.update(levels=lv, shares=sh, spent=sp, vwap=vwap, slip=vwap-seen,
                       status=('partial' if sp < STAKE - 0.01 else 'full'),
                       cash_after=cash - sp)
    d.execute('INSERT OR REPLACE INTO nc(epoch,print_ts,print_sec,print_px,side,detect_ts,latency_ms,'
              'vol,seen_ask,lim,levels,shares,spent,vwap,slip,status,cash_before,cash_after) '
              'VALUES(:epoch,:print_ts,:print_sec,:print_px,:side,:detect_ts,:latency_ms,:vol,'
              ':seen_ask,:lim,:levels,:shares,:spent,:vwap,:slip,:status,:cash_before,:cash_after)', row)
    d.commit()
    print(f'{ep} {sd} print {px:.3f} sec {row["print_sec"]} lat {row["latency_ms"]}ms vol {vol:.3f} '
          f'seen {seen} lim {row["lim"]} -> {row["status"]} shares {row["shares"]:.2f} '
          f'spent ${row["spent"]:.2f} slip {"" if row["slip"] is None else format(row["slip"],"+.4f")}',
          flush=True)

def skip(d, ep, why, vol=None):
    d.execute('INSERT OR REPLACE INTO nc(epoch,status,vol,cash_before,cash_after) VALUES(?,?,?,?,?)',
              (ep, why, vol, cash_now(d), cash_now(d))); d.commit()
    print(f'{ep} {why}' + (f' vol {vol:.3f}' if vol is not None else ''), flush=True)

async def main():
    d = db()
    bn()
    print(f'{dt.datetime.now(dt.UTC):%F %T} M53-NC up - PAPER ONLY, places nothing. prereg 3224c11, '
          f'counts from epoch {START}, bankroll ${cash_now(d):.2f}, vol series refreshed every 120 s',
          flush=True)
    while True:
        try:
            ep = int(time.time() // 300 * 300); nxt = ep + 300
            ids, m = [], {}
            for e in (ep, nxt):
                r = toks(e)
                if r: ids += [r[0], r[1]]; m[r[0]] = (e, 'UP'); m[r[1]] = (e, 'DOWN')
            if not ids: await asyncio.sleep(5); continue
            done = {x for (x,) in d.execute('select epoch from nc')}
            books = {}                                  # asset_id -> {price: size}
            async with websockets.connect(WS, ping_interval=20, family=socket.AF_INET,
                                          max_queue=32768) as w:
                await w.send(json.dumps({"assets_ids": ids, "type": "market"}))
                while time.time() < nxt + 5:
                    try: raw = await asyncio.wait_for(w.recv(), timeout=20)
                    except asyncio.TimeoutError: continue
                    now = time.time()
                    if ('book' not in raw) and ('price_change' not in raw) and ('last_trade_price' not in raw):
                        continue
                    try: data = json.loads(raw)
                    except Exception: continue
                    for ev in (data if isinstance(data, list) else [data]):
                        et = ev.get('event_type')
                        if et == 'book':
                            a = ev.get('asset_id')
                            if a: books[a] = {float(x['price']): float(x['size'])
                                              for x in (ev.get('asks') or []) if float(x['size']) > 0}
                        elif et == 'price_change':
                            for ch in (ev.get('price_changes') or []):
                                a = ch.get('asset_id')
                                if a is None or str(ch.get('side', '')).upper() not in ('SELL', 'ASK'):
                                    continue
                                bk = books.setdefault(a, {})
                                p, s = float(ch['price']), float(ch['size'])
                                if s <= 0: bk.pop(p, None)
                                else: bk[p] = s
                        elif et == 'last_trade_price':
                            if str(ev.get('side', '')).upper() != 'BUY': continue
                            a = ev.get('asset_id')
                            if a not in m: continue
                            e, sd = m[a]
                            if e < START or e in done: continue
                            pts = float(ev['timestamp']) / 1000.0
                            px = float(ev['price']); s = pts - e
                            if not (SEC0 <= s <= SEC1) or not (LO <= px <= HI): continue
                            done.add(e)
                            vol = S._vol_bn(bn(), e)
                            if vol is None: skip(d, e, 'skipped-no-data'); continue
                            if vol < S.FAV_CUT_LOW: skip(d, e, 'skipped-calm', vol); continue
                            tok = a
                            seen = min(books.get(tok, {}) or {None: None}) if books.get(tok) else None
                            await asyncio.sleep(RTT)     # order round-trip; book moves meanwhile
                            record(d, e, pts, px, sd, now, vol, seen, dict(books.get(tok, {})))
        except Exception as ex:
            print(f'reconnect after {repr(ex)[:110]}', flush=True); await asyncio.sleep(3)

if __name__ == '__main__': asyncio.run(main())
