#!/usr/bin/env python3
"""BTC 15-minute Polymarket up/down on its own (V/multi/btc15, 09-27). Adapted from ../analyze.py (ETH_SOL_EF.md);
same rules, the candle length CL comes from the panel so the SAME script scores BTC 5m as the comparator.

Arms (walk-forward Platt/logistic BY DAY: train all earlier days, test the day; first 2 days train only):
  (i)   venue       : [logit mid, logit mid * s/(CL-60)]
  (ii)  venue+move  : (i) + [zt, zt * s/(CL-60)]
  (iii) model-only  : [zt, zt * s/(CL-60)]          (Binance move since the TWAP60 line in sigma units, scaled by time left)
Decision grid (defined before looking): s = 15, 30, ..., CL-60 (15 s steps); training rows = the same grid.
Rule: first grid second where max-side EV = p/(ask*(1+0.07*(1-ask))) - 1 >= theta, theta in {0.05,0.10,0.15,0.25};
decision ask = past-only proxy aged <= 5 s, 0.02..0.98; trade PRICED at the first print at-or-after the decision (<= 4 s).
One trade per candle. Scoring, London-exec MC, permutation and paired test exactly as ../analyze.py.
T5 lead lifetime (arms ii and iii): the same fires priced at the first print in [s+k, s+k+4] for k = 0..240 s, and the drift of the
fired side's price from s to s+k. If the lead lives longer on 15m, the edge survives a larger k.
usage (from repo root): analyze15.py PANEL.npz NAME > out.txt"""
import sys, random, numpy as np, datetime as dt
from math import comb
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, 'analysis/h1'); import verify as V
P = np.load(sys.argv[1]); NAME = sys.argv[2]
CL = int(P['CL']); ep = P['ep']; y = P['y']; N = len(ep); day = ep // 86400; days = sorted(set(day)); TEST = days[2:]
G = np.arange(15, CL - 60 + 1, 15)
D = lambda d: dt.datetime.utcfromtimestamp(int(d) * 86400).strftime('%m-%d')
lg = lambda p: np.log(np.clip(p, .01, .99) / (1 - np.clip(p, .01, .99)))
cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: np.where(w, 1 / (x * cost(x)) - 1, -1.0)
au, ad, agu, agd, eu, ed = (P[k] for k in ('au', 'ad', 'agu', 'agd', 'eu', 'ed'))

print(f'# {NAME}: {N} candles (CL {CL} s), {len(days)} days {D(days[0])}..{D(days[-1])}, test days {len(TEST)} ({D(TEST[0])}..{D(TEST[-1])})')
pl = P['post']
print(f'grading: Polymarket outcome vs post-close prints agree {np.mean(pl[pl>=0]==y[pl>=0]):.4f} (read {np.mean(pl>=0):.3f}, n={np.sum(pl>=0)}); '
      f'vs Binance TWAP60 proxy agree {np.mean(P["bnc"]==y):.3f}; UP rate {y.mean():.3f}; trade fetch capped (>=10000 prints): {int(P["capped"].sum())}')
both = (agu[:, G] <= 2) & (agd[:, G] <= 2); spr = (au[:, G] + ad[:, G] - 1)[both]
ageU = agu[:, G]
print(f'trades/candle median {np.median(P["ntr"]):.0f} (p10 {np.percentile(P["ntr"],10):.0f}); past ask-proxy age on the decision grid (UP): '
      f'p50 {np.nanmedian(ageU):.0f}s p90 {np.nanpercentile(ageU, 90):.0f}s, share <=2s {np.mean(ageU <= 2):.2f}, <=5s {np.mean(ageU <= 5):.2f}; '
      f'exec print within 4 s: {np.mean(~np.isnan(eu[:, G])):.2f}')
print(f'spread (ask_up+ask_dn-1, both prints <=2 s old, n={len(spr)}): p25 {np.percentile(spr,25):+.3f} p50 {np.median(spr):+.3f} '
      f'p75 {np.percentile(spr,75):+.3f};  exec - past (same side) mean {np.nanmean((eu-au)[:, G]):+.4f}')
