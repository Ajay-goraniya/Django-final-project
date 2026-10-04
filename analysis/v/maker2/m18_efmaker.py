#!/usr/bin/env python3
"""M18 (V, 10-01) - EF-maker: London's real fixed15 fires, executed as a resting post-only bid instead of taking the ask.
Pre-registered in PREREG_M18_EFMAKER.md (1e76d75). usage: m18_efmaker.py <fills.csv> <tape glob>"""
import sys, csv, glob, gzip, json, random
import numpy as np

SPLIT, STAKE = 1790553600, 10.0
F = list(csv.DictReader(open(sys.argv[1])))
TP = {}
for f in glob.glob(sys.argv[2]): TP.update({int(k): v for k, v in json.load(gzip.open(f)).items()})

rows = []
for r in F:
    e = int(r['candle_epoch'])
    if e not in TP: continue
    tok = 1 if r['side'] == 'U' else 0
    win = r['side'] == r['venue_outcome']
    pr = sorted((p[0], p[2]) for p in TP[e]['p'] if p[1] == tok)
    rows.append(dict(e=e, f=float(r['fire_ts']), ask=float(r['ask_paid']), win=win, pr=pr,
                     taker=float(r['pnl_usd']) / float(r['stake_usd']) * STAKE))
rows.sort(key=lambda x: x['e'])
print(f'M18: {len(rows)} of {len(F)} London fixed15 fires have Polymarket tape.')


def run(S, d, W):
    out = []
    for x in S:
        bid = round(x['ask'] - d, 2)
        if bid <= 0.01: out.append(None); continue
        end = min(x['f'] + W, x['e'] + 270)
        filled = any(x['f'] < t <= end and p < bid - 1e-9 for t, p in x['pr'])
        out.append((STAKE / bid * (1 - bid)) if (filled and x['win']) else (-STAKE if filled else None))
    return out


def summ(S, res):
    fl = [(x, v) for x, v in zip(S, res) if v is not None]
    return dict(n=len(fl), mk=sum(v for _, v in fl), tk_same=sum(x['taker'] for x, _ in fl),
                tk_all=sum(x['taker'] for x in S), win=np.mean([v > 0 for _, v in fl]) * 100 if fl else 0,
                tkwin_same=np.mean([x['win'] for x, _ in fl]) * 100 if fl else 0)


TR = [x for x in rows if x['e'] < SPLIT]; TE = [x for x in rows if x['e'] >= SPLIT]
print(f'train {len(TR)}  test {len(TE)}.  taker (real, scaled to $10): train {sum(x["taker"] for x in TR):+.2f}  test {sum(x["taker"] for x in TE):+.2f}')
print('cell        | TRAIN fills  maker$   taker$(all fires) | TEST fills fill%  maker$  halves          win%  taker$(all)  taker$(same fires)')
best = None
for d in (0.01, 0.02, 0.03):
    for W in (30, 60, 120):
        a = summ(TR, run(TR, d, W)); rt = run(TE, d, W); t = summ(TE, rt)
        h = len(TE) // 2
        h1 = summ(TE[:h], rt[:h])['mk']; h2 = summ(TE[h:], rt[h:])['mk']
        print(f'd={d:.2f} W={W:3d} | {a["n"]:4d} {a["mk"]:+8.2f} {a["tk_all"]:+8.2f}       | {t["n"]:4d} {t["n"]/len(TE)*100:4.1f}% {t["mk"]:+8.2f} {h1:+7.2f}/{h2:+7.2f} {t["win"]:5.1f} {t["tk_all"]:+8.2f} {t["tk_same"]:+8.2f}')
        if best is None or a['mk'] > best[0]: best = (a['mk'], d, W, t, h1, h2)
_, d, W, t, h1, h2 = best
ok = t['mk'] > 0 and t['mk'] > t['tk_all'] and h1 > 0 and h2 > 0 and t['n'] >= 60
print(f'\nchosen on TRAIN: d={d:.2f} W={W}. SEALED TEST: maker {t["mk"]:+.2f} on {t["n"]} fills vs taker {t["tk_all"]:+.2f} on all fires; '
      f'halves {h1:+.2f}/{h2:+.2f}; filled win {t["win"]:.1f}% -> {"PASS" if ok else "FAIL"}')
# null: same number of fills drawn at random from the test fires, priced at bid with no fee
random.seed(18); res = []
for _ in range(4000):
    s = random.sample(TE, t['n']); res.append(sum((STAKE / round(x['ask'] - d, 2) * (1 - round(x['ask'] - d, 2))) if x['win'] else -STAKE for x in s))
print(f'null (random fires, same count, same price rule): mean {np.mean(res):+.2f}; P(null >= ours) = {np.mean([v >= t["mk"] for v in res]):.3f}')
