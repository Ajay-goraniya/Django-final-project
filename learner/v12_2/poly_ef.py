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


def ef_metrics(f, ticks, prices, now_ms, line_open, sigma_rs, flow_rms=None, micro=None):
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
    # 12.23.0: PERP microstructure when the perp lane is ready (build11 16414-16478 swaps flows, paths and the
    # book wholesale); spot stands in otherwise. Candle / line geometry stays spot.
    perp = micro if (micro and micro.get('ready')) else None
    fticks, fprices = (perp['ticks'], perp['prices']) if perp else (ticks, prices)
    if perp and perp.get('flow_rms'): flow_rms = perp['flow_rms']
    scale_flow = (2.0 * flow_rms) if flow_rms else (EF_FLOW_NORM * 1000.0 * max(1.0, sigma_rs))   # a 2-RMS 5 s flow reads 1.0
    # flows, aligned to the EF side
    if perp: d1, d5, d30 = window_delta(fticks, now_ms, 1000), window_delta(fticks, now_ms, 5000), window_delta(fticks, now_ms, 30000)
    else: d1, d5, d30 = float(f.get('delta_1s', 0)), float(f.get('delta_5s', 0)), float(f.get('delta_30s', 0))
    book = (micro or {}).get('book'); memory = (micro or {}).get('memory') or {}
    mem_ready = bool(memory.get('ready'))
    mem_ctl = 2.0 * (memory.get('control_handoff', 0.5) - 0.5) * EF_MEMORY_CONTROL_MAX_SHIFT if mem_ready else 0.0
    mem_book = 2.0 * (memory.get('book_handoff', 0.5) - 0.5) * EF_MEMORY_CONTROL_MAX_SHIFT if mem_ready else 0.0
    opposite_flow = clamp((s * d5) / scale_flow)              # new-side (EF side) aggression over 5 s
    old_flow = clamp((-s * d5) / scale_flow)
    fast_support = clamp((s * d1) / (scale_flow / math.sqrt(5.0)))
    prof = flow_profile(fticks, now_ms, s)
    prof['persistence'] = clamp(prof['persistence'] + mem_ctl); prof['transition'] = clamp(prof['transition'] + mem_ctl)
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
    if book:
        # build11 book_signed (PERP branch): near book dominant, deeper zones incremental, replenishment must persist
        deep_book = 0.55 * book['book_1_5'] + 0.25 * book['book_6_10'] + 0.20 * book['book_11_20']
        deep_repl = 0.60 * book['repl_1_5'] + 0.25 * book['repl_6_10'] + 0.15 * book['repl_11_20']
        book_signed = clamp(0.48 * book['book_1_5'] + 0.24 * deep_book + 0.12 * deep_repl + 0.10 * book['event_ofi'] + 0.06 * book['microprice'], -1.0, 1.0)
        old_side_book_replenishment = clamp(-s * book['repl_1_5'])
    else:
        book_signed = clamp(float(f.get('spot_imbalance5', 0)), -1.0, 1.0); old_side_book_replenishment = 0.0
    imb = book_signed
    book_support = clamp(0.5 + 0.5 * s * imb / EF_BOOK_NORM + mem_book); opposite_book = book_support
    # the old side's aggression over 30 s that no longer moves price (build11 old_side_failure reads the long window)
    p30 = path_stats(fprices, now_s, 30.0)
    old_flow_30 = clamp((-s * d30) / (scale_flow * math.sqrt(6.0)))
    old_response_30 = clamp((-s * p30['move']) / (2.0 * max(1e-9, sigma_rs * math.sqrt(30.0))))
    old_side_failure = clamp(max(old_flow, old_flow_30) * (1.0 - max(old_response, old_response_30)))
    old_side_exhaustion = clamp(0.46 * old_side_failure + 0.24 * rejection + 0.16 * recovery + 0.14 * book_support
                                + (2.0 * (memory.get('exhaustion_score', 0.5) - 0.5) * EF_MEMORY_EXHAUSTION_MAX_SHIFT if mem_ready else 0.0))
    p5 = path_stats(fprices, now_s, 5.0); path_quality = p5['efficiency'] if s * p5['move'] > 0 else 0.0
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
    fake = clamp(0.26 * impulse_only + 0.18 * book_disagreement + 0.18 * old_side_book_replenishment + 0.16 * reclaim + 0.14 * chop
                 + 0.08 * (1.0 - rejection) * (1.0 - prof['persistence']))
    real = clamp(0.24 * control_transfer + 0.18 * old_side_exhaustion + 0.16 * prof['persistence'] + 0.14 * settlement_feasibility
                 + 0.10 * new_eff + 0.08 * rejection + 0.06 * path_quality + 0.04 * prof['transition'] - 0.24 * fake)
    if mem_ready:   # build11 16596-16613: the memory re-classification
        fake = clamp(fake - 2.0 * (memory['control_handoff'] - 0.5) * EF_MEMORY_FAKE_MAX_SHIFT - (memory['book_handoff'] - 0.5) * EF_MEMORY_FAKE_MAX_SHIFT)
        real = clamp(real + 2.0 * (memory['control_handoff'] - 0.5) * EF_MEMORY_REAL_MAX_SHIFT + (memory['effectiveness_decay'] - 0.5) * EF_MEMORY_REAL_MAX_SHIFT)
    accel = clamp(s * (d1 - 0.6 * d5 / 5.0) / (scale_flow / 5.0))
    early_prep = clamp(0.27 * reachability + 0.27 * control_transfer + 0.22 * settlement_feasibility + 0.12 * quality
                       + 0.07 * accel + 0.05 * fast_support)
    return dict(ef_dir=ef_dir, body=body, phase=phase, seconds_left=left, distance=distance, extension_sigma=extension_sigma,
                opposite_flow=opposite_flow, old_flow=old_flow, fast_support=fast_support, persistence=prof['persistence'],
                transition=prof['transition'], chop=chop, rejection=rejection, recovery=recovery, path_quality=path_quality,
                new_eff=new_eff, old_eff=old_eff, old_side_exhaustion=old_side_exhaustion, control_transfer=control_transfer,
                reachability=reachability, settlement_feasibility=settlement_feasibility, settlement_probability=p_settle,
                p_base=p_base, quality=quality, fake=fake, real=real, early_prep=early_prep, book_support=book_support,
                micro_source=('PERP' if perp else 'SPOT'), book_age_ms=(book['age_ms'] if book else None), memory_ready=mem_ready,
                old_side_book_replenishment=old_side_book_replenishment)


