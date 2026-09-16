"""R-29 -- the owner's v12.16.1 "adaptive EF" candidate, gridded on the real fire record.

THE TRANSFORM, copied from the candidate's own source
(analysis/v/candidates/btc_model_v12_16_1_adaptive/btc_model_v10.py:385-425), not from a summary:

    trust = min(1, 1 / max(ratio, 1))
    z     = logit(anchor) + trust * (logit(base) - logit(anchor))     anchor = clamp(p_venue,.02,.98)
    final = clamp(sigmoid(z), .01, .99)

It shrinks v10's log-odds TOWARD THE VENUE, not toward 0.5 -- that is the difference from R-28 --
and it engages only when ratio > 1, so it never amplifies v10.  ratio is build11's fast/slow ENGAGED
factor, so it is 1.0 (exact frozen v10) everywhere inside the 0.85-1.15 identity band.

THREE THINGS THIS FILE DOES THAT THE LAST TWO BUGS DEMAND:
 1. `p` in `trades` is the CHOSEN-SIDE probability, `p_venue` is UP-oriented (verified: mean
    |p_venue - _ask_up| = 0.0065 vs 0.1527 against _ask_dn). The transform runs in UP orientation
    and is converted back, because logit is odd and mixing the two silently flips every DOWN fire.
 2. Shrinking toward the venue CAN CROSS 0.5 and flip the side. When it does, the trade is repriced
    at the OTHER side's own ask (_ask_dn / _ask_up) and its outcome is inverted -- this is the exact
    wrong-side-ask bug that inflated a day of results on 09-16, and a venue-anchored transform is
    precisely the kind that crosses.
 3. The identity cell (m=0) is printed FIRST and must reproduce the real fire count, or nothing
    below it can be read.
"""
import json, math, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T
import r28_adapt_ef as A

SP = T.SP
MS = [0.0, 0.5, 1.0, 2.0]          # m=1 is the owner's exact transform; m=0 is frozen v10
LANES = (('poly_pnl', 'ts_ms', 'ask'), ('v12_poly_lane', 'signal_ms', 'quote_ask'),
         ('v12_poly_weekend', 'signal_ms', 'quote_ask'))


def logit(p):
    return math.log(p / (1.0 - p))


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


def fires():
    """Graded Polymarket fires carrying p_venue and BOTH side asks -- both are required."""
    out, drop = [], 0
    for lane, tcol, acol in LANES:
        f = os.path.join(SP, 'db', lane + '.sqlite3')
        if not os.path.exists(f):
            continue
        c = sqlite3.connect(f)
        for ep, ts, side, p, ask, sec, rv60, win, feat in c.execute(
                'select candle_epoch,%s,side,p,%s,sec,rv60,win,feat from trades '
                'where win is not null and feat is not null' % (tcol, acol)):
            if not ask or p is None:
                continue
            d = json.loads(feat)
            pv, au, ad = d.get('p_venue'), d.get('_ask_up'), d.get('_ask_dn')
            ok = d.get('_venue_ok', 1.0)
            if pv is None or au is None or ad is None or not ok or not (0 < pv < 1):
                drop += 1
                continue
            out.append(dict(ep=int(ep), side=side, p=float(p), ask=float(ask),
                            pv=float(pv), au=float(au), ad=float(ad),
                            sec=int(sec) if sec is not None else int(ts) // 1000 - int(ep),
                            rv60=float(rv60) if rv60 is not None else 0.0,
                            win=int(win), lane=lane))
    return out, drop


def apply_transform(f, m):
    """Return (ps_chosen, ask, won, flipped) after the candidate's transform at exponent m."""
    base_up = f['p'] if f['side'] == 'UP' else 1.0 - f['p']
    ratio = f['eng']
    if m == 0.0 or not math.isfinite(ratio) or ratio <= 1.0:
        final_up = base_up
    else:
        anchor = min(0.98, max(0.02, f['pv']))
        trust = min(1.0, 1.0 / (max(ratio, 1.0) ** m))
        b = min(0.99, max(0.01, base_up))
        final_up = min(0.99, max(0.01, sigmoid(logit(anchor) + trust * (logit(b) - logit(anchor)))))
    side = 'UP' if final_up >= 0.5 else 'DOWN'
    flipped = side != f['side']
    ask = f['au'] if side == 'UP' else f['ad']
    ps = final_up if side == 'UP' else 1.0 - final_up
    won = (1 - f['win']) if flipped else f['win']
    return ps, ask, won, flipped


