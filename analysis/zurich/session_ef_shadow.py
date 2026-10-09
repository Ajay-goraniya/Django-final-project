#!/usr/bin/env python3
"""Does London's 00-13 vs 13-24 fixed15 split hold OUTSIDE 09-23..10-01? READ-ONLY. Owner via V.

London's real fixed15 fills 09-23..10-01 (n=366) split 00-13 UTC -235 / 13-24 UTC +151. The owner asks
whether that happens all the time. This is the independent check on Zurich's own EF history, and V's
instruction was to prefer DAYS NOT IN 09-23..10-01.

Nothing is re-derived: fires, the FIXED (= fixed15) predicate, gamma grading and the lane_exec_sim
London execution all come from stable_ef.py, which carries the frozen definitions.
Buckets fixed before looking: Asia 00-07, Europe 07-13, US 13-20, Late 20-24 UTC.
"""
import sys, collections, datetime as dt, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import stable_ef as S

STAKE = 10.0
SESS = [('Asia 00-07', 0, 7), ('Europe 07-13', 7, 13), ('US 13-20', 13, 20), ('Late 20-24', 20, 24)]
WINDOW = {f'09-{d}' for d in range(23, 31)} | {'10-01'}      # London's own window, to be avoided
hour = lambda r: dt.datetime.fromtimestamp(r['epoch'], dt.UTC).hour


def paper(rows):
    """$ at a flat $10, paid at the recorded ask with the exact fee - no execution model."""
    return sum(STAKE * S.per1(r['win'], r['ask']) for r in rows)


def block(title, rows):
    out = [f'\n{title}', f'  {"bucket":14s} {"n":>5s} {"win%":>7s} {"$ paper":>10s} {"$/$1 paper":>11s}'
           f' {"$ London":>10s} {"$/$1 London":>12s}   flag']
    for nm, lo, hi in SESS:
        sel = [r for r in rows if lo <= hour(r) < hi]
        if not sel:
            out.append(f'  {nm:14s} {0:5d} {"-":>7s} {"-":>10s} {"-":>11s} {"-":>10s} {"-":>12s}   no fires')
            continue
        w = sum(r['win'] for r in sel); pp = paper(sel)
        lper, ltot = S.london(sel, [STAKE] * len(sel))
        out.append(f'  {nm:14s} {len(sel):5d} {100*w/len(sel):6.1f}% {pp:+10.2f} {pp/(STAKE*len(sel)):+11.3f}'
                   f' {ltot:+10.2f} {lper:+12.3f}   ' + ('UNDER 60 FILLS' if len(sel) < 60 else ''))
    # the owner's own split
    lo13 = [r for r in rows if hour(r) < 13]; hi13 = [r for r in rows if hour(r) >= 13]
    for nm, sel in (('00-13', lo13), ('13-24', hi13)):
        if not sel: continue
        lper, ltot = S.london(sel, [STAKE] * len(sel))
        out.append(f'  {nm:14s} {len(sel):5d} {100*sum(r["win"] for r in sel)/len(sel):6.1f}% '
                   f'{paper(sel):+10.2f} {paper(sel)/(STAKE*len(sel)):+11.3f} {ltot:+10.2f} {lper:+12.3f}'
                   f'   ' + ('UNDER 60 FILLS' if len(sel) < 60 else ''))
    return out


def per_day(rows):
    out = ['\n  per day (London execution), 00-13 vs 13-24:',
           f'    {"day":6s} {"n":>4s} {"00-13 $":>9s} {"13-24 $":>9s}   00-13 result']
    lost = days = 0
    for d in sorted({r['day'] for r in rows}):
        dr = [r for r in rows if r['day'] == d]
        a = [r for r in dr if hour(r) < 13]; b = [r for r in dr if hour(r) >= 13]
        av = S.london(a, [STAKE] * len(a))[1] if a else 0.0
        bv = S.london(b, [STAKE] * len(b))[1] if b else 0.0
        if a:
            days += 1; lost += int(av < 0)
        out.append(f'    {d:6s} {len(dr):4d} {av:+9.2f} {bv:+9.2f}   '
                   + ('' if not a else ('LOST' if av < 0 else 'won')))
    out.append(f'    days with any 00-13 fires: {days}; days 00-13 LOST: {lost}')
    return out, lost, days


if __name__ == '__main__':
    rows = [r for r in S.load() if r['arm'] == 'FIXED']
    outside = [r for r in rows if r['day'] not in WINDOW]
    inside = [r for r in rows if r['day'] in WINDOW]
    L = [__doc__.strip(), '',
         f'FIXED (= fixed15) fires rebuilt from the engine diagnostics: {len(rows)} over '
         f'{len({r["day"] for r in rows})} days.',
         f'  days OUTSIDE 09-23..10-01 (the independent sample): '
         f'{sorted({r["day"] for r in outside})} -> {len(outside)} fires',
         f'  days INSIDE  09-23..10-01 (overlaps London, context only): '
         f'{sorted({r["day"] for r in inside})} -> {len(inside)} fires',
         f'  grading: gamma venue resolution where present, engine results.actual otherwise '
         f'({sum(1 for r in rows if r["gsrc"]=="gamma")} gamma / '
         f'{sum(1 for r in rows if r["gsrc"]!="gamma")} engine)']
    L += block('A. THE INDEPENDENT SAMPLE - days NOT in 09-23..10-01', outside)
    o, lost_o, days_o = per_day(outside); L += o
    L += block('B. CONTEXT - days inside 09-23..10-01 (same window London measured)', inside)
    i, lost_i, days_i = per_day(inside); L += i
    L += block('C. ALL DAYS TOGETHER', rows)
    a, lost_a, days_a = per_day(rows); L += a
    open('/home/ubuntu/claude-work/repo/analysis/zurich/SESSION_EF_SHADOW.txt', 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))
