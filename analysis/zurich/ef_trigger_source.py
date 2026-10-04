#!/usr/bin/env python3
"""What TRIGGERS an EF fire - the book moving, or the model moving? READ-ONLY, Zurich decide_log, gamma-graded.

London's real fills: attempt-1 on a book <50 ms old -> 69% candle fill, against 31% per attempt overall. So the
fires that work are the ones aimed at a book the engine has just seen move. Zurich's decide_log has NO quote-age
column (44 feature keys, none of them an age), so V's proxy is the available test: classify each fire by what
CHANGED since the previous same-candle pass, 257 ms earlier (p50 row gap).

Per fire, against the previous pass in the same candle, using OUR side's ask on BOTH rows (up_ask/dn_ask; the
logged `ask` equals the own-side book ask on 852,162/852,162 rows, so this is exact):
  dask = own ask now - own ask on the previous pass          dp = p now - p on the previous pass
  BOOK     |dask| >= 1 tick  and  |dp| <  0.01   - the book moved to us
  MODEL    |dask| <  1 tick  and  |dp| >= 0.01   - the model moved to the book
  BOTH     |dask| >= 1 tick  and  |dp| >= 0.01
  NEITHER  |dask| <  1 tick  and  |dp| <  0.01   - qualified on sub-tick/sub-0.01 drift alone
  FLIP     the previous pass logged the OTHER side, so dp is not comparable (p is not symmetric across a flip:
           residual mean +0.0715, 0.0% within 0.02 - the flip is itself selected on p moving). |dask| still is.
  FIRST    no previous pass in the candle.
BOOK and BOTH are split by the SIGN of dask, because "the book moved to us" is a dip we chase and "the book moved
away" is not the same event at all.

`p` is the RAW model p: meta has ef_profile raw_v10_live25 and calibration.enabled false (and p_raw is NULL on all
1,240,440 live rows), so raw25 reads p directly and fixed15 applies the Platt a=1.0677 b=-0.3208 to it.

Fill simulator, scoring, halves and the permutation control are IMPORTED from ef_persist so they are the same
code that produced EF_PERSIST.md - nothing is re-implemented here.

Then the policy V asked for: fire only on a pass whose book moved; a MODEL-triggered pass WAITS for the next
book change and fires there if it still qualifies. Reported strict (a candle's first pass has no observed book
change, so it waits) and lenient (treat the candle's first pass as a book change).
"""
import sys, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef_persist import (load, fill, runs, fire_at_k, score, halves, perm as _perm, line, HDR, MIN_CELL,
                        qual_raw, qual_fix, per1, cost, TICK)

EPS = 1e-9
CLASSES = ['BOOK-dn', 'BOOK-up', 'MODEL', 'BOTH-dn', 'BOTH-up', 'NEITHER', 'FLIP-mv', 'FLIP-still', 'FIRST']

def classify(cand):
    """Attach cls / dask / dp / dt to every pass, comparing with the previous pass in the same candle."""
    for ep, rs in cand.items():
        for i, r in enumerate(rs):
            r['dask'] = r['dp'] = None; r['dt'] = None
            if i == 0: r['cls'] = 'FIRST'; r['bookmv'] = None; continue
            pv = rs[i - 1]
            own = pv['ua'] if r['side'] == 'UP' else pv['da']
            r['dt'] = r['t'] - pv['t']
            if not (0.01 < own < 0.99):
                r['cls'] = 'FIRST'; r['bookmv'] = None; continue    # no usable previous quote on our side
            r['dask'] = r['ask'] - own
            bk = abs(r['dask']) >= TICK - EPS
            r['bookmv'] = bk
            if pv['side'] != r['side']:
                r['cls'] = 'FLIP-mv' if bk else 'FLIP-still'; continue
            r['dp'] = r['p_raw'] - pv['p_raw']
            pm = abs(r['dp']) >= 0.01
            sg = 'dn' if r['dask'] < 0 else 'up'
            r['cls'] = f'BOOK-{sg}' if (bk and not pm) else f'BOTH-{sg}' if (bk and pm) else 'MODEL' if pm else 'NEITHER'

def perm(sel):
    """ef_persist's sign-flip permutation. 500 draws; 100 on the very large all-pass cells, where the p-value is
    descriptive rather than a gate (the gate cells in (1) and (4) are one fire per candle and always get 500)."""
    n = sum(1 for _, q in sel if q is not None)
    return _perm(sel, draws=500 if n <= 5000 else 100)


def rev(sel):
    """Mean ask reversion between the fire and the +250 ms row, on OUR side. EF_VETO_V2's mechanism."""
    v = [r['later'] - r['ask'] for r, _ in sel if r.get('later') is not None]
    return float(np.mean(v)) if v else float('nan')

H2 = HDR + f'{"revC":>7}{"dask":>7}{"dt":>6}'

def line2(lab, sel):
    s = score(sel)
    if not s:
        print(f'  {lab:30s}{len(sel):5d}      (no fills)'); return None
    a, b = halves(sel); pp, pm = perm(sel)
    da = [r['dask'] for r, _ in sel if r.get('dask') is not None]
    dts = [r['dt'] for r, _ in sel if r.get('dt') is not None]
    print(f'  {lab:30s}{s["n"]:5d}{s["nf"]:6d}{100*s["fillpct"]:7.1f}%{100*s["win"]:7.1f}%'
          f'{s["per1"]:+9.3f}{s["total"]:+9.1f}{(a or 0):+8.3f}{(b or 0):+8.3f}{pp:7.3f}{pm:+8.3f}{s["days"]:>5}'
          f'{100*rev(sel):+7.2f}{(100*np.mean(da) if da else float("nan")):+7.2f}'
          f'{(np.median(dts) if dts else float("nan")):6.0f}' + ('  *n<60' if s['nf'] < MIN_CELL else ''))
    return dict(lab=lab, sel=sel, **s)