print(f'taker BUY print size ($): per-candle median of median {np.median(P["usd_med"]):.1f}, of p90 {np.median(P["usd_p90"]):.1f}; '
      f'$ bought per active second (median) {np.median(P["usd_sec"]):.1f}  (lower bounds on depth at best; the book itself is not in the trades)')

mid = np.where((agu <= 30) & (agd <= 30), (au + (1 - ad)) / 2, np.nan)
fr = np.broadcast_to(np.arange(CL) / (CL - 60.0), (N, CL)); zt = P['zt']
ARMS = {'(i) venue': [lg(mid), lg(mid) * fr],
        '(ii) venue+move': [lg(mid), lg(mid) * fr, zt, zt * fr],
        '(iii) model-only': [zt, zt * fr]}
PU = {}
for name, fs in ARMS.items():
    F = np.stack(fs, -1); pu = np.full((N, CL), np.nan)
    for d in TEST:
        tr = np.where(day < d)[0]; te = np.where(day == d)[0]
        Xtr = F[tr][:, G].reshape(-1, F.shape[-1]); ytr = np.repeat(y[tr], len(G)); ok = ~np.isnan(Xtr).any(1)
        m = LogisticRegression(C=1.0).fit(Xtr[ok], ytr[ok])
        Xte = F[te][:, G].reshape(-1, F.shape[-1]); okt = ~np.isnan(Xte).any(1); p = np.full(len(Xte), np.nan)
        p[okt] = m.predict_proba(Xte[okt])[:, 1]; pu[np.ix_(te, G)] = p.reshape(len(te), len(G))
    PU[name] = pu

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(r):
    u = r.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)
def london(F, runs=1000):
    r = random.Random(11); tots = []; sp = []; t2 = []; s2 = []
    for _ in range(runs):
        tot = spent = tot2 = spent2 = 0.0
        for f in F:
            if r.random() > (0.541 if f['win'] else 0.650): continue
            px = min(0.99, max(0.01, f['x'] + slip(r))); sh = 10 / px; fee = 0.07 * sh * px * (1 - px)
            spent += 10 + fee; tot += (sh if f['win'] else 0) - 10 - fee
            px = f['x']; sh = 10 / px; fee = 0.07 * sh * px * (1 - px)
            spent2 += 10 + fee; tot2 += (sh if f['win'] else 0) - 10 - fee
        tots.append(tot); sp.append(spent); t2.append(tot2); s2.append(spent2)
    tots = np.array(tots)
    return tots.mean() / max(1e-9, np.mean(sp)), tots.mean(), np.percentile(tots, 5), np.percentile(tots, 95), np.mean(t2) / max(1e-9, np.mean(s2))

GRIDMASK = np.zeros(CL, bool); GRIDMASK[G] = True
def fires(pu, theta):
    okU = ~np.isnan(au) & (agu <= 5) & (au >= .02) & (au <= .98) & ~np.isnan(pu)
    okD = ~np.isnan(ad) & (agd <= 5) & (ad >= .02) & (ad <= .98) & ~np.isnan(pu)
    with np.errstate(invalid='ignore', divide='ignore'):
        evU = np.where(okU, pu / (au * cost(au)) - 1, -9); evD = np.where(okD, (1 - pu) / (ad * cost(ad)) - 1, -9)
    sideU = evU >= evD; ev = np.maximum(evU, evD); xx = np.where(sideU, eu, ed)
    hit = (ev >= theta) & ~np.isnan(xx); hit[:, ~GRIDMASK] = False; hit[~np.isin(day, TEST)] = False
    out = {}
    for i in np.where(hit.any(1))[0]:
        s = int(np.argmax(hit[i])); su = bool(sideU[i, s])
        x = eu[i, s] if su else ed[i, s]; xo = ed[i, s] if su else eu[i, s]; ao = ad[i, s] if su else au[i, s]
        xo = xo if not np.isnan(xo) else (ao if not np.isnan(ao) else 1 - x)
        out[i] = dict(i=i, s=s, side=int(su), a=au[i, s] if su else ad[i, s], x=x, xo=xo, win=int(int(su) == y[i]), day=day[i], ev=ev[i, s])
    return out

