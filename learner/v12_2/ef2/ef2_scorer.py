#!/usr/bin/env python3
"""Score one EF-2 candidate row -> P(this side wins). Pure standard library, no numpy needed.

    from ef2_scorer import Scorer
    s = Scorer()
    p, info = s.score(row)            # info['imputed'] = list of feature names filled with the training mean
    ev = s.ev(p, ask)                 # p / (ask * (1 + 0.07*(1-ask))) - 1

MISSING KEYS (V, 09-28: London's final-test table carries 35 of the model's 52). A missing or non-finite
feature is filled with its TRAINING MEAN, which after standardisation contributes exactly zero to the logit -
the model falls back to knowing nothing about that feature rather than to a wrong value. Every call returns
the list of what was imputed, and `strict=True` restores the old behaviour of raising.

This is a real loss of information, not a free pass, and it is not evenly spread. `dip30` - own ask minus its
own 30 s MINIMUM - is the selected-dip detector, the one feature built specifically to capture the record of
being picked off. London's table has ask_1s/5s/30s but not a 30 s running minimum, so dip30 will be imputed
unless London adds it, and it is cheap to add: keep a 30 s deque of your own side's best ask and subtract its
min from the current ask. `score_batch` reports the imputation rate across a table so the cost is visible
before any conclusion is drawn from the scores.

The model is a logistic on standardised features. It is a SCORER, not a config - it arms nothing.
"""
import json, math, os

_HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 0.07


class Scorer:
    def __init__(self, path=None, strict=False):
        with open(path or os.path.join(_HERE, 'ef2_model.json')) as f:
            m = json.load(f)
        self.m = m
        self.strict = strict
        self.names = list(m['features'])
        self.mean = [float(v) for v in m['mean']]
        self.sd = [float(v) for v in m['sd']]
        self.coef = [float(v) for v in m['coef']]
        self.intercept = float(m['intercept'])
        if not (len(self.names) == len(self.mean) == len(self.sd) == len(self.coef)):
            raise ValueError('ef2_model.json is inconsistent: features/mean/sd/coef differ in length')

    def missing(self, row):
        out = []
        for k in self.names:
            v = row.get(k)
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not math.isfinite(float(v)):
                out.append(k)
        return out

    def score(self, row, strict=None):
        """Returns (p_win, info). info: imputed=[names], n_imputed=int, coef_mass_imputed=float.

        coef_mass_imputed is the share of total |coefficient| the imputed features carry - a better guide to
        how much was lost than the plain count, since 20 irrelevant features missing costs less than one
        important one."""
        strict = self.strict if strict is None else strict
        bad = self.missing(row)
        if bad and strict:
            raise KeyError(f'ef2 scorer (strict): {len(bad)} feature(s) missing or non-finite: {bad[:8]}'
                           + (' ...' if len(bad) > 8 else ''))
        tot = sum(abs(c) for c in self.coef) or 1.0
        lost = 0.0
        z = self.intercept
        for k, mu, sd, c in zip(self.names, self.mean, self.sd, self.coef):
            v = row.get(k)
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not math.isfinite(float(v)):
                lost += abs(c)
                continue                      # training mean -> standardised 0 -> contributes nothing
            z += c * ((float(v) - mu) / (sd if sd else 1.0))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        return p, dict(imputed=bad, n_imputed=len(bad), coef_mass_imputed=lost / tot)

    def score_batch(self, rows):
        """Score many rows and summarise what was imputed across the whole table."""
        ps, ns, mass, seen = [], [], [], {}
        for r in rows:
            p, info = self.score(r)
            ps.append(p); ns.append(info['n_imputed']); mass.append(info['coef_mass_imputed'])
            for k in info['imputed']: seen[k] = seen.get(k, 0) + 1
        n = max(len(ps), 1)
        return ps, dict(rows=len(ps), mean_n_imputed=sum(ns) / n,
                        mean_coef_mass_imputed=sum(mass) / n,
                        always_missing=sorted(k for k, v in seen.items() if v == len(ps)),
                        sometimes_missing=sorted(k for k, v in seen.items() if 0 < v < len(ps)))

    @staticmethod
    def ev(p_win, ask):
        """EV per $1 staked at the QUOTED ask, in the engine's own convention.

        The decision is taken on the QUOTED ask, never on the fill price - pricing the decision at the fill
        is a 250 ms lookahead. The fill price is what the economics are settled at afterwards."""
        be = ask * (1.0 + RATE * (1.0 - ask))
        return p_win / be - 1.0 if be > 0 else float('-inf')

    def fires(self, row, ask, margin):
        p, _ = self.score(row)
        return self.ev(p, ask) >= margin


if __name__ == '__main__':
    s = Scorer()
    print(f'ef2 scorer loaded: {len(s.names)} features')
    print(f'  {s.m["caveat"]}')
    full = {k: 0.0 for k in s.names}
    full['own_ask'] = 0.45; full['sec'] = 30.0; full['p_side'] = 0.62
    p, i = s.score(full)
    print(f'  full row      -> p_win {p:.4f}  ev {s.ev(p, 0.45):+.4f}  imputed {i["n_imputed"]}')
    LONDON_MISSING = ['dip30', 'own_ask', 'opp_ask']
    part = {k: v for k, v in full.items() if k not in ('dip30',)}
    p2, i2 = s.score(part)
    print(f'  without dip30 -> p_win {p2:.4f}  ev {s.ev(p2, 0.45):+.4f}  imputed {i2["n_imputed"]} '
          f'({100*i2["coef_mass_imputed"]:.1f}% of coefficient mass)')
    p3, i3 = s.score({'own_ask': 0.45})
    print(f'  nearly empty  -> p_win {p3:.4f}  imputed {i3["n_imputed"]} '
          f'({100*i3["coef_mass_imputed"]:.1f}% of coefficient mass) - degrades, does not raise')
    try:
        s.score({'own_ask': 0.45}, strict=True); print('  strict=True DID NOT raise - that is a bug')
    except KeyError:
        print('  strict=True still raises, for callers that want the old behaviour')
