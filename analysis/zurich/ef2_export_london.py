import sys, json, datetime as dt, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import fit_logistic, predict, auc, ROWS
from ef2_london import ABSENT
z = np.load(ROWS, allow_pickle=True)
X, y = z['X'], z['y'].astype(float)
names = [str(s) for s in z['names']]
keep = np.all(np.isfinite(X), axis=1)
X, y = X[keep], y[keep]
cols = [j for j, n in enumerate(names) if n not in ABSENT]
sub = [names[j] for j in cols]
Xs = X[:, cols]
mu, sd = Xs.mean(0), Xs.std(0); sd = np.where(sd < 1e-9, 1.0, sd)
w = fit_logistic(((Xs - mu) / sd).astype(np.float32), y)
ins = auc(y, predict(w, ((Xs - mu) / sd).astype(np.float64)))
m = dict(name='ef2_london', version=1,
         produced_by='Zurich, analysis/zurich/ef2_london_refit.py',
         produced_at=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
         what='P(this side wins | buying THIS side at THIS ask at THIS second), fitted ONLY on the features '
              "London's final-test table carries.",
         why_a_separate_model='Scoring London\'s table with the 52-feature model and imputing the 8 it lacks '
              'keeps AUC (0.8608 -> 0.8573) but INVERTS the trading result (win 65.9% -> 32.5%, per $1 +0.016 '
              '-> -0.076). AUC is rank-based and survives imputation; the decision depends on the calibrated '
              'LEVEL of p_win against the price, and the missing features carry 34.2% of the coefficient '
              'mass. Refitting on London\'s own keys restores it: walk-forward AUC 0.8609 on 44 features '
              'against 0.8608 on 52, and per $1 +0.020 against +0.016. USE THIS ONE ON LONDON\'S TABLE.',
         omitted=sorted(ABSENT),
         fitted_on=dict(rows=int(len(y)), features=len(sub), base_rate=float(y.mean())),
         caveat=f'Refitted on ALL days for export. Out-of-sample numbers are in analysis/zurich/EF2.md. '
                f'In-sample AUC here is {ins:.4f} and must not be quoted as performance.',
         model_type='logistic', link='p = 1 / (1 + exp(-(intercept + w . ((x - mean) / sd))))',
         features=sub, mean=[float(v) for v in mu], sd=[float(v) for v in sd],
         intercept=float(w[0]), coef=[float(v) for v in w[1:]],
         decision_rule=dict(fire_when='p_win / (ask * (1 + 0.07 * (1 - ask))) - 1 >= margin',
                            price_for_decision='the QUOTED ask, never the fill price',
                            margins_tested=[0.0, 0.02, 0.05, 0.10],
                            walk_forward_best='margin 0.02: per $1 +0.020, total +161.1, 89.8% sim fill, '
                                              '66.0% win, halves +0.028/+0.012, perm 0.007 - and it still '
                                              'does NOT pass the owner\'s bar, which requires beating '
                                              'fixed15 on per $1 as well'),
         not_a_deploy='A scorer for London to evaluate its own real attempts. Not a config; arms nothing.')
open('/home/ubuntu/claude-work/repo/learner/v12_2/ef2/ef2_model_london.json', 'w').write(json.dumps(m, indent=1))
print(f'wrote ef2_model_london.json: {len(sub)} features, in-sample AUC {ins:.4f}')