def fires(cand, qual):
    """The engine's own behaviour: the FIRST qualifying pass of each candle."""
    out = {}
    for ep, rs in cand.items():
        r = fire_at_k(rs, qual, 1)
        if r is not None: out[ep] = r
    return out

def policy(cand, qual, lenient):
    """Fire only where the book moved; a model-only pass waits for the next book change that still qualifies."""
    out = {}; waited = {}
    for ep, rs in cand.items():
        runs(rs, qual)
        first = None
        for r in rs:
            if r['run'] == 0: continue
            if first is None: first = r
            mv = r['bookmv'] if r['bookmv'] is not None else lenient
            if mv:
                out[ep] = r
                if first is not r: waited[ep] = (first, r)
                break
    return out, waited

def policy_inverse(cand, qual):
    """The mirror of V's policy: fire only on a pass whose book did NOT move (the model moved to a still book)."""
    out = {}
    for ep, rs in cand.items():
        runs(rs, qual)
        for r in rs:
            if r['run'] == 0: continue
            if r['bookmv'] is False:
                out[ep] = r; break
    return out, None


if __name__ == '__main__':
    cand, _ = load()
    classify(cand)
    allrows = [r for rs in cand.values() for r in rs]
    days = sorted({r['day'] for r in allrows})
    print(f'candles graded {len(cand)}, passes {len(allrows)}, days {days}')
    cnt = collections.Counter(r['cls'] for r in allrows)
    print('  ALL passes by class: ' + '  '.join(f'{k} {cnt[k]} ({100*cnt[k]/len(allrows):.1f}%)' for k in CLASSES))

    for pname, qual in (('raw25', qual_raw), ('fixed15', qual_fix)):
        f1 = fires(cand, qual)
        sel_all = [(r, fill(r)) for r in f1.values()]
        print(f'\n{"="*160}\n(1) {pname}: THE ACTUAL FIRE (first qualifying pass of each candle), split by what moved\n{"="*160}')
        print(H2)
        line2('ALL fires', sel_all)
        print('  ' + '-' * 158)
        for cl in CLASSES:
            line2(cl, [(r, q) for r, q in sel_all if r['cls'] == cl])
        print(f'\n  (2) {pname}: EVERY qualifying pass (not just the first per candle) - the conditional edge by class')
        print(H2)
        qa = [(r, fill(r)) for rs in cand.values() for r in runs(rs, qual) if r['run'] >= 1]
        line2('ALL qualifying passes', qa)
        print('  ' + '-' * 158)
        for cl in CLASSES:
            line2(cl, [(r, q) for r, q in qa if r['cls'] == cl])

        print(f'\n  (3) {pname}: PER DAY, fires / fill% / per$1, book moved vs model-only')
        print(f'    {"day":8s}{"fires":>7}{"BOOK moved":>22}{"model-only":>22}{"no prev quote":>22}')
        for d in days:
            sd = [(r, q) for r, q in sel_all if r['day'] == d]
            row = f'    {d:8s}{len(sd):7d}'
            for want in (True, False, None):
                s_ = [(r, q) for r, q in sd if r['bookmv'] is want]
                v = score(s_); nf = sum(1 for _, q in s_ if q is not None)
                cell = f'{len(s_)} {100*nf/len(s_):.0f}% {v["per1"]:+.3f}' if (s_ and v) else f'{len(s_)} -'
                row += f'{cell:>22}'
            print(row)

        print(f'\n  (4) {pname}: POLICY - fire only when the book moved, model-only passes wait for the next book change')
        print(H2)
        base = line2('baseline: first qualifying', sel_all)
        for lenient in (False, True):
            pol, waited = policy(cand, qual, lenient)
            sel = [(r, fill(r)) for r in pol.values()]
            lab = 'policy, FIRST waits' if not lenient else 'policy, FIRST counts as mv'
            line2(lab, sel)
            if not lenient:
                inv, _w = policy_inverse(cand, qual)
                line2('INVERSE: only book-still', [(r, fill(r)) for r in inv.values()])
            lost = sorted(set(f1) - set(pol))
            both = [e for e in sorted(set(f1) & set(pol))
                    if fill(f1[e]) is not None and fill(pol[e]) is not None]
            if both:
                v1 = sum(per1(f1[e]['win'], fill(f1[e])) * cost(fill(f1[e])) for e in both) / sum(cost(fill(f1[e])) for e in both)
                vp = sum(per1(pol[e]['win'], fill(pol[e])) * cost(fill(pol[e])) for e in both) / sum(cost(fill(pol[e])) for e in both)
                mvd = [e for e in both if f1[e]['t'] != pol[e]['t']]
                print(f'      paired on {len(both)} candles filled in both ({len(mvd)} moved to a later pass): '
                      f'baseline {v1:+.3f} vs policy {vp:+.3f}' + ('  *n<60' if len(both) < MIN_CELL else ''))
            wl = [pol[e]['t'] - w[0]['t'] for e, w in waited.items()]
            print(f'      candles the policy gives up entirely: {len(lost)} of {len(f1)}; waited on {len(waited)}'
                  + (f', wait p50 {np.median(wl):.0f} ms p90 {np.percentile(wl,90):.0f} ms' if wl else ''))
