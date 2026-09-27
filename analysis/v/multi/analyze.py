#!/usr/bin/env python3
"""ETH / SOL on their own + BTC as information (V/multi, 09-27). Tests defined before looking (brief from V):

T1 lead-lag (Binance only): walk-forward logistic BY DAY (train all earlier days, test the day; first 2 days train only),
   one model per second bucket s = 15,30,..,240. Label = the coin's own Polymarket resolution.
   A = [z_own]  B = A + [z_btc]  C = B + [r10_own, r10_btc] (10 s returns: the short lead-lag)
   Report pooled AUC / Brier per bucket, dAUC(B-A) with a by-day cluster bootstrap 95% CI, days where B beats A.
T2 EF per coin, walk-forward Platt by day, rows every 5 s in 15..240:
   (i)   venue   : [logit mid, logit mid * s/240]
   (ii)  venue+BTC: (i) + [zt_btc, logit BTC-venue mid (0 when missing), missing flag]
   (iii) model   : [zt_own, zt_btc]  (no venue)
   (iv)  own-only: [zt_own]         (control for iii: what BTC adds on the model side)
   Rule (Fixed-style): first second in 15..240 where max over sides of EV = p/(ask*(1+0.07*(1-ask))) - 1 >= theta,
   theta in {0.05,0.10,0.15,0.25}; decision ask = past-only proxy aged <= 5 s, 0.02..0.98; the trade is PRICED at the
   exec print (first print at-or-after the decision, <= 4 s later); if there is none the second is skipped.
T3 score each cell: n, hit, median ask, paper per$1 at exec price, paper per$1 at the past proxy (the optimistic read),
   London-exec (fill 54.1% if it would win / 65.0% if it would lose, slippage p10/p50/p90 -1/+2/+11 c on top of the exec
   print, fee 0.07*sh*p*(1-p), $10, 1000 runs) per$1 and total p05/p95, H1/H2, negative days, permutation (shuffle the
   side, price the flipped side at ITS OWN exec print), paired McNemar vs arm (i).
T4 verify.Finding on the best cell per coin (by London-exec); the whole grid is printed regardless.
usage: analyze.py PANEL.npz COIN [--t1] > out.txt   (T1 skipped unless --t1: Zurich ran it on 30 days, 0.000 AUC gain)"""
import sys, random, numpy as np, datetime as dt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
sys.path.insert(0, 'analysis/h1'); import verify as V
P = np.load(sys.argv[1]); COIN = sys.argv[2].upper()
ep = P['ep']; y = P['y']; N = len(ep); day = (ep // 86400); days = sorted(set(day)); TEST = days[2:]
D = lambda d: dt.datetime.utcfromtimestamp(int(d) * 86400).strftime('%m-%d')
lg = lambda p: np.log(np.clip(p, .01, .99) / (1 - np.clip(p, .01, .99)))
cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: np.where(w, 1 / (x * cost(x)) - 1, -1.0)

print(f'# {COIN}: {N} candles, {len(days)} days {D(days[0])}..{D(days[-1])}, test days {len(TEST)} ({D(TEST[0])}..{D(TEST[-1])})')
print(f'grading: Polymarket outcome vs post-close prints agree {np.mean(P["post"][P["post"]>=0]==y[P["post"]>=0]):.4f} '
      f'(read {np.mean(P["post"]>=0):.3f}); vs Binance TWAP60 proxy agree {np.mean(P["bnc"]==y):.3f}; UP rate {y.mean():.3f}')
# data quality
au, ad, agu, agd, eu, ed = (P[k] for k in ('au', 'ad', 'agu', 'agd', 'eu', 'ed'))
W = slice(15, 241)
both = (agu[:, W] <= 2) & (agd[:, W] <= 2)
spr = (au[:, W] + ad[:, W] - 1)[both]
print(f'trades/candle median {np.median(P["ntr"]):.0f}; past-proxy age (UP, s 15..240) p50 {np.nanmedian(agu[:, W]):.0f}s '
      f'p90 {np.nanpercentile(agu[:, W], 90):.0f}s, share <=2s {np.mean(agu[:, W] <= 2):.2f}, <=5s {np.mean(agu[:, W] <= 5):.2f}; '
      f'exec print within 4 s: {np.mean(~np.isnan(eu[:, W])):.2f}')
print(f'spread (ask_up+ask_dn-1, both prints <=2 s old, n={len(spr)}): p25 {np.percentile(spr,25):+.3f} p50 {np.median(spr):+.3f} '
      f'p75 {np.percentile(spr,75):+.3f};  exec - past (same side) mean {np.nanmean((eu-au)[:, W]):+.4f}')

# ---------------- T1 ----------------
if '--t1' in sys.argv:   # skipped by default: V 09-27, done by Zurich on 30 days (analysis/zurich/MULTI_MARKET.md, 34cf8ad)
    print('\n## T1 lead-lag (Binance only), walk-forward by day, pooled over test days')
    print('| sec | n | AUC A | AUC B | AUC C | dAUC B-A [95% CI by day] | days B>A | Brier A | Brier B | Brier C |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    FEAT = {'A': ['z'], 'B': ['z', 'bz'], 'C': ['z', 'bz', 'r10', 'br10']}
    rng = np.random.default_rng(3); T1rows = []
    for s in range(15, 241, 15):
        X = {k: np.column_stack([P[f][:, s] for f in v]) for k, v in FEAT.items()}
        pr = {k: np.full(N, np.nan) for k in FEAT}
        for d in TEST:
            tr, te = day < d, day == d
            for k in FEAT:
                m = LogisticRegression(C=1.0).fit(X[k][tr], y[tr]); pr[k][te] = m.predict_proba(X[k][te])[:, 1]
        t = np.isin(day, TEST); yt = y[t]
        auc = {k: roc_auc_score(yt, pr[k][t]) for k in FEAT}; br = {k: np.mean((pr[k][t] - yt) ** 2) for k in FEAT}
        dd = [roc_auc_score(y[day == d], pr['B'][day == d]) - roc_auc_score(y[day == d], pr['A'][day == d]) for d in TEST]
        boots = []
        for _ in range(500):
            pick = rng.choice(TEST, len(TEST)); ii = np.concatenate([np.where(day == d)[0] for d in pick])
            boots.append(roc_auc_score(y[ii], pr['B'][ii]) - roc_auc_score(y[ii], pr['A'][ii]))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        print(f'| {s} | {t.sum()} | {auc["A"]:.4f} | {auc["B"]:.4f} | {auc["C"]:.4f} | {auc["B"]-auc["A"]:+.4f} [{lo:+.4f},{hi:+.4f}] | '
              f'{sum(x > 0 for x in dd)}/{len(dd)} | {br["A"]:.4f} | {br["B"]:.4f} | {br["C"]:.4f} |')


# ---------------- T2 ----------------
S = np.arange(300); TR = np.arange(15, 241, 5)
mid = np.where((agu <= 30) & (agd <= 30), (au + (1 - ad)) / 2, np.nan)
bmid = np.where(~np.isnan(P['bau']) & ~np.isnan(P['bad']), (P['bau'] + (1 - P['bad'])) / 2, np.nan)
bl = np.where(np.isnan(bmid), 0.0, lg(bmid)); bmiss = np.isnan(bmid).astype(float)
sgrid = np.broadcast_to(S / 240.0, (N, 300))
ARMS = {
    '(i) venue': [lg(mid), lg(mid) * sgrid],
    '(ii) venue+BTC': [lg(mid), lg(mid) * sgrid, P['bzt'], bl, bmiss],
    '(iii) model own+BTC': [P['zt'], P['bzt']],
    '(iv) model own-only': [P['zt']],
}
print(f'\nBTC venue mid available on {np.mean(~np.isnan(bmid[:, W])):.2f} of decision seconds')
PU = {}
for name, fs in ARMS.items():
    F = np.stack(fs, -1)                                   # N x 300 x k
    pu = np.full((N, 300), np.nan)
    for d in TEST:
        tr = np.where(day < d)[0]; te = np.where(day == d)[0]
        Xtr = F[tr][:, TR].reshape(-1, F.shape[-1]); ytr = np.repeat(y[tr], len(TR))
        ok = ~np.isnan(Xtr).any(1)
        m = LogisticRegression(C=1.0).fit(Xtr[ok], ytr[ok])
        Xte = F[te].reshape(-1, F.shape[-1]); okt = ~np.isnan(Xte).any(1); p = np.full(len(Xte), np.nan)
        p[okt] = m.predict_proba(Xte[okt])[:, 1]; pu[te] = p.reshape(len(te), 300)
    PU[name] = pu

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(r):
    u = r.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)
def london(F, runs=1000):
    r = random.Random(11); tots = []; sp = []
    for _ in range(runs):
        tot = spent = 0.0
        for f in F:
            if r.random() > (0.541 if f['win'] else 0.650): continue
            px = min(0.99, max(0.01, f['x'] + slip(r))); sh = 10 / px; fee = 0.07 * sh * px * (1 - px)
            spent += 10 + fee; tot += (sh if f['win'] else 0) - 10 - fee
        tots.append(tot); sp.append(spent)
    tots = np.array(tots); return tots.mean() / max(1e-9, np.mean(sp)), tots.mean(), np.percentile(tots, 5), np.percentile(tots, 95)

def fires(pu, theta):
    """Vectorised: EV per side per second; the first second (15..240) where the better side clears theta AND has an exec print."""
    okU = ~np.isnan(au) & (agu <= 5) & (au >= .02) & (au <= .98) & ~np.isnan(pu)
    okD = ~np.isnan(ad) & (agd <= 5) & (ad >= .02) & (ad <= .98) & ~np.isnan(pu)
    with np.errstate(invalid='ignore', divide='ignore'):
        evU = np.where(okU, pu / (au * cost(au)) - 1, -9); evD = np.where(okD, (1 - pu) / (ad * cost(ad)) - 1, -9)
    sideU = evU >= evD; ev = np.maximum(evU, evD); xx = np.where(sideU, eu, ed)
    hit = (ev >= theta) & ~np.isnan(xx); hit[:, :15] = False; hit[:, 241:] = False
    hit[~np.isin(day, TEST)] = False
    out = {}
    for i in np.where(hit.any(1))[0]:
        s = int(np.argmax(hit[i])); su = bool(sideU[i, s])
        x = eu[i, s] if su else ed[i, s]; xo = ed[i, s] if su else eu[i, s]; ao = ad[i, s] if su else au[i, s]
        xo = xo if not np.isnan(xo) else (ao if not np.isnan(ao) else 1 - x)
        out[i] = dict(i=i, s=s, side=int(su), a=au[i, s] if su else ad[i, s], x=x, xo=xo, win=int(int(su) == y[i]), day=day[i], ev=ev[i, s])
    return out

print('\n## T2/T3 EF grid (walk-forward, test days only). paper = every order fills at the exec print; London-exec adds fill odds + slippage ON TOP of the exec print')
print('| arm | theta | n | hit | med ask | med sec | paper/$1 (exec) | paper/$1 (past proxy) | H1 | H2 | neg days | London-exec/$1 | London total $ [p05, p95] | perm p | paired vs (i): disc b/c, p |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
GRID = {}; FI = {}
for name in ARMS:
    for th in (0.05, 0.10, 0.15, 0.25):
        fz = fires(PU[name], th); FI[(name, th)] = fz; R = [fz[k] for k in sorted(fz)]
        if not R: print(f'| {name} | {th} | 0 |'); continue
        w = np.array([f['win'] for f in R]); x = np.array([f['x'] for f in R]); a = np.array([f['a'] for f in R])
        v = per1(w, x); vp = per1(w, a); h = len(R) // 2
        dv = {}
        for f, val in zip(R, v): dv.setdefault(f['day'], []).append(val)
        neg = sum(np.sum(z) < 0 for z in dv.values())
        le, lt, l5, l95 = london(R)
        side = np.array([f['side'] for f in R]); yy = np.array([y[f['i']] for f in R])
        XU = np.array([f['x'] if f['side'] == 1 else f['xo'] for f in R]); XD = np.array([f['xo'] if f['side'] == 1 else f['x'] for f in R])
        def pnl(y_, p_, _):
            xx = np.where(p_ == 1, XU, XD); return float(np.mean(per1(p_ == y_, xx)))
        r2 = np.random.default_rng(7); real = pnl(yy, side, None)
        sims = [pnl(yy, r2.permutation(side), None) for _ in range(500)]; pp = np.mean(np.array(sims) >= real)
        pr = ''
        if name != '(i) venue':
            base = FI[('(i) venue', th)]; common = sorted(set(fz) & set(base))
            b = sum(1 for k in common if fz[k]['win'] and not base[k]['win']); c = sum(1 for k in common if base[k]['win'] and not fz[k]['win'])
            from math import comb
            m_ = b + c; pv = min(1.0, 2 * sum(comb(m_, k) * 0.5 ** m_ for k in range(0, min(b, c) + 1))) if m_ else 1.0
            pr = f'{len(common)} common, {b}/{c}, p={pv:.3f}'
        GRID[(name, th)] = dict(n=len(R), le=le, v=v.mean(), R=R)
        print(f'| {name} | {th:.2f} | {len(R)}{"*" if len(R) < 60 else ""} | {w.mean():.3f} | {np.median(x):.2f} | {np.median([f["s"] for f in R]):.0f} | '
              f'{v.mean():+.3f} | {vp.mean():+.3f} | {v[:h].mean():+.3f} | {v[h:].mean():+.3f} | {neg}/{len(dv)} | {le:+.3f} | {lt:+.1f} [{l5:+.1f}, {l95:+.1f}] | {pp:.3f} | {pr} |')
print('(* = under 60 fires: insufficient)')

# ---------------- T4 ----------------
best = max((k for k in GRID if GRID[k]['n'] >= 1), key=lambda k: GRID[k]['le'])
name, th = best; R = GRID[best]['R']
w = np.array([f['win'] for f in R]); x = np.array([f['x'] for f in R]); v = per1(w, x); h = len(R) // 2
print(f'\n## T4 verify.Finding on the best cell by London-exec: {name} theta {th}')
Fd = V.Finding(f'{COIN} EF {name} theta {th}', v.mean(), len(R))
pl = P['post']; ok = pl >= 0
Fd.grading(gamma_outcome={int(ep[i]): int(y[i]) for i in range(N) if ok[i]}, post_close_prints={int(ep[i]): int(pl[i]) for i in range(N) if ok[i]})
Fd.quote_age('at-or-after', 0.0, 'first print at-or-after the decision second (decision uses a past print <=5 s old)')
Fd.sample({'cell': len(R)}); Fd.halves(v[:h].mean(), v[h:].mean())
side = np.array([f['side'] for f in R]); yy = np.array([y[f['i']] for f in R])
XU = np.array([f['x'] if f['side'] == 1 else f['xo'] for f in R]); XD = np.array([f['xo'] if f['side'] == 1 else f['x'] for f in R])
Fd.permutation(yy, side.astype(float), np.zeros(len(R)), lambda y_, p_, _: float(np.mean(per1(p_ == y_, np.where(p_ == 1, XU, XD)))), draws=1000)
Fd.sweep([GRID[(name, t)]['le'] for t in (0.05, 0.10, 0.15, 0.25) if (name, t) in GRID])
Fd.costs({k: float(np.mean(per1(w, np.minimum(.99, x + k)))) for k in (0, .01, .02, .05)})
cheap = np.where(XU <= XD, 1, 0); Fd.null(v.mean(), float(np.mean(per1(cheap == yy, np.minimum(XU, XD)))), 'buy the cheaper side, same second')
if name != '(i) venue':
    base = FI[('(i) venue', th)]; common = sorted(set(FI[best]) & set(base))
    Fd.paired([FI[best][k]['win'] for k in common], [base[k]['win'] for k in common])
Fd.verdict()
