#!/usr/bin/env python3
"""FROZEN window-1 calibrated-venue filter for REVERSAL, tested out of sample on window 2. READ-ONLY.

Nothing is fitted here. The coefficients come from V's window-1 fit (NC-9 lead, 2,194 REV call rows,
0-240 s, same-second quote) and are hard-coded:

    p = sigmoid(0.4951 + 0.8907*logit(ask) - 0.5533*sec/300)

Rule fixed before the run: on the window-2 REV call stream, 0-240 s, past-only age-0 quote, ask <= 0.90,
take the FIRST call per candle with p/(ask*(1+0.07*(1-ask))) - 1 >= theta. theta 0.03 is the frozen
decision; 0, 0.05 and 0.10 are printed as context only.

This is a clean out-of-sample test in the one way the earlier brain work was not: the model was fit on a
different window and is not refit, so there is no walk-forward thinness and no selection on window-2
outcomes. Note what the model IS, though: ask and sec only - i.e. a frozen version of the venue-only
null, not a new information source.

`REV R1` is reported on the SAME candles the cell selected, so the comparison is paired; only the
candles where the two rules disagree carry information, and that count is printed.

Grading: results.actual (the venues snapshot on the branch ends 09-16 and covers none of this window).
Execution: the London model from analysis/v/model/lane_exec_sim.py.
"""
import csv, sqlite3, bisect, math, random, numpy as np

VEN = '/tmp/venues_zurich_0923.sqlite3'
CALLS = '/tmp/calls_rev.csv'
B0, B_ASK, B_SEC = 0.4951, 0.8907, -0.5533        # FROZEN on window 1 - never refit here
SEC_LO, SEC_HI, MAX_ASK, AGE = 0, 240, 0.90, 0
STAKE, RUNS, SIMS = 10.0, 1000, 500

cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: (w / x - cost(x)) / cost(x)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))
frozen = lambda ask, sec: 1 / (1 + math.exp(-(B0 + B_ASK * lg(ask) + B_SEC * (sec / 300.0))))
ev = lambda p, ask: p / (ask * cost(ask)) - 1

def load():
    vq = sqlite3.connect(f'file:{VEN}?mode=ro', uri=True)
    Q = [(int(t), float(u), float(d)) for t, u, d in vq.execute('select ts,poly_up,poly_dn from q order by ts')
         if u is not None and d is not None]
    QT = [q[0] for q in Q]
    out = []
    for r in csv.DictReader(open(CALLS)):
        if r['kind'] != 'REVERSAL': continue
        ep, sec = int(r['epoch']), int(r['sec'])
        if not (SEC_LO <= sec <= SEC_HI): continue
        ts = ep + sec
        i = bisect.bisect_right(QT, ts) - 1
        if i < 0 or ts - QT[i] > AGE: continue                    # past-only, age 0
        ask, opp = (Q[i][1], Q[i][2]) if r['side'] == 'UP' else (Q[i][2], Q[i][1])
        if not (0 < ask <= MAX_ASK): continue
        out.append(dict(epoch=ep, sec=sec, ask=ask, opp=opp, win=int(r['win']), p_lane=float(r['p']),
                        p_frozen=frozen(ask, sec)))
    return out

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def london(R):
    rng = random.Random(11); tots = []; spent = []
    for _ in range(RUNS):
        t = s = 0.0
        for c in R:
            if rng.random() > (0.541 if c['win'] else 0.650): continue
            px = min(0.99, max(0.01, c['ask'] + slip(rng))); sh = STAKE / px
            fee = 0.07 * sh * px * (1 - px); s += STAKE + fee
            t += (sh if c['win'] else 0) - STAKE - fee
        tots.append(t); spent.append(s)
    tots = np.array(tots)
    return tots.mean() / max(1e-9, float(np.mean(spent))), tots.mean(), np.percentile(tots, 5), np.percentile(tots, 95)

def first(C, ok):
    seen = {}
    for c in sorted(C, key=lambda c: (c['epoch'], c['sec'])):
        if c['epoch'] not in seen and ok(c): seen[c['epoch']] = c
    return [seen[e] for e in sorted(seen)]

def show(name, R, rng):
    if not R: print(f'  {name:34s} none'); return None
    v = np.array([per1(c['win'], c['ask']) for c in R]); h = len(R) // 2
    sims = [np.mean([per1(1 - c['win'], c['opp']) if fl else per1(c['win'], c['ask'])
                     for c, fl in zip(R, rng.random(len(R)) < .5)]) for _ in range(SIMS)]
    pp = float(np.mean(np.array(sims) >= v.mean()))
    e, tot, lo, hi = london(R)
    print(f'  {name:34s} n{len(R):4d}{"*" if len(R) < 60 else " "} hit {100*np.mean([c["win"] for c in R]):5.1f}% '
          f'ask {np.median([c["ask"] for c in R]):.2f} paper {v.mean():+.3f} (H1 {v[:h].mean():+.3f} '
          f'H2 {v[h:].mean():+.3f}) LON {e:+.3f}/$1 ${tot:+.1f} [p05 {lo:+.1f}, p95 {hi:+.1f}] perm p {pp:.2f}')
    return v.mean()

if __name__ == '__main__':
    C = load()
    print(f'window-2 REV calls, {SEC_LO}-{SEC_HI}s, past-only age {AGE}s, ask<={MAX_ASK}: '
          f'{len(C)} calls on {len({c["epoch"] for c in C})} candles')
    print(f'frozen model p = sigmoid({B0} + {B_ASK}*logit(ask) {B_SEC}*sec/300)   NOT refit here')
    pf = [c['p_frozen'] for c in C]
    print(f'its p on this window: p05 {np.percentile(pf,5):.3f} p50 {np.percentile(pf,50):.3f} '
          f'p95 {np.percentile(pf,95):.3f};  ev>=0.03 on {100*np.mean([ev(c["p_frozen"],c["ask"])>=0.03 for c in C]):.1f}% of calls')
    rng = np.random.default_rng(7)
    print('\nFROZEN CELL (the decision) and the theta sweep as context:')
    cells = {}
    for th in (0.0, 0.03, 0.05, 0.10):
        R = first(C, lambda c: ev(c['p_frozen'], c['ask']) >= th)
        cells[th] = R
        show(f'frozen ev>={th:.2f}' + ('  <-- THE RULE' if th == 0.03 else ''), R, rng)
    print('\nPAIRED against plain REV R1 (lane p breakeven) on the SAME candles the rule picked:')
    for th in (0.0, 0.03, 0.05, 0.10):
        R = cells[th]
        if not R: continue
        eps = {c['epoch'] for c in R}
        R1 = first([c for c in C if c['epoch'] in eps], lambda c: ev(c['p_lane'], c['ask']) >= 0)
        both = {c['epoch'] for c in R1} & eps
        a = {c['epoch']: c for c in R}; b = {c['epoch']: c for c in R1}
        disc = [e for e in both if a[e]['sec'] != b[e]['sec']]
        print(f'  theta {th:.2f}: rule n{len(R)} on {len(eps)} candles | R1 fires on {len(R1)} of them, '
              f'{len(disc)} at a DIFFERENT second (only those carry information)')
        show(f'   R1 on the same candles', R1, rng)
