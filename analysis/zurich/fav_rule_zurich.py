#!/usr/bin/env python3
"""Zurich replication of V's favourite-buyer grid (NC-19, 1e58001, analysis/v/wallets/fav_rule_test.py).

IDENTICAL 36-cell grid, no retune: 3 windows x 3 ask bands x {low, mid, high, all} vol.
Rule, fixed before the run: per candle, the FIRST second in window W where our side is the FAVOURITE
(own ask > opp ask) with own ask in band B, and the candle's trailing-5-min vol at the open in tercile V.
$10 a fire. Whole grid printed, never the best cell.

WHAT IS "OUR SIDE". The rule is model-free - it buys whatever the market calls the favourite, so own = the
side with the strictly HIGHER ask and opp = the other. The `own ask > opp ask` clause is therefore not a
tautology: it drops the seconds where the two asks are equal and there is no favourite to buy.

LABELS ARE VENUE TRUTH, per CLAUDE.md: Polymarket resolution from the gamma mirror, extended by the
archive's own results.actual. Those two agree on 838 of 838 overlapping candles (100.00%), which is why
the union is safe to use; the check is re-run and printed on every run rather than trusted from memory.

FILL, V's spec: +250 ms FAK where decide_log exists, else the same-side ask 1 s later, both filling only
if that later ask is within one tick and filling AT it. "Where decide_log exists" is applied PER FIRE, not
per day: a candle with decide_log rows but none at >= t+250 ms falls back to the 1 s tape rather than being
scored as a no-fill, which would be an artefact of EF's logging window and not of the market.

READ-ONLY. Nothing live, nothing written outside this directory's output file.
"""
import sqlite3, sys, datetime as dt, numpy as np

ARCH  = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE  = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
TICK, RATE, STAKE, DELAY_MS, MIN_VOL_PTS = 0.01, 0.07, 10.0, 250, 60
WINDOWS = ((30, 60), (30, 120), (60, 180))
BANDS   = ((0.65, 0.75), (0.70, 0.80), (0.65, 0.85))
cost = lambda a: a * (1 + RATE * (1 - a))
dayof = lambda e: dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d')


