"""13.2.0 DRAFT - the delay brain's VETO on EF's own fires. OFF unless meta 'ef_veto' says enabled (owner's confirmation).

Why (NC-15, analysis/zurich/EF_DELAY_BRAIN.md, EF_VETO.md): EF's edge is real at the ask it SEES and mostly gone at the
ask it GETS ~0.25 s later (taker-order delay, itode=true). A ridge trained walk-forward on "per$1 at the +250 ms delayed ask"
splits EF's fires into a half that keeps its edge through the delay and a half that does not. This module only ever
REMOVES a fire; it never creates or widens one.

Inputs, exactly as the model was trained (analysis/zurich/ef_delay_brain.py, ef_veto.py):
  the decision's own feature dict d['features'] (the decide_log vector), in model['feature_names'] order, then
  logit_ask = logit(d['ask']), logit_p_raw = logit(d['p_raw'] or d['p']), sec_over_300 = (t - epoch)/300,
  logit clamped to [1e-3, 1-1e-3]. Standardised with the chosen fit's TRAINING mean/sd, then w0 + w.z.
A missing or non-finite input never vetoes: the fire goes through unchanged and the reason is recorded.
Pure functions, no I/O except load().
"""
import json, math

EXTRA = ('logit_ask', 'logit_p_raw', 'sec_over_300')
DEFAULT = dict(enabled=False, theta=0.0, fit='all_days')


def _logit(x):
    x = min(max(float(x), 1e-3), 1 - 1e-3)
    return math.log(x / (1 - x))


def load(path):
    with open(path) as fh:
        m = json.load(fh)
    if not m.get('intercept_first', False): raise ValueError('veto model: weights[0] must be the intercept')
    names = m['feature_names']
    for fit in [m['all_days']] + list(m.get('folds') or []):
        if not (len(fit['mean']) == len(fit['sd']) == len(names) and len(fit['weights']) == len(names) + 1):
            raise ValueError('veto model: mean/sd/weights do not match feature_names')
    return m


def vector(model, d, ep, t_s):
    """The model's input row, or (None, name_of_first_missing)."""
    f = d.get('features') or {}
    p_raw = d.get('p_raw') if d.get('p_raw') is not None else d.get('p')
    out = []
    for k in model['feature_names']:
        if k == 'logit_ask': v = None if d.get('ask') is None else _logit(d['ask'])
        elif k == 'logit_p_raw': v = None if p_raw is None else _logit(p_raw)
        elif k == 'sec_over_300': v = (float(t_s) - ep) / 300.0
        else: v = f.get(k)
        if not isinstance(v, (int, float)) or not math.isfinite(v): return None, k
        out.append(float(v))
    return out, None


def predict(model, x, fit='all_days'):
    p = model['all_days'] if fit == 'all_days' else next(fo for fo in model['folds'] if fo['test_day'] == fit)
    w = p['weights']; z = 0.0
    for xi, mu, sd, wi in zip(x, p['mean'], p['sd'], w[1:]):
        z += wi * (xi - mu) / (sd if abs(sd) > 1e-12 else 1.0)
    return w[0] + z


def apply(d, model, cfg, ep, t_s):
    """Return d unchanged, or with fire=False when the brain predicts the edge will not survive the delay."""
    if not d.get('fire') or model is None or not cfg.get('enabled'): return d
    x, missing = vector(model, d, ep, t_s)
    if x is None: return dict(d, veto='skipped: missing ' + str(missing))
    pred = predict(model, x, cfg.get('fit', 'all_days'))
    theta = float(cfg.get('theta', 0.0))
    if pred < theta:
        return dict(d, fire=False, veto_pred=round(pred, 4),
                    reason=f'Veto: delay brain {pred:+.3f} < {theta:+.2f} (edge not expected to survive the order delay)')
    return dict(d, veto_pred=round(pred, 4), veto='keep')
