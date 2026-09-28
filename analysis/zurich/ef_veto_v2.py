#!/usr/bin/env python3
"""VETO v2: the delay veto on EVERY raw25 fire I have, not only the decide_log window. READ-ONLY.

The 250 ms brain (EF_VETO.md) had 263 fires on 4 test days because decide_log only starts 09-24 12:30.
Every EF fire, however, stores its own decision features in `signals.decision`, back to the start of the
journals - 686 raw25 fires. The price of using them is the delay resolution: before decide_log the only
forward price is `tape1s`, which is 1 Hz, so the label here is the **+1 s** ask, not +250 ms.

  fires   = every EF signal across all four journals whose STORED decision gives raw EV >= 0.25
            (recomputed from the stored p_raw and ask, so it does not matter which profile was live),
            deduped on epoch - the same candle decided in two journals is one observation.
  label   = per$1 at OUR side's tape1s ask at fire_ts + 1 s (first row at or after it; achieved lag reported)
  features= the same 35 inputs as v1: the stored feature dict minus absolute price levels, then
            logit(ask), logit(p_raw), sec/300
  model   = ridge, walk-forward by day, standardised on TRAINING rows only

Grading: the venue's own gamma resolution. Execution: the London model (fill .541 win / .650 lose,
slippage -1/+2/+11c on top of the delayed ask).
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections, bisect, numpy as np

JS = ['/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3',
      '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich_2.sqlite3',
      '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_paper1.sqlite3',
      '/home/ubuntu/pm_paper_zurich/polymarket_v12_live_zurich.sqlite3']
TAPE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
RATE, STAKE, RUNS, MIN_CELL = 0.07, 10.0, 1000, 60
MAX_LAG = 4                     # seconds; a 1 Hz tape can miss a second, but not four
DROP = {'_price', '_ask_up', '_ask_dn', '_venue_ok', 'ref_now', 'ref_open', 'bn_line_now',
        'bn_line_open', 'ref_src', 'ref_inst', 'ref_inst_ok', 'sec_left', 'ts_ms'}
THETAS = (-0.10, -0.05, 0.0, 0.05, 0.10)

cost = lambda q: 1 + RATE * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)
be = lambda q: q * cost(q)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out

def tape():
    c = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
    rows = [(int(t), float(u), float(d)) for t, u, d in c.execute(
        'SELECT ts,up_ask,dn_ask FROM tape1s WHERE up_ask IS NOT NULL AND dn_ask IS NOT NULL ORDER BY ts')]
    return [r[0] for r in rows], rows

def load():
    vo = outcomes(); TT, TR = tape()
    seen, fires, dup, nolabel, nograde = set(), [], 0, 0, 0
    keys = None
    for path in JS:
        try: c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        except Exception: continue
        try: it = c.execute("SELECT epoch,ts,side,decision FROM signals WHERE kind='EF' "
                            "AND decision IS NOT NULL ORDER BY ts").fetchall()
        except Exception: continue
        for ep, ts, side, dec in it:
            if ep in seen: dup += 1; continue
            try: d = json.loads(dec)
            except Exception: continue
            f = d.get('features')
            if not isinstance(f, dict) or not side: continue
            pr = d.get('p_raw'); pr = pr if isinstance(pr, (int, float)) else d.get('p')
            ask = d.get('ask')
            if not isinstance(pr, (int, float)) or not isinstance(ask, (int, float)): continue
            if not (0.01 < ask < 0.99): continue
            if pr / be(ask) - 1 < 0.25: continue
            if ep not in vo: nograde += 1; continue
            if keys is None: keys = sorted(k for k in f if k not in DROP)
            if any(f.get(k) is None for k in keys): continue
            # TWO-SOURCE TRAP, measured not assumed: tape1s is the engine's periodic 1 Hz book read, the
            # decision ask is the executor's read at the fire. Their gap at the SAME second is already
            # +8.88c on this sample, while one second of actual repricing is only +0.95c. Taking the raw
            # +1 s tape ask as the price therefore charges ~9c of phantom cost to every fire - the same
            # artifact TIMING_TEST.md documented, walked into again here.
            # So the label is built TAPE-TO-TAPE and anchored on the decision ask:
            #     q1 = decision ask + (tape@+1s - tape@fire second)
            t0 = int(ts)
            i0 = bisect.bisect_left(TT, t0)
            if i0 >= len(TT) or TT[i0] - t0 > 1: nolabel += 1; continue
            q0 = TR[i0][1] if side == 'UP' else TR[i0][2]
            i = bisect.bisect_left(TT, t0 + 1)
            if i >= len(TT) or TT[i] - (t0 + 1) > MAX_LAG: nolabel += 1; continue
            qt = TR[i][1] if side == 'UP' else TR[i][2]
            if not (0.01 < q0 < 0.99 and 0.01 < qt < 0.99): nolabel += 1; continue
            q_raw = qt                                    # the naive label, kept for the comparison
            q = min(0.99, max(0.01, ask + (qt - q0)))     # the corrected, tape-to-tape label
            seen.add(ep)
            fires.append(dict(ep=ep, ts=ts, side=side, ask=ask, p_raw=float(pr), q1=q, q1_naive=q_raw,
                              tape0=q0, tape1=qt,
                              lag=TT[i] - int(ts), sec=int(ts) - ep, win=int(side == vo[ep]),
                              feats=[float(f[k]) for k in keys],
                              day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')))
        c.close()
    return sorted(fires, key=lambda r: r['ts']), keys, dict(dup=dup, nolabel=nolabel, nograde=nograde)

def fit_ridge(X, y, l2=1.0):
    X = np.c_[np.ones(len(X)), X]
    R = np.eye(X.shape[1]) * l2; R[0, 0] = 0
    return np.linalg.solve(X.T @ X + R, X.T @ y)
pred = lambda w, X: np.c_[np.ones(len(X)), X] @ w

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def delayed(sel):
    if not sel: return None
    return sum(per1(r['win'], r['q1']) * cost(r['q1']) for r in sel) / sum(cost(r['q1']) for r in sel)

def london(sel, seed=17, runs=RUNS):
    if not sel: return None, None, None
    rng = random.Random(seed); tots = []; spent = []; posd = []
    for _ in range(runs):
        t = s = 0.; day = collections.defaultdict(float)
        for r in sel:
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r['q1'] + slip(rng))); sh = STAKE / px
            fee = RATE * sh * px * (1 - px); s += STAKE + fee
            g = (sh if r['win'] else 0) - STAKE - fee
            t += g; day[r['day']] += g
        tots.append(t); spent.append(s)
        if day: posd.append(sum(1 for v in day.values() if v > 0) / len(day))
    return (np.mean(tots) / max(1e-9, np.mean(spent))), float(np.mean(tots)), (np.mean(posd) if posd else None)

def halves(sel, fn):
    h = len(sel) // 2; s = sorted(sel, key=lambda r: r['ts'])
    return (fn(s[:h]) if h else None), (fn(s[h:]) if len(s) - h else None)

def perm(sel, draws=600, seed=11):
    if not sel: return (float('nan'),) * 3
    real = delayed(sel); rng = random.Random(seed); sims = []
    for _ in range(draws):
        alt = [dict(r, win=1 - r['win'], q1=min(0.99, max(0.01, 1 - r['q1'] + 0.01))) if rng.random() < 0.5 else r
               for r in sel]
        sims.append(delayed(alt))
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), st.mean(sims), sims[int(.95 * len(sims))]

if __name__ == '__main__':
    fires, keys, drops = load()
    names = list(keys) + ['logit_ask', 'logit_p_raw', 'sec_over_300']
    days = sorted({r['day'] for r in fires})
    print(f'raw25 fires with stored features, graded and labelled: {len(fires)} on {len(days)} days '
          f'{days[0]}..{days[-1]}')
    print(f'  dropped: {drops["dup"]} duplicate epochs across journals, {drops["nograde"]} ungraded, '
          f'{drops["nolabel"]} with no tape1s ask within {MAX_LAG}s of +1s')
    lags = np.array([r['lag'] for r in fires])
    print(f'  achieved label lag: p50 {np.percentile(lags,50):.0f}s p90 {np.percentile(lags,90):.0f}s max {lags.max()}s')
    g0 = np.array([r['tape0'] - r['ask'] for r in fires]); gd = np.array([r['tape1'] - r['tape0'] for r in fires])
    print(f'  TWO-SOURCE CHECK: tape ask at the FIRE SECOND minus the decision ask = {100*g0.mean():+.2f}c mean '
          f'(p50 {100*np.median(g0):+.2f}c) - that is source mismatch, not drift.')
    print(f'  one second of real repricing, tape-to-tape = {100*gd.mean():+.2f}c mean (p50 {100*np.median(gd):+.2f}c). '
          f'The naive +1 s tape label would charge {100*np.mean([r["q1_naive"]-r["ask"] for r in fires]):+.2f}c.')
    print(f'  LABEL USED: decision ask + tape-to-tape drift -> effective move {100*np.mean([r["q1"]-r["ask"] for r in fires]):+.2f}c mean')
    print(f'  features {len(names)}; win rate {100*np.mean([r["win"] for r in fires]):.1f}%; '
          f'ask p50 {np.median([r["ask"] for r in fires]):.2f}')

    Xraw = np.c_[np.array([r['feats'] for r in fires], float),
                 np.array([[lg(r['ask']), lg(r['p_raw']), r['sec'] / 300.0] for r in fires], float)]
    y = np.array([per1(r['win'], r['q1']) for r in fires])
    dayarr = np.array([r['day'] for r in fires])
    p = np.full(len(fires), np.nan)
    for d in days[1:]:
        tr, te = dayarr < d, dayarr == d
        if tr.sum() < 40 or te.sum() == 0: continue
        mu, sd = Xraw[tr].mean(0), Xraw[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
        p[te] = pred(fit_ridge((Xraw[tr] - mu) / sd, y[tr]), (Xraw[te] - mu) / sd)
    for r, pv in zip(fires, p): r['pred'] = pv
    sub = [r for r in fires if not np.isnan(r['pred'])]
    print(f'  walk-forward scored {len(sub)} fires on {len({r["day"] for r in sub})} test days\n')

    print(f'{"="*134}\nKEEP vs VETO at pred >= 0\n{"="*134}')
    print(f'  {"cell":22s}{"n":>5}{"":2s}{"hit":>7}{"delayed":>10}{"H1":>9}{"H2":>9}{"permP":>8}{"permMean":>10}'
          f'{"LONDON":>9}{"lonTot$":>9}{"posDays":>9}')
    for nm, sel in (('KEEP (pred >= 0)', [r for r in sub if r['pred'] >= 0]),
                    ('VETO (pred <  0)', [r for r in sub if r['pred'] < 0]),
                    ('ALL raw25 fires', sub)):
        if not sel: print(f'  {nm:22s}    0   (none)'); continue
        v = delayed(sel); a, b = halves(sel, delayed); pp, pm, _ = perm(sel)
        lon, tot, posd = london(sel)
        nd = len({r['day'] for r in sel})
        print(f'  {nm:22s}{len(sel):5d}{"" if len(sel)>=MIN_CELL else " *":2s}'
              f'{100*np.mean([r["win"] for r in sel]):6.1f}%{v:+10.3f}{(a or 0):+9.3f}{(b or 0):+9.3f}'
              f'{pp:8.3f}{pm:+10.3f}{lon:+9.3f}{tot:+9.1f}{100*(posd or 0):8.0f}%')

    print(f'\n  PER DAY (n, delayed, London):')
    print(f'    {"day":8s}{"keep n":>8}{"keep dly":>10}{"keep LON":>10}{"veto n":>8}{"veto dly":>10}{"veto LON":>10}')
    byd = collections.defaultdict(lambda: {'K': [], 'V': []})
    for r in sub: byd[r['day']]['K' if r['pred'] >= 0 else 'V'].append(r)
    kd_pos = vd_pos = 0
    for d in sorted(byd):
        k, vv = byd[d]['K'], byd[d]['V']
        kd, vd = delayed(k), delayed(vv)
        kl = london(k, runs=200)[0] if k else None
        vl = london(vv, runs=200)[0] if vv else None
        if kl is not None and kl > 0: kd_pos += 1
        if vl is not None and vl > 0: vd_pos += 1
        f2 = lambda x: f'{x:+10.3f}' if x is not None else f'{"-":>10}'
        print(f'    {d:8s}{len(k):>8}{f2(kd)}{f2(kl)}{len(vv):>8}{f2(vd)}{f2(vl)}')
    print(f'    KEEP London-positive on {kd_pos}/{len(byd)} days; VETO London-positive on {vd_pos}/{len(byd)}')

    print(f'\n{"="*134}\nSWEEP of the veto bar\n{"="*134}')
    print(f'  {"keep when pred >=":20s}{"n":>5}{"hit":>7}{"delayed":>10}{"LONDON":>9}{"H1":>9}{"H2":>9}{"permP":>8}')
    vals = []
    for th in THETAS:
        sel = [r for r in sub if r['pred'] >= th]
        if not sel: print(f'  {th:+20.2f}    0   (none)'); vals.append(float('nan')); continue
        v = delayed(sel); a, b = halves(sel, delayed); pp, _, _ = perm(sel, draws=300)
        lon = london(sel, runs=300)[0]
        vals.append(lon)
        print(f'  {th:+20.2f}{len(sel):5d}{100*np.mean([r["win"] for r in sel]):6.1f}%{v:+10.3f}{lon:+9.3f}'
              f'{(a or 0):+9.3f}{(b or 0):+9.3f}{pp:8.3f}' + ('  *n<60' if len(sel) < 60 else ''))
    dv = np.diff([v for v in vals if not math.isnan(v)])
    mono = bool((dv >= 0).all() or (dv <= 0).all())
    print(f'  London column {["%+.3f" % v for v in vals]} -> '
          + ('MONOTONE' if mono else 'NOT monotone')
          + (f', peaks at an interior point' if not mono and 0 < int(np.nanargmax(vals)) < len(vals) - 1 else ''))

    print(f'\n{"="*134}\nCROSS-CHECK vs the 250 ms brain on the decide_log days\n{"="*134}')
    try:
        import sys as _s; _s.path.insert(0, 'analysis/zurich')
        import ef_veto as V1
        r1, n1 = V1.load()
        X1 = V1.raw_matrix(r1, n1)
        y1 = np.array([per1(r['win'], r[f'ask{V1.D_MS}']) for r in r1])
        d1 = np.array([r['day'] for r in r1]); ds1 = sorted(set(d1))
        p1 = np.full(len(r1), np.nan)
        for d in ds1[1:]:
            tr, te = d1 < d, d1 == d
            if tr.sum() < 500 or te.sum() == 0: continue
            mu, sd = X1[tr].mean(0), X1[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
            p1[te] = pred(fit_ridge((X1[tr] - mu) / sd, y1[tr]), (X1[te] - mu) / sd)
        best = {}
        for r, pv in zip(r1, p1):
            if np.isnan(pv) or r['ev'] < 0.25: continue
            if r['ep'] not in best or r['t'] < best[r['ep']][0]: best[r['ep']] = (r['t'], pv)
        agree = tot_ = 0; both = []
        for r in sub:
            if r['ep'] not in best: continue
            tot_ += 1
            a2 = (r['pred'] >= 0); b2 = (best[r['ep']][1] >= 0)
            agree += (a2 == b2); both.append((a2, b2))
        if tot_:
            kk = sum(1 for a2, b2 in both if a2 and b2); vv2 = sum(1 for a2, b2 in both if not a2 and not b2)
            print(f'  candles in both: {tot_};  AGREEMENT {100*agree/tot_:.1f}%  '
                  f'(both keep {kk}, both veto {vv2}, disagree {tot_-agree})')
            print(f'  v2 keeps {sum(1 for a2,_ in both if a2)}/{tot_}, the 250 ms brain keeps '
                  f'{sum(1 for _,b2 in both if b2)}/{tot_}')
        else: print('  no overlapping candles')
    except Exception as e:
        print(f'  cross-check unavailable: {type(e).__name__}: {str(e)[:120]}')
