"""EF reversal lane for Polymarket (12.22.0) - a port of build11's legacy EF decision STRUCTURE.

Owner, 09-22: EF "is supposed to wait for the reversal to happen ... catch that reversal before anyone
else does and fire ... It's supposed to buy cheap shares." And: Polymarket settles on the Chainlink 60 s
TWAP at close vs at the open, not on the candle's open/close.

What is ported from build11 (learner/btc_model_build11.py; line refs there):
  - the side: contrarian to the move so far (16394-16396), here measured against the SETTLEMENT LINE
    (line_open = TWAP60 at the open) instead of the Binance candle open;
  - old-side exhaustion (16480-16620), control transfer and settlement feasibility (ef_runway_v2, 3981),
    settlement probability (ef_adaptive_settlement, 3825), the reversal classifier with its real/fake
    weights (3481-3533), the 12-gate final check at the ANCHOR thresholds (14026, EF_* constants 961-1380),
    the 250 ms confirm latch (17390, B35_STRUCTURE_LATCH), one fire per candle (18169).
What is NOT ported (yet): the perp lane (EFPerpPrep), the aged depth history (replenishment / event OFI),
  the online EFLearner and the frequency controller. Features that need them read as neutral here and the
  anchors stand in for the learned thresholds. Stated so the first shadow read is interpreted correctly.
What is ADDED for Polymarket: the price rule. build11 fires with no quote (18333: "no quote lookup may
  veto the signal") because Predict.fun pays the same for every share. Polymarket prices the side, so the
  lane fires only when its own settlement probability beats the ask by EF_EV_MARGIN plus the fee, and
  never above EF_MAX_ASK - that is "buy cheap shares" written down.

Pure functions take feature dicts; EFReversal holds the per-candle state. No I/O.
"""
import math
from collections import deque

# build11 anchors (EF_* block, 961-1380); the learner moved these inside the bounds noted in the map.
EF_MIN_REACHABILITY = 0.38
EF_MIN_CONTROL_TRANSFER = 0.42
EF_MIN_SETTLEMENT_FEASIBILITY = 0.60
EF_MIN_QUALITY = 0.35
EF_MAX_CHOP = 0.54
EF_MIN_EARLY_PREP = 0.40
EF_MIN_EXTENSION_SIGMA = 0.60        # soft gate (EF_DECISION_SOFT_GATES=("EXTENSION",)): fire at once above it, else latch
EF_MIN_OLD_SIDE_EXHAUSTION = 0.38
EF_MIN_FLOW_PERSISTENCE = 0.42
EF_MAX_FAKE_REVERSAL_PENALTY = 0.55
EF_MIN_REAL_REVERSAL_SCORE = 0.56
EF_CONFIRM_WINDOW_MS = 250
EF_LATCH_MAX_MS = 750
EF_SETTLEMENT_EVIDENCE_Z = 0.50
EF_FLOW_NORM = 0.65
EF_BOOK_NORM = 0.47
# Polymarket price rule (added)
EF_EV_MARGIN = 0.06                  # build11 EF_EV_MARGIN, used there only as a pclose floor
EF_MAX_ASK = 0.60                    # the side we buy is the side the book has written off; above this it is not cheap
EF_MIN_PHASE_S = 20.0                # no line, no sigma before this
EF_LAST_PHASE_S = 280.0
TWAP_HORIZON_SHIFT_S = 30.0          # the closing TWAP60 is centred 30 s before the close


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x

def ncdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def sign(x):
    return 1.0 if x > 0 else -1.0 if x < 0 else 0.0


def sigma_per_root_second(prices, now_s, window_s=120, min_samples=12):
    """build11 _ef_sigma_per_root_second (16014-16064): RMS of completed 1 s log returns over the last
    120 s, in $ per root-second. prices: (ts_s, price) oldest first. 0.0 when under min_samples."""
    last = {}; lo = now_s - window_s - 1
    for t, p in reversed(prices):                     # newest first; stop once outside the window
        if t > now_s: continue
        if t < lo: break
        last.setdefault(int(t), p)                    # first seen = latest price in that second
    secs = sorted(last)
    if len(secs) < min_samples + 1: return 0.0
    r = [math.log(last[b] / last[a]) / math.sqrt(b - a) for a, b in zip(secs, secs[1:]) if last[a] > 0 and b > a]
    if len(r) < min_samples: return 0.0
    return math.sqrt(sum(x * x for x in r) / len(r)) * last[secs[-1]]