print(f'\n## EF grid (walk-forward, test days only; decision grid s=15..{CL-60} step 15). paper = fills at the exec print; '
      'London-exec adds fill odds + slippage ON TOP of the exec print')
print('| arm | theta | n | hit | med ask | med sec | paper/$1 (exec) | paper/$1 (past proxy) | H1 | H2 | neg days | London-exec/$1 | fill odds only/$1 | London total $ [p05, p95] | perm p | paired vs (i): common, b/c, p |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
GRID = {}; FI = {}; TH = (0.05, 0.10, 0.15, 0.25)
for name in ARMS:
    for th in TH:
        fz = fires(PU[name], th); FI[(name, th)] = fz; R = [fz[k] for k in sorted(fz)]
        if not R: print(f'| {name} | {th} | 0 |'); continue
        w = np.array([f['win'] for f in R]); x = np.array([f['x'] for f in R])
        v = per1(w, x); vp = per1(w, np.array([f['a'] for f in R])); h = len(R) // 2
        dv = {}
        for f, val in zip(R, v): dv.setdefault(f['day'], []).append(val)
        neg = sum(np.sum(z) < 0 for z in dv.values())
        le, lt, l5, l95, lf = london(R)
        side = np.array([f['side'] for f in R]); yy = np.array([y[f['i']] for f in R])
        XU = np.array([f['x'] if f['side'] == 1 else f['xo'] for f in R]); XD = np.array([f['xo'] if f['side'] == 1 else f['x'] for f in R])
        pnl = lambda y_, p_: float(np.mean(per1(p_ == y_, np.where(p_ == 1, XU, XD))))
        r2 = np.random.default_rng(7); real = pnl(yy, side)
        pp = np.mean(np.array([pnl(yy, r2.permutation(side)) for _ in range(500)]) >= real)
        pr = ''
        if name != '(i) venue':
            base = FI[('(i) venue', th)]; common = sorted(set(fz) & set(base))
            b = sum(1 for k in common if fz[k]['win'] and not base[k]['win']); c = sum(1 for k in common if base[k]['win'] and not fz[k]['win'])
            m_ = b + c; pv = min(1.0, 2 * sum(comb(m_, k) * 0.5 ** m_ for k in range(0, min(b, c) + 1))) if m_ else 1.0
            pr = f'{len(common)}, {b}/{c}, p={pv:.3f}'
        GRID[(name, th)] = dict(n=len(R), le=le, v=v.mean(), R=R)
        print(f'| {name} | {th:.2f} | {len(R)}{"*" if len(R) < 60 else ""} | {w.mean():.3f} | {np.median(x):.2f} | {np.median([f["s"] for f in R]):.0f} | '
              f'{v.mean():+.3f} | {vp.mean():+.3f} | {v[:h].mean():+.3f} | {v[h:].mean():+.3f} | {neg}/{len(dv)} | {le:+.3f} | {lf:+.3f} | '
              f'{lt:+.1f} [{l5:+.1f}, {l95:+.1f}] | {pp:.3f} | {pr} |')
print('(* = under 60 fires: insufficient)')

# ---------------- T5 lead lifetime ----------------
SU, SDn = P['secu'], P['secd']; LQ = SU.shape[1]
def nxt_ptr(sec):
    have = ~np.isnan(sec); ar = np.broadcast_to(np.arange(sec.shape[1]), sec.shape)
    nx = np.where(have, ar, 10**6); return np.minimum.accumulate(nx[:, ::-1], axis=1)[:, ::-1]
NU, ND = nxt_ptr(SU), nxt_ptr(SDn)
def price_at(i, side, s0, k):
    """Price available k s after the decision at s0: the first print in [s0+k, s0+k+4]; if none, the latest print in
    [s0, s0+k) (every fire has an exec print in [s0, s0+4], so this is always defined -> no subset selection). Returns (px, fresh)."""
    sec = SU if side else SDn; t = 60 + s0 + k
    if t < LQ:
        nx = (NU if side else ND)[i, t]
        if nx < LQ and nx - t <= 4: return sec[i, nx], 1
    seg = sec[i, 60 + s0:min(t, LQ)]; seg = seg[~np.isnan(seg)]
    return (seg[-1] if len(seg) else np.nan), 0
KS = (0, 1, 2, 3, 5, 10, 20, 30, 60)
print('\n## T5 lead lifetime: ALL fires of the cell priced k s after the decision (first print in [s+k, s+k+4], else the latest print since s)')
print('paper/$1 at s+k (SE); the fired side\'s price drift from s to s+k in cents; share of fires with a fresh print at s+k')
print('| arm | theta | n | row | ' + ' | '.join(f'k={k}' for k in KS) + ' |')
print('|---|---|---|---|' + '---|' * len(KS))
for arm, th in [(a, t) for a in ('(ii) venue+move', '(iii) model-only') for t in (0.10, 0.15, 0.25)]:
    R = GRID[(arm, th)]['R']; n = len(R)
    Q = [[price_at(f['i'], f['side'], f['s'], k) for k in KS] for f in R]
    PX = np.clip(np.array([[q[0] for q in r] for r in Q]), .01, .99); FR = np.array([[q[1] for q in r] for r in Q])
    w = np.array([f['win'] for f in R]); x0 = np.array([f['x'] for f in R])
    pp = [per1(w, PX[:, j]) for j in range(len(KS))]
    print(f'| {arm} | {th:.2f} | {n}{"*" if n < 60 else ""} | paper | ' + ' | '.join(f'{v.mean():+.3f} ({v.std() / np.sqrt(n):.3f})' for v in pp) + ' |')
    print(f'| {arm} | {th:.2f} | {n} | drift c | ' + ' | '.join(f'{100 * np.mean(PX[:, j] - x0):+.1f}' for j in range(len(KS))) + ' |')
    print(f'| {arm} | {th:.2f} | {n} | fresh | ' + ' | '.join(f'{FR[:, j].mean():.2f}' for j in range(len(KS))) + ' |')

# ---------------- T4 ----------------
best = max(GRID, key=lambda k: GRID[k]['le']); name, th = best; R = GRID[best]['R']
w = np.array([f['win'] for f in R]); x = np.array([f['x'] for f in R]); v = per1(w, x); h = len(R) // 2
print(f'\n## T4 verify.Finding on the best cell by London-exec: {name} theta {th}')
Fd = V.Finding(f'{NAME} EF {name} theta {th}', v.mean(), len(R)); ok = pl >= 0
Fd.grading(gamma_outcome={int(ep[i]): int(y[i]) for i in range(N) if ok[i]}, post_close_prints={int(ep[i]): int(pl[i]) for i in range(N) if ok[i]})
Fd.quote_age('at-or-after', 0.0, 'first print at-or-after the decision second (decision uses a past print <=5 s old)')
Fd.sample({'cell': len(R)}); Fd.halves(v[:h].mean(), v[h:].mean())
side = np.array([f['side'] for f in R]); yy = np.array([y[f['i']] for f in R])
XU = np.array([f['x'] if f['side'] == 1 else f['xo'] for f in R]); XD = np.array([f['xo'] if f['side'] == 1 else f['x'] for f in R])
Fd.permutation(yy, side.astype(float), np.zeros(len(R)), lambda y_, p_, _: float(np.mean(per1(p_ == y_, np.where(p_ == 1, XU, XD)))), draws=1000)
Fd.sweep([GRID[(name, t)]['le'] for t in TH if (name, t) in GRID])
Fd.costs({k: float(np.mean(per1(w, np.minimum(.99, x + k)))) for k in (0, .01, .02, .05)})
cheap = np.where(XU <= XD, 1, 0); Fd.null(v.mean(), float(np.mean(per1(cheap == yy, np.minimum(XU, XD)))), 'buy the cheaper side, same second')
if name != '(i) venue':
    base = FI[('(i) venue', th)]; common = sorted(set(FI[best]) & set(base))
    Fd.paired([FI[best][k]['win'] for k in common], [base[k]['win'] for k in common])
Fd.verdict()
