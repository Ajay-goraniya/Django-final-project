#!/usr/bin/env python3
"""Stricter re-read of arb_trades_check (V, 09-28 05:4x). The first check took the MIN taker price of EACH leg
independently over a 3 s window. The two legs move against each other, so two independent minima understate
the pair cost. Here, per second, variants:
  W3min  - the original (min of each leg over s-3..s)
  W0min  - both legs traded in the SAME second, min price of each
  W0max  - both legs traded in the same second, MAX price of each (conservative: what the unlucky taker paid)
A window counts only if |L15-L5| >= $5 (the pair_bot default)."""
import sys, collections, datetime as dt
import arb_trades_check as A

def scan(e, m15, m5, L15, L5):
    up15 = L15 < L5
    tok15 = m15[1][0 if up15 else 1]; tok5 = m5[1][1 if up15 else 0]
    by = lambda ts: collections.defaultdict(list)
    s15, s5 = collections.defaultdict(list), collections.defaultdict(list)
    for t in A.trades(m15[0], e + 600):
        if t['asset'] == tok15 and t['side'] == 'BUY' and e + 600 <= t['timestamp'] < e + 900: s15[t['timestamp']].append(t['price'])
    for t in A.trades(m5[0], e + 600):
        if t['asset'] == tok5 and t['side'] == 'BUY' and e + 600 <= t['timestamp'] < e + 900: s5[t['timestamp']].append(t['price'])
    cost = lambda a, b: a + A.fee(a) + b + A.fee(b)
    out = {}
    for name, W, agg in (('W3min', 3, min), ('W0min', 0, min), ('W0max', 0, max)):
        secs = []
        for s in range(e + 600, e + 896):
            p15 = [p for k in range(s - W, s + 1) for p in s15.get(k, [])]
            p5 = [p for k in range(s - W, s + 1) for p in s5.get(k, [])]
            if p15 and p5: secs.append(cost(agg(p15), agg(p5)))
        ok = [c for c in secs if c < 1]
        out[name] = (len(ok), min(ok) if ok else None)
    return out

def main(a, b):
    px = A.closes(a - 120, b + 900)
    line = lambda e: (lambda v: sum(v) / len(v) if len(v) >= 45 else None)([px[k] for k in range(e - 60, e) if k in px])
    tot = collections.Counter(); secs = collections.Counter(); best = collections.defaultdict(list); n = 0
    for e in range(a, b + 1, 900):
        m15, m5 = A.market(f'{A.ASSET}-updown-15m-{e}'), A.market(f'{A.ASSET}-updown-5m-{e+600}')
        L15, L5 = line(e), line(e + 600)
        if not m15 or not m5 or L15 is None or L5 is None or abs(L5 - L15) < 5.0: continue
        n += 1
        for k, (c, m) in scan(e, m15, m5, L15, L5).items():
            if c: tot[k] += 1; secs[k] += c; best[k].append(round(m, 4))
    print(f'{A.ASSET} {dt.datetime.fromtimestamp(a, dt.timezone.utc):%m-%d %H:%M}..{dt.datetime.fromtimestamp(b, dt.timezone.utc):%H:%M}  windows with |gap|>=$5: {n}')
    for k in ('W3min', 'W0min', 'W0max'):
        bs = sorted(best[k])
        print(f'  {k}: windows with a traded pair cost<1: {tot[k]} of {n}; riskless seconds {secs[k]}; '
              f'median best {bs[len(bs)//2] if bs else None}; best costs {bs[:12]}')

if __name__ == '__main__':
    if len(sys.argv) > 3: A.ASSET, A.SYM = sys.argv[3], sys.argv[4]
    main(int(sys.argv[1]), int(sys.argv[2]))
