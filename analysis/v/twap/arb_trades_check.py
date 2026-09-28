#!/usr/bin/env python3
"""Independent check of Zurich's ARB_5M_15M from PUBLIC data only (V, 09-28). Read-only, nothing traded.

Zurich saw pair cost < 1 on 25/81 windows from its own recorder books. If those prices were real, takers must
have BOUGHT the two dominance legs at such prices. This uses Polymarket's public trade tape (data-api /trades,
taker side) - an independent source - and Binance 1 s klines for the two lines (the ~3% Chainlink/Binance
disagreement only matters when L15 ~ L5, and those windows are reported separately).

Legs: L15 < L5 -> 15m UP + 5m DOWN; L15 > L5 -> 15m DOWN + 5m UP (payoff 1 or 2, never 0).
For every second of the last 5m candle: the latest taker BUY price of each leg within the previous W seconds.
cost = p15 + fee + p5 + fee, fee = 0.07 p (1-p). A window "trades riskless" if some second has cost < 1.
Also reports the realised payoff (gamma outcomePrices) so the zero-payoff check is repeated on public data.
"""
import json, time, sys, urllib.request, datetime as dt, collections

GAMMA = 'https://gamma-api.polymarket.com/events?slug={}'
TRADES = 'https://data-api.polymarket.com/trades?market={}&limit=500&offset={}&takerOnly=true'
KL = 'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1s&startTime={}&limit=1000'
fee = lambda p: 0.07 * p * (1 - p)
W = 3

def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'v-check'}), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(1.5 * (i + 1))

def market(slug):
    for ev in get(GAMMA.format(slug)) or []:
        for m in ev.get('markets', []):
            if m.get('slug') == slug:
                return m['conditionId'], json.loads(m['clobTokenIds']), json.loads(m.get('outcomePrices') or '[]')
    return None

def trades(cid, t_lo):
    out, off = [], 0
    while off < 20000:
        page = get(TRADES.format(cid, off))
        if not page: break
        out += page; off += len(page)
        if min(t['timestamp'] for t in page) < t_lo or len(page) < 500: break
        time.sleep(0.15)
    return out

def closes(t0, t1):
    px, t = {}, t0 * 1000
    while t < t1 * 1000:
        rows = get(KL.format(t))
        if not rows: break
        for r in rows: px[int(r[0]) // 1000] = float(r[4])
        t = int(rows[-1][0]) + 1000
        time.sleep(0.05)
    return px

def main(a, b):
    eps = list(range(a, b + 1, 900))
    px = closes(a - 120, b + 900)
    print(f'binance 1 s closes: {len(px)}')
    line = lambda e: (lambda v: sum(v) / len(v) if len(v) >= 45 else None)([px[k] for k in range(e - 60, e) if k in px])
    rep = collections.Counter(); rows = []
    for e in eps:
        m15, m5 = market(f'btc-updown-15m-{e}'), market(f'btc-updown-5m-{e+600}')
        if not m15 or not m5: rep['no_market'] += 1; continue
        L15, L5 = line(e), line(e + 600)
        if L15 is None or L5 is None: rep['no_line'] += 1; continue
        up15 = L15 < L5
        tok15 = m15[1][0 if up15 else 1]; tok5 = m5[1][1 if up15 else 0]
        w15 = m15[2] and float(m15[2][0 if up15 else 1]) > 0.5
        w5 = m5[2] and float(m5[2][1 if up15 else 0]) > 0.5
        pay = (1 if w15 else 0) + (1 if w5 else 0) if (m15[2] and m5[2]) else None
        t15 = [t for t in trades(m15[0], e + 600) if t['asset'] == tok15 and t['side'] == 'BUY' and e + 600 <= t['timestamp'] < e + 900]
        t5 = [t for t in trades(m5[0], e + 600) if t['asset'] == tok5 and t['side'] == 'BUY' and e + 600 <= t['timestamp'] < e + 900]
        last15, last5, best = {}, {}, None
        for t in t15: last15.setdefault(t['timestamp'], []).append((t['price'], t['size']))
        for t in t5: last5.setdefault(t['timestamp'], []).append((t['price'], t['size']))
        for s in range(e + 600, e + 896):
            p15 = min((p for k in range(s - W, s + 1) for p, _ in last15.get(k, [])), default=None)
            p5 = min((p for k in range(s - W, s + 1) for p, _ in last5.get(k, [])), default=None)
            if p15 is None or p5 is None: continue
            c = p15 + fee(p15) + p5 + fee(p5)
            if best is None or c < best[0]: best = (c, s - e - 600, p15, p5)
        close_lines = abs(L15 - L5) < 5.0
        rows.append(dict(e=e, gap=round(L5 - L15, 2), n15=len(t15), n5=len(t5), best=best, pay=pay, close=close_lines))
        rep['windows'] += 1
        time.sleep(0.1)
    ok = [r for r in rows if r['best'] and r['best'][0] < 1]
    print(f'windows scanned {rep["windows"]} (no market {rep["no_market"]}, no line {rep["no_line"]})')
    print(f'windows with a TRADED pair cost < 1 (both legs bought by takers within {W}s): {len(ok)} of {len(rows)}; '
          f'of those with lines < $5 apart: {sum(r["close"] for r in ok)}')
    pays = collections.Counter(r['pay'] for r in rows if r['pay'] is not None)
    print(f'payoff of the dominance pair on gamma, all windows: {dict(pays)}  (0 would break the structure)')
    for r in sorted(ok, key=lambda r: r['best'][0])[:30]:
        c, sec, p15, p5 = r['best']
        print(f"  {dt.datetime.fromtimestamp(r['e'], dt.timezone.utc):%m-%d %H:%M} gap {r['gap']:+8.2f}  cost {c:.4f} at sec {sec:3d} "
              f"(15m {p15:.3f} + 5m {p5:.3f})  trades 15m/5m {r['n15']}/{r['n5']}  pay {r['pay']}")
    json.dump(rows, open('arb_trades_rows.json', 'w'))

if __name__ == '__main__':
    main(int(sys.argv[1]), int(sys.argv[2]))
