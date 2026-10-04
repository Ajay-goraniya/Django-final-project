#!/usr/bin/env python3
"""The REVERSAL on its OWN condition: the settlement reference has re-crossed the opening line.
READ-ONLY. Master OFF, London untouched.

Owner's intent, confirmed by V 09-28 13:2x. The previous test re-ran the ENTRY rule on the other side, which
fires on cheapness and therefore fires when you are winning. This one fires on the thing he actually means:
the reference has crossed back through the line, so the move that justified the first leg is now wrong.

TRIGGER: the first second after the first fire at which ref_px is on the OTHER side of the candle's opening
line from our first leg, AND has been there for K consecutive seconds (K = 0, 2, 5, 10). Past-only by
construction - the K seconds are the K before the trigger, never after.
  line = TWAP60 of ref_px over [ep-60, ep-1] - the settlement rule's own line, not a Binance proxy.
  our leg UP  -> the other side is ref < line;  our leg DOWN -> ref > line.

TWO ACTIONS, side by side:
  (i)  BUY the opposite side at its ask, ef_persist FAK fill.
  (ii) SELL the first leg at its bid, i.e. EXIT. Polymarket's two tokens are complements, so the best bid on
       our side is 1 - the best ask on the other side; that identity is what makes an exit priceable from a
       log that only stores asks. The 0.07*sh*p*(1-p) fee is charged on the exit as well as the entry.

THE NULL V ASKED FOR: at the trigger, what the opposite ask ALREADY is. Binance leads the Chainlink reference
by 2-3 s (EF_FIRE_TIME section 6), so by the time the reference re-crosses, the crowd has had seconds to move
the price - and if the opposite ask is already expensive there is nothing left to collect.
"""
import sys, sqlite3, math, collections, statistics as st, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, be

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
KS = (0, 2, 5, 10)
A_P, B_P, TICK, RATE, PAD, STAKE = 1.0677, -0.3208, 0.01, 0.07, 1, 10.0
MIN_CELL = 60
Dc = lambda x: Decimal(str(x))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(a):
    # float32 asks out of ef2_rows.npz defeat the `Decimal(str(x))` guard: str() yields
    # '0.3400000035762787', ROUND_CEILING adds a free tick on 44.8% of rows, and only the padded
    # (fixed15) profile is affected. See ef3.py for the full write-up. Snap to the grid first.
    a = float(Decimal(str(a)).quantize(Decimal('0.000001')))
    px = float((Dc(a) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


QUAL = {'raw25': lambda p, a: (p / be(a) - 1) >= 0.25 if be(a) > 0 else False,
        'fixed15': lambda p, a: (platt(p) / pad_cost(a) - 1) >= 0.15}
fee = lambda sh, px: RATE * sh * px * (1 - px)


def refs():
    r = {}
    for src in (ARCH, LIVE):
        try:
            c = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
            for ts, v in c.execute('SELECT ts,ref_px FROM tape1s WHERE ref_px IS NOT NULL'):
                r[int(ts)] = float(v)
        except Exception as e: print(f'  (ref source {src}: {e})')
    return r


def dd_run(pnls_t):
    cum = peak = mdd = 0.; run = worst = 0
    for _, x in sorted(pnls_t):
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return mdd, worst


if __name__ == '__main__':
    R = refs()
    z = np.load(ROWS, allow_pickle=True)
    X, y, q, ep, ts, day = z['X'], z['y'].astype(float), z['q'], z['ep'], z['ts'], z['day']
    names = [str(s) for s in z['names']]; isup = z['is_up']
    fin = np.all(np.isfinite(X), axis=1)
    X, y, q, ep, ts, day, isup = X[fin], y[fin], q[fin], ep[fin], ts[fin], day[fin], isup[fin]
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    C = collections.defaultdict(list); K2 = {}
    for i in range(len(y)):
        d = dict(t=int(ts[i]), p=float(X[i, ip]), ask=float(X[i, ia]), q=float(q[i]), win=float(y[i]),
                 sec=int(X[i, isec]), up=int(isup[i]), day=str(day[i]), ep=int(ep[i]))
        C[int(ep[i])].append(d); K2[(int(ts[i]), int(isup[i]))] = d
    for e in C: C[e].sort(key=lambda c: c['t'])
    days = sorted(set(day.tolist()))
    line = {}
    for e in C:
        v = [R[e - k] for k in range(1, 61) if (e - k) in R]
        if len(v) >= 45: line[e] = sum(v) / len(v)
    print(f'candles {len(C)}, days {days}; opening line from the Chainlink ref on {len(line)} of them; '
          f'ref seconds held {len(R):,}')

    def trigger(e, f1, K):
        """First second after the first fire with ref on the OTHER side of the line for K+1 consecutive s."""
        if e not in line: return None
        L = line[e]; want_below = (f1['up'] == 1)
        t0 = f1['t'] // 1000 + 1
        for t in range(t0, e + 300):
            ok = True
            for k in range(0, K + 1):
                v = R.get(t - k)
                if v is None or ((v < L) != want_below): ok = False; break
            if ok: return t
        return None

    HDR = (f'  {"K / action":28s}{"trig":>6}{"fill%":>7}{"win/save":>9}{"leg$1":>8}{"leg$":>9}'
           f'{"CANDLE$":>10}{"vs 1st":>9}{"DD$":>7}{"run":>5}{"H1":>8}{"H2":>8}{"oppAsk":>8}')
    for arm, qual in QUAL.items():
        first = {}
        for e, lst in C.items():
            f1 = next((c for c in lst if c['p'] >= 0.5 and qual(c['p'], c['ask'])), None)
            if f1 is not None and e in line: first[e] = f1
        f1fl = [l for l in first.values() if l['q'] == l['q']]
        base_t = sum(STAKE * per1(l['win'], l['q']) for l in f1fl)
        bdd, brun = dd_run([(l['t'], STAKE * per1(l['win'], l['q'])) for l in f1fl])
        print(f'\n{"="*150}\n{arm}: first fire on {len(first)} candles with a line, {len(f1fl)} fills, '
              f'total {base_t:+.1f}$, DD {bdd:.1f}$, run {brun}\n{"="*150}')
        print(HDR)
        for K in KS:
            TR = {}
            for e, f1 in first.items():
                t = trigger(e, f1, K)
                if t is None: continue
                nxt = next((c for c in C[e] if c['t'] >= t * 1000), None)
                if nxt is None: continue
                opp = K2.get((nxt['t'], 1 - f1['up']))
                if opp is None: continue
                TR[e] = (f1, opp, t)
            if not TR:
                print(f'  {f"K={K} (no triggers)":28s}{0:>6}'); continue
            oa = [o['ask'] for _, o, _ in TR.values()]
            for act in ('i BUY opposite', 'ii SELL first leg'):
                rows = []
                for e, (f1, opp, t) in TR.items():
                    if f1['q'] != f1['q']: continue          # the first leg never filled: nothing to act on
                    s1 = STAKE / f1['q']; c1 = STAKE + fee(s1, f1['q'])
                    hold = (s1 if f1['win'] else 0.) - c1
                    if act.startswith('i '):
                        if opp['q'] != opp['q']: rows.append((e, t, hold, None, opp)); continue
                        s2 = STAKE / opp['q']; c2 = STAKE + fee(s2, opp['q'])
                        leg = (s2 if opp['win'] else 0.) - c2
                        rows.append((e, t, hold + leg, leg, opp))
                    else:
                        bid = 1.0 - opp['ask']
                        if not (0.01 < bid < 0.99): rows.append((e, t, hold, None, opp)); continue
                        got = s1 * bid - fee(s1, bid)
                        exitp = got - c1
                        rows.append((e, t, exitp, exitp - hold, opp))
                acted = [r for r in rows if r[3] is not None]
                if not rows: continue
                cand_tot = sum(r[2] for r in rows)
                only1 = sum(STAKE * per1(first[r[0]]['win'], first[r[0]]['q']) for r in rows)
                legs = [r[3] for r in acted]
                if act.startswith('i '):
                    wins = [r[4]['win'] for r in acted]
                    den = sum(cost(r[4]['q']) for r in acted)
                    v = (sum(per1(r[4]['win'], r[4]['q']) * cost(r[4]['q']) for r in acted) / den) if den else float('nan')
                    wl = 100 * np.mean(wins) if wins else float('nan')
                else:
                    v = sum(legs) / max(sum(STAKE for _ in acted), 1e-9)
                    wl = 100 * np.mean([1.0 if x > 0 else 0.0 for x in legs]) if legs else float('nan')
                mdd, run = dd_run([(r[1], r[2]) for r in rows])
                srt = sorted(acted, key=lambda r: r[1]); h = len(srt) // 2
                h1 = sum(r[3] for r in srt[:h]) / max(STAKE * h, 1e-9) if h else float('nan')
                h2 = sum(r[3] for r in srt[h:]) / max(STAKE * (len(srt) - h), 1e-9) if len(srt) > h else float('nan')
                print(f'  {f"K={K} {act}":28s}{len(TR):>6}{100*len(acted)/max(len(rows),1):>6.1f}%'
                      f'{wl:>8.1f}%{v:>+8.3f}{sum(legs):>+9.1f}{cand_tot:>+10.1f}{cand_tot-only1:>+9.1f}'
                      f'{mdd:>7.1f}{run:>5}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
                      f'{np.median(oa):>8.2f}' + ('  *n<60' if len(acted) < MIN_CELL else ''))
            print('  ' + '-' * 148)
        # the null and the split, at K=2
        TR = {}
        for e, f1 in first.items():
            t = trigger(e, f1, 2)
            if t is None: continue
            nxt = next((c for c in C[e] if c['t'] >= t * 1000), None)
            if nxt is None: continue
            opp = K2.get((nxt['t'], 1 - f1['up']))
            if opp is not None: TR[e] = (f1, opp, t)
        if TR:
            oa = np.array([o['ask'] for _, o, _ in TR.values()])
            won = np.array([f['win'] for f, _, _ in TR.values()])
            print(f'  NULL at K=2: the opposite ask AT THE TRIGGER is p10 {np.percentile(oa,10):.2f} '
                  f'p50 {np.percentile(oa,50):.2f} p90 {np.percentile(oa,90):.2f}; on candles where the first '
                  f'leg went on to LOSE it is p50 {np.median(oa[won==0]) if (won==0).any() else float("nan"):.2f}, '
                  f'where it WON p50 {np.median(oa[won==1]) if (won==1).any() else float("nan"):.2f}')
            print(f'  SPLIT by first-fire second, K=2, action (i) buy opposite:')
            for lo, hi in ((15, 120), (120, 200), (200, 241)):
                s = [(f, o) for f, o, _ in TR.values() if lo <= f['sec'] < hi and o['q'] == o['q']]
                if not s: print(f'    1st {lo}-{hi}: none'); continue
                den = sum(cost(o['q']) for _, o in s)
                print(f'    1st {lo}-{hi}: n {len(s):>3}  opp win {100*np.mean([o["win"] for _, o in s]):>5.1f}%  '
                      f'per$1 {sum(per1(o["win"], o["q"])*cost(o["q"]) for _, o in s)/den:>+7.3f}  '
                      f'opp ask p50 {np.median([o["ask"] for _, o in s]):.2f}'
                      + ('  *n<60' if len(s) < MIN_CELL else ''))
