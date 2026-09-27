#!/usr/bin/env python3
"""REV brain (V, 09-27; owner: "give it a trained brain that knows that move is wrong and it will reverse").

Question: does a model on rich Binance microstructure (spot 1 s klines, spot + perp aggTrades, perp bookDepth; all
rebuilt from data.binance.vision by rev_brain_fetch.py) know when the current leader of a 5-min candle (spot vs the
TWAP60 settlement line) will lose - and does that make REVERSAL pay under London-like execution?

Everything below was fixed BEFORE any result was looked at:
  rows      every Polymarket tape row (both asks present) at sec 30..240 of every candle (tape ~ every 5 s), so the quote
            is SAME-SECOND by construction (age 0). Extra train-only window (arm B): v10_features_8days.parquet rows,
            08-29..09-06, offsets 30..240, its asks (mostly trade-inferred, is_book=0) and its y (Gamma-resolved
            Polymarket outcome - same oracle as venues.outcome; no overlap to cross-check, stated plainly).
  label     y = 1 if the UNDERDOG (side opposite the spot leader vs the TWAP60 line) wins on venues.outcome / parquet y.
  features  bucket s = events in [s, s+1); a row at second t reads buckets <= t-1 only and bookDepth snapshots <= t-1.
            Directional features are ORIENTED by the leader sign L (positive = in the leader's favour).
  sets      NULL = [logit ask_underdog, sec]; BIN = Binance only (+sec); FULL = NULL + BIN.
  learners  LR  = standardise, clip +-5, L2 logistic C=0.1.  GBM = HistGradientBoosting(max_depth 3, lr .05, 150 iter,
            min_samples_leaf 200, l2 10).
  walk-fwd  arm A: tape days only, test day d needs >= 3 prior tape days (09-11..09-16).
            arm B: parquet 8 days + tape days < d, test every tape day 09-08..09-16 (same days as the +0.065 baseline).
  trading   one trade per candle, first qualifying second, buy the side with p/(ask*cost) - 1 >= theta, ask <= 0.90,
            theta in {0, .03, .05, .10}.
            ALL  : every test row, side = underdog.
            REV  : the REAL REVERSAL call seconds (calls_rev.csv, sec 0..240) re-priced with a past-only quote of
                   age 0 (primary) or <= 1 s; side = REV's side, p = model p for that side.
            REV&R1: as REV and ALSO the lane's own R1 (lane p breakeven) - the brain as a filter on live REV.
            Baselines: REV R1 (lane p) and REV R0 on the same test days.
  report    n, hit, paper per$1, London-exec per$1 + total mean/p05/p95 (lane_exec_sim.py model), H1/H2, negative
            days, permutation (coin-flip the side, flipped trade pays the OPPOSITE ask), paired vs the NULL learner's
            same cell (McNemar on candles, right = traded and won; plus a sign-flip test on candle PnL).
Grading: venues.outcome (Polymarket's own resolution)."""
import argparse, csv, glob, gzip, math, os, sqlite3, sys, bisect, datetime as dt
import numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'analysis', 'h1')); from verify import Finding
ap = argparse.ArgumentParser(); ap.add_argument('--scratch', required=True); ap.add_argument('--runs', type=int, default=1000)
a = ap.parse_args(); S = a.scratch
THETAS = (0.0, 0.03, 0.05, 0.10)
cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: (w / x - cost(x)) / cost(x)
lg = lambda x: np.log(np.clip(x, 1e-3, 1 - 1e-3) / (1 - np.clip(x, 1e-3, 1 - 1e-3)))
day_of = lambda t: dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime('%m-%d')

# ---------------------------------------------------------------- Binance per-second series
files = sorted(glob.glob(os.path.join(S, 'bn', '*.npz')))
Z = [np.load(f) for f in files]; T0 = int(Z[0]['d0'])
assert all(int(z['d0']) == T0 + 86400 * k for k, z in enumerate(Z)), 'day files must be contiguous'
A = {k: np.concatenate([z[k] for z in Z]) for k in ('sc', 'sh', 'sl', 'sbuy', 'ssell', 'pc', 'pbuy', 'psell', 'pn')}
BD_TS = np.concatenate([z['bd_ts'] for z in Z]); BD = np.concatenate([z['bd'] for z in Z])
o = np.argsort(BD_TS, kind='stable'); BD_TS, BD = BD_TS[o], BD[o]

