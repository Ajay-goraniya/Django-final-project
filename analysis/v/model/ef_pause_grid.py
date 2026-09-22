"""EF drawdown-pause grid on the stored v10 EF fires (owner, 09-22 22:5x: "profitable ef that has no drawdowns
by tomorrow ... you can stop trading in drawdown period or when market is wrong for us ... but don't waste profit").

A pause is a regime switch, so every bucket and every cell of the grid is defined here, before any result is
read, and the whole grid is printed. Fires: poly_pnl.sqlite3 `trades` (paper EF fires with p, ask, sec, rv60),
graded on venues.outcome (Polymarket's own resolution), fee 1.67%, fixed $3 stake. A loss is only KNOWN at the
candle close (epoch+300 s): a pause rule may only look at fires whose candle closed before the new fire's ts.

Usage: python3 ef_pause_grid.py --pnl poly_pnl.sqlite3 --venues venues.sqlite3
"""
import argparse, sqlite3, math, random, statistics as st, datetime as dt
from collections import defaultdict

ap = argparse.ArgumentParser(); ap.add_argument('--pnl', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--stake', type=float, default=3.0); ap.add_argument('--shuffles', type=int, default=200)
a = ap.parse_args()
FEE, MARGIN, MAX_ASK = 0.0167, 0.06, 0.60
A_PLATT, B_PLATT = 1.0677, -0.3208            # H1 EF_BRAIN.md D, pooled on 1108 venue-graded fires

out = dict(sqlite3.connect(a.venues).execute('select epoch,actual from outcome'))
rows = []
for ep, ts_ms, side, p, ask, sec, rv60 in sqlite3.connect(a.pnl).execute(
        'select candle_epoch,ts_ms,side,p,ask,sec,rv60 from trades where win is not null order by ts_ms'):
    act = out.get(int(ep))
    if act is None or ask is None or p is None or ask <= 0 or ask >= 1: continue
    win = int(str(act).upper() == str(side).upper())
    per1 = ((1 - FEE) / ask - 1) if win else -1.0
    z = math.log(p / (1 - p)); pc = 1 / (1 + math.exp(-(A_PLATT * z + B_PLATT))); pc = min(p, pc)
    rows.append(dict(ep=int(ep), ts=ts_ms / 1000.0, close=int(ep) + 300, side=side, p=float(p), p_cal=pc, ask=float(ask),
                     sec=int(sec or 0), rv60=(float(rv60) if rv60 is not None else None), win=win, per1=per1,
                     day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d'),
                     hour=dt.datetime.utcfromtimestamp(int(ep)).hour))
rows.sort(key=lambda r: r['ts'])
print(f'fires {len(rows)} graded on venues.outcome, {rows[0]["day"]} -> {rows[-1]["day"]}, days {len(set(r["day"] for r in rows))}')

def stats(R, label):
    if not R: print(f'{label:38s} none'); return None
    v = [r['per1'] * a.stake for r in R]; cum = 0; peak = 0; dd = 0; run = 0; worst = 0
    for r in R:
        cum += r['per1'] * a.stake; peak = max(peak, cum); dd = max(dd, peak - cum)
        run = run + 1 if not r['win'] else 0; worst = max(worst, run)
    days = defaultdict(list)
    for r in R: days[r['day']].append(r['per1'])
    dstr = ' '.join(f'{st.mean(days[d]):+.2f}' for d in sorted(days))
    neg = sum(1 for d in days if st.mean(days[d]) < 0)
    print(f'{label:38s} n={len(R):4d} W={100*st.mean(x["win"] for x in R):5.1f}% per$1={st.mean(x["per1"] for x in R):+.3f} '
          f'total={sum(v):+7.2f} maxDD={dd:6.2f} run={worst:2d} negdays={neg}/{len(days)} | {dstr}')
    return dict(n=len(R), total=sum(v), dd=dd)

print('\n## base arms')
base = stats(rows, 'raw v10 EF (all fires)')
cal = [r for r in rows if r['ask'] <= MAX_ASK and r['p_cal'] >= r['ask'] + MARGIN + FEE]
calst = stats(cal, 'calibrated p (pooled a,b), same rule')

print('\n## clustering: do losses cluster? (lag autocorrelation of win, permutation p; runs test)')
def acf(x, k):
    m = st.mean(x); num = sum((x[i] - m) * (x[i + k] - m) for i in range(len(x) - k)); den = sum((xi - m) ** 2 for xi in x)
    return num / den if den else 0.0
for label, R in (('raw', rows), ('calibrated', cal)):
    x = [r['win'] for r in R]
    for k in (1, 2, 3, 5):
        obs = acf(x, k); cnt = 0
        for _ in range(a.shuffles):
            y = x[:]; random.shuffle(y)
            if abs(acf(y, k)) >= abs(obs): cnt += 1
        print(f'  {label:11s} lag{k}: acf={obs:+.3f} perm p={cnt/a.shuffles:.2f}')
    runs = 1 + sum(1 for i in range(1, len(x)) if x[i] != x[i - 1]); n1 = sum(x); n0 = len(x) - n1
    mu = 1 + 2 * n1 * n0 / len(x); var = 2 * n1 * n0 * (2 * n1 * n0 - len(x)) / (len(x) ** 2 * (len(x) - 1))
    print(f'  {label:11s} runs={runs} expected={mu:.1f} z={(runs-mu)/math.sqrt(var):+.2f}  (z<0 = losses/wins cluster)')

def apply_pause(R, L=None, M=None, X=None, W=10):
    """Fires kept under a pause rule that only sees candles CLOSED before the fire."""
    kept = []; taken = []   # taken: fires actually placed (the rule sees only its own history)
    for r in R:
        settled = [t for t in taken if t['close'] <= r['ts']]
        paused = False
        if L is not None:
            k = 0
            for t in reversed(settled):
                if t['win']: break
                k += 1
            if k >= L:
                last_close = max(t['close'] for t in settled[-k:]); paused = r['ts'] < last_close + M * 60
        if X is not None and len(settled) >= W:
            if sum(t['per1'] for t in settled[-W:]) < -X: paused = True
        if not paused: kept.append(r); taken.append(r)
    return kept

def null_removal(R, n_keep, shuffles):
    tot = []; dds = []
    for _ in range(shuffles):
        S = sorted(random.sample(R, n_keep), key=lambda r: r['ts']); cum = peak = dd = 0
        for r in S:
            cum += r['per1'] * a.stake; peak = max(peak, cum); dd = max(dd, peak - cum)
        tot.append(cum); dds.append(dd)
    dds.sort(); return st.mean(tot), st.mean(dds), dds[int(0.05 * len(dds))]

for label, R in (('RAW', rows), ('CALIBRATED', cal)):
    print(f'\n## pause grid on {label} (null = random removal of the same number of fires: mean total, mean maxDD, p5 maxDD)')
    for L in (2, 3, 4):
        for M in (15, 30, 60, 120):
            K = apply_pause(R, L=L, M=M); s = stats(K, f'  after {L} losses pause {M:3d} min')
            if s: nt, nd, nd5 = null_removal(R, s['n'], a.shuffles); print(f'{"":38s} null: total={nt:+7.2f} maxDD={nd:6.2f} p5={nd5:6.2f}')
    for X in (2, 3, 4):
        K = apply_pause(R, X=X); s = stats(K, f'  pause while last-10 pnl < -{X} stakes')
        if s: nt, nd, nd5 = null_removal(R, s['n'], a.shuffles); print(f'{"":38s} null: total={nt:+7.2f} maxDD={nd:6.2f} p5={nd5:6.2f}')

print('\n## market-wrong buckets (defined first; * = n<60)')
def bucketize(R, key, edges, names):
    for lo, hi, nm in zip(edges[:-1], edges[1:], names):
        S = [r for r in R if r[key] is not None and lo <= r[key] < hi]
        stats(S, f'  {key} {nm}' + ('*' if len(S) < 60 else ''))
for label, R in (('RAW', rows), ('CALIBRATED', cal)):
    print(f'-- {label}')
    rv = sorted(r['rv60'] for r in R if r['rv60'] is not None)
    if rv:
        t1, t2 = rv[len(rv) // 3], rv[2 * len(rv) // 3]
        bucketize(R, 'rv60', [-1e9, t1, t2, 1e9], [f'low<{t1:.2f}', f'mid', f'high>={t2:.2f}'])
    bucketize(R, 'hour', [0, 6, 12, 18, 24], ['00-06', '06-12', '12-18', '18-24'])
    bucketize(R, 'ask', [0, 0.3, 0.4, 0.5, 0.61], ['<0.30', '0.30-0.40', '0.40-0.50', '0.50-0.60'])
    bucketize(R, 'sec', [0, 60, 120, 180, 240, 301], ['0-60', '60-120', '120-180', '180-240', '240+'])