def flow_profile(ticks, now_ms, side_sign, window_ms=5000, bucket_ms=500):
    """build11 ef_flow_transition_profile (2152-2224): 500 ms buckets of signed quote over the last 5 s,
    read in the EF side's direction. Returns persistence, transition, support_fraction, chop, n."""
    start = now_ms - window_ms; nb = window_ms // bucket_ms
    buckets = [0.0] * nb; counts = [0] * nb
    for ts, q in ticks:
        if ts < start or ts >= now_ms: continue
        i = int((ts - start) // bucket_ms)
        if 0 <= i < nb: buckets[i] += q * side_sign; counts[i] += 1
    live = [b for b, c in zip(buckets, counts) if c]
    if len(live) < 2: return dict(persistence=0.0, transition=0.0, support=0.0, chop=0.0, n=len(live))
    pos = sum(1 for b in live if b > 0) / len(live)
    consec = 0
    for b in reversed(live):
        if b > 0: consec += 1
        else: break
    total = sum(abs(b) for b in live) or 1e-9
    strength = clamp(sum(live) / total)                      # net support in [-1,1] -> [0,1]
    persistence = 0.50 * strength + 0.30 * pos + 0.20 * min(1.0, consec / 4.0)
    half = max(1, len(live) // 2)
    early, late = sum(live[:half]), sum(live[half:])
    transition = clamp(0.5 + 0.5 * (sign(late) - sign(early)) / 2.0 * (1.0 if late > 0 else -1.0)) if (early or late) else 0.0
    flips = sum(1 for x, y in zip(live, live[1:]) if sign(x) * sign(y) < 0)
    chop = flips / (len(live) - 1)
    return dict(persistence=clamp(persistence), transition=clamp(transition), support=pos, chop=clamp(chop), n=len(live))


def path_stats(prices, now_s, window_s):
    """|move| / path over the window (build11 path efficiency). prices: iterable of (ts_s, price), oldest first."""
    seg = []; lo = now_s - window_s
    for t, p in reversed(prices):
        if t > now_s: continue
        if t < lo: break
        seg.append(p)
    seg.reverse()
    if len(seg) < 3: return dict(move=0.0, path=0.0, efficiency=0.0)
    move = seg[-1] - seg[0]; path = sum(abs(b - a) for a, b in zip(seg, seg[1:])) or 1e-9
    return dict(move=move, path=path, efficiency=clamp(abs(move) / path))


def ef_metrics(f, ticks, prices, now_ms, line_open, sigma_rs, flow_rms=None):
    """The EF ladder (build11 _compute_ef_metrics 16480-16628) on the features the Polymarket lane has.
    f: LaneEngine.compute() dict; ticks: deque of (ts_ms, signed_quote); prices: deque of (ts_s, price);
    flow_rms: rolling RMS of the 5 s signed flow (the lane's own scale for "strong" flow - adaptive, like
    build11's memory-shifted normalisers); when None a sigma-scaled constant stands in."""
    price = float(f['price']); phase = float(f['phase_second']); left = max(1.0, 300.0 - phase)
    body = price - line_open
    if body == 0.0 or sigma_rs <= 0.0: return None
    ef_dir = 'DOWN' if body > 0 else 'UP'      # contrarian to the move vs the settlement line
    s = -1.0 if ef_dir == 'DOWN' else 1.0       # EF side sign (+1 up)
    now_s = now_ms / 1000.0
    scale_flow = (2.0 * flow_rms) if flow_rms else (EF_FLOW_NORM * 1000.0 * max(1.0, sigma_rs))   # a 2-RMS 5 s flow reads 1.0
    # flows, aligned to the EF side
    d1, d5, d30 = float(f.get('delta_1s', 0)), float(f.get('delta_5s', 0)), float(f.get('delta_30s', 0))
    opposite_flow = clamp((s * d5) / scale_flow)              # new-side (EF side) aggression over 5 s
    old_flow = clamp((-s * d5) / scale_flow)
    fast_support = clamp((s * d1) / (scale_flow / math.sqrt(5.0)))
    prof = flow_profile(ticks, now_ms, s)
    # price response over 5 s, in sigma units of the window
    r5 = float(f.get('return_5s_bps', 0)) / 1e4 * price
    unit5 = max(1e-9, sigma_rs * math.sqrt(5.0))
    new_response = clamp((s * r5) / (2.0 * unit5)); old_response = clamp((-s * r5) / (2.0 * unit5))
    new_eff = math.sqrt(opposite_flow * new_response); old_eff = math.sqrt(old_flow * old_response)
    # rejection at the old side's extreme: wick + the lane's rejection accumulators
    hi, lo = float(f.get('candle_high_seen', price)), float(f.get('candle_low_seen', price))
    rng = max(hi - lo, 1e-9)
    if ef_dir == 'DOWN':                                     # old side went UP: extreme is the high
        wick = (hi - price) / rng; rej_acc = clamp(float(f.get('reject_up', 0)) / 6.0)
        recovery = clamp((hi - price) / max(hi - line_open, 1e-9)) if hi > line_open else 0.0
    else:
        wick = (price - lo) / rng; rej_acc = clamp(float(f.get('reject_down', 0)) / 6.0)
        recovery = clamp((price - lo) / max(line_open - lo, 1e-9)) if lo < line_open else 0.0
    rejection = clamp(0.5 * wick + 0.5 * rej_acc)
    imb = float(f.get('spot_imbalance5', 0))
    book_support = clamp(0.5 + 0.5 * s * imb / EF_BOOK_NORM); opposite_book = book_support
    # the old side's aggression over 30 s that no longer moves price (build11 old_side_failure reads the long window)
    p30 = path_stats(prices, now_s, 30.0)
    old_flow_30 = clamp((-s * d30) / (scale_flow * math.sqrt(6.0)))
    old_response_30 = clamp((-s * p30['move']) / (2.0 * max(1e-9, sigma_rs * math.sqrt(30.0))))
    old_side_failure = clamp(max(old_flow, old_flow_30) * (1.0 - max(old_response, old_response_30)))
    old_side_exhaustion = clamp(0.46 * old_side_failure + 0.24 * rejection + 0.16 * recovery + 0.14 * book_support)
    p5 = path_stats(prices, now_s, 5.0); path_quality = p5['efficiency'] if s * p5['move'] > 0 else 0.0
    chop = clamp(0.5 * prof['chop'] + 0.5 * (1.0 - p5['efficiency']))
    # geometry against the settlement line (TWAP60): the closing window is centred 30 s before the close
    horizon = max(1.0, left - TWAP_HORIZON_SHIFT_S)
    distance = abs(body) / max(1e-9, sigma_rs * math.sqrt(horizon))
    extension_sigma = abs(body) / max(1e-9, sigma_rs * math.sqrt(max(1.0, phase)))
    control_transfer = clamp(0.18 * opposite_flow + 0.16 * opposite_book + 0.14 * prof['persistence'] + 0.10 * prof['transition']
                             + 0.12 * rejection + 0.08 * path_quality + 0.10 * clamp(new_eff - old_eff + 0.5)
                             + 0.07 * old_side_exhaustion + 0.05 * book_support)
    reachability = clamp(1.0 - distance / 2.5)                # FEASIBILITY_SIGMAS
    stay = clamp(recovery)
    p_base = ncdf(-distance)                                  # P(the line is crossed back by the horizon)
    p_settle = clamp(ncdf(-distance + EF_SETTLEMENT_EVIDENCE_Z * (2.0 * control_transfer - 1.0)), 0.01, 0.99)
    uncertainty = clamp(1.0 - phase / 75.0) * (1.0 - control_transfer)
    settlement_feasibility = clamp(0.46 * reachability + 0.36 * control_transfer + 0.18 * stay - 0.28 * chop - 0.22 * uncertainty)
    quality = clamp(0.53 * control_transfer + 0.47 * p_settle - 0.12 * uncertainty)
    impulse_only = clamp(new_response - opposite_flow)
    book_disagreement = clamp(-s * imb / EF_BOOK_NORM)
    reclaim = clamp(old_eff - new_eff)
    fake = clamp(0.26 * impulse_only + 0.18 * book_disagreement + 0.16 * reclaim + 0.14 * chop
                 + 0.08 * (1.0 - rejection) * (1.0 - prof['persistence']))
    real = clamp(0.24 * control_transfer + 0.18 * old_side_exhaustion + 0.16 * prof['persistence'] + 0.14 * settlement_feasibility
                 + 0.10 * new_eff + 0.08 * rejection + 0.06 * path_quality + 0.04 * prof['transition'] - 0.24 * fake)
    accel = clamp(s * (d1 - 0.6 * d5 / 5.0) / (scale_flow / 5.0))
    early_prep = clamp(0.27 * reachability + 0.27 * control_transfer + 0.22 * settlement_feasibility + 0.12 * quality
                       + 0.07 * accel + 0.05 * fast_support)
    return dict(ef_dir=ef_dir, body=body, phase=phase, seconds_left=left, distance=distance, extension_sigma=extension_sigma,
                opposite_flow=opposite_flow, old_flow=old_flow, fast_support=fast_support, persistence=prof['persistence'],
                transition=prof['transition'], chop=chop, rejection=rejection, recovery=recovery, path_quality=path_quality,
                new_eff=new_eff, old_eff=old_eff, old_side_exhaustion=old_side_exhaustion, control_transfer=control_transfer,
                reachability=reachability, settlement_feasibility=settlement_feasibility, settlement_probability=p_settle,
                p_base=p_base, quality=quality, fake=fake, real=real, early_prep=early_prep, book_support=book_support)


def gates(m):
    """build11 ef_final_gate_checks (14026-14053) at the anchors. EXTENSION is soft."""
    return [('REACH', m['reachability'] >= EF_MIN_REACHABILITY), ('CONTROL', m['control_transfer'] >= EF_MIN_CONTROL_TRANSFER),
            ('SETTLEMENT', m['settlement_feasibility'] >= EF_MIN_SETTLEMENT_FEASIBILITY), ('QUALITY', m['quality'] >= EF_MIN_QUALITY),
            ('CHOP', m['chop'] <= EF_MAX_CHOP), ('EARLY_SCORE', m['early_prep'] >= EF_MIN_EARLY_PREP),
            ('OLD_SIDE_EXHAUSTION', m['old_side_exhaustion'] >= EF_MIN_OLD_SIDE_EXHAUSTION),
            ('FLOW_PERSISTENCE', m['persistence'] >= EF_MIN_FLOW_PERSISTENCE), ('FAKE_REVERSAL', m['fake'] <= EF_MAX_FAKE_REVERSAL_PENALTY),
            ('REAL_REVERSAL_SCORE', m['real'] >= EF_MIN_REAL_REVERSAL_SCORE)]


class EFReversal:
    """Per-candle EF state: the latch, one fire per candle, the last metrics for the monitor."""
    def __init__(self):
        self.reset()
    def reset(self):
        self.fired = None; self.latch_dir = None; self.latch_ms = 0; self.last = None; self.block = ''; self.attempts = 0
    def watch(self, m, now_ms, ask, fee_rate):
        """Returns a decision dict or None. `ask` is the venue ask of the EF side (None = unknown)."""
        self.last = m
        if self.fired is not None: self.block = 'fired'; return None
        if m is None: self.block = 'no line / sigma'; return None
        if not (EF_MIN_PHASE_S <= m['phase'] <= EF_LAST_PHASE_S): self.block = 'outside window'; return None
        failed = [n for n, ok in gates(m) if not ok]
        if failed:
            self.latch_dir = None; self.block = 'gate ' + failed[0]; return None
        # price rule (Polymarket): the side must be cheap and the settlement probability must pay for it
        if ask is None: self.block = 'no venue quote'; return None
        if ask > EF_MAX_ASK: self.block = f'ask {ask:.2f} above {EF_MAX_ASK:.2f}'; return None
        floor = clamp(ask + EF_EV_MARGIN + ask * fee_rate, 0.12, 0.98)
        if m['settlement_probability'] < floor: self.block = f'p {m["settlement_probability"]:.2f} < floor {floor:.2f}'; return None
        # B35 latch: fire at once when the structure is developed, else confirm over 250 ms
        if m['extension_sigma'] >= EF_MIN_EXTENSION_SIGMA: how = 'STRUCTURE_DEVELOPED'
        else:
            if self.latch_dir != m['ef_dir']: self.latch_dir = m['ef_dir']; self.latch_ms = now_ms; self.block = 'latched'; return None
            held = now_ms - self.latch_ms
            if held < EF_CONFIRM_WINDOW_MS: self.block = f'latch {held} ms'; return None
            if held > EF_LATCH_MAX_MS: self.latch_dir = None; self.block = 'latch expired'; return None
            how = 'STRUCTURE_CONFIRMED'
        self.block = ''
        return dict(kind='EF', side=m['ef_dir'], p=round(m['settlement_probability'], 4), probability_up=(m['settlement_probability'] if m['ef_dir'] == 'UP' else 1.0 - m['settlement_probability']),
                    sec=int(m['phase']), engine='build11', how=how, price_rule='lane_cap', max_ask=EF_MAX_ASK, threshold=0.0,
                    ef=dict(real=round(m['real'], 3), fake=round(m['fake'], 3), control=round(m['control_transfer'], 3), exhaustion=round(m['old_side_exhaustion'], 3),
                            settle=round(m['settlement_feasibility'], 3), ext=round(m['extension_sigma'], 2), body=round(m['body'], 2), ask=ask),
                    reason=f"EF:{how} {m['ef_dir']} body {m['body']:+.1f} vs line, real {m['real']:.2f} fake {m['fake']:.2f} p {m['settlement_probability']:.2f} ask {ask:.2f}")
