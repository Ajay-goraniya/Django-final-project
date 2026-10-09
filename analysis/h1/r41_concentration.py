"""Concentration check on the calibrated EF arms -- is my +0.55 also one lottery ticket?

V found two replay edges (REVERSAL +0.46, MAIN +0.066) were each a single 0.010-ask fill. The same
test must be run on my own result before it is trusted: r39's calibrated arm under the live rule.
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r39_live_rule as M

STAKE = 3.0


def block(lab, rows):
    v = np.array(sorted([M.per1(r['ask'], r['won']) for r in rows], reverse=True))
    n, tot = len(v), v.sum()
    print('\n  %s  n=%d  per$1 %+.4f  total $%+.2f' % (lab, n, v.mean(), tot * STAKE))
    for k in (1, 3, 5):
        if n <= k:
            continue
        rest = v[k:]
        print('     drop top %d -> n=%-4d per$1 %+8.4f  total $%+8.2f   (top %d carried %.1f%% of total)'
              % (k, len(rest), rest.mean(), rest.sum() * STAKE, k, 100 * v[:k].sum() / tot))
    cheap = [r for r in rows if r['ask'] < 0.10]
    keep = [r for r in rows if r['ask'] >= 0.10]
    if keep:
        vk = np.array([M.per1(r['ask'], r['won']) for r in keep])
        print('     ask >= 0.10  -> n=%-4d per$1 %+8.4f  total $%+8.2f   (%d fires under 0.10 removed)'
              % (len(keep), vk.mean(), vk.sum() * STAKE, len(cheap)))
    if cheap:
        vc = np.array([M.per1(r['ask'], r['won']) for r in cheap])
        print('     the sub-0.10 fires: n=%d, %d won, per$1 %+.4f, total $%+.2f'
              % (len(cheap), sum(1 for r in cheap if r['won']), vc.mean(), vc.sum() * STAKE))
    top = sorted(rows, key=lambda r: -M.per1(r['ask'], r['won']))[:5]
    print('     top 5 fills: ' + ' | '.join(
        'ask %.3f sec %3d %s %+.2f' % (r['ask'], r['sec'], 'W' if r['won'] else 'L',
                                       M.per1(r['ask'], r['won'])) for r in top))


def main():
    R = M.loo_cal(M.load())
    print('CONCENTRATION CHECK -- EF under the live rule (ev >= threshold), stake $%.0f' % STAKE)
    block('raw p, own regime threshold', M.fires(R, 'p'))
    block('calibrated pooled (a,b)', M.fires(R, 'p_cal'))
    block('calibrated leave-one-day-out', M.fires(R, 'p_loo'))


if __name__ == '__main__':
    main()
