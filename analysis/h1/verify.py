"""The verification harness every H1 finding must pass BEFORE it is reported.

The user, 2026-09-11: "verification is the most important part so this kind of issues should never
be happening." On 09-10 a claimed +0.44/fire edge turned out to be a grading artifact, and it was
caught by V rather than by me. The failure was not a lack of skill, it was relying on remembering to
check. This turns each of those checks into a function that has to return PASS.

Use it like this:

    from verify import Finding
    f = Finding('EF2 later entry', per_fire=0.153, n=128)
    f.grading(engine=actual_from_candles, alt=actual_from_venues)   # do the labels even agree?
    f.sample(cells={'<1bps': 77, '1-2.5': 76})
    f.halves(first=0.141, second=0.045)
    f.permutation(y, pred, price, pnl_fn)
    f.sweep([0.05, 0.11, 0.18, 0.24])
    f.costs({0.0: 0.44, 0.05: 0.25, 0.10: 0.16})
    f.verdict()          # prints the table and returns True only if nothing FAILED

Every check is deliberately conservative: it fails loudly rather than passing quietly.
"""
import numpy as np

MIN_CELL = 60          # H1's standing bar: under 60 graded fires in a bucket is "insufficient"
PERM_DRAWS = 200


class Finding:
    def __init__(self, name, per_fire=None, n=None):
        self.name, self.per_fire, self.n = name, per_fire, n
        self.rows = []

    def _add(self, check, ok, detail, fatal=True):
        self.rows.append((check, 'PASS' if ok else ('FAIL' if fatal else 'WARN'), detail))
        return ok

    # ---- 1. the one that actually bit us ----
    def grading(self, **sources):
        """Do the candidate outcome labels agree? Pass dicts of key -> 'UP'/'DOWN'.

        The venues `outcome` table is Polymarket's resolution; Predict.fun settles on the engine's
        candles.actual. They disagree on ~10% of candles, and grading with the wrong one invented a
        large fake edge. If two sources disagree at all, you must say which one the venue pays on.
        """
        names = list(sources)
        if len(names) < 2:
            return self._add('grading provenance', False,
                             'only one outcome source given - name the source the VENUE SETTLES ON '
                             'and confirm it is not a different venue\'s oracle')
        a, b = sources[names[0]], sources[names[1]]
        common = set(a) & set(b)
        if not common:
            return self._add('grading provenance', False, 'sources share no keys - cannot compare')
        dis = sum(1 for k in common if a[k] != b[k])
        rate = dis / len(common)
        return self._add('grading provenance', rate == 0,
                         '%s vs %s disagree on %d/%d (%.1f%%)%s'
                         % (names[0], names[1], dis, len(common), 100 * rate,
                            '' if rate == 0 else ' - results are only valid on the settling source'))

    # ---- 2. sample size ----
    def sample(self, cells):
        thin = {k: v for k, v in cells.items() if v < MIN_CELL}
        return self._add('sample size', not thin,
                         'all %d cells >= %d' % (len(cells), MIN_CELL) if not thin
                         else 'under the %d bar: %s' % (MIN_CELL, thin))

    # ---- 3. both halves ----
    def halves(self, first, second):
        ok = np.sign(first) == np.sign(second) and first != 0 and second != 0
        return self._add('both halves', ok, 'h1 %+.3f / h2 %+.3f%s'
                         % (first, second, '' if ok else '  <- SIGN FLIPS, not a finding'))

    # ---- 4. the control that separates signal from plumbing ----
    def permutation(self, y, pred, price, pnl_fn, draws=PERM_DRAWS, seed=7):
        """Permute the MODEL'S PREDICTIONS, keep outcome<->price paired.

        Do NOT shuffle the labels: that also destroys the market's calibration, so cheap longshots
        'win' at the base rate and the control prints a fake profit. That mistake cost an hour on
        09-10 and is the reason this function exists in this exact form.
        """
        y, pred, price = map(np.asarray, (y, pred, price))
        ok = ~np.isnan(pred)
        real = pnl_fn(y, pred, price)
        rng = np.random.default_rng(seed)
        sims = []
        for _ in range(draws):
            p = pred.copy()
            v = p[ok].copy()
            rng.shuffle(v)
            p[ok] = v
            s = pnl_fn(y, p, price)
            if not np.isnan(s):
                sims.append(s)
        sims = np.array(sims)
        pval = float((sims >= real).mean()) if len(sims) else 1.0
        return self._add('permutation control', pval <= 0.01,
                         'real %+.3f vs permuted mean %+.3f (p95 %+.3f), p=%.3f over %d draws'
                         % (real, sims.mean(), np.percentile(sims, 95), pval, len(sims)))

    # ---- 5. monotonicity ----
    def sweep(self, values):
        """A smoothly monotone sweep is a real regularity; one peaking at your chosen value is noise."""
        v = np.asarray(values, float)
        d = np.diff(v)
        mono = bool((d >= 0).all() or (d <= 0).all())
        peak_inside = 0 < int(np.argmax(v)) < len(v) - 1
        return self._add('sweep shape', mono,
                         ('monotone: ' if mono else 'NON-monotone: ') + np.array2string(v, precision=3)
                         + ('  <- peaks at an interior point, classic overfit' if peak_inside and not mono else ''))

    # ---- 6. does it survive being paid for ----
    def costs(self, by_haircut):
        ks = sorted(by_haircut)
        worst = by_haircut[ks[-1]]
        return self._add('cost sensitivity', worst > 0,
                         ' '.join('%+.0fc:%+.3f' % (100 * k, by_haircut[k]) for k in ks)
                         + ('' if worst > 0 else '  <- dies once you pay realistically'))

    # ---- 7. beat the obvious null ----
    def null(self, mine, null_value, null_name='null'):
        ok = mine > null_value
        return self._add('beats the null', ok, 'mine %+.3f vs %s %+.3f' % (mine, null_name, null_value))

    def verdict(self):
        w = max(len(r[0]) for r in self.rows)
        print('=' * 78)
        head = 'FINDING: %s' % self.name
        if self.per_fire is not None:
            head += '   (%+.3f/fire' % self.per_fire + (', n=%d)' % self.n if self.n else ')')
        print(head)
        print('=' * 78)
        for check, status, detail in self.rows:
            print('  [%-4s] %-*s  %s' % (status, w, check, detail))
        failed = [r[0] for r in self.rows if r[1] == 'FAIL']
        print('-' * 78)
        if failed:
            print('  VERDICT: NOT A FINDING - failed: %s' % ', '.join(failed))
        else:
            print('  VERDICT: passes all checks. Report it WITH its sample size and limits.')
        print()
        return not failed


