#!/usr/bin/env python3
"""Arm E: the nightly refit behind EF-5's CAUSAL column. PAPER ONLY - no order path, no network client.

V pre-registered this 09-28 16:1x. EF-5 showed that what makes the causal rule work is not the quantile
cut but the NIGHTLY REFIT on a growing window - so the production form is to actually do that:

    00:05 UTC   refit EF-4gb (squared-loss stumps, absolute price columns excluded) on every day to date
                threshold = the q-quantile of YESTERDAY's predictions UNDER TONIGHT'S MODEL
    all day     fire at the first pass with p_side >= 0.5 and pred >= threshold, one per candle, S0=0
                E1 q=0.90 (primary)   E2 q=0.95

WHAT THIS CANNOT DO, measured and on record before it runs. The threshold is a VALUE carried across a
model refit, and each refit moves the prediction scale, so the same q lands at a different rank each day.
On the five days available that produced 4 fills one day and 188 the next, with 74% of the profit on a
single day. A rank-stable rule (fire on today's top 1-q fraction) is not causal - it needs the whole day
before the first candle. So arm E is expected to be lumpy, and lumpiness is not evidence against it; the
decision rule is the A/B/C one and nothing else.

DEVIATION FROM THE BRIEF: V said "all days so far". Training is capped at MAXDAYS because 1.6M rows x 46
features is already ~590 MB and unbounded growth takes the box down eventually. Reported, not hidden.

It cannot trade: no broker import, no socket, engine DB opened read-only, writes only its own JSON.
"""
import sys, os, json, time, hashlib, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1
from ef4 import gb_reg, gb_reg_pred, LEVEL
import ef3_shadow as S

OUTDIR = '/home/ubuntu/pm_ef3'
MAXDAYS = 21
QS = {'q90': 0.90, 'q95': 0.95}
MIN_TRAIN = 50000


