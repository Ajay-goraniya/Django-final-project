"""R-27 -- EF parameters per volatility regime. Owner: "in high volatility EF for sure needs
different parameters". Not "don't fire in high vol" - fire and win there with its own parameters.

BUCKETS FIRST, fixed before any number is read: realised vol of the PRIOR 6 candles (30 min),
strictly earlier than the candle being judged, cut at the 33rd/67th percentile of the full sample.
Same buckets for every table below.

SCOPE, and it is a limit worth stating: the sweep is over RESTRICTIONS (a higher EV floor, a lower
max entry price, a narrower fire-second window, a larger |p-0.5|), so every cell is a SUBSET of the
fires the engine already took. That makes it exact on the graded record without reconstructing the
tick universe - but it means the grid can only ever remove fires, never find ones the engine missed.

Polymarket lanes are graded on venues.outcome and Zurich live on its own results; Predict.fun lanes
are excluded rather than pooled, because mixing oracles is the error this project keeps paying for.
"""
import json, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T

SP = T.SP
EVF = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
MAXP = [0.40, 0.50, 0.60, 0.70, 0.80]
SECW = [(0, 30), (30, 45), (45, 60), (60, 300)]
PMIN = [0.0, 0.05, 0.10, 0.15]


def rv6():
    """Realised vol of the 6 candles BEFORE each candle. Strictly earlier - no self-inclusion."""
    d = np.load(os.path.join(SP, 'build', 'paths.npz'))
    cid = (d['cid'] // 1000).astype(np.int64)
    p = d['paths'].astype(float)
    ret = p[:, 299] / p[:, 0] - 1.0
    o = np.argsort(cid)
    cid, ret = cid[o], ret[o]
    out = {}
    for i in range(6, len(cid)):
        if cid[i] - cid[i - 6] == 6 * 300:
            out[int(cid[i])] = float(np.std(ret[i - 6:i]) * 1e4)
    return out


def fires():
    """Every graded Polymarket fire with the fields the grid needs, plus Zurich live."""
    out = []
    for lane, tcol, acol, ecol in (('poly_pnl', 'ts_ms', 'ask', 'ev'),
                                   ('v12_poly_lane', 'signal_ms', 'quote_ask', 'signal_ev'),
                                   ('v12_poly_weekend', 'signal_ms', 'quote_ask', 'signal_ev')):
        f = os.path.join(SP, 'db', lane + '.sqlite3')
        if not os.path.exists(f):
            continue
        c = sqlite3.connect(f)
        for ep, ts, side, p, ask, ev, sec, win in c.execute(
                'select candle_epoch,%s,side,p,%s,%s,sec,win from trades where win is not null'
                % (tcol, acol, ecol)):
            if not ask or p is None:
                continue
            out.append(dict(ep=int(ep), side=side, p=float(p), ask=float(ask),
                            ev=float(ev) if ev is not None else None,
                            sec=int(sec) if sec is not None else int(ts) // 1000 - int(ep),
                            win=int(win), lane=lane))
    return out


def stat(rows):
    if not rows:
        return None
    pnl = np.array([R8.per1(r['ask'], r['win'] == 1) for r in rows])
    return len(rows), float(np.mean([r['win'] for r in rows])), float(pnl.mean()), float(pnl.sum())


def main():
    V = rv6()
    F = [r for r in fires() if r['ep'] in V]
    for r in F:
        r['rv6'] = V[r['ep']]
    vals = np.array([r['rv6'] for r in F])
    lo, hi = np.percentile(vals, 33), np.percentile(vals, 67)
    for r in F:
        r['bucket'] = 'LOW' if r['rv6'] < lo else ('MID' if r['rv6'] < hi else 'HIGH')
    print('R-27  EF parameters per volatility regime')
    print('  %d graded Polymarket fires with a prior-6-candle vol reading' % len(F))
    print('  buckets fixed FIRST: rv6 (bps) cut at the 33rd/67th pct = %.2f / %.2f' % (lo, hi))
    print('\n  THE PLAIN ANSWER: what the CURRENT parameters already do per bucket')
    print('  %-6s %7s %7s %9s %10s %9s' % ('bucket', 'n', 'W%', 'per $1', 'total', 'med ask'))
    for b in ('LOW', 'MID', 'HIGH'):
        g = [r for r in F if r['bucket'] == b]
        s = stat(g)
        if not s or s[0] < MIN_CELL:
            print('  %-6s %7d   insufficient' % (b, len(g))); continue
        print('  %-6s %7d %6.1f%% %+9.3f %+10.2f %9.3f'
              % (b, s[0], 100 * s[1], s[2], s[3], np.median([r['ask'] for r in g])))

    print('\n  FULL GRID per bucket. Every cell; <%d fires marked insufficient.' % MIN_CELL)
    print('  Each cell is a RESTRICTION of the fires already taken.')
    best = {}
    for b in ('LOW', 'MID', 'HIGH'):
        G = [r for r in F if r['bucket'] == b]
        print('\n  === %s (n=%d) ===' % (b, len(G)))
        print('  %-6s %-6s %-9s %-6s %6s %7s %9s %9s'
              % ('evflr', 'maxp', 'secwin', '|p-.5|', 'n', 'W%', 'per $1', 'total'))
        rows = []
        for e in EVF:
            for mp in MAXP:
                for (s0, s1) in SECW:
                    for pm in PMIN:
                        g = [r for r in G if (r['ev'] is None or r['ev'] >= e) and r['ask'] <= mp
                             and s0 <= r['sec'] < s1 and abs(r['p'] - 0.5) >= pm]
                        st = stat(g)
                        rows.append(((e, mp, (s0, s1), pm), st))
        shown = 0
        for k, st in rows:
            if st is None or st[0] < MIN_CELL:
                continue
            shown += 1
            print('  %-6.2f %-6.2f %-9s %-6.2f %6d %6.1f%% %+9.3f %+9.2f'
                  % (k[0], k[1], '%d-%d' % k[2], k[3], st[0], 100 * st[1], st[2], st[3]))
        ins = sum(1 for _, st in rows if st is None or st[0] < MIN_CELL)
        print('  readable cells: %d of %d   (%d insufficient, not read)' % (shown, len(rows), ins))
        best[b] = shown
    print('\n  READABLE-CELL COUNT PER BUCKET: ' + ', '.join('%s %d' % (b, best[b]) for b in best))


if __name__ == '__main__':
    main()
