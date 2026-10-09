"""Dynamic staking grid on the Zurich EF shadow journals. BACKTEST ONLY - touches no engine.

Implements analysis/v/staking/STAKING_GRID_SPEC.md (V, 09-26). Arms A-G, paired (every arm takes
every trade), equal capital deployed as arm A, B/F parameters fitted on the first half by time and
scored on the second. Full grid printed; no cell selected.

No stake rule reads p, EV or any model score - per the spec, only money state, entry price, or
market state. Arm G's sigma is realised volatility of the previous 12 BTC 5-min candles, all of
which close before the fire.

Per-trade return is stake-invariant: fees are proportional to shares and shares to stake, so
per$1 = (payout - cost)/cost scales linearly and a stake S gives S * per$1. The [3, 50] engine
limits are applied AFTER normalisation, so the deployed total is reported rather than assumed.
"""
import sqlite3, json, math, statistics as st, datetime as dt, collections

JOURNALS = [
    ('z1',     '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3'),
    ('z2',     '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3'),
    ('z3',     '/tmp/z3copy.sqlite3'),
    ('paper1', '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3'),
    ('live4',  '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'),
]
BASE, MIN_ST, MAX_ST, START_EQ, MIN_CELL = 5.0, 3.0, 50.0, 50.0, 60

def load():
    trades, candles = [], {}
    for name, path in JOURNALS:
        c = sqlite3.connect(path if path.startswith('/tmp') else f'file:{path}?mode=ro',
                            uri=not path.startswith('/tmp'))
        c.row_factory = sqlite3.Row
        for r in c.execute('SELECT epoch,close FROM candles WHERE close IS NOT NULL'):
            candles[r['epoch']] = float(r['close'])
        res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
        for r in c.execute("""SELECT o.epoch,o.ts,o.plan,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe
                              FROM orders o JOIN fills f ON f.order_id=o.id
                              WHERE o.status='FILLED' AND o.kind='EF' GROUP BY o.id"""):
            a = res.get(r['epoch'])
            if a is None: continue
            side = (c.execute("SELECT side FROM signals WHERE epoch=? AND kind='EF' LIMIT 1",
                              (r['epoch'],)).fetchone() or [None])[0]
            cost = (r['sp'] or 0.) + (r['fe'] or 0.)
            if side is None or not cost or not r['sh']: continue
            entry = r['sp'] / r['sh']                       # price actually paid per share
            if not (0.01 < entry < 0.99): continue
            win = (side == a)
            trades.append(dict(ts=r['ts'], epoch=r['epoch'], entry=entry, win=win,
                               per1=(((r['sh'] or 0.) if win else 0.) - cost) / cost))
        c.close()
    trades.sort(key=lambda t: t['ts'])
    return trades, candles

def sigma_before(epoch, candles, n=12):
    """Realised vol of the n 5-min candles that CLOSED before this candle opened."""
    px = [candles[epoch - 300 * k] for k in range(1, n + 2) if (epoch - 300 * k) in candles]
    if len(px) < 6: return None
    px = px[::-1]
    rets = [math.log(b / a) for a, b in zip(px, px[1:]) if a > 0 and b > 0]
    return st.pstdev(rets) if len(rets) >= 5 and st.pstdev(rets) > 0 else None

def run(trades, raw_fn, normalise=True):
    """raw_fn(trade, equity, hist) -> unclipped, unnormalised stake. Returns per-trade stakes+pnl."""
    raws, eq, hist = [], START_EQ, []
    for t in trades:
        s = raw_fn(t, eq, hist)
        raws.append(s); hist.append(t); eq += BASE * t['per1']      # equity path for non-compounding arms
    scale = (BASE * len(trades)) / sum(raws) if normalise and sum(raws) else 1.0
    out, eq = [], START_EQ
    for t, s in zip(trades, raws):
        stake = min(MAX_ST, max(MIN_ST, s * scale))
        pnl = stake * t['per1']
        out.append(dict(ts=t['ts'], stake=stake, pnl=pnl)); eq += pnl
    return out

def run_compound(trades, f):
    out, eq = [], START_EQ
    for t in trades:
        stake = min(MAX_ST, max(MIN_ST, f * eq))
        pnl = stake * t['per1']
        out.append(dict(ts=t['ts'], stake=stake, pnl=pnl)); eq += pnl
    return out

def stats(rows):
    if not rows: return None
    cum = peak = mdd = 0.
    for r in rows:
        cum += r['pnl']; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    day = collections.defaultdict(float)
    for r in rows:
        day[dt.datetime.fromtimestamp(r['ts'], dt.timezone.utc).strftime('%m-%d')] += r['pnl']
    return dict(n=len(rows), pnl=cum, mdd=mdd, ratio=(cum / mdd if mdd else float('inf')),
                worst_day=min(day.values()), deployed=sum(r['stake'] for r in rows))

def half(rows, lo, hi):
    return [r for r in rows if lo <= r['ts'] < hi]

