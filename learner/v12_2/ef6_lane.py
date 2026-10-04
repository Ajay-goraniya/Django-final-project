"""13.4.0 DRAFT, OFF, NOT WIRED: EF-6 lane = pre-registered forward-shadow arm E3 (NC-19, Zurich ef6.py / ef3_shadow.py).

Rule, as registered (do not tune here - the forward shadow decides):
  * model: squared-loss stump booster predicting AFTER-FILL $ per $1 of a candidate (0 if the FAK would not fill), trained NIGHTLY
    on the last <= 21 days, without the six absolute-price columns (NC-19: they let a linear fit learn the date). The model file is
    produced by ef6_train.py at 00:05 UTC and loaded read-only for the whole day; a day's model is never edited once the day starts.
  * candidates: at every decision pass, both sides are scored; own_ask, d_ask_1s/5s/30s, dip30, sec and p_side are built here.
  * threshold: the q-quantile (0.90) of this model's predictions over ALL candidate rows of the trailing W = 1 h, recomputed on a
    60 s grid, past rows only; fewer than 500 rows in the window -> no threshold -> no fire.
  * fire: first pass where the model's side (p_side >= 0.5) has pred >= threshold; one fire per candle.
It is a decision function only: it places nothing and the engine does not import it. Wiring it into decide_now needs the owner's
confirmation of this exact arm (CLAUDE.md), and the forward shadow must pass first."""
import bisect, collections, json, math, os

_HERE = os.path.dirname(os.path.abspath(__file__))
ASK_LO, ASK_HI = 0.01, 0.99
DEFAULT = dict(enabled=False, q=0.90, window_s=3600.0, grid_s=60.0, min_rows=500, anchor_s=0.0, model_dir=os.path.join(_HERE, 'ef6'))


class StumpModel:
    """{'names': [...], 'base': float, 'trees': [[j, thr, vl, vr], ...]}; missing/non-finite input -> the right branch is
    ambiguous, so the row is not scored at all (never guessed)."""
    def __init__(self, m):
        self.names = list(m['names']); self.base = float(m['base'])
        self.trees = [(int(j), float(t), float(a), float(b)) for j, t, a, b in m['trees']]
        self.used = sorted({j for j, *_ in self.trees})

    @classmethod
    def load(cls, path):
        with open(path) as f: return cls(json.load(f))

    def predict(self, row):
        x = {}
        for j in self.used:
            v = row.get(self.names[j])
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)): return None
            x[j] = float(v)
        f = self.base
        for j, thr, vl, vr in self.trees: f += vl if x[j] <= thr else vr
        return f


class TrailingQuantile:
    """Causal rolling quantile over (t, value) pairs, refreshed on a fixed grid."""
    def __init__(self, q, window_s, grid_s, min_rows, anchor_s=0.0):
        self.q, self.w, self.g, self.min, self.a = q, window_s, grid_s, min_rows, anchor_s
        self.rows = collections.deque(); self.thr = None; self.next_at = None

    def add(self, t, v):
        self.rows.append((t, v))

    def threshold(self, now):
        """Threshold usable at `now`, computed from rows strictly before the current grid step."""
        step = math.floor((now - self.a) / self.g) * self.g + self.a     # anchor offset: the robustness check runs 0/15/30/45 s
        if self.next_at is None or step >= self.next_at:
            while self.rows and self.rows[0][0] < step - self.w: self.rows.popleft()
            vals = sorted(v for t, v in self.rows if t < step)
            if len(vals) >= self.min:
                k = self.q * (len(vals) - 1); lo = int(math.floor(k)); hi = min(lo + 1, len(vals) - 1)
                qv = vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
                # STRICT (NC-19, Zurich 548f04d): a stump ensemble emits few distinct values, so a plain quantile IS one of them and
                # 'pred >= q' is decided by ties. Use the smallest distinct value strictly above q; none above -> no fire this step.
                i = bisect.bisect_right(vals, qv)
                self.thr = vals[i] if i < len(vals) else None
            else:
                self.thr = None
            self.next_at = step + self.g
        return self.thr