def build_all():
    """Every resolved candle the archive still holds, through ef3_shadow's own selftest-proven builder."""
    a_ = __import__('sqlite3').connect(f'file:{S.LIVE}?mode=ro', uri=True)
    keys = json.loads(a_.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    cand, vo, nk = S.load_candles()
    X, tgt, day, tss = [], [], [], []
    for ep, lst in cand.items():
        rows = S.build_rows(lst, ep, vo[ep], nk)
        d = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        for r in rows:
            X.append(r['x']); day.append(d); tss.append(r['ts'])
            tgt.append(per1(r['win'], r['q']) if r['q'] == r['q'] else 0.0)
    return ((np.stack(X).astype(np.float64) if X else np.zeros((0, 52))), np.array(tgt),
            np.array(day), np.array(tss, dtype=np.int64), keys)


if __name__ == '__main__':
    t0 = time.time()
    # --day lets a PAST day's model be built for parity testing: trained on days < that day, exactly as
    # the 00:05 run would have built it. It is not a way to re-fit today.
    argday = None
    for i, a in enumerate(sys.argv):
        if a == '--day' and i + 1 < len(sys.argv): argday = sys.argv[i + 1]
    today = argday or dt.datetime.now(dt.timezone.utc).strftime('%m-%d')
    out = f'{OUTDIR}/ef5_model_{today}.json'
    if os.path.exists(out) and '--force' not in sys.argv:
        sys.exit(f'{out} exists - tonight is already fitted, refusing to refit (use --force deliberately)')
    X, tgt, day, tsall, keys = build_all()
    if not len(X): sys.exit('no rows')
    names = list(keys) + ['own_ask', 'opp_ask', 'd_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30', 'sec', 'p_side']
    assert X.shape[1] == len(names), f'{X.shape[1]} cols vs {len(names)} names'
    cols = [i for i in range(len(names)) if names[i] not in LEVEL]
    X = X[:, cols]; fnames = [names[i] for i in cols]
    days = sorted(set(day.tolist()))
    train_days = [d for d in days if d < today][-MAXDAYS:]
    if not train_days: sys.exit('no complete day to train on')
    prev = train_days[-1]
    tr = np.isin(day, train_days)
    if tr.sum() < MIN_TRAIN: sys.exit(f'only {tr.sum():,} training rows, need {MIN_TRAIN:,}')
    mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd > 0, sd, 1.0)
    g = gb_reg((X[tr] - mu) / sd, tgt[tr])
    pv = day == prev
    pp = gb_reg_pred(g, (X[pv] - mu) / sd)
    # E3's trailing window reaches back across the day boundary, and EF-6 scored those rows under TODAY's
    # model. A live shadow cannot do that on its own - yesterday's rows were scored last night, under
    # last night's model. So tonight's job emits the seed: the previous day's final hour, re-scored under
    # the new model. Without it E3's first hour each day would silently use a different model from the
    # one its backtest used.
    ts_prev = tsall[pv]
    if len(ts_prev):
        cut = ts_prev.max() - 3600_000
        m = ts_prev >= cut
        seed = [[int(a), float(b)] for a, b in zip(ts_prev[m], pp[m])]
    else: seed = []
    body = dict(trees=[[int(j), float(t), float(vl), float(vr)] for j, t, vl, vr in g['trees']],
                base=float(g['base']), mean=mu.tolist(), sd=sd.tolist(), names=fnames,
                thr={k: float(np.quantile(pp, q)) for k, q in QS.items()},
                seed=seed, seed_n=len(seed),
                qs=QS, for_day=today, prev_day=prev, train_days=train_days,
                n_train=int(tr.sum()), n_prev=int(pv.sum()), sec_floor=0,
                note='Arm E nightly refit. Target = realised $ per $1 as executed by the +250 ms FAK sim. '
                     'Absolute BTC price columns excluded by construction. Threshold is the q-quantile of '
                     "the previous day's predictions under THIS model.")
    body['sha256'] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    body['fitted_at'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    json.dump(body, open(out, 'w'))

    # ---- the engine-side copy V's ef6_lane.py loads ------------------------------------------------
    # Same trees, same base, names in the engine's key space. decide_log_features IS the engine key list,
    # so no renaming is needed; the only names with no plain engine equivalent are the underscore-prefixed
    # ones the logger adds, and they are reported rather than silently emitted as if they were features.
    ENGINE_BUILT = {'own_ask', 'opp_ask', 'd_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30', 'sec', 'p_side'}
    odd = [n for n in fnames if n.startswith('_')]
    used = sorted({int(t[0]) for t in body['trees']})
    used_names = [fnames[j] for j in used]
    edir = '/home/ubuntu/claude-work/repo/learner/v12_2/ef6'
    os.makedirs(edir, exist_ok=True)
    year = dt.datetime.now(dt.timezone.utc).strftime('%Y')
    epath = f'{edir}/ef6_{year}-{today}.json'
    json.dump(dict(names=fnames, base=body['base'], trees=body['trees']), open(epath, 'w'))
    print(f'  engine copy -> {epath}')
    print(f'    names {len(fnames)}: {len(fnames) - len(ENGINE_BUILT & set(fnames))} engine feature keys '
          f'+ {sorted(ENGINE_BUILT & set(fnames))}')
    print(f'    NO PLAIN ENGINE EQUIVALENT (logger-added, underscore-prefixed): {odd or "none"}')
    print(f'    features actually SPLIT ON by the trees ({len(used_names)}): {used_names}')
    missing = [n for n in used_names if n not in ENGINE_BUILT and n.startswith('_')]
    if missing:
        print(f'    *** WARNING: the trees split on {missing}, which ef6_lane cannot build -> predict() '
              f'returns None on every row and THE LANE WILL NEVER FIRE ***')
    if 'opp_ask' in used_names:
        print(f'    *** WARNING: the trees split on opp_ask, which is NOT in ef6_lane\'s row -> '
              f'predict() returns None on every row and THE LANE WILL NEVER FIRE ***')

    print(f'{today}: trained on {tr.sum():,} rows over {len(train_days)} days {train_days}')
    print(f'  thresholds from {prev} ({pv.sum():,} rows): '
          + '  '.join(f'{k} {v:+.4f}' for k, v in body["thr"].items()))
    print(f'  -> {out}  sha256 {body["sha256"][:16]}  [{time.time()-t0:.0f}s]')
    for f in sorted(os.listdir(OUTDIR)):
        if f.startswith('ef5_model_') and f < f'ef5_model_{sorted(days)[-MAXDAYS] if len(days) > MAXDAYS else "00-00"}.json':
            os.remove(f'{OUTDIR}/{f}'); print(f'  pruned {f}')