# ---------------------------------------------------------------- arms
def arms(trades, candles, fit_hi):
    """fit_hi = end of the FIRST half; B and F parameters are chosen using only trades before it."""
    A = dict(name='A fixed $5', rows=run(trades, lambda t, e, h: BASE, normalise=False))

    def eq_at(hist, rows_pnl):  # equity used by F's moving average
        return START_EQ + sum(rows_pnl)

    # --- B: bankroll %, compounding. Fit f on the first half only.
    fits = {}
    first = [t for t in trades if t['ts'] < fit_hi]
    for f in (.02, .04, .06, .08, .10, .15):
        s = stats(run_compound(first, f))
        fits[f] = s['pnl'] / s['mdd'] if s and s['mdd'] else -1e9
    f_star = max(fits, key=fits.get)

    # --- F: half stake while equity below its MA(k). Fit k on the first half only.
    def f_rows(k, tr):
        out, eq, curve = [], START_EQ, []
        raws = []
        for t in tr:
            ma = st.mean(curve[-k:]) if len(curve) >= k else None
            raws.append(BASE * (0.5 if (ma is not None and eq < ma) else 1.0))
            eq += BASE * t['per1']; curve.append(eq)
        scale = (BASE * len(tr)) / sum(raws) if sum(raws) else 1.0
        for t, s in zip(tr, raws):
            stake = min(MAX_ST, max(MIN_ST, s * scale))
            out.append(dict(ts=t['ts'], stake=stake, pnl=stake * t['per1']))
        return out
    kfits = {}
    for k in (10, 20, 40):
        s = stats(f_rows(k, first))
        kfits[k] = s['pnl'] / s['mdd'] if s and s['mdd'] else -1e9
    k_star = max(kfits, key=kfits.get)

    sig = {t['epoch']: sigma_before(t['epoch'], candles) for t in trades}
    med_sig = st.median([v for v in sig.values() if v]) or 1.0

    out = [A,
        dict(name=f'B bankroll {f_star*100:.0f}% (norm)',
             rows=run(trades, lambda t, e, h: max(1e-9, f_star * e), normalise=True)),
        dict(name=f'B bankroll {f_star*100:.0f}% (compounding, un-normalised)',
             rows=run_compound(trades, f_star)),
        dict(name='C fixed shares (stake ~ entry)',
             rows=run(trades, lambda t, e, h: t['entry'], normalise=True)),
        dict(name='D fixed win target (~ entry/(1-entry))',
             rows=run(trades, lambda t, e, h: t['entry'] / (1 - t['entry']), normalise=True)),
        dict(name='E cheap-entry tilt (~ 1-entry)',
             rows=run(trades, lambda t, e, h: 1 - t['entry'], normalise=True)),
        dict(name=f'F de-risk below MA({k_star})', rows=f_rows(k_star, trades)),
        dict(name='G vol scaled (~ 1/sigma)',
             rows=run(trades, lambda t, e, h: 1.0 / (sig.get(t['epoch']) or med_sig), normalise=True)),
    ]
    return out, f_star, k_star, fits, kfits

if __name__ == '__main__':
    trades, candles = load()
    lo, hi = trades[0]['ts'], trades[-1]['ts']
    mid = lo + (hi - lo) / 2
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'Zurich EF shadow journals. {len(trades)} graded EF fills, {f(lo)} -> {f(hi)} UTC')
    print(f'First half {f(lo)} -> {f(mid)} | Second half {f(mid)} -> {f(hi)} (split by TIME)')
    A, f_star, k_star, fits, kfits = arms(trades, candles, mid)
    print(f'\nB fit on FIRST HALF ONLY, pnl/maxDD by f: ' +
          '  '.join(f'{int(k*100)}%:{v:+.2f}' for k, v in sorted(fits.items())) + f'  -> chose {int(f_star*100)}%')
    print(f'F fit on FIRST HALF ONLY, pnl/maxDD by k:  ' +
          '  '.join(f'{k}:{v:+.2f}' for k, v in sorted(kfits.items())) + f'  -> chose {k_star}')
    hdr = f"{'arm':<42}{'n':>5}{'deployed':>10}{'totPnL':>10}{'maxDD':>9}{'P/DD':>8}{'1st half':>10}{'2nd half':>10}{'worst day':>11}"
    for scope, sel in (('FULL PERIOD', lambda r: r), ('SECOND HALF (scoring)', lambda r: half(r, mid, hi + 1))):
        print(f'\n=== {scope} ===\n{hdr}')
        for a in A:
            s = stats(sel(a['rows']))
            if not s: continue
            s1 = stats(half(a['rows'], lo, mid)); s2 = stats(half(a['rows'], mid, hi + 1))
            mark = '  INSUFFICIENT' if s['n'] < MIN_CELL else ''
            print(f"{a['name']:<42}{s['n']:>5}{s['deployed']:>10.0f}{s['pnl']:>+10.2f}{s['mdd']:>9.2f}"
                  f"{s['ratio']:>8.2f}{(s1['pnl'] if s1 else 0):>+10.2f}{(s2['pnl'] if s2 else 0):>+10.2f}"
                  f"{s['worst_day']:>+11.2f}{mark}")