if __name__ == '__main__':
    # Validating the validator on the two real cases from 09-10: it must REJECT the claim that
    # turned out to be false, and ACCEPT the one that survived scrutiny.
    print('SELF-TEST 1 - the cross-venue claim I got wrong (should be REJECTED)\n')
    rng = np.random.default_rng(0)
    keys = range(641)
    engine = {k: ('UP' if rng.random() < 0.5 else 'DOWN') for k in keys}
    poly = {k: (engine[k] if rng.random() > 0.103 else ('DOWN' if engine[k] == 'UP' else 'UP'))
            for k in keys}
    bad = Finding('cross-venue spread rule @ t=210', per_fire=0.441, n=259)
    bad.grading(engine_actual=engine, venues_outcome=poly)
    bad.sample({'t=210': 259})
    bad.halves(first=0.461, second=0.419)
    bad.costs({0.0: 0.441, 0.05: 0.253, 0.10: 0.164})
    bad.null(mine=0.441, null_value=0.011, null_name='level-only')
    bad.verdict()
    print('(Correctly rejected on grading provenance alone - every other check passed,')
    print(' which is exactly why the checks have to be run together and this one has to be first.)\n')

    print('SELF-TEST 2 - the distance premise (should PASS)\n')
    good = Finding('P(close same side) rises with |price(S)-open|', per_fire=None)
    good.grading(engine_actual=engine, tokyo_financial_result=engine)
    good.sample({'<1': 24420, '1-2.5': 19508, '2.5-5': 16022, '5-10': 9467, '10-25': 2930, '25+': 229})
    good.halves(first=0.530, second=0.523)
    good.sweep([0.526, 0.593, 0.639, 0.698, 0.748, 0.817])
    good.verdict()
