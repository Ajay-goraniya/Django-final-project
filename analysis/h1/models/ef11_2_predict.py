"""Frozen Task 11.2 direction model — feature builder and fire rule (Task 17.1).

FROZEN 2026-09-11. Training cutoff is the venue-window start; nothing after that timestamp went
into this artifact, and nothing ever will. Any retrain is a NEW artifact with a new name.

Usage:
    import joblib
    from ef11_2_predict import feats_at, trailing12, SECS, EV_MARGIN, FEE, decide
    m = joblib.load('ef11_2_gbm_seed0.joblib')
    p_up = m.predict_proba(feats_at(path, S, trail12).reshape(1, -1))[0, 1]

`path` is the 300 one-second closes of the candle so far (index = seconds into the candle; only
indices <= S are read, so it is safe to pass a partially filled array).
"""
import numpy as np

SECS = [15, 20, 30, 45, 60, 90, 120]
EV_MARGIN = 0.15          # the margin the replay used; the edge is broad and shallow, so loose wins
FEE = 0.02                # Predict.fun taker fee used in training-time evaluation
FEATS = ['move_bps', 'abs_move', 'ret5', 'ret15', 'ret30', 'rvol', 'rng', 'pos_in_rng',
         'crossings', 'sec', 'trail12']
TRAINING_CUTOFF_MS = 1788887700000   # venue-window start; training data is strictly before this


def feats_at(path, S, trail12):
    """Feature vector at second S. Reads only path[:S+1]. Order must match FEATS."""
    op = path[0]
    px = path[S]
    w = path[:S + 1]
    hi, lo = w.max(), w.min()
    d = np.diff(w)
    sign = np.sign(w - op)
    nz = sign[sign != 0]
    cross = int((np.diff(nz) != 0).sum()) if len(nz) > 1 else 0
    bps = lambda a, b: (a - b) / op * 1e4
    return np.array([
        bps(px, op), abs(bps(px, op)),
        bps(px, w[max(0, S - 5)]), bps(px, w[max(0, S - 15)]), bps(px, w[max(0, S - 30)]),
        (d.std() / op * 1e4) if len(d) > 1 else 0.0,
        bps(hi, lo), ((px - lo) / (hi - lo)) if hi > lo else 0.5,
        cross, float(S), trail12], dtype=np.float32)


def trailing12(prev_paths, op):
    """Mean high-low range in bps over the previous 12 candles. prev_paths: (12, 300) newest last."""
    rng = (prev_paths.max(1) - prev_paths.min(1)) / op * 1e4
    return float(rng.mean())


def decide(model, path, S, trail12, ask_up, ask_dn, size_up, size_dn,
           margin=EV_MARGIN, fee=FEE, min_notional=10.0):
    """Return ('UP'|'DOWN', ask, ev) if the rule fires at this second, else None.

    Identical arithmetic to the replay: choose the side the model favours, price it at that side's
    raw ask, require notional >= $10, and fire only if p*(1/ask)*(1-fee) - 1 >= margin.
    """
    p_up = float(model.predict_proba(feats_at(path, S, trail12).reshape(1, -1))[0, 1])
    side = 'UP' if p_up >= 0.5 else 'DOWN'
    p = p_up if side == 'UP' else 1.0 - p_up
    ask = ask_up if side == 'UP' else ask_dn
    size = size_up if side == 'UP' else size_dn
    if ask is None or not (0.02 < ask < 0.98):
        return None
    if size is None or size * ask < min_notional:
        return None
    ev = p * (1.0 / ask) * (1.0 - fee) - 1.0
    return (side, ask, ev) if ev >= margin else None
