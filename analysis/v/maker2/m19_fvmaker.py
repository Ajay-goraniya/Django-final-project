#!/usr/bin/env python3
"""M19 (V, 10-02) - fair-value two-sided maker on Polymarket BTC 5m. Pre-registered: PREREG_M19_FVMAKER.md.
usage: m19_fvmaker.py <bn1s json files,> <tape glob>"""
import sys, json, glob, gzip, math, random
import numpy as np

SPLIT = 1790553600  # 09-28 00:00 UTC
BN = {}
for f in sys.argv[1].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
TP = {}
for f in glob.glob(sys.argv[2]): TP.update({int(k): v for k, v in json.load(gzip.open(f)).items()})
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))


def series(a, b):  # forward-filled 1 s closes on [a, b]
    out, last = [], None
    for t in range(a, b + 1):
        last = BN.get(t, last); out.append(last)
    return out


C = []  # per candle precomputation
for e in sorted(TP):
    if e < 1790121600: continue
    s = series(e - 300, e + 299)
    if any(x is None for x in s): continue
    lr = np.diff(np.log(s))
    pre, cur = s[:300], s[300:]
    prints = {0: {}, 1: {}}
    for t, tok, p, sz in TP[e]['p']:
        sec = int(t) - e
        if 0 <= sec < 300: prints[tok].setdefault(sec, []).append((p, sz))
    C.append(dict(e=e, up=TP[e]['up_won'], cur=cur, lr=lr, prints=prints))
print(f'M19: {len(C)} candles with full Binance + tape. train {sum(c["e"] < SPLIT for c in C)}  test {sum(c["e"] >= SPLIT for c in C)}')


def fair(c, k):
    """p_up for sec 0..299 using info up to that second."""
    cur, lr = c['cur'], c['lr']; out = []
    for t in range(300):
        n = min(t + 1, 60); O = sum(cur[:n]) / n
        sig = float(np.std(lr[t:t + 300])) or 1e-6  # previous 300 s of returns ending at sec t
        tau = max(300 - t, 1)
        out.append(Phi(math.log(cur[t] / O) / (k * sig * math.sqrt(tau))))
    return out


# fit k on TRAIN by log-likelihood at sec 60..270
TR = [c for c in C if c['e'] < SPLIT]
best = None
for k in (0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8):
    ll = 0
    for c in TR[::3]:
        f = fair(c, k)
        for t in range(60, 271, 30):
            p = min(max(f[t], 1e-4), 1 - 1e-4); ll += math.log(p if c['up'] else 1 - p)
    if best is None or ll > best[0]: best = (ll, k)
K = best[1]; print(f'k fitted on train = {K}')
for c in C: c['f'] = fair(c, K)

# calibration
for nm, S in (('TRAIN', TR), ('TEST', [c for c in C if c['e'] >= SPLIT])):
    rows = [(c['f'][t], c['up']) for c in S for t in range(60, 271, 30)]
    bins = [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)]
    print(nm, 'calibration (fair bucket: n, mean fair, actual up%):', ' | '.join(
        f'{lo:.1f}-{hi:.1f}: {len(b)} {np.mean([x for x, _ in b]):.2f} {np.mean([y for _, y in b]):.2f}'
        for lo, hi in bins for b in [[r for r in rows if lo <= r[0] < hi]] if b))


def run(S, m):
    fills = []
    for c in S:
        done = {0: False, 1: False}
        for t in range(30, 271):
            pu = c['f'][t - 1]  # 1 s latency
            for tok, pf in ((1, pu), (0, 1 - pu)):
                if done[tok]: continue
                bid = math.floor((pf - m) * 100) / 100
                if not (0.05 <= bid <= 0.90): continue
                if any(p < bid - 1e-9 for p, _ in c['prints'][tok].get(t, [])):
                    won = (c['up'] == 1) == (tok == 1)
                    fills.append(dict(e=c['e'], tok=tok, bid=bid, won=won, pnl=5 * ((1 - bid) if won else -bid), cost=5 * bid))
                    done[tok] = True
    return fills


def summ(F):
    if not F: return 0, 0, 0, 0
    return len(F), np.mean([f['won'] for f in F]) * 100, sum(f['pnl'] for f in F), sum(f['pnl'] for f in F) / sum(f['cost'] for f in F)


TE = [c for c in C if c['e'] >= SPLIT]
print('\n   m  | TRAIN fills win%  pnl   /$   | TEST fills win%   pnl    /$    halves          | null(random side) p')
res = {}
for m in (0.02, 0.04, 0.06, 0.08, 0.10, 0.15):
    a = summ(run(TR, m)); FT = run(TE, m); t = summ(FT); res[m] = (a, FT)
    h = sorted(FT, key=lambda f: f['e']); hh = len(h) // 2
    h1, h2 = sum(f['pnl'] for f in h[:hh]), sum(f['pnl'] for f in h[hh:])
    # null: same fills, coin-flip whether the filled side won (keeps prices, kills the fair model's selection)
    random.seed(19); nulls = []
    for _ in range(2000):
        nulls.append(sum(5 * ((1 - f['bid']) if random.random() < f['bid'] else -f['bid']) for f in FT))
    p = np.mean([x >= t[2] for x in nulls]) if FT else 1
    print(f' {m:.2f} | {a[0]:5d} {a[1]:5.1f} {a[2]:+8.2f} {a[3]:+.3f} | {t[0]:5d} {t[1]:5.1f} {t[2]:+8.2f} {t[3]:+.3f}  {h1:+7.2f}/{h2:+7.2f} | {p:.3f}')
mstar = max(res, key=lambda m: res[m][0][2])
a, FT = res[mstar]; t = summ(FT)
h = sorted(FT, key=lambda f: f['e']); hh = len(h) // 2
ok = t[2] > 0 and sum(f['pnl'] for f in h[:hh]) > 0 and sum(f['pnl'] for f in h[hh:]) > 0 and t[0] >= 60
print(f'\nchosen on TRAIN: m={mstar}. SEALED TEST: {t[0]} fills, win {t[1]:.1f}%, pnl {t[2]:+.2f} ({t[3]:+.3f}/$) -> {"PASS (pending null)" if ok else "FAIL"}')