class AskState:
    """Per-candle own-side ask history: deltas over 1/5/30 s and dip30 = ask minus its own 30 s minimum."""
    def __init__(self):
        self.h = {'UP': collections.deque(), 'DOWN': collections.deque()}

    def push(self, now, up, dn):
        for s, a in (('UP', up), ('DOWN', dn)):
            if a is None or not math.isfinite(a): continue
            q = self.h[s]; q.append((now, float(a)))
            while q and now - q[0][0] > 31.0: q.popleft()

    def feats(self, side, now):
        q = self.h[side]
        if not q: return {}
        cur = q[-1][1]; out = {}
        for k in (1, 5, 30):
            past = None
            for t, a in q:
                if t <= now - k: past = a
                else: break
            out[f'd_ask_{k}s'] = None if past is None else cur - past
        out['dip30'] = cur - min(a for _, a in q)
        return out

    def reset(self):
        for q in self.h.values(): q.clear()


class EF6Lane:
    def __init__(self, cfg=None, model=None):
        self.cfg = dict(DEFAULT); self.cfg.update(cfg or {})
        self.model = model
        self.tq = TrailingQuantile(self.cfg['q'], self.cfg['window_s'], self.cfg['grid_s'], self.cfg['min_rows'], self.cfg['anchor_s'])
        self.asks = AskState(); self.candle = None; self.fired = set()

    def load_day_model(self, day):
        """Loads the day's model and, if present, its SEED: the previous day's final hour of candidate predictions re-scored under
        THIS model (ef5_nightly.py, Zurich 16:40). Without it the first hour of a day would mix two models' scales in the window."""
        p = os.path.join(self.cfg['model_dir'], f'ef6_{day}.json')
        self.model = StumpModel.load(p) if os.path.exists(p) else None     # no model for the day -> the lane never fires
        self.tq = TrailingQuantile(self.cfg['q'], self.cfg['window_s'], self.cfg['grid_s'], self.cfg['min_rows'], self.cfg['anchor_s'])
        sp = os.path.join(self.cfg['model_dir'], f'ef6_{day}_seed.json')
        if self.model is not None and os.path.exists(sp):
            with open(sp) as f:
                for t, v in json.load(f): self.tq.add(float(t), float(v))
        return self.model is not None

    def decide(self, ep, now, sec, feats, up_ask, dn_ask, side, p):
        """Scores both sides every pass (they all feed the trailing window); returns a fire dict or None. Never raises."""
        if ep != self.candle: self.candle = ep; self.asks.reset()
        self.asks.push(now, up_ask, dn_ask)
        if self.model is None or side not in ('UP', 'DOWN') or p is None or not math.isfinite(p): return None
        p_up = p if side == 'UP' else 1.0 - p
        thr = self.tq.threshold(now)
        best = None
        for s, a, o, ps in (('UP', up_ask, dn_ask, p_up), ('DOWN', dn_ask, up_ask, 1.0 - p_up)):
            if a is None or not (ASK_LO < a < ASK_HI): continue            # same bounds as ef6.py / the shadow (Zurich parity 17:0x)
            row = dict(feats); row.update(self.asks.feats(s, now))
            row.update(own_ask=a, opp_ask=o, _ask_up=up_ask, _ask_dn=dn_ask, sec=float(sec), p_side=ps)
            pred = self.model.predict(row)
            if pred is None: continue
            self.tq.add(now, pred)
            if ps < 0.5 or thr is None or pred < thr: continue            # pinned to the model's side
            if best is None or pred > best['pred']:
                best = dict(fire=True, lane='EF6', side=s, ask=a, pred=pred, thr=thr, sec=sec)
        if not self.cfg.get('enabled') or best is None or ep in self.fired: return None
        self.fired.add(ep)
        return best