# ---- 12.23.0: the perp lane and the depth history (build11 EFPerpPrep 2352-3238, ef_depth_* 4278-4360) ----
EF_MEMORY_SECONDS = 120; EF_MEMORY_MIN_VALID_SECONDS = 14; EF_MEMORY_PRIOR_MIN_SECONDS = 4; EF_MEMORY_RECENT_MIN_SECONDS = 3
EF_MEMORY_FUTILITY_SCALE = 0.22; EF_MEMORY_DECAY_FLOOR = 0.25
EF_MEMORY_EXHAUSTION_MAX_SHIFT = 0.06; EF_MEMORY_CONTROL_MAX_SHIFT = 0.05; EF_MEMORY_FAKE_MAX_SHIFT = 0.05; EF_MEMORY_REAL_MAX_SHIFT = 0.05
EF_DEPTH_RETENTION_MS = 9_000; EF_REPL_MIN_AGE_MS = 800; EF_REPL_MAX_AGE_MS = 1_800; EF_OFI_MIN_AGE_MS = 120; EF_OFI_MAX_AGE_MS = 800
EF_MIN_TRADE_EVENTS = 3; EF_MAX_TRADE_AGE_MS = 1_500; EF_DEPTH_STALE_MS = 1_000; EF_MIN_DEPTH_LEVELS = 10

