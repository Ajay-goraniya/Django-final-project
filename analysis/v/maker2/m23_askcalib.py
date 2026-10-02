#!/usr/bin/env python3
"""M23 (V, 10-02) - M22 again, but on REAL ASKS (1 Hz Polymarket top of book, book1s 09-11..16), so the taker's price is
known, not guessed from prints. Grid FIXED before running, all cells: ask band (0.05 wide, 0.30..0.95) x second window
{0-60,60-120,120-180,180-240,240-290} x calm {calm, not}. Per candle per cell: the FIRST second the ask of either token
is in the band (decision); entry = that token's ask ONE SECOND LATER (latency), skipped if that ask is stale (>2 s old)
or out of [0.02, 0.99]. Taker fee 0.07*p*(1-p). Graded on the venue resolution (tape up_won). Halves in time.
usage: m23_askcalib.py <book1s.sqlite3> <bn1s json files,> <tape glob>"""
import sys, json, glob, gzip, sqlite3, collections
import numpy as np

B = collections.defaultdict(dict)
for ep, sec, au, agu, ad, agd in sqlite3.connect(sys.argv[1]).execute(
        'select epoch, sec, ask_up, age_up, ask_dn, age_dn from b1 where epoch = book_candle and sec is not null'):
    s = int(sec)
    if 0 <= s < 300: B[int(ep)][s] = (au, agu, ad, agd)
BN = {}
for f in sys.argv[2].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
UP = {}
for f in glob.glob(sys.argv[3]):
    for k, v in json.load(gzip.open(f)).items():
        if 'up_won' in v: UP[int(k)] = v['up_won']
BANDS = [round(0.30 + 0.05 * i, 2) for i in range(13)]
WINS = [(0, 60), (60, 120), (120, 180), (180, 240), (240, 290)]
fee = lambda p: 0.07 * p * (1 - p)

rows, skipped = [], collections.Counter()
for e, S in B.items():
    if e not in UP: skipped['no outcome'] += 1; continue
    raw = [BN[t] for t in range(e - 300, e) if t in BN]
    if len(raw) < 240: skipped['no bn'] += 1; continue
    calm = float(np.std(np.diff(np.log(raw)))) * 1e4 < 0.304
    for wi, (a, b) in enumerate(WINS):
        for lo in BANDS:
            hit = None
            for s in range(a, b):
                if s not in S: continue
                au, agu, ad, agd = S[s]
                for tok, ask in ((1, au), (0, ad)):
                    if ask is not None and lo <= ask < lo + 0.05: hit = (s, tok); break
                if hit: break
            if not hit: continue
            s0, tok = hit
            nx = S.get(s0 + 1)
            if not nx: skipped['no next sec'] += 1; continue
            ask, age = (nx[0], nx[1]) if tok == 1 else (nx[2], nx[3])
            if ask is None or not (0.02 <= ask <= 0.99) or (age or 0) > 2000: skipped['stale/odd ask'] += 1; continue
            won = (UP[e] == 1) == (tok == 1)
            rows.append((calm, wi, lo, won, ask, e))
print(f'M23: {len(B)} candles with book, {len(rows)} entries; skipped {dict(skipped)}. * = n<60 INSUFFICIENT')


def cell(R):
    if not R: return '   -'
    n = len(R); cost = sum(r[4] + fee(r[4]) for r in R)
    pn = [(1 if r[3] else 0) - r[4] - fee(r[4]) for r in sorted(R, key=lambda r: r[5])]
    k = n // 2
    return (f'{n:4d} win {np.mean([r[3] for r in R])*100:5.1f} ask {np.mean([r[4] for r in R]):.3f} '
            f'{sum(pn)/cost:+.3f}/$ {"*" if n < 60 else " "} halves {sum(pn[:k]):+6.2f}/{sum(pn[k:]):+6.2f}')


for calm in (True, False):
    print(f'\n===== {"CALM" if calm else "NOT CALM"} =====')
    for wi, (a, b) in enumerate(WINS):
        print(f'-- sec {a}-{b}')
        for lo in BANDS:
            print(f'  {lo:.2f}-{lo+0.05:.2f} | {cell([r for r in rows if r[0] == calm and r[1] == wi and r[2] == lo])}')
