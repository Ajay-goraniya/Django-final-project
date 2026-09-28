#!/usr/bin/env python3
"""EF-2 step 4: export the fitted model so London can score its REAL attempts. READ-ONLY, master OFF.

Writes learner/v12_2/ef2/ef2_model.json and ef2_scorer.py.

WHAT IS FITTED. The walk-forward numbers in EF2.md are the honest out-of-sample estimate; the EXPORTED model
is refitted on ALL days, because it will be applied to attempts that happen after every day in the sample.
Those are two different objects and the json says so in its own metadata rather than leaving it to be
inferred.

WHAT LONDON MUST REPRODUCE, and the scorer refuses to guess about any of it:
  - the 44 engine feature values as its own decide path computes them, under the engine's own key names;
  - own_ask / opp_ask for the side being scored;
  - d_ask_1s / d_ask_5s / d_ask_30s = own-side ask now minus own-side ask ~1/5/30 s ago;
  - dip30 = own-side ask now minus the MINIMUM own-side ask over the last 30 s;
  - sec, and p_side = the engine's p for THIS side (1 - p for the side the engine did not pick).
A missing key raises. It does not impute, because an imputed feature here is a silent wrong answer on a
model whose whole point is to notice small asymmetries.
"""
import sys, json, time, datetime as dt, numpy as np

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import fit_logistic, predict, auc, ROWS

OUTDIR = '/home/ubuntu/claude-work/repo/learner/v12_2/ef2'


def main(grid_note=None):
    z = np.load(ROWS, allow_pickle=True)
    X, y, day = z['X'], z['y'].astype(float), z['day']
    names = [str(s) for s in z['names']]
    keep = np.all(np.isfinite(X), axis=1)
    X, y, day = X[keep], y[keep], day[keep]
    mu, sd = X.mean(0), X.std(0); sd = np.where(sd < 1e-9, 1.0, sd)
    w = fit_logistic(((X - mu) / sd).astype(np.float32), y)
    p = predict(w, ((X - mu) / sd).astype(np.float64))
    ins = auc(y, p)
    days = sorted(set(day.tolist()))

    model = dict(
        name='ef2', version=1,
        produced_by='Zurich (eu-central-2), analysis/zurich/ef2_model.py + ef2_export.py',
        produced_at=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        what='P(this side wins | buying THIS side at THIS ask at THIS second). One model, no direction '
             'model plus a gate.',
        fitted_on=dict(rows=int(len(y)), days=days, candles=int(len(set(z['ep'][keep].tolist()))),
                       label='1 if this side is the side the venue resolved to (gamma outcomePrices)',
                       base_rate=float(y.mean())),
        caveat='This object is refitted on ALL days. The out-of-sample numbers in analysis/zurich/EF2.md '
               'come from the walk-forward fits (day k on days < k), NOT from this object. In-sample AUC '
               f'here is {ins:.4f} and must not be quoted as performance.',
        model_type='logistic', link='p = 1 / (1 + exp(-(intercept + w . ((x - mean) / sd))))',
        features=names, mean=[float(v) for v in mu], sd=[float(v) for v in sd],
        intercept=float(w[0]), coef=[float(v) for v in w[1:]],
        feature_notes=dict(
            engine_features='the first 44 names are the engine decide_log feature keys, in the engine\'s own '
                            'sorted order; London computes them already',
            own_ask='best ask on the side being scored, as quoted at the decision instant',
            opp_ask='best ask on the other side at the same instant',
            d_ask_1s='own_ask now minus own_ask ~1 s ago (positive = the ask has risen)',
            d_ask_5s='own_ask now minus own_ask ~5 s ago',
            d_ask_30s='own_ask now minus own_ask ~30 s ago',
            dip30='own_ask now minus the MINIMUM own_ask over the last 30 s; 0 means we are at the low, '
                  'large means the ask has already bounced. This is the selected-dip detector.',
            sec='seconds into the candle, 15-240',
            p_side='the engine p for THIS side; for the side the engine did not pick, 1 - p'),
        decision_rule=dict(
            fire_when='p_win / (ask * (1 + 0.07 * (1 - ask))) - 1 >= margin',
            price_for_decision='the QUOTED ask at the decision instant, never the fill price - deciding at '
                               'the fill price is a 250 ms lookahead',
            margins_tested=[0.0, 0.02, 0.05, 0.10],
            note=grid_note or 'see analysis/zurich/EF2.md for the full margin grid'),
        not_a_deploy='This is a scorer for London to evaluate its OWN real attempts. It is not a config, it '
                     'does not arm anything, and no box should trade on it without the owner saying so.')
    with open(f'{OUTDIR}/ef2_model.json', 'w') as f:
        json.dump(model, f, indent=1)
    print(f'wrote {OUTDIR}/ef2_model.json  ({len(names)} features, {len(y):,} rows, in-sample AUC {ins:.4f})')
    return model


if __name__ == '__main__':
    main()