def cell(rows):
    if not rows:
        return None
    v = np.array([R8.per1(x[1], x[2] == 1) for x in rows])
    return len(rows), float(np.mean([x[2] for x in rows])), float(v.mean()), float(v.sum())


def halves(rows):
    g = sorted(rows, key=lambda z: z[4])
    h = len(g) // 2
    return cell(g[:h]), cell(g[h:])


def refire(F, m, only=None):
    out = []
    for f in F:
        if only is not None and not only(f):
            continue
        ps, ask, won, fl = apply_transform(f, m)
        if not (0 < ask < 1):
            continue
        if R8.ev_of(ps, ask) >= R8.threshold(f['rv60']):
            out.append((ps, ask, won, fl, f['ep']))
    return out


def main():
    t0, px = A.second_series()
    r = A.returns_series(t0, px)
    F0, drop = fires()
    F = []
    for f in F0:
        raw, eng = A.ratio_at(t0, r, f['ep'] + f['sec'])
        if raw is None:
            continue
        f['raw'], f['eng'] = raw, eng
        f['ev_s'] = R8.ev_of(f['p'], f['ask'])
        F.append(f)

    print('R-29  the owner\'s v12.16.1 venue-shrink candidate, on the real fire record')
    print('  %d graded Polymarket fires with p_venue, both asks and a reconstructable ratio'
          % len(F))
    print('  (%d dropped for a missing venue price, a missing side ask, or _venue_ok=0)' % drop)
    eng_hi = [f for f in F if f['eng'] > 1.0]
    print('  the transform engages on %d/%d = %.1f%% of fires (engaged ratio > 1)'
          % (len(eng_hi), len(F), 100.0 * len(eng_hi) / len(F)))

    print('\n  IDENTITY CELL FIRST -- m=0 must reproduce the real fire count or nothing below reads')
    ident = refire(F, 0.0)
    print('  m=0 refires %d of %d actual fires, side flips %d' % (
        len(ident), len(F), sum(1 for x in ident if x[3])))

    print('\n  THE GRID  (m=1 is the owner\'s exact transform; m=0 is frozen v10)')
    print('  %-5s %6s %7s %9s %10s %9s %9s %7s' % (
        'm', 'n', 'W%', 'per $1', 'total', 'h1', 'h2', 'flips'))
    for m in MS:
        g = refire(F, m)
        s = cell(g)
        if not s:
            continue
        a, b = halves(g)
        tag = '  <-- candidate' if m == 1.0 else ('  <-- frozen v10' if m == 0.0 else '')
        print('  %-5.1f %6d %6.1f%% %+9.3f %+10.2f %+9.3f %+9.3f %7d%s' % (
            m, s[0], 100 * s[1], s[2], s[3], a[2], b[2], sum(1 for x in g if x[3]), tag))

    print('\n  THE >1 BUCKET, which is the whole test (ratio <= 1 is identical by construction)')
    print('  %-5s %6s %7s %9s %10s %9s %9s' % ('m', 'n', 'W%', 'per $1', 'total', 'h1', 'h2'))
    for m in MS:
        g = refire(F, m, only=lambda f: f['eng'] > 1.0)
        s = cell(g)
        if not s:
            print('  %-5.1f      (no fires)' % m)
            continue
        a, b = halves(g)
        print('  %-5.1f %6d %6.1f%% %+9.3f %+10.2f %+9.3f %+9.3f%s' % (
            m, s[0], 100 * s[1], s[2], s[3], a[2], b[2],
            '' if s[0] >= MIN_CELL else '  INSUFFICIENT'))

    print('\n  CONFIRMING THE <=1 BUCKET IS UNTOUCHED (it must be identical at every m)')
    for m in MS:
        s = cell(refire(F, m, only=lambda f: f['eng'] <= 1.0))
        print('  m=%-4.1f n=%-5d per $1 %+7.3f' % (m, s[0], s[2]) if s else '  m=%.1f empty' % m)

    print('\n  THE R-19 NULL: does it beat "fewer, cheaper fires" at the same fire count?')
    by_ev = sorted(F, key=lambda z: -z['ev_s'])
    print('  %-5s %6s %10s %11s %11s %12s' % (
        'm', 'n', 'cand /$1', 'cand total', 'topEV /$1', 'topEV total'))
    for m in MS:
        g = refire(F, m)
        n = len(g)
        s = cell(g)
        nul = [(x['p'], x['ask'], x['win'], False, x['ep']) for x in by_ev[:n]]
        b = cell(nul)
        print('  %-5.1f %6d %+10.3f %+11.2f %+11.3f %+12.2f' % (m, n, s[2], s[3], b[2], b[3]))


if __name__ == '__main__':
    main()
