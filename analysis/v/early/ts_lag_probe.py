#!/usr/bin/env python3
"""Is data-api /trades 'timestamp' late versus the live match? (V, 09-28). Read-only, public.
Subscribes to the Polymarket market WS for the current + next btc 5m markets, records every last_trade_price event with the WS
event timestamp and our local receive time, then pulls data-api /trades (takerOnly) for the same markets and matches prints by
asset + price + size. Reports lag = data-api timestamp - WS timestamp (seconds). usage: ts_lag_probe.py <seconds to record>"""
import sys, json, time, asyncio, urllib.request, socket
import websockets
socket.setdefaulttimeout(30)
GAMMA = 'https://gamma-api.polymarket.com/events?slug={}'
TRADES = 'https://data-api.polymarket.com/trades?market={}&limit=500&offset={}&takerOnly=true'
WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'


def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v-check'}), timeout=30) as r: return json.load(r)


def market(e):
    slug = f'btc-updown-5m-{e}'
    for ev in get(GAMMA.format(slug)) or []:
        for m in ev.get('markets', []):
            if m.get('slug') == slug: return m['conditionId'], json.loads(m['clobTokenIds'])
    return None


async def record(tokens, secs):
    out = []; t_end = time.time() + secs
    while time.time() < t_end:
        try:
            async with websockets.connect(WS, ping_interval=20, max_size=None, max_queue=None) as ws:
                await ws.send(json.dumps({'assets_ids': tokens, 'type': 'market'}))
                while time.time() < t_end:
                    try: raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, t_end - time.time()))
                    except asyncio.TimeoutError: break
                    now = time.time()
                    if 'last_trade_price' not in raw: continue          # skip book snapshots cheaply
                    try: msgs = json.loads(raw)
                    except Exception: continue
                    for m in (msgs if isinstance(msgs, list) else [msgs]):
                        if isinstance(m, dict) and m.get('event_type') == 'last_trade_price':
                            out.append(dict(asset=m.get('asset_id'), price=float(m['price']), size=float(m['size']), side=m.get('side'),
                                            ws_ts=int(m.get('timestamp', 0)) / 1000.0, rx=now))
        except websockets.exceptions.ConnectionClosed as e:
            print(f'ws closed ({e.code}), reconnecting; prints so far {len(out)}', flush=True); await asyncio.sleep(0.5)
    return out


def main(secs):
    now = int(time.time()); e0 = now // 300 * 300
    mk = [x for x in (market(e0),) if x]
    toks = [t for _, ts in mk for t in ts]
    prints = asyncio.run(record(toks, secs))
    time.sleep(20)                                    # let the chain / indexer catch up
    api = []
    for cid, _ in mk:
        off = 0
        while off < 3000:
            page = get(TRADES.format(cid, off))
            if not page: break
            api += page; off += len(page)
            if len(page) < 500: break
    lags, rx_lags = [], []
    used = set()
    for p in prints:
        best = None
        for i, a in enumerate(api):
            if i in used or a['asset'] != p['asset']: continue
            if abs(float(a['price']) - p['price']) > 1e-9 or abs(float(a['size']) - p['size']) > 1e-6: continue
            d = a['timestamp'] - p['ws_ts']
            if abs(d) <= 30 and (best is None or abs(d) < abs(best[1])): best = (i, d)
        if best:
            used.add(best[0]); lags.append(best[1]); rx_lags.append(p['rx'] - p['ws_ts'])
    import statistics as st
    q = lambda v, x: sorted(v)[int(x * (len(v) - 1))] if v else float('nan')
    print(f'WS prints {len(prints)}, data-api trades {len(api)}, matched {len(lags)}')
    if lags:
        print(f'lag data-api_ts - ws_ts (s): p10 {q(lags,.1):+.2f}  p50 {q(lags,.5):+.2f}  p90 {q(lags,.9):+.2f}  '
              f'>=1s {100*sum(l>=1 for l in lags)/len(lags):.0f}%  >=3s {100*sum(l>=3 for l in lags)/len(lags):.0f}%  <=-1s {100*sum(l<=-1 for l in lags)/len(lags):.0f}%')
        print(f'WS delivery rx - ws_ts (s): p50 {q(rx_lags,.5):+.3f}  p90 {q(rx_lags,.9):+.3f}')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240)
