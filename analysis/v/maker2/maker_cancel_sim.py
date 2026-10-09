#!/usr/bin/env python3
"""M1 latency-protected maker sim - see PREREG.md. usage: maker_cancel_sim.py <scratch dir with book_archive/polybook.sqlite3, book1s.sqlite3, venues.sqlite3>"""
import sys, sqlite3, collections, math
import numpy as np
S = sys.argv[1]
pb = sqlite3.connect(S + '/book_archive/polybook.sqlite3'); b1 = sqlite3.connect(S + '/book1s.sqlite3'); vn = sqlite3.connect(S + '/venues.sqlite3')
out = dict(vn.execute('select epoch, actual from outcome'))
px = collections.defaultdict(dict)
for e, sec, p in b1.execute('select epoch, sec, price from b1 where price is not null'): px[e][int(sec)] = p
bk = collections.defaultdict(dict)
for e, sec, au, bu, ad, bd in pb.execute("select epoch, sec, ask_up, bid_up, ask_dn, bid_dn from pb where ask_up is not null and bid_up is not null and ask_dn is not null and bid_dn is not null"):
    bk[e][int(sec)] = (au, bu, ad, bd)
eps = sorted(e for e in bk if e in out and e in px and len(bk[e]) > 200 and len(px[e]) > 200)
day = lambda e: (e // 86400)
days = sorted({day(e) for e in eps})
# 5-min trailing vol at the open: std of 1 s log returns (bps) over the previous candle's seconds
allpx = {}
for e in px:
    for s, p in px[e].items(): allpx[e + s] = p
def vol(e):
    r = [allpx.get(t) for t in range(e - 300, e)]; r = [x for x in r if x]
    if len(r) < 240: return None
    a = np.array(r); return float(np.std(np.diff(np.log(a))) * 1e4)
V = {e: vol(e) for e in eps}
cut = float(np.median([V[e] for e in eps if day(e) == days[0] and V[e] is not None]))
test = [e for e in eps if day(e) != days[0]]
def run(e, side, k, lo, hi):
    B, P = bk[e], px[e]; win = (out[e] == side)
    bid = None
    for s in range(30, 241):
        if s not in B: continue
        au, bu, ad, bd = B[s]; ask, bb = (au, bu) if side == 'UP' else (ad, bd)
        # fill check first (a cancel decided at s cannot stop a fill at s)
        if bid is not None and ask <= bid + 1e-9:
            return bid, win
        mv = None
        if s in P and (s - 3) in P: mv = (P[s] / P[s - 3] - 1) * 1e4 * (1 if side == 'UP' else -1)
        adverse = (k is not None and mv is not None and mv <= -k)
        if bid is not None and adverse: bid = None; continue
        if bid is None and not adverse and lo <= bb <= hi: bid = bb
        elif bid is not None and bb > bid and lo <= bb <= hi and not adverse: bid = bb   # stay at the best bid (re-join)
    return None
def stats(f):
    f.sort(); p = np.array([(10 / b - 10) if w else -10.0 for _, _, b, w in f]); c = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])); h = len(p) // 2
    bd = collections.defaultdict(float)
    for (e, *_), x in zip(f, p): bd[day(e)] += x
    return len(p), 100 * np.mean([w for *_, w in f]), c[-1], dd, (c[-1] / dd if dd else 0), sum(v > 0 for v in bd.values()), len(bd), p[:h].sum() / (10 * h), p[h:].sum() / (10 * (len(p) - h))
print(f'candles {len(eps)} (test {len(test)} on {len(days)-1} days), calm cut {cut:.3f} bps/s from day 1')
print(f"{'k':>4s} {'band':>9s} {'calm':>5s} {'fills':>6s} {'/day':>5s} {'win%':>5s} {'$tot':>8s} {'maxDD':>7s} {'P/DD':>5s} {'days+':>6s} {'H1':>7s} {'H2':>7s}")
for k in (None, 1, 2, 4):
    for lo, hi in ((0.30, 0.70), (0.40, 0.60)):
        for calm in (False, True):
            f = []
            for e in test:
                if calm and (V[e] is None or V[e] >= cut): continue
                for side in ('UP', 'DOWN'):
                    r = run(e, side, k, lo, hi)
                    if r: f.append((e, side, r[0], r[1]))
            if not f: continue
            n, w, t, dd, pd, dp, nd, h1, h2 = stats(f)
            print(f"{str(k):>4s} {lo:.2f}-{hi:.2f} {'calm' if calm else 'all':>5s} {n:6d} {n/(len(days)-1):5.0f} {w:5.1f} {t:+8.1f} {dd:7.1f} {pd:5.2f} {dp:3d}/{nd:<2d} {h1:+7.3f} {h2:+7.3f}{'  *n<60' if n < 60 else ''}")