def load():
    a = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    ts, ref, ua, da = map(np.array, zip(*a.execute(
        "SELECT ts, ref_px, up_ask, dn_ask FROM tape1s ORDER BY ts").fetchall()))
    ts = ts.astype(np.int64)
    base, top = int(ts[0]), int(ts[-1])
    n = top - base + 1
    REF = np.full(n, np.nan); UA = np.full(n, np.nan); DA = np.full(n, np.nan)
    k = ts - base
    REF[k] = [np.nan if v is None else v for v in ref]
    UA[k]  = [np.nan if v is None else v for v in ua]
    DA[k]  = [np.nan if v is None else v for v in da]

    # venue truth: gamma mirror, extended by the archive's own label, with the agreement re-measured here
    vo = {}
    for p in GAMMA:
        try:
            g = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            vo.update({int(e): str(o).upper() for e, o in g.execute(
                "SELECT epoch, outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception:
            pass
    res = {int(e): str(v).upper() for e, v in a.execute(
        "SELECT epoch, actual FROM results WHERE actual IS NOT NULL")}
    both = [e for e in res if e in vo]
    agree = sum(1 for e in both if res[e] == vo[e])
    for e, v in res.items():
        vo.setdefault(e, v)

    # decide_log, per candle, for the 250 ms FAK branch
    DL = {}
    for ep, tms, u, d in a.execute(
            "SELECT epoch, ts_ms, up_ask, dn_ask FROM decide_log ORDER BY epoch, ts_ms"):
        DL.setdefault(int(ep), []).append((int(tms), u, d))
    DL = {e: (np.array([r[0] for r in v], dtype=np.int64),
              np.array([np.nan if r[1] is None else r[1] for r in v]),
              np.array([np.nan if r[2] is None else r[2] for r in v])) for e, v in DL.items()}

    try:
        lv = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
        live_eps = {int(e) for (e,) in lv.execute("SELECT DISTINCT epoch FROM orders WHERE lane='LIVE'")}
    except Exception:
        live_eps = set()
    return base, REF, UA, DA, vo, DL, live_eps, (agree, len(both))


def main():
    base, REF, UA, DA, vo, DL, live_eps, (agree, nboth) = load()
    n = len(REF)
    print(f'labels: gamma+archive agree {agree}/{nboth} = {100*agree/max(nboth,1):.2f}% on overlap')

    eps = sorted(e for e in vo if base <= e - 300 and e - base + 300 < n and e % 300 == 0)
    dropped_live = [e for e in eps if e in live_eps]
    eps = [e for e in eps if e not in live_eps]

    # trailing-5-min vol at the open, 1 s log-return std x 1e4, on the settlement reference
    vol, keep = {}, []
    for e in eps:
        w = REF[e - 300 - base: e - base]
        w = w[~np.isnan(w)]
        if len(w) < MIN_VOL_PTS:
            continue
        vol[e] = float(np.std(np.diff(np.log(w))) * 1e4)
        keep.append(e)
    eps = keep
    days = sorted({dayof(e) for e in eps})
    CUT_D, TEST = days[:2], days[2:]
    cv = np.array([vol[e] for e in eps if dayof(e) in CUT_D])
    c1, c2 = np.quantile(cv, [1/3, 2/3])
    test_eps = [e for e in eps if dayof(e) in TEST]
    print(f'candles {len(eps)} | cut days {CUT_D} (n={len(cv)}) -> vol cuts {c1:.3f}/{c2:.3f} | '
          f'test days {TEST} (n={len(test_eps)})')
    if dropped_live:
        print(f'excluded {len(dropped_live)} candle(s) this box traded LIVE on: {sorted(dropped_live)}')

    def ask_at(t, up):
        i = t - base
        if i < 0 or i >= n: return np.nan
        return UA[i] if up else DA[i]

    def later_ask(e, t, up):
        """First same-candle quote at >= t+250 ms from decide_log; else the 1 s tape."""
        d = DL.get(e)
        if d is not None:
            j = int(np.searchsorted(d[0], t * 1000 + DELAY_MS))
            if j < len(d[0]):
                v = (d[1] if up else d[2])[j]
                if not np.isnan(v): return float(v)
        return float(ask_at(t + 1, up))

    rows = []            # one row per candle per (W,B): the first qualifying second
    for W in WINDOWS:
        for B in BANDS:
            for e in test_eps:
                for s in range(W[0], W[1] + 1):
                    au, ad = ask_at(e + s, True), ask_at(e + s, False)
                    if np.isnan(au) or np.isnan(ad) or au == ad: continue
                    up = au > ad
                    own, opp = (au, ad) if up else (ad, au)
                    if not (B[0] <= own <= B[1]): continue
                    lt = later_ask(e, e + s, up)
                    filled = (not np.isnan(lt)) and lt <= own + TICK + 1e-12
                    paid = float(lt) if filled else np.nan
                    win = 1.0 if vo[e] == ('UP' if up else 'DOWN') else 0.0
                    rows.append((W, B, e, dayof(e), vol[e], own, filled, paid, win))
                    break

    hdr = ('window   band        vol    fires /day fill%  win%  paid   $@10    DD   days+  +1c      per day')
    print(hdr)
    buckets = (('low', lambda v: v < c1), ('mid', lambda v: c1 <= v < c2),
               ('high', lambda v: v >= c2), ('all', lambda v: True))
    for W in WINDOWS:
        for B in BANDS:
            for vn, vf in buckets:
                f = [r for r in rows if r[0] == W and r[1] == B and vf(r[4])]
                if not f: continue
                f.sort(key=lambda r: r[2])
                fl   = np.array([r[6] for r in f])
                win  = np.array([r[8] for r in f])
                paid = np.array([r[7] for r in f])
                pn = np.where(fl, STAKE * (win / np.array([cost(p) if fl[i] else 1.0
                                                           for i, p in enumerate(paid)]) - 1), 0.0)
                p1 = np.where(fl, STAKE * (win / np.array([cost(min(p + .01, .99)) if fl[i] else 1.0
                                                           for i, p in enumerate(paid)]) - 1), 0.0)
                cum = np.cumsum(pn)
                dd = float(np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]))
                per = [pn[[i for i, r in enumerate(f) if r[3] == d]].sum() for d in TEST]
                wr = 100 * win[fl].mean() if fl.any() else 0
                pa = paid[fl].mean() if fl.any() else 0
                print(f'{W[0]:3d}-{W[1]:<3d}  {B[0]:.2f}-{B[1]:.2f}  {vn:5s} {len(f):5d} {len(f)/len(TEST):5.0f} '
                      f'{100*fl.mean():4.0f}  {wr:4.0f}  {pa:.3f} {pn.sum():+7.1f} {dd:6.1f}  '
                      f'{sum(v > 0 for v in per)}/{len(TEST)} {p1.sum():+7.1f}  '
                      + ' '.join(f'{v:+.0f}' for v in per))
    if '--checks' in sys.argv:
        checks(rows, TEST, c1, c2)


def per1(f):
    """$ per $1 STAKED across all fires - unfilled fires stake nothing but are counted, as in the grid."""
    if not f: return 0.0
    pn = sum(STAKE * (r[8] / cost(r[7]) - 1) for r in f if r[6])
    return pn / (STAKE * len(f))


def checks(rows, TEST, c1, c2):
    """The three questions the grid alone cannot answer."""
    print()
    print('=' * 100)
    print('CHECK 1 - does the VOL filter add anything, or is this just "buy the favourite"?')
    print('  cell                      n_low  per$1 low | n_all  per$1 all |  lift   n_mid  n_high  per$1 mid/high')
    for W in WINDOWS:
        for B in BANDS:
            f = [r for r in rows if r[0] == W and r[1] == B]
            lo = [r for r in f if r[4] < c1]; mi = [r for r in f if c1 <= r[4] < c2]; hi = [r for r in f if r[4] >= c2]
            print(f'  {W[0]:3d}-{W[1]:<3d} {B[0]:.2f}-{B[1]:.2f}   {len(lo):5d} {per1(lo):+7.3f}   | {len(f):5d} '
                  f'{per1(f):+7.3f}   | {per1(lo)-per1(f):+6.3f}  {len(mi):5d}  {len(hi):5d}  '
                  f'{per1(mi):+6.3f} {per1(hi):+6.3f}')

    print()
    print('CHECK 2 - PERMUTATION. Shuffle vol across candles, keeping every fire, price and outcome as it is,')
    print('  and re-cut the terciles. If vol carries no information the real low-bucket lift is unremarkable.')
    rng = np.random.default_rng(0)
    for W, B in ((( 60, 180), (0.65, 0.85)), ((30, 120), (0.70, 0.80)), ((30, 60), (0.65, 0.75))):
        f = [r for r in rows if r[0] == W and r[1] == B]
        eps = sorted({r[2] for r in f}); vmap = {r[2]: r[4] for r in f}
        real = per1([r for r in f if r[4] < c1]) - per1(f)
        vals = np.array([vmap[e] for e in eps])
        null = []
        for _ in range(2000):
            sh = rng.permutation(vals); m = {e: v for e, v in zip(eps, sh)}
            null.append(per1([r for r in f if m[r[2]] < c1]) - per1(f))
        null = np.array(null); pv = float((null >= real).mean())
        print(f'  {W[0]:3d}-{W[1]:<3d} {B[0]:.2f}-{B[1]:.2f}  real lift {real:+.4f}  '
              f'null mean {null.mean():+.4f} sd {null.std():.4f}  p = {pv:.4f}')

    print()
    print('CHECK 3 - HALVES. Test candles split in two by time; a real effect survives both.')
    print('  cell                      H1 n   H1 per$1 | H2 n   H2 per$1 | sign agrees')
    for W in WINDOWS:
        for B in BANDS:
            f = sorted([r for r in rows if r[0] == W and r[1] == B and r[4] < c1], key=lambda r: r[2])
            if len(f) < 60: continue
            h = len(f) // 2; a, b = f[:h], f[h:]
            print(f'  {W[0]:3d}-{W[1]:<3d} {B[0]:.2f}-{B[1]:.2f} low {len(a):5d} {per1(a):+8.3f}  | {len(b):5d} '
                  f'{per1(b):+8.3f}  | {"yes" if per1(a)*per1(b) > 0 else "NO"}')


if __name__ == '__main__':
    main()