def side_change(old_rows, new_rows, is_bid):
    """build11 ef_depth_change.side_change: matched-level size change plus meaningful best shifts, in [-1,1]."""
    old = {round(float(p), 8): max(0.0, float(q)) for p, q in old_rows[:5]}
    new = {round(float(p), 8): max(0.0, float(q)) for p, q in new_rows[:5]}
    if not old or not new: return 0.0
    common = set(old) & set(new); raw = sum(new[p] - old[p] for p in common)
    ob, nb = (max(old), max(new)) if is_bid else (min(old), min(new))
    if is_bid:
        raw += sum(q for p, q in new.items() if p not in old and p > ob); raw -= sum(q for p, q in old.items() if p not in new and p > nb)
    else:
        raw += sum(q for p, q in new.items() if p not in old and p < ob); raw -= sum(q for p, q in old.items() if p not in new and p < nb)
    scale = 0.5 * (sum(old.values()) + sum(new.values()))
    return clamp(raw / max(scale, 1e-9), -1.0, 1.0)

def depth_change(prev, cur):
    if not prev: return dict(bid_change=0.0, ask_change=0.0, replenishment=0.0)
    b = side_change(prev['bids'], cur['bids'], True); a = side_change(prev['asks'], cur['asks'], False)
    return dict(bid_change=b, ask_change=a, replenishment=clamp(0.5 * (b - a), -1.0, 1.0))

def zone_imbalance(bids, asks, lo, hi):
    """(bid - ask) / (bid + ask) over levels lo..hi-1, in [-1,1]; 0 when the zone is empty."""
    bq = sum(float(q) for _, q in bids[lo:hi]); aq = sum(float(q) for _, q in asks[lo:hi])
    return (bq - aq) / (bq + aq) if (bq + aq) > 0 else 0.0

def zone_change(prev, cur, lo, hi):
    if not prev: return 0.0
    b = side_change(prev['bids'][lo:hi], cur['bids'][lo:hi], True); a = side_change(prev['asks'][lo:hi], cur['asks'][lo:hi], False)
    return clamp(0.5 * (b - a), -1.0, 1.0)


class DepthHistory:
    """Aged top-20 snapshots (9 s), the zone imbalances and the replenishment / event-OFI reads."""
    def __init__(self): self.rows = deque(); self.last = None
    def push(self, bids, asks, ts_ms):
        cur = dict(ts=int(ts_ms), bids=[(float(p), float(q)) for p, q in bids[:20]], asks=[(float(p), float(q)) for p, q in asks[:20]])
        self.rows.append(cur); self.last = cur
        cut = int(ts_ms) - EF_DEPTH_RETENTION_MS
        while self.rows and self.rows[0]['ts'] < cut: self.rows.popleft()
    def at_age(self, now_ms, lo, hi):
        for r in reversed(self.rows):
            age = now_ms - r['ts']
            if lo <= age <= hi: return r
        return None
    def read(self, now_ms):
        """Book features for the EF ladder (signed, + = bid side)."""
        cur = self.last
        if cur is None or now_ms - cur['ts'] > EF_DEPTH_STALE_MS or len(cur['bids']) < EF_MIN_DEPTH_LEVELS or len(cur['asks']) < EF_MIN_DEPTH_LEVELS: return None
        b15 = zone_imbalance(cur['bids'], cur['asks'], 0, 5); b610 = zone_imbalance(cur['bids'], cur['asks'], 5, 10); b1120 = zone_imbalance(cur['bids'], cur['asks'], 10, 20)
        old = self.at_age(now_ms, EF_REPL_MIN_AGE_MS, EF_REPL_MAX_AGE_MS); ofi_prev = self.at_age(now_ms, EF_OFI_MIN_AGE_MS, EF_OFI_MAX_AGE_MS)
        repl15 = zone_change(old, cur, 0, 5); repl610 = zone_change(old, cur, 5, 10); repl1120 = zone_change(old, cur, 10, 20)
        event_ofi = depth_change(ofi_prev, cur)['replenishment']
        bp, bq = cur['bids'][0]; ap, aq = cur['asks'][0]
        micro = ((bp * aq + ap * bq) / (bq + aq) - 0.5 * (bp + ap)) / max(1e-9, 0.5 * (ap - bp)) if (bq + aq) > 0 and ap > bp else 0.0
        return dict(book_1_5=b15, book_6_10=b610, book_11_20=b1120, repl_1_5=repl15, repl_6_10=repl610, repl_11_20=repl1120,
                    event_ofi=event_ofi, microprice=clamp(micro, -1.0, 1.0), age_ms=now_ms - cur['ts'])


