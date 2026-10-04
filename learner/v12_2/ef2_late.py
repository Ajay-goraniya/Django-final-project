"""13.3.0 DRAFT, OFF, NOT WIRED: EF-2 late lane = pre-registered shadow arm A (NC-19, Zurich ef3_shadow.py).

Rule, exactly as pre-registered (do not tune here - the forward shadow decides):
  at each decision pass with sec >= S0 (150), score both sides with the EF-2 london44 logistic (ef2/ef2_model_london.json,
  44 keys the London engine already stores), take the side with p_win >= 0.5, fire if p_win / (ask * (1 + 0.07 (1 - ask)))
  >= 1 + margin (0.02), one fire per candle.
Inputs per pass: the engine's feature dict (d['features']), both asks, the engine's p for its own side, and the second.
own_ask / d_ask_1s / d_ask_5s / d_ask_30s are built here from a per-side ask history (price units, like training).

It is a decision function only. It places nothing, arms nothing, and the engine does not import it. Wiring it into
decide_now is a separate change that needs the owner's confirmation of this exact arm (CLAUDE.md)."""
import collections, math, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'ef2'))
from ef2_scorer import Scorer, RATE   # noqa: E402

DEFAULT = dict(enabled=False, s0=150, margin=0.02, model='ef2_model_london.json')


def cost(ask):
    return ask * (1.0 + RATE * (1.0 - ask))


class AskHistory:
    """Own-side ask history per candle side: value now minus value ~k seconds ago (nearest sample at or before)."""
    def __init__(self, keep_s=35.0):
        self.keep = keep_s
        self.h = {'UP': collections.deque(), 'DOWN': collections.deque()}

    def push(self, now, up_ask, dn_ask):
        for side, a in (('UP', up_ask), ('DOWN', dn_ask)):
            if a is None or not math.isfinite(a): continue
            q = self.h[side]; q.append((now, float(a)))
            while q and now - q[0][0] > self.keep: q.popleft()

    def delta(self, side, now, k):
        q = self.h[side]
        if not q: return None
        cur = q[-1][1]; past = None
        for t, a in q:
            if t <= now - k: past = a
            else: break
        return None if past is None else cur - past

    def reset(self):
        for q in self.h.values(): q.clear()


class EF2Late:
    def __init__(self, cfg=None, scorer=None):
        self.cfg = dict(DEFAULT); self.cfg.update(cfg or {})
        self.scorer = scorer or Scorer(os.path.join(_HERE, 'ef2', self.cfg['model']))
        self.hist = AskHistory()
        self.fired = set()
        self.candle = None

    def row(self, feats, side, ask, p_side, sec, now):
        r = dict(feats)
        r.update(own_ask=ask, sec=float(sec), p_side=p_side,
                 d_ask_1s=self.hist.delta(side, now, 1.0), d_ask_5s=self.hist.delta(side, now, 5.0),
                 d_ask_30s=self.hist.delta(side, now, 30.0))
        return r

    def decide(self, ep, now, sec, feats, up_ask, dn_ask, side, p):
        """ep: candle epoch; side/p: the engine's own side and its p. Returns a fire dict or None. Never raises on bad input."""
        if ep != self.candle:
            self.candle = ep; self.hist.reset()
        self.hist.push(now, up_ask, dn_ask)
        if not self.cfg.get('enabled') or ep in self.fired or sec < self.cfg['s0']: return None
        if side not in ('UP', 'DOWN') or p is None or not math.isfinite(p): return None
        p_up = p if side == 'UP' else 1.0 - p
        best = None
        for s, a, ps in (('UP', up_ask, p_up), ('DOWN', dn_ask, 1.0 - p_up)):
            if a is None or not (0.0 < a < 1.0): continue
            pw, info = self.scorer.score(self.row(feats, s, a, ps, sec, now))
            if pw < 0.5: continue                                  # pinned to the model's side (Zurich's -$2,024 lesson)
            ev = pw / cost(a) - 1.0
            if ev >= self.cfg['margin'] and (best is None or ev > best['ev']):
                best = dict(fire=True, lane='EF2_LATE', side=s, ask=a, p_win=pw, ev=ev, sec=sec,
                            imputed=info['n_imputed'], imputed_mass=info['coef_mass_imputed'])
        if best: self.fired.add(ep)
        return best
