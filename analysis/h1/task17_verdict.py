"""Task 17.2 THE VERDICT — the pre-registered 100-fire read on the frozen 11.2 model.

Criteria were set before the forward window opened and restated at n=95 before the 100th fire landed:
  >= 100 forward fires, POSITIVE IN BOTH HALVES, and verify.py verdict True.
This script applies them. It does not choose a cell, a margin or a window.
"""
import sys, json, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

H1 = '/home/user/Django-final-project/analysis/h1'
HONEST_BASELINE = 0.018      # the same replay under the at-or-after rule (Task 20)


def main():
    f = json.load(open('%s/task17_forward_state.json' % H1))['fires']
    per = np.array([x['pnl'] for x in f])
    hit = np.array([x['hit'] for x in f], float)
    wk = np.array([x['wknd'] for x in f], bool)
    h = len(per) // 2

    print('forward fires %d  per-fire %+.3f  hit %.1f%%  total %+.2f'
          % (len(per), per.mean(), 100 * hit.mean(), per.sum()))
    print('halves  %+.3f / %+.3f' % (per[:h].mean(), per[h:].mean()))
    print('weekday n=%d %+.3f   weekend n=%d %+.3f%s'
          % ((~wk).sum(), per[~wk].mean(), wk.sum(), per[wk].mean(),
             '' if wk.sum() >= 60 else '   <- weekend under the 60 bar, NOT READ'))

    F = Finding('Task 17.2 VERDICT - frozen 11.2 model, 100-fire forward test',
                per_fire=per.mean(), n=len(per))
    F.quote_age('at-or-after', 0.0, 'NEXT collector sample at or after the decision second')
    F.sample({'forward fires': len(per)})
    F.halves(per[:h].mean(), per[h:].mean())
    F.null(per.mean(), HONEST_BASELINE, 'the honest-rule replay it was tested against')
    print()
    print('  (grading: engine candles.actual = Predict.fun\'s settling source; == Tokyo'
          ' financial_result on 383/383, Task 21)')
    ok = F.verdict()
    print('VERDICT', ok, '->', 'CONFIRMED' if ok else 'REFUTED')


if __name__ == '__main__':
    main()
