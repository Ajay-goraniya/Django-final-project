#!/usr/bin/env python3
"""EF-8 (V, 09-28): does the EF-4/5 METHOD (after-fill target, stump booster, nightly refit, causal strict quantile) hold on an
INDEPENDENT period? Data: polybook 1 Hz book 09-11..16 (learner/live_backup/polybook.sqlite3.gz, both sides ask/bid/size/age),
venues.outcome (Polymarket's own resolution), Binance 1 s closes (data-api.binance.vision). No Zurich/London day overlaps.
Builds one row per (candle, second, side). Target = after-fill $ per $1: FAK at cap = ask + 1c; fills if the SAME side's ask one
second later is <= cap (the 1 s tape is slower than the ~250 ms venue path, so this is a conservative fill model); paid = that ask;
cost = paid * (1 + 0.07 (1 - paid)); pnl = win / cost - 1, 0 if no fill. Line = Binance TWAP60 ending at the open (96.7% proxy).
usage: ef8_build.py <scratch dir with polybook.sqlite3, venues.sqlite3, bin1s_0911.json> -> rows.npz"""
import sys, json, sqlite3, math, collections
import numpy as np

S = sys.argv[1]
px = {int(t) // 1000: c for t, c in json.load(open(f'{S}/bin1s_0911.json'))}
out = dict(sqlite3.connect(f'{S}/venues.sqlite3').execute('select epoch, actual from outcome').fetchall())
pb = sqlite3.connect(f'{S}/polybook.sqlite3').execute(
    "select epoch, sec, ask_up, size_up, bid_up, ask_dn, size_dn, bid_dn, age_s from pb "
    "where status='live websocket' and sec >= 0 and sec < 300 order by ts_ms").fetchall()
book = collections.defaultdict(dict)
for ep, sec, au, su, bu, ad, sd, bd, age in pb:
    book[int(ep)][int(sec)] = (au, su, bu, ad, sd, bd, age)          # last row in each integer second


def P(t):
    for k in range(4):
        if t - k in px: return px[t - k]
    return None


def twap(a, b):                                                        # mean close over [a, b)
    v = [px[t] for t in range(a, b) if t in px]
    return sum(v) / len(v) if len(v) >= 0.8 * (b - a) else None


cols = ['ep', 'sec', 'side', 'own_ask', 'opp_ask', 'own_bid', 'opp_bid', 'own_size', 'opp_size', 'age', 'spread',
        'd_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30', 'dist_bps', 'proj_bps', 'z', 'vol', 'mom5', 'mom15', 'mom60',
        'win', 'fill', 'paid', 'pnl']
R = []
nc = 0
for ep in sorted(book):
    if ep not in out: continue
    line = twap(ep - 60, ep)
    if line is None: continue
    b = book[ep]; nc += 1
    rets = [math.log(P(t) / P(t - 1)) for t in range(ep - 300, ep) if P(t) and P(t - 1)]
    vol0 = float(np.std(rets)) * 1e4 if len(rets) > 100 else None     # bps per sqrt(s), trailing 5 min before the open
    hist = {'UP': [], 'DOWN': []}
    for sec in range(0, 296):
        if sec not in b: continue
        au, su, bu, ad, sd, bd, age = b[sec]
        t = ep + sec; p = P(t)
        for s, a in (('UP', au), ('DOWN', ad)):
            if a is not None: hist[s].append((sec, a))
        if p is None or au is None or ad is None or not (0.01 < au < 0.99 and 0.01 < ad < 0.99): continue
        # projected closing TWAP60 (window [ep+240, ep+300)): locked part + current price for the rest
        if sec <= 240: proj = p
        else:
            lk = [px[x] for x in range(ep + 240, t + 1) if x in px]
            proj = (sum(lk) + p * (300 - sec - 1)) / (len(lk) + 300 - sec - 1)
        dist = (p / line - 1) * 1e4; pj = (proj / line - 1) * 1e4
        rem = max(1.0, (300 - sec) if sec < 240 else (300 - sec) / 3.0)   # the average shrinks the remaining variance
        z = pj / (vol0 * math.sqrt(rem)) if vol0 else None
        m = {k: ((p / P(t - k) - 1) * 1e4 if P(t - k) else None) for k in (5, 15, 60)}
        nxt = b.get(sec + 1)
        for s, a, o, ob, oo, sz, so in (('UP', au, ad, bu, bd, su, sd), ('DOWN', ad, au, bd, bu, sd, su)):
            sg = 1 if s == 'UP' else -1
            h = hist[s]
            def past(k):
                v = None
                for ss, aa in h:
                    if ss <= sec - k: v = aa
                    else: break
                return None if v is None else a - v
            last30 = [aa for ss, aa in h if ss >= sec - 30]
            win = 1 if out[ep] == s else 0
            na = None if nxt is None else (nxt[0] if s == 'UP' else nxt[3])
            fill = 1 if (na is not None and 0 < na <= a + 0.0100001) else 0
            paid = na if fill else a
            pnl = (win / (paid * (1 + 0.07 * (1 - paid))) - 1) if fill else 0.0
            R.append([ep, sec, sg, a, o, ob, oo, sz, so, age, a - (ob if ob is not None else np.nan),
                      past(1), past(5), past(30), a - min(last30) if last30 else None,
                      sg * dist, sg * pj, None if z is None else sg * z, vol0,
                      *(None if m[k] is None else sg * m[k] for k in (5, 15, 60)), win, fill, paid, pnl])
X = np.array([[np.nan if v is None else float(v) for v in r] for r in R], dtype=np.float64)
np.savez_compressed(f'{S}/ef8_rows.npz', X=X, cols=np.array(cols))
print(f'candles {nc}, rows {len(X)}, fill {np.nanmean(X[:, cols.index("fill")]):.3f}')