class PerpMemory:
    """build11 EFPerpPrep's 120 s one-second history and _memory_for_direction (2604-2730)."""
    def __init__(self):
        self.history = deque(maxlen=EF_MEMORY_SECONDS + 5); self._sec = None; self._row = None
    def _new(self, sec): return dict(sec=sec, buy=0.0, sell=0.0, first=None, last=None, path=0.0, prev=None, n=0, nbook=0, b15=0.0, b610=0.0, b1120=0.0, r15=0.0, r610=0.0, r1120=0.0)
    def _ensure(self, ts_ms):
        sec = int(ts_ms) // 1000
        if self._sec is None: self._sec = sec; self._row = self._new(sec); return
        if sec <= self._sec: return
        self._finalize(); self._sec = sec; self._row = self._new(sec)
    def _finalize(self):
        r = self._row
        if not r: return
        tot = r['buy'] + r['sell']; delta = (r['buy'] - r['sell']) / tot if tot > 0 else 0.0
        move = (r['last'] - r['first']) if (r['first'] is not None and r['last'] is not None) else 0.0
        eff = clamp(move / r['path'], -1.0, 1.0) if r['path'] > 1e-12 else 0.0
        nb = r['nbook'] or 1
        self.history.append(dict(end_ms=(r['sec'] + 1) * 1000, n=r['n'], delta=clamp(delta, -1.0, 1.0), price_eff=eff, nbook=r['nbook'],
                                 book_1_5=r['b15'] / nb, book_6_10=r['b610'] / nb, book_11_20=r['b1120'] / nb, repl_1_5=r['r15'] / nb, repl_6_10=r['r610'] / nb, repl_11_20=r['r1120'] / nb))
    def on_trade(self, ts_ms, price, quote, is_buy):
        self._ensure(ts_ms); r = self._row
        if is_buy: r['buy'] += quote
        else: r['sell'] += quote
        if r['first'] is None: r['first'] = price
        if r['prev'] is not None: r['path'] += abs(price - r['prev'])
        r['prev'] = price; r['last'] = price; r['n'] += 1
    def on_book(self, ts_ms, book):
        self._ensure(ts_ms); r = self._row
        r['nbook'] += 1; r['b15'] += book['book_1_5']; r['b610'] += book['book_6_10']; r['b1120'] += book['book_11_20']
        r['r15'] += book['repl_1_5']; r['r610'] += book['repl_6_10']; r['r1120'] += book['repl_11_20']
    @staticmethod
    def neutral(): return dict(ready=0.0, history_seconds=0.0, old_aggression=0.0, old_side_futility=0.0, aggression_decay=0.5, effectiveness_decay=0.5, control_handoff=0.5, book_handoff=0.5, exhaustion_score=0.5, deep_persistence=0.5)
    def memory_for(self, direction):
        ns = 1.0 if direction == 'UP' else -1.0; os_ = -ns
        H = list(self.history)
        if not H: return self.neutral()
        newest = H[-1]['end_ms']; rows = [r for r in H if 0 <= newest - r['end_ms'] < EF_MEMORY_SECONDS * 1000]
        tr = [r for r in rows if r['n'] > 0]; br = [r for r in rows if r['nbook'] > 0]
        age = lambda r: max(0, newest - r['end_ms'])
        sl = lambda src, lo, hi: [r for r in src if lo <= age(r) < hi]
        recent, recent8, middle = sl(tr, 0, 10_000), sl(tr, 0, 8_000), sl(tr, 8_000, 30_000)
        prior, prior20, long_prior = sl(tr, 10_000, 10**9), sl(tr, 20_000, 10**9), sl(tr, 45_000, 10**9)
        b_recent, b_prior, b_long = sl(br, 0, 8_000), sl(br, 20_000, 10**9), sl(br, 45_000, 10**9)
        if not (len(tr) >= EF_MEMORY_MIN_VALID_SECONDS and len(recent) >= EF_MEMORY_RECENT_MIN_SECONDS and len(prior20) >= EF_MEMORY_PRIOR_MIN_SECONDS):
            n = self.neutral(); n['history_seconds'] = float(len(tr)); return n
        mean = lambda xs, d=0.0: (sum(xs) / len(xs)) if xs else d
        old_aggr = lambda r: max(0.0, os_ * r['delta']); old_eff = lambda r: math.sqrt(old_aggr(r) * max(0.0, os_ * r['price_eff']))
        aligned_new = lambda r: clamp(ns * r['delta'], -1.0, 1.0)
        oh_all = mean([old_aggr(r) for r in prior]); oh = 0.65 * oh_all + 0.35 * mean([old_aggr(r) for r in long_prior], oh_all)
        o_recent = mean([old_aggr(r) for r in recent])
        eh_all = mean([old_eff(r) for r in prior]); eh = 0.65 * eh_all + 0.35 * mean([old_eff(r) for r in long_prior], eh_all)
        e_recent = mean([old_eff(r) for r in recent])
        futility = mean([old_aggr(r) * (1.0 - clamp(max(0.0, os_ * r['price_eff']))) for r in prior])
        sustained = clamp(futility / EF_MEMORY_FUTILITY_SCALE); gate = EF_MEMORY_DECAY_FLOOR + (1.0 - EF_MEMORY_DECAY_FLOOR) * sustained
        aggression_decay = clamp(0.5 + 0.8 * (oh - o_recent) * gate)
        effectiveness_decay = clamp(0.5 + 1.1 * (eh - e_recent) * (0.60 + 0.40 * o_recent) * gate)
        prior_old = mean([max(0.0, -aligned_new(r)) for r in prior20]); recent_new = mean([max(0.0, aligned_new(r)) for r in recent8])
        neutral_middle = 1.0 - clamp(abs(mean([aligned_new(r) for r in middle])) / 0.55)
        transition = clamp(0.5 + 0.55 * (mean([aligned_new(r) for r in recent8]) - mean([aligned_new(r) for r in prior20])))
        control_handoff = clamp(0.30 * prior_old + 0.35 * recent_new + 0.15 * neutral_middle + 0.20 * transition)
        ab = lambda r: clamp(ns * (0.55 * r['book_1_5'] + 0.25 * r['book_6_10'] + 0.20 * r['book_11_20']), -1.0, 1.0)
        pob_all = mean([max(0.0, -ab(r)) for r in b_prior]); pob = 0.65 * pob_all + 0.35 * mean([max(0.0, -ab(r)) for r in b_long], pob_all)
        rnb = mean([max(0.0, ab(r)) for r in b_recent])
        rrepl = mean([clamp(ns * (0.60 * r['repl_1_5'] + 0.25 * r['repl_6_10'] + 0.15 * r['repl_11_20']), -1.0, 1.0) for r in b_recent])
        book_handoff = clamp(0.35 * pob + 0.40 * rnb + 0.25 * clamp(0.5 + 0.5 * rrepl))
        deep = [ns * r['book_11_20'] for r in b_recent]
        deep_persistence = clamp(0.5 + 0.25 * mean(deep) + 0.25 * (2 * (sum(1 for v in deep if v > 0.05) / len(deep)) - 1)) if deep else 0.5
        exhaustion = clamp(0.45 * effectiveness_decay + 0.25 * aggression_decay + 0.20 * book_handoff + 0.10 * clamp(oh / 0.65))
        return dict(ready=1.0, history_seconds=float(len(tr)), old_aggression=clamp(oh), old_side_futility=sustained, aggression_decay=aggression_decay,
                    effectiveness_decay=effectiveness_decay, control_handoff=control_handoff, book_handoff=book_handoff, exhaustion_score=exhaustion, deep_persistence=deep_persistence)


def window_delta(ticks, now_ms, window_ms):
    s = 0.0
    for ts, q in reversed(ticks):
        if ts > now_ms: continue
        if ts < now_ms - window_ms: break
        s += q
    return s


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
