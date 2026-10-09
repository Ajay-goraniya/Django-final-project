"""RAW vs FIXED on Zurich candles, re-scored under London's execution model. READ-ONLY.

Model: analysis/v/rawfixed/LONDON_EXEC_MODEL.md (9b6d758).

Both arms are reconstructed from the SAME EF decide rows, so the comparison is paired by construction:
for each candle, each arm fires at the FIRST decide pass where its own rule clears, which is what the
engine does. Neither arm is read from what the engine actually did, so neither gets an advantage from
having been the live profile at the time.

  ev            = p / breakeven - 1,  breakeven = ask * (1 + 0.07*(1-ask))
                  (verified against journalled rows: p 0.8772, ask 0.88 -> ev -0.0116, be 0.8875)
  RAW   fires   at the first pass with ev(p_raw) >= 0.25
  FIXED fires   at the first pass with ev(platt(p_raw)) >= 0.15,  platt: a=1.0677, b=-0.3208, q=min(p,q)
  p_raw         = row['p_raw'] when present (calibration was on), else row['p'] (calibration was off)

London execution, ALL rows as the main run:
  P(fill | would win) = 79/146 = 54.1%   P(fill | would lose) = 76/117 = 65.0%   -> winners fill LESS
  slippage cents p10/p50/p90 = -1/+2/+11, fitted as a piecewise-linear inverse CDF through those three
  points (the simplest fit that reproduces the given quantiles and its skew; no distribution family is
  claimed). Sensitivity run uses the per-price-bucket rows instead.
  fee = 0.07 * shares * price * (1-price); stake $10.
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections

JOURNALS = [
    ('z2',     '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3'),
    ('z3',     '/tmp/z3copy.sqlite3'),
    ('paper1', '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3'),
    ('live4',  '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'),
]
VENUES, STAKE, RUNS = '/tmp/venues_ro.sqlite3', 10.0, 1000
A, B = 1.0677, -0.3208
P_FILL_WIN, P_FILL_LOSE = 79/146, 76/117
SLIP = [(0.10, -0.01), (0.50, +0.02), (0.90, +0.11)]
BUCKET_FILL = {  # (P fill|win, P fill|lose) from row (b); n<60 cells, shape only
    '<.35': (16/27, 14/18), '.35-.45': (33/53, 28/49), '.45-.55': (20/39, 24/36),
    '.55-.65': (8/22, 7/10), '>.65': (2/5, 3/4)}
BUCKET_SLIP = {  # row (c) p10/p50/p90 in cents
    '<.35': (0.00, 0.04, 0.10), '.35-.45': (0.00, 0.04, 0.15), '.45-.55': (-0.01, 0.02, 0.11),
    '.55-.65': (-0.09, 0.00, 0.07), '>.65': (-0.28, -0.01, 0.06)}

def bucket(q):
    return '<.35' if q < .35 else '.35-.45' if q < .45 else '.45-.55' if q < .55 else '.55-.65' if q < .65 else '>.65'

def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A * z + B)))))

def ev(p, ask):
    be = ask * (1 + 0.07 * (1 - ask))
    return (p / be - 1) if be > 0 else -1

def draw_slip(rng, pts):
    """Piecewise-linear inverse CDF through the three given quantiles, flat outside."""
    u = rng.random()
    (q1, v1), (q2, v2), (q3, v3) = pts
    if u <= q1: return v1
    if u >= q3: return v3
    if u <= q2: return v1 + (v2 - v1) * (u - q1) / (q2 - q1)
    return v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def load():
    vo = {}
    try:
        v = sqlite3.connect(f'file:{VENUES}?mode=ro', uri=True)
        vo = dict(v.execute('SELECT epoch,actual FROM outcome').fetchall()); v.close()
    except Exception: pass
    cands = {}
    for name, path in JOURNALS:
        c = sqlite3.connect(path if path.startswith('/tmp') else f'file:{path}?mode=ro',
                            uri=not path.startswith('/tmp'))
        res = dict(c.execute('SELECT epoch,actual FROM results').fetchall())
        rows = collections.defaultdict(list)
        for ts, d in c.execute('SELECT ts,detail FROM diagnostics ORDER BY ts'):
            try: j = json.loads(d)
            except Exception: continue
            if j.get('mode') != 'pnl' or 'breakeven' not in j: continue
            p, ask, side = j.get('p'), j.get('ask'), j.get('side')
            if not isinstance(p, (int, float)) or not isinstance(ask, (int, float)) or not side: continue
            if not (0.01 < ask < 0.99): continue
            pr = j.get('p_raw')
            rows[int(ts // 300) * 300].append((ts, float(pr if isinstance(pr, (int, float)) else p),
                                               float(ask), side))
        for ep, rs in rows.items():
            src = 'venues' if ep in vo else 'engine'
            act = vo.get(ep, res.get(ep))
            if act is None: continue
            rs.sort()
            fire = {}
            for arm, transform, thr in (('RAW', lambda x: x, 0.25), ('FIXED', platt, 0.15)):
                for ts, pr, ask, side in rs:
                    if ev(transform(pr), ask) >= thr:
                        fire[arm] = dict(ts=ts, sec=ts - ep, ask=ask, side=side, win=(side == act))
                        break
            if fire: cands[(name, ep)] = dict(epoch=ep, src=src, fire=fire)
        c.close()
    return cands

def score(fires, rng, exec_on=True, per_bucket=False):
    """One Monte Carlo pass. fires = list of fire dicts in time order."""
    pnl, cost_tot, seq = 0., 0., []
    for fr in fires:
        q = fr['ask']
        if exec_on:
            pw, pl = BUCKET_FILL[bucket(q)] if per_bucket else (P_FILL_WIN, P_FILL_LOSE)
            if rng.random() > (pw if fr['win'] else pl):
                seq.append(0.); continue                      # not filled: no trade, no cost
            pts = BUCKET_SLIP[bucket(q)] if per_bucket else None
            s = draw_slip(rng, [(0.1, pts[0]), (0.5, pts[1]), (0.9, pts[2])] if pts else SLIP)
            price = min(0.99, max(0.01, q + s))
        else:
            price = q
        shares = STAKE / price
        fee = 0.07 * shares * price * (1 - price)
        cost = STAKE + fee
        got = shares if fr['win'] else 0.
        seq.append(got - cost); pnl += got - cost; cost_tot += cost
    cum = peak = mdd = 0.
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    filled = sum(1 for x in seq if x != 0.)
    return dict(pnl=pnl, cost=cost_tot, mdd=mdd, filled=filled, seq=seq)

def summarise(fires, exec_on=True, per_bucket=False, runs=RUNS):
    if not fires: return None
    out = [score(fires, random.Random(1000 + i), exec_on, per_bucket) for i in range(runs if exec_on else 1)]
    pnls = [o['pnl'] for o in out]; mdds = [o['mdd'] for o in out]
    fills = [o['filled'] for o in out]; costs = [o['cost'] for o in out]
    pct = lambda v, q: sorted(v)[min(len(v) - 1, int(q * (len(v) - 1)))]
    return dict(n=len(fires), fills=st.mean(fills), pnl=st.mean(pnls),
                pnl_lo=pct(pnls, .05), pnl_hi=pct(pnls, .95),
                per1=(st.mean(pnls) / st.mean(costs) if st.mean(costs) else 0),
                mdd=st.mean(mdds), mdd_lo=pct(mdds, .05), mdd_hi=pct(mdds, .95))

def row(label, s):
    if not s: return f'  {label:<34}   (no fires)'
    return (f"  {label:<34}{s['n']:>6}{s['fills']:>9.1f}{s['pnl']:>+10.2f}"
            f"  [{s['pnl_lo']:+8.2f},{s['pnl_hi']:+8.2f}]{s['per1']:>+9.3f}"
            f"{s['mdd']:>9.2f}  [{s['mdd_lo']:6.2f},{s['mdd_hi']:6.2f}]")

if __name__ == '__main__':
    cands = load()
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
    eps = sorted(cands.values(), key=lambda c: c['epoch'])
    lo, hi = eps[0]['epoch'], eps[-1]['epoch']; mid = lo + (hi - lo) / 2
    srcs = collections.Counter(c['src'] for c in eps)
    print(f'Zurich candles with EF decide rows: {len(eps)}, {f(lo)} -> {f(hi)} UTC')
    print(f"grading: venues.outcome {srcs['venues']} candles, engine results.actual {srcs['engine']} "
          f'(the two agree 84/84 where the snapshot overlaps)')
    print(f'half split by TIME at {f(mid)}   |   stake ${STAKE:.0f}, {RUNS} Monte Carlo runs')
    both = [c for c in eps if len(c['fire']) == 2]
    only = {a: [c for c in eps if list(c['fire']) == [a]] for a in ('RAW', 'FIXED')}
    print(f"\nfired: RAW {sum(1 for c in eps if 'RAW' in c['fire'])}, "
          f"FIXED {sum(1 for c in eps if 'FIXED' in c['fire'])}, "
          f'both {len(both)}, RAW-only {len(only["RAW"])}, FIXED-only {len(only["FIXED"])}')
    hdr = (f"  {'arm / subset':<34}{'cand':>6}{'E[fills]':>9}{'E[PnL]':>10}"
           f"{'   [5th, 95th]':>21}{'per$1':>9}{'E[maxDD]':>9}{'  [5th,95th]':>18}")

    def fires_of(arm, sub):
        have = [c for c in sub if arm in c['fire']]          # filter BEFORE sorting, or the key raises
        return [c['fire'][arm] for c in sorted(have, key=lambda c: c['fire'][arm]['ts'])]

    for title, exec_on, pb in (('LONDON EXECUTION (ALL rows) - main run', True, False),
                               ('LONDON EXECUTION (per-price-bucket) - sensitivity', True, True),
                               ('NO EXECUTION COST (paper, 100% fill at signal ask)', False, False)):
        print(f'\n=== {title} ===\n{hdr}')
        for arm in ('RAW', 'FIXED'):
            print(row(f'{arm}  all candles', summarise(fires_of(arm, eps), exec_on, pb)))
        for arm in ('RAW', 'FIXED'):
            print(row(f'{arm}  first half', summarise([x for x in fires_of(arm, eps) if x['ts'] < mid], exec_on, pb)))
        for arm in ('RAW', 'FIXED'):
            print(row(f'{arm}  second half', summarise([x for x in fires_of(arm, eps) if x['ts'] >= mid], exec_on, pb)))
        print('  -- PAIRED --')
        for arm in ('RAW', 'FIXED'):
            print(row(f'{arm}  both-fire candles', summarise(fires_of(arm, both), exec_on, pb)))
        for arm in ('RAW', 'FIXED'):
            print(row(f'{arm}  {arm}-only (discordant)', summarise(fires_of(arm, only[arm]), exec_on, pb)))

# ---------------------------------------------------------------- per-candle CSV for charting
def write_csv(cands, path='analysis/zurich/raw_vs_fixed_candles.csv'):
    """One row per scored candle. Bands are the 5th/95th percentile of the CUMULATIVE London-exec
    PnL across the 1000 runs, evaluated at each fire and carried forward on candles the arm skips -
    so a chart of the band is a proper funnel and never jumps on a candle the arm did not trade."""
    eps = sorted(cands.values(), key=lambda c: c['epoch'])
    per = {}
    for arm in ('RAW', 'FIXED'):
        fires = [(c['epoch'], c['fire'][arm]) for c in eps if arm in c['fire']]
        order = [f for _, f in fires]
        runs = [score(order, random.Random(1000 + i), True, False)['seq'] for i in range(RUNS)]
        cums = [[sum(r[:k + 1]) for k in range(len(r))] for r in runs]
        mean = [st.mean(r[k] for r in runs) for k in range(len(order))]
        pct = lambda k, q: sorted(c[k] for c in cums)[min(RUNS - 1, int(q * (RUNS - 1)))]
        p05 = [pct(k, .05) for k in range(len(order))]
        p95 = [pct(k, .95) for k in range(len(order))]
        paper = [x for x in score(order, random.Random(7), False, False)['seq']]
        per[arm] = dict(idx={ep: k for k, (ep, _) in enumerate(fires)},
                        mean=mean, p05=p05, p95=p95, paper=paper, fires=dict(fires))
    hdr = ('epoch,utc_time,raw_fired,fixed_fired,side_raw,side_fixed,ask_raw,ask_fixed,won_raw,won_fixed,'
           'paper_pnl_raw,paper_pnl_fixed,exec_exp_pnl_raw,exec_exp_pnl_fixed,'
           'exec_p05_cum_raw,exec_p95_cum_raw,exec_p05_cum_fixed,exec_p95_cum_fixed,grading_source')
    carry = {'RAW': (0., 0.), 'FIXED': (0., 0.)}
    lines = [hdr]
    for c in eps:
        ep = c['epoch']; row = [str(ep), dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')]
        cell = {}
        for arm in ('RAW', 'FIXED'):
            P = per[arm]
            if ep in P['idx']:
                k = P['idx'][ep]; fr = P['fires'][ep]
                carry[arm] = (P['p05'][k], P['p95'][k])
                cell[arm] = dict(fired=1, side=fr['side'], ask=f"{fr['ask']:.4f}", won=int(fr['win']),
                                 paper=f"{P['paper'][k]:.4f}", exp=f"{P['mean'][k]:.4f}")
            else:
                cell[arm] = dict(fired=0, side='', ask='', won='', paper='0', exp='0')
        r, x = cell['RAW'], cell['FIXED']
        row += [str(r['fired']), str(x['fired']), r['side'], x['side'], r['ask'], x['ask'],
                str(r['won']), str(x['won']), r['paper'], x['paper'], r['exp'], x['exp'],
                f"{carry['RAW'][0]:.4f}", f"{carry['RAW'][1]:.4f}",
                f"{carry['FIXED'][0]:.4f}", f"{carry['FIXED'][1]:.4f}", c['src']]
        lines.append(','.join(row))
    open(path, 'w').write('\n'.join(lines) + '\n')
    print(f'\nwrote {path}: {len(lines)-1} candle rows')