def prep(A):
    P = dict(A); P['pcf'] = pd.Series(A['pc']).ffill().values
    ls = np.log(A['sc']); r = np.r_[0.0, np.diff(ls)]
    cs = lambda x: np.r_[0.0, np.cumsum(x)]
    for k in ('sbuy', 'ssell', 'pbuy', 'psell', 'pn', 'sc'): P['cs_' + k] = cs(A[k])
    P['cs_r'] = cs(r); P['cs_r2'] = cs(r * r); P['ls'] = ls
    return P

def features(ts, P, bd_ts, bd, check=True):
    """ts: int array of decision seconds. Reads buckets <= t-1 only (asserted)."""
    i = ts - T0; e = (ts // 300 * 300) - T0; sec = ts % 300
    last = i - 1                                                  # newest bucket allowed
    if check: assert (last < i).all() and (e - 1 <= last).all()
    W = lambda k, w: P['cs_' + k][i] - P['cs_' + k][i - w]        # sum of buckets i-w .. i-1
    line = (P['cs_sc'][e] - P['cs_sc'][e - 60]) / 60              # TWAP60 of closes ep-60..ep-1
    spot = P['sc'][last]; perp = P['pcf'][last]
    mv = (spot - line) / spot; L = np.sign(mv)
    var = lambda w: np.maximum((P['cs_r2'][i] - P['cs_r2'][i - w]) / w - ((P['cs_r'][i] - P['cs_r'][i - w]) / w) ** 2, 1e-14)
    sig = np.sqrt(var(120)); sigL = np.sqrt(var(900))
    ret = lambda w: (P['ls'][last] - P['ls'][last - w]) * 1e4 * L
    hi = np.array([np.max(P['sh'][a_:b_]) if b_ > a_ else np.nan for a_, b_ in zip(e, i)])
    lo = np.array([np.min(P['sl'][a_:b_]) if b_ > a_ else np.nan for a_, b_ in zip(e, i)])
    rng_ = np.where(hi > lo, hi - lo, np.nan); rp = (spot - lo) / rng_; rp = np.where(L > 0, rp, 1 - rp)
    retreat = np.where(L > 0, hi - spot, spot - lo) / spot / sig
    cross = np.where(L > 0, np.maximum(0, line - lo), np.maximum(0, hi - line)) / spot / sig
    imb = lambda b, s_, w: (W(b, w) - W(s_, w)) / np.maximum(W(b, w) + W(s_, w), 1e-9) * L
    j = np.searchsorted(bd_ts, ts - 1, side='right') - 1
    if check: assert (j >= 0).all() and (bd_ts[j] <= ts - 1).all(), 'bookDepth snapshot after t-1'
    D = bd[j]; di = lambda k: (D[:, 4 - k] - D[:, 7 + k]) / (D[:, 4 - k] + D[:, 7 + k]) * L  # k=0:1%, 1:2%, 4:5%
    vol60 = W('pbuy', 60) + W('psell', 60); vol600 = (W('pbuy', 600) + W('psell', 600)) / 10
    F = dict(sec=sec.astype(float), z_line=np.abs(mv) / sig, z_rem=np.abs(mv) / (sig * np.sqrt(np.maximum(270 - sec, 1) + 20)),
             move_bps=np.abs(mv) * 1e4, ret5=ret(5), ret15=ret(15), ret30=ret(30), ret60=ret(60), rp=rp, retreat=retreat,
             cross_ext=cross, sig_bps=sig * 1e4, vol_ratio=sig / sigL, basis=(perp - spot) / spot * 1e4 * L,
             pret5=(np.log(perp) - np.log(P['pcf'][last - 5])) * 1e4 * L, pret15=(np.log(perp) - np.log(P['pcf'][last - 15])) * 1e4 * L,
             ofi5=imb('pbuy', 'psell', 5), ofi15=imb('pbuy', 'psell', 15), ofi60=imb('pbuy', 'psell', 60),
             pact=np.log1p(W('pn', 60)), vratio=vol60 / np.maximum(vol600, 1e-9),
             simb5=imb('sbuy', 'ssell', 5), simb15=imb('sbuy', 'ssell', 15), simb60=imb('sbuy', 'ssell', 60),
             dimb1=di(0), dimb2=di(1), dimb5=di(4), dage=(ts - bd_ts[j]).astype(float))
    raw = dict(ret5_raw=F['ret5'] * L, ofi15_raw=F['ofi15'] * L, simb15_raw=F['simb15'] * L, basis_raw=F['basis'] * L, move_line_bps=mv * 1e4)
    return F, L, raw

P = prep(A)
BIN = ['sec', 'z_line', 'z_rem', 'move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'rp', 'retreat', 'cross_ext', 'sig_bps', 'vol_ratio',
       'basis', 'pret5', 'pret15', 'ofi5', 'ofi15', 'ofi60', 'pact', 'vratio', 'simb5', 'simb15', 'simb60', 'dimb1', 'dimb2', 'dimb5', 'dage']
NULL = ['la_dog', 'sec']; FULL = NULL + [f for f in BIN if f != 'sec']
SETS = {'NULL': NULL, 'BIN': BIN, 'FULL': FULL}

# ---------------------------------------------------------------- rows: tape window + parquet window
vc = sqlite3.connect(os.path.join(S, 'venues.sqlite3'))
OUT = {int(e): x for e, x in vc.execute('select epoch,actual from outcome')}
Q = [(int(t), float(u), float(d)) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q where poly_up is not null and poly_dn is not null order by ts')]
QT = [q[0] for q in Q]; QD = {q[0]: q for q in Q}

def build(ts, up, dn, act, src):
    ts = np.asarray(ts, dtype=np.int64); F, L, raw = features(ts, P, BD_TS, BD)
    df = pd.DataFrame(F); df['ts'] = ts; df['epoch'] = ts // 300 * 300; df['L'] = L
    df['ask_up'] = up; df['ask_dn'] = dn; df['act'] = act; df['src'] = src
    for k, v in raw.items(): df[k] = v
    df['dog'] = np.where(L > 0, 'DOWN', 'UP'); df['ask_dog'] = np.where(L > 0, df.ask_dn, df.ask_up); df['ask_lead'] = np.where(L > 0, df.ask_up, df.ask_dn)
    df['la_dog'] = lg(df.ask_dog.values); df['y'] = (df.act == df.dog).astype(int)
    df['day'] = [day_of(t) for t in ts]
    return df[(df.L != 0) & df.act.notna()].reset_index(drop=True)

tr = [q for q in Q if 30 <= q[0] % 300 <= 240 and (q[0] // 300 * 300) in OUT]
TAPE = build([q[0] for q in tr], [q[1] for q in tr], [q[2] for q in tr], [OUT[q[0] // 300 * 300] for q in tr], 'tape')
pq = pd.read_parquet(gzip.open(os.path.join(ROOT, 'learner', 'live_backup', 'v10_features_8days.parquet.gz')))
pq = pq[(pq.offset >= 30) & (pq.offset <= 240) & pq.ask_up.notna() & pq.ask_dn.notna()].reset_index(drop=True)
PQ = build((pq.epoch + pq.offset).values, pq.ask_up.values, pq.ask_dn.values, np.where(pq.y == 1, 'UP', 'DOWN'), 'parquet')
PQ_raw = pq.set_index(pq.epoch + pq.offset)
print(f'rows: tape {len(TAPE)} on {TAPE.epoch.nunique()} candles, days {sorted(TAPE.day.unique())}; parquet {len(PQ)} on {PQ.epoch.nunique()} candles')

# ---------------------------------------------------------------- leakage checks
print('\n== LEAKAGE CHECKS')
rs = np.random.default_rng(3); samp = rs.choice(TAPE.ts.values, 40, replace=False)
bad = 0
for t in samp:
    i = int(t - T0); Ag = {k: v.copy() for k, v in A.items()}
    for k in Ag: Ag[k][i:] = rs.normal(1e5, 1e4, len(Ag[k]) - i) if k in ('sc', 'sh', 'sl', 'pc') else rs.random(len(Ag[k]) - i) * 1e3
    bdg = BD.copy(); bdg[BD_TS >= t] = rs.random((int((BD_TS >= t).sum()), BD.shape[1])) * 1e5
    f1, _, _ = features(np.array([t]), P, BD_TS, BD); f2, _, _ = features(np.array([t]), prep(Ag), BD_TS, bdg)
    bad += sum(1 for k in f1 if not np.allclose(f1[k], f2[k], equal_nan=True))
print(f'  truncation test: 40 random rows recomputed with EVERY bucket >= t (and bookDepth >= t) replaced by garbage -> {bad} feature values changed (must be 0)')
assert bad == 0
print(f'  bookDepth age at decision (s): median {TAPE.dage.median():.0f}, max {TAPE.dage.max():.0f}; asserted snapshot ts <= t-1 on every row')
# parity with the live-feature parquet on its own window (definitions differ: parquet move is from the first trade, depth is live depth20)
m = PQ.set_index('ts').join(PQ_raw[['ret5', 'ofi15', 'spot_imb15', 'basis_bps', 'move_bps']], rsuffix='_pq')
for mine, theirs in (('ret5_raw', 'ret5_pq'), ('ofi15_raw', 'ofi15_pq'), ('simb15_raw', 'spot_imb15'), ('basis_raw', 'basis_bps'), ('move_line_bps', 'move_bps_pq')):
    ok = m[[mine, theirs]].dropna(); print(f'  parity vs parquet (live features) {mine:14s} ~ {theirs:12s} corr {np.corrcoef(ok[mine], ok[theirs])[0,1]:+.3f} (n {len(ok)})')
# TWAP60 proxy label vs the venue oracle (context only; never used to grade)
def proxy(ep):
    i = ep - T0; line = (P['cs_sc'][i] - P['cs_sc'][i - 60]) / 60; cl = (P['cs_sc'][i + 300] - P['cs_sc'][i + 240]) / 60
    return 'UP' if cl >= line else 'DOWN'
agree = [proxy(e) == OUT[e] for e in OUT if e + 300 - T0 < len(P['sc'])]
pqe = PQ.groupby('epoch').act.first(); agq = [proxy(e) == v for e, v in pqe.items()]
print(f'  label context: Binance-spot TWAP60 proxy agrees with venues.outcome {np.mean(agree):.3f} (n {len(agree)}), with parquet y {np.mean(agq):.3f} (n {len(agq)})')
lane = sqlite3.connect(os.path.join(S, 'v12lane.sqlite3'))
LA = {int(e): x.upper() for e, x in lane.execute('select candle_epoch,actual from trades where actual is not null')}

# ---------------------------------------------------------------- REV calls (past-only quotes)
def past_quote(t, age):
    k = bisect.bisect_right(QT, t) - 1
    return Q[k] if k >= 0 and t - QT[k] <= age else None
REVC = [r for r in csv.DictReader(open(os.path.join(S, 'calls_rev.csv'))) if r['kind'] == 'REVERSAL' and 0 <= int(r['sec']) <= 240]
def rev_rows(age):
    keep = []
    for r in REVC:
        t = int(r['epoch']) + int(r['sec']); q = past_quote(t, age)
        if q is None or int(r['epoch']) not in OUT: continue
        keep.append((t, q[1], q[2], r['side'], float(r['p']), int(r['win'])))
    df = build([k[0] for k in keep], [k[1] for k in keep], [k[2] for k in keep], [OUT[k[0] // 300 * 300] for k in keep], 'rev')
    info = {k[0]: k for k in keep}
    df['side'] = [info[t][3] for t in df.ts]; df['lane_p'] = [info[t][4] for t in df.ts]; df['win'] = [info[t][5] for t in df.ts]
    assert (df.win == (df.act == df.side).astype(int)).all(), 'calls_rev win must equal venues.outcome grading'
    df['ask'] = np.where(df.side == 'UP', df.ask_up, df.ask_dn); df['opp'] = np.where(df.side == 'UP', df.ask_dn, df.ask_up)
    return df
REV = {0: rev_rows(0), 1: rev_rows(1)}
print(f'  REV calls sec 0..240: {len(REVC)}; with a past-only quote age 0: {len(REV[0])} rows / {REV[0].epoch.nunique()} candles, '
      f'age<=1: {len(REV[1])} / {REV[1].epoch.nunique()}; REV side = underdog on {np.mean(REV[0].side == REV[0].dog):.1%} of rows')

# ---------------------------------------------------------------- walk-forward fits
def learner(kind):
    if kind == 'LR': return LogisticRegression(C=0.1, max_iter=3000)
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=200, l2_regularization=10.0, random_state=0)
def fitpred(kind, cols, trn, tests):
    X = trn[cols].values.astype(float)
    if kind == 'LR':
        med = np.nanmedian(X, 0); X = np.where(np.isnan(X), med, X); mu, sd = X.mean(0), X.std(0) + 1e-9
        f = lambda Z_: np.clip((np.where(np.isnan(Z_), med, Z_) - mu) / sd, -5, 5)
        mdl = learner(kind).fit(f(X), trn.y.values); return [mdl.predict_proba(f(t[cols].values.astype(float)))[:, 1] for t in tests]
    mdl = learner(kind).fit(X, trn.y.values); return [mdl.predict_proba(t[cols].values.astype(float))[:, 1] for t in tests]

tape_days = sorted(TAPE.day.unique())
ARMS = {'A': tape_days[3:], 'B': tape_days}
PRED = {}                                   # (arm, learner, set) -> (test rows df with p, {age: rev df with p})
for arm, tdays in ARMS.items():
    for kind in ('LR', 'GBM'):
        for sname, cols in SETS.items():
            outs, rv0, rv1 = [], [], []
            for d in tdays:
                trn = TAPE[TAPE.day < d]
                if arm == 'B': trn = pd.concat([PQ, trn])
                assert trn.ts.max() < TAPE[TAPE.day == d].ts.min()
                te = TAPE[TAPE.day == d].copy(); r0 = REV[0][REV[0].day == d].copy(); r1 = REV[1][REV[1].day == d].copy()
                pt, p0, p1 = fitpred(kind, cols, trn, [te, r0, r1]); te['p'] = pt; r0['p'] = p0; r1['p'] = p1
                outs.append(te); rv0.append(r0); rv1.append(r1)
            PRED[(arm, kind, sname)] = (pd.concat(outs), {0: pd.concat(rv0), 1: pd.concat(rv1)})

print('\n== MODEL QUALITY on walk-forward test rows (label: underdog wins; pooled over test days)')
print('  arm learner set   n_rows  base   AUC    Brier   | AUC by test day')
for (arm, kind, sname), (te, _) in PRED.items():
    byday = ' '.join(f'{roc_auc_score(g.y, g.p):.3f}' for _, g in te.groupby('day'))
    print(f'  {arm}   {kind:4s}  {sname:5s} {len(te):6d}  {te.y.mean():.3f}  {roc_auc_score(te.y, te.p):.4f} {brier_score_loss(te.y, te.p):.4f}  | {byday}')
te = PRED[('B', 'LR', 'NULL')][0]
print(f'  market alone (1 - ask_leader normalised, no fit), arm-B rows: AUC {roc_auc_score(te.y, te.ask_dog / (te.ask_dog + te.ask_lead)):.4f} '
      f'Brier {brier_score_loss(te.y, te.ask_dog / (te.ask_dog + te.ask_lead)):.4f}')

print('  on the REAL REV call rows (age 0; label = REV side wins; p = model p for that side):')
for (arm, kind, sname), (_, rv) in PRED.items():
    r = rv[0]; ps = np.where(r.side == r.dog, r.p, 1 - r.p)
    print(f'    {arm} {kind:4s} {sname:5s} n {len(r):5d} base {r.win.mean():.3f} AUC {roc_auc_score(r.win, ps):.4f} Brier {brier_score_loss(r.win, ps):.4f}')
r = PRED[('B', 'LR', 'NULL')][1][0]; mk = 1 - np.where(r.side == 'UP', r.ask_dn, r.ask_up) / (r.ask_up + r.ask_dn)
print(f'    market alone on the same rows: AUC {roc_auc_score(r.win, mk):.4f}; lane p: AUC {roc_auc_score(r.win, r.lane_p):.4f}')

# ---------------------------------------------------------------- trading cells
SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip_vec(u):
    (q1, v1), (q2, v2), (q3, v3) = SLIP
    return np.where(u <= q1, v1, np.where(u >= q3, v3, np.where(u <= q2, v1 + (v2 - v1) * (u - q1) / (q2 - q1), v2 + (v3 - v2) * (u - q2) / (q3 - q2))))
def london(win, ask, runs=a.runs, seed=11):
    rng = np.random.default_rng(seed); n = len(win); win = np.asarray(win); ask = np.asarray(ask)
    fill = rng.random((runs, n)) <= np.where(win == 1, 0.541, 0.650)
    px = np.clip(ask + slip_vec(rng.random((runs, n))), 0.01, 0.99); sh = 10 / px; fee = 0.07 * sh * px * (1 - px)
    tot = (fill * (np.where(win == 1, sh, 0) - 10 - fee)).sum(1); spent = (fill * (10 + fee)).sum(1)
    return tot.mean() / max(spent.mean(), 1e-9), tot

def first(df, ok):
    d = df[ok].sort_values(['epoch', 'ts']); return d.groupby('epoch', sort=True).head(1)
def pick(df, theta, universe):
    if universe == 'ALL':
        d = df.assign(side=df.dog, ask=df.ask_dog, opp=df.ask_lead, win=df.y, ps=df.p)
    else:
        d = df.assign(ps=np.where(df.side == df.dog, df.p, 1 - df.p))
    ok = (d.ask <= 0.90) & (d.ps / (d.ask * cost(d.ask)) - 1 >= theta)
    if universe.startswith('REV&R1'): ok &= d.lane_p / (d.ask * cost(d.ask)) >= 1
    return first(d, ok)

GRID = []
def cell(label, R, cand_epochs=None, null_R=None, extra=None):
    if len(R) == 0: print(f'  {label:44s} none'); return None
    v = per1(R.win.values, R.ask.values); h = len(R) // 2
    dm = pd.Series(v).groupby(R.day.values).mean(); neg = int((dm < 0).sum())
    ex, tot = london(R.win.values, R.ask.values)
    rng = np.random.default_rng(7); fl = rng.random((1000, len(R))) < 0.5
    alt = np.where(fl, per1(1 - R.win.values, R.opp.values), v).mean(1); pperm = float((alt >= v.mean()).mean())
    s = f'  {label:44s} n{len(R):5d}{"*" if len(R) < 60 else " "} hit {100*R.win.mean():4.1f}% ask {R.ask.median():.2f} | paper {v.mean():+.3f} (H1 {v[:h].mean():+.3f} H2 {v[h:].mean():+.3f}) neg days {neg}/{len(dm)} perm p {pperm:.3f} | LONDON {ex:+.3f}/$1 tot ${tot.mean():+.0f} [p05 {np.percentile(tot,5):+.0f} p95 {np.percentile(tot,95):+.0f}]'
    pair = None
    if null_R is not None:
        ep = sorted(set(R.epoch) | set(null_R.epoch)); mw = dict(zip(R.epoch, R.win)); nw = dict(zip(null_R.epoch, null_R.win))
        # right = the better decision on that candle: traded and won, or stayed out while the other rule's trade lost
        # (a plain 'traded and won' count would reward whichever rule simply trades more)
        mine = [bool(mw[e]) if e in mw else (e in nw and not nw[e]) for e in ep]
        theirs = [bool(nw[e]) if e in nw else (e in mw and not mw[e]) for e in ep]
        b = sum(x and not y for x, y in zip(mine, theirs)); c = sum(y and not x for x, y in zip(mine, theirs))
        from math import comb
        pm = min(1.0, 2 * sum(comb(b + c, k) * 0.5 ** (b + c) for k in range(0, min(b, c) + 1))) if b + c else 1.0
        mp = dict(zip(R.epoch, v)); npp = dict(zip(null_R.epoch, per1(null_R.win.values, null_R.ask.values)))
        dd = np.array([mp.get(e, 0.0) - npp.get(e, 0.0) for e in ep]); sf = np.random.default_rng(5).choice([-1, 1], (2000, len(dd)))
        psf = float(((sf * dd).mean(1) >= dd.mean()).mean())
        s += f' | vs NULL: McNemar {b}v{c} p={pm:.3f}, candle-PnL diff {dd.sum():+.1f}$1 sign-flip p={psf:.3f}'
        pair = (mine, theirs)
    print(s)
    GRID.append(dict(label=label, n=len(R), paper=v.mean(), h1=v[:h].mean(), h2=v[h:].mean(), london=ex, perm=pperm, neg=neg, days=len(dm), R=R, pair=pair))
    return GRID[-1]

print('\n== BASELINES (lane as it is), same test days, London exec')
BASE = {}
for arm, tdays in ARMS.items():
    for age in (0, 1):
        r = REV[age][REV[age].day.isin(tdays)]
        BASE[(arm, age, 'R1')] = cell(f'arm {arm} REV R1 lane-p   age{age}', first(r, (r.ask <= .9) & (r.lane_p / (r.ask * cost(r.ask)) >= 1)))
        cell(f'arm {arm} REV R0 first call age{age}', first(r, r.ask <= .9))

for arm in ARMS:
    for universe, age in (('ALL', 0), ('REV', 0), ('REV&R1', 0), ('REV', 1), ('REV&R1', 1)):
        print(f'\n== arm {arm}  universe {universe}  quote age {age} s')
        for kind in ('LR', 'GBM'):
            for th in THETAS:
                res = {}
                for sname in ('NULL', 'FULL'):
                    te, rv = PRED[(arm, kind, sname)]
                    res[sname] = pick(te if universe == 'ALL' else rv[age], th, universe)
                for sname in ('NULL', 'FULL'):
                    g = cell(f'{kind:3s} {sname} theta {th:.2f}', res[sname], null_R=(res['NULL'] if sname == 'FULL' else None))
                    if g: g.update(arm=arm, universe=universe, age=age, kind=kind, theta=th, set=sname)

# ---------------------------------------------------------------- verify.py on the best-looking FULL cells (by London per$1, n >= 60)
def run_verify(best):
    print(f"\n== verify.py: arm {best['arm']} {best['universe']} age {best['age']} {best['kind']} FULL theta {best['theta']}")
    R = best['R']; f = Finding(f"REV brain {best['arm']}/{best['universe']}/age{best['age']}/{best['kind']}/th{best['theta']}", per_fire=best['london'], n=best['n'])
    f.grading(venues_outcome={e: OUT[e] for e in R.epoch}, v12_lane_actual=LA)
    f.quote_age('same-instant' if best['age'] == 0 else 'stale', max_age_s=float(best['age']), source='Polymarket tape q')
    f.sample({'cell': best['n']})
    f.halves(best['h1'], best['h2'])
    f._add('permutation control', best['perm'] <= 0.01, f"coin-flip side at the opposite ask, p={best['perm']:.3f}")
    same = lambda g, st: g.get('set') == st and all(g.get(k) == best[k] for k in ('arm', 'universe', 'age', 'kind'))
    f.sweep([g['london'] for g in GRID if same(g, 'FULL')])
    f.costs({c: per1(R.win.values, np.minimum(.99, R.ask.values + c)).mean() for c in (0.0, 0.02, 0.05)})
    f.null(best['london'], BASE[(best['arm'], best['age'], 'R1')]['london'], 'REV R1 lane-p baseline (London)')
    nl = [g for g in GRID if same(g, 'NULL') and g['theta'] == best['theta']]
    f.null(best['london'], nl[0]['london'] if nl else -9, 'same cell, venue-only NULL learner (London)')
    if best['pair']: f.paired(*best['pair'])
    return f.verdict()
cand = [g for g in GRID if g.get('set') == 'FULL' and g['n'] >= 60]
run_verify(max(cand, key=lambda g: g['london']))
run_verify(max([g for g in cand if g['age'] == 0], key=lambda g: g['london']))
