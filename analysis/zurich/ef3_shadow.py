#!/usr/bin/env python3
"""EF-3 pre-registered shadow. PAPER ONLY - there is no order path in this file, and no network client.

V pre-registered this at 09-28 14:0x, BEFORE any further tables, and the decision rule below is fixed:

    A = EF-2 v0, m=0.02, S0=150, pinned to the model's side (pw >= 0.5)
    B = raw25, S0=60
    C = fixed15 exactly as London runs it                     <- the control

    After >= 3 FULL days an arm qualifies only if ALL of: $ total > C, worst drawdown <= C's,
    positive on >= 2 of 3 days, fill% >= C's, and V's opposite-ask flip p < 0.05.
    Then it goes to the owner. Nothing reaches London without his confirmation of that exact arm.

HOW IT CANNOT TRADE
  It opens the engine database read-only, opens no socket, imports no broker, and writes only to its own
  file. It is an evaluator, not a bot: it replays already-resolved candles out of decide_log. The most it
  can do if it goes wrong is write a wrong number into /home/ubuntu/pm_ef3/ef3_shadow.sqlite3.

WHY IT REPLAYS INSTEAD OF WATCHING LIVE
  The per-pass FAK simulator needs the row at >= t+250 ms, which only exists after the fact, and the grade
  needs the venue's resolution. Replaying resolved candles gives numbers identical to EF-3's, on the same
  code path. A live watcher would have to approximate both and would not be comparable to the control.

THE MODEL IS FROZEN
  Arm A scores with ef2_fits.npz fit #3 - trained on 09-24..09-27, 1,583,160 rows - which was computed
  BEFORE this shadow was designed and so cannot have been tuned for it. It is copied once to
  ef3_model_A.json with its sha256 and this script refuses to run if that file ever changes.
"""
import sys, os, json, time, sqlite3, hashlib, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1, cost, be
from ef3 import platt, pad_cost, STAKE
from london_z import london_z_at

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
FITS, ROWS = '/home/ubuntu/pm_ef2/ef2_fits.npz', '/home/ubuntu/pm_ef2/ef2_rows.npz'
DB = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
MODEL = '/home/ubuntu/pm_ef3/ef3_model_A.json'
MODEL_D = '/home/ubuntu/pm_ef3/ef4_model_D.json'
SEC_LO, SEC_HI, TICK, DELAY_MS = 15, 240, 0.01, 250
DYN = (1000, 5000, 30000)
ARMS = ('A_v0_m02_S150', 'B_raw25_S60', 'C_fixed15', 'D_ef4gb_t000', 'D2_ef4gb_q95',
        'E1_nightly_q90', 'E2_nightly_q95', 'E3_trail_1h_q90',
        'E4_trail_1h_q90_strict', 'E5_causal_q90_strict', 'S_fixed_top20', 'S_raw_top20',
        'F_z50', 'F25_z25', 'F75_z75')
# ---- ARM F, registered 09-28 21:4x, rule frozen before its first forward row (V, after EF-14).
# fixed15's OWN fire, skipped when |z| < 0.50 with LONDON'S EXACT z (ef14.london_z_at). F25 and F75 are
# REFERENCE arms: logged so the sweep's shape is watched forward rather than re-picked. The backfill sweep
# is non-monotone - +48.6 / +64.7 / +2.4 / +16.6 at .25/.50/.75/1.00 - so a forward run that keeps only the
# cell that won the backfill would be measuring my hindsight, not the rule.
F_CUTS = {'F_z50': 0.50, 'F25_z25': 0.25, 'F75_z75': 0.75}
# ---- ARM S, registered 09-28 18:5x, rule written BEFORE its first forward row (V, owner's NC-12
# "stable version", STABLE_EF.md). Take the profile's OWN fire pass in a candle and keep it only when its
# calibrated edge sits in the top 20% of the edges of that profile's fires over the TRAILING 24 h,
# strictly before this fire. Fewer than 30 fires in that window -> no fire, so the rule never ranks
# against a handful of points. This is the causal form of "top 20% per day": a day-bucket version would
# need the day's later fires to rank the morning's.
#   edge, FIXED  = platt(p_side) - be(own_ask)      (profile fixed15, ev >= 0.15 at ask+1 tick)
#   edge, RAW    = p_side        - be(own_ask)      (profile raw_v10_live25, ev >= 0.25)
# Both logged; FIXED is primary. Same FAK sim and the same forward decision rule as every other arm.
S_WINDOW_MS, S_Q, S_MIN = 24 * 3600_000, 0.80, 30
# RETIRED from the decision 09-28 17:3x (V, NC-19 c8a460d): E1 and E3 use a plain sample quantile as the
# threshold, which for a stump model IS one of its ~545 distinct output values - so `pred >= thr` fires on
# EQUALITY (8,415 of 09-27's rows sit exactly on it) and which pass wins is decided by ties. They keep
# logging as history; they are not candidates. E4/E5 are the SAME two cells under the strict threshold.
RETIRED = {'E1_nightly_q90', 'E3_trail_1h_q90'}
STRICT_F = '/home/ubuntu/pm_ef3/ef5_thr_strict.json'
# E3, registered by V 09-28 16:4x ON A RELAXED ENTRY BAR: the best-day-share <50% entry test was ill-posed
# on three days (unbounded when the total is small; its floor moves with the day count). V relaxed the
# ENTRY bar only and said so on the record. The FORWARD decision rule is unchanged and binds E3 exactly
# like every other arm. Entry was relaxed; nothing about how it will be judged was.
E3_W_MS, E3_Q, E3_GRID_MS = 3600_000, 0.90, 60_000
EDIR = '/home/ubuntu/pm_ef3'      # arm E: one model per day, written by ef5_nightly.py at 00:05 UTC
Q_D2 = 0.95      # D2 = the SAME frozen model as D, only the threshold rule differs (EF-5, V 09-28 15:5x)
ALL52 = None            # set in run_once from the frozen row table's name list

# The frozen arm-A model was trained on 09-24..09-27, so those days are IN-SAMPLE for it and 09-28 was
# already on the table when V wrote the decision rule. The rule says "from now". Everything up to and
# including this day is therefore backfill - kept because reproducing EF-3's numbers is a useful check on
# the evaluator, and excluded from the decision by code rather than by my remembering to.
PREREG_DAY = '09-28'


def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out


def load_D():
    """Arm D - registered 09-28 15:4x with a NEGATIVE prior. NOT a qualifying candidate.

    V authorised arm D if EF-4 beat C on $ and drawdown. Walk-forward it did: EF-4gb t=0.00 S0=0 was
    +$164.0 / DD $75.5 / 4-of-4 days against C's +$16.3 / $85.3. Frozen into a SINGLE model - the only
    form that could ever run forward - it does not reproduce: -$138.1 / DD $226.7 / 1-of-5 days on the
    same candles, -$72.4 on the four walk-forward days where the grid said +$164.0.

    That is not a bug. The scorer was checked against ef4.gb_reg_pred (max abs diff 0.0) and the feature
    map drops exactly the six level columns. The cause is the threshold: predictions have sd 0.130 about
    a base of -0.0996, so "pred >= 0" is a cut about 0.76 sd into the upper tail, and WHERE that cut
    lands depends on each fit's calibration offset. A walk-forward model trained on 213k rows and one
    trained on 1.58M put it in different places, so the grid's success was partly a per-day quantile
    accident rather than a rule.

    It stays in the shadow as a FALSIFICATION CHECK, not a candidate: the prediction on record is that
    it runs negative forward. V can drop it at will - it costs nothing, this is paper with no order
    path. It must not be read as qualifying under the A/B/C decision rule.
    """
    if not os.path.exists(MODEL_D): return None
    M = json.load(open(MODEL_D))
    body = {k: M[k] for k in M if k not in ('sha256', 'frozen_at')}
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if h != M['sha256']:
        raise SystemExit(f'REFUSING TO RUN: {MODEL_D} has changed since it was frozen '
                         f'({M["sha256"][:16]} -> {h[:16]}). Arm D must not move.')
    return M


def score_D(X, M):
    """X must be the 52-wide row; the level columns are dropped to match the frozen 46."""
    idx = [ALL52.index(n) for n in M['names']]
    Z = (X[:, idx] - np.array(M['mean'])) / np.array(M['sd'])
    F = np.full(len(Z), M['base'])
    for j, thr, vl, vr in M['trees']:
        F += np.where(Z[:, int(j)] <= thr, vl, vr)
    return F


def strict_above(sorted_v, qq):
    """smallest DISTINCT value strictly greater than the sample quantile; inf if none."""
    if len(sorted_v) < 500: return float('inf')
    qv = float(np.quantile(sorted_v, qq))
    i = int(np.searchsorted(sorted_v, qv, side='right'))
    return float(sorted_v[i]) if i < len(sorted_v) else float('inf')


def load_E(day):
    """Arm E, pre-registered by V 09-28 16:1x. Tonight's model scores today only - a day with no model
    file simply does not fire, which is what every day before the first nightly run should do."""
    p = f'{EDIR}/ef5_model_{day}.json'
    if not p or not os.path.exists(p): return None
    M = json.load(open(p))
    body = {k: M[k] for k in M if k not in ('sha256', 'fitted_at')}
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if h != M['sha256']:
        raise SystemExit(f'REFUSING TO RUN: {p} changed after it was written ({M["sha256"][:16]} -> '
                         f'{h[:16]}). A nightly model must not be edited once the day has started.')
    if M['for_day'] != day:
        raise SystemExit(f'{p} says for_day={M["for_day"]} but was loaded for {day}')
    return M


def score_E(X, M):
    idx = [ALL52.index(n) for n in M['names']]
    Z = (X[:, idx] - np.array(M['mean'])) / np.array(M['sd'])
    F = np.full(len(Z), M['base'])
    for j, thr, vl, vr in M['trees']:
        F += np.where(Z[:, int(j)] <= thr, vl, vr)
    return F


def freeze_model():
    """Copy fit #3 out of ef2_fits.npz once, then never again. Refuse to run if it has changed."""
    f = np.load(FITS, allow_pickle=True)
    body = dict(coef=f['coef'][3].tolist(), mean=f['mean'][3].tolist(), sd=f['sd'][3].tolist(),
                names=[str(s) for s in f['names']], fitted_for=str(f['fitted'][3]),
                source='ef2_fits.npz fit #3, trained on 09-24..09-27 (1,583,160 rows)')
    blob = json.dumps(body, sort_keys=True)
    h = hashlib.sha256(blob.encode()).hexdigest()
    if os.path.exists(MODEL):
        old = json.load(open(MODEL))
        if old['sha256'] != h:
            raise SystemExit(f'REFUSING TO RUN: {MODEL} no longer matches ef2_fits.npz fit #3.\n'
                             f'  frozen {old["sha256"][:16]}  now {h[:16]}\n'
                             f'  The pre-registered model must not move. Investigate before deleting this file.')
        return old
    body['sha256'] = h
    body['frozen_at'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    json.dump(body, open(MODEL, 'w'), indent=1)
    print(f'froze arm A model -> {MODEL}  sha256 {h[:16]}')
    return body


def build_rows(rs, ep, out, keys_n):
    """VERBATIM the inner loop of ef2_rows.py. --selftest proves it row-for-row against ef2_rows.npz."""
    rs = sorted(rs, key=lambda r: r[0])
    ts_a = np.array([r[0] for r in rs])
    ua_a = np.array([r[3] for r in rs]); da_a = np.array([r[4] for r in rs])
    R = []
    for i, (ts, side_l, p_l, ua, da, fire, v) in enumerate(rs):
        j = int(np.searchsorted(ts_a, ts + DELAY_MS, side='left'))
        lo30 = int(np.searchsorted(ts_a, ts - DYN[2], side='left'))
        back = [int(np.searchsorted(ts_a, ts - d, side='right')) - 1 for d in DYN]
        for side in ('UP', 'DOWN'):
            own = ua if side == 'UP' else da
            opp = da if side == 'UP' else ua
            if not (0.01 < own < 0.99): continue
            oa = ua_a if side == 'UP' else da_a
            dyn = [own - oa[b] if 0 <= b < len(oa) else 0.0 for b in back]
            w = oa[lo30:i + 1]
            dip = own - float(w.min()) if len(w) else 0.0
            q = None
            if j < len(rs):
                lat = float(ua_a[j] if side == 'UP' else da_a[j])
                if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q = lat
            x = v + [own, opp, dyn[0], dyn[1], dyn[2], dip, float((ts // 1000) - ep),
                     (p_l if side == side_l else 1.0 - p_l)]
            R.append(dict(x=np.array(x, dtype=np.float32), own=own, q=(q if q is not None else float('nan')),
                          win=(1.0 if side == out else 0.0), sec=int((ts // 1000) - ep), ts=ts,
                          up=(1 if side == 'UP' else 0), pe=x[-1]))
    return R


def load_candles(eps=None, min_epoch=None):
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    nk = len(keys)
    vo = outcomes()
    cand = collections.defaultdict(list)
    seen_ts = collections.defaultdict(set)
    for src in (ARCH, LIVE):
        try: c = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
        except Exception: continue
        q = ('SELECT ts_ms,epoch,side,p,ask,up_ask,dn_ask,fire,feats FROM decide_log '
             'WHERE p IS NOT NULL AND side IS NOT NULL AND up_ask IS NOT NULL AND dn_ask IS NOT NULL')
        args = ()
        if min_epoch is not None:            # incremental: only candles we have not already scored
            q += ' AND epoch > ?'; args = (min_epoch,)
        try: cur = c.execute(q + ' ORDER BY ts_ms', args)
        except Exception: continue
        for ts, ep, side, p, ask, ua, da, fire, fs in cur:
            if ep not in vo: continue
            if eps is not None and ep not in eps: continue
            sec = (ts // 1000) - ep
            if not (SEC_LO <= sec <= SEC_HI): continue
            v = None
            if fs:
                try:
                    raw = json.loads(fs)
                    if len(raw) == nk: v = raw
                except Exception: pass
            if v is None: continue
            # dedup on ts alone: ARCH and LIVE overlap, and a pass is uniquely identified by its
            # millisecond. `row not in cand[ep]` was O(n^2) on ~1500 rows a candle and dominated runtime.
            if ts in seen_ts[ep]: continue
            seen_ts[ep].add(ts)
            cand[ep].append((ts, side, float(p), float(ua), float(da), int(fire or 0), v))
    return cand, vo, nk


def score_A(X, M):
    mu, sd = np.array(M['mean']), np.array(M['sd'])
    w = np.array(M['coef'])
    Z = (X - mu) / np.where(sd > 0, sd, 1.0)
    z = Z @ w[1:] + w[0]
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def pick(rows, pA, pD=None, thr_d2=None, pE=None, thrE=None, e3thr=None, e5thr=None):
    """The three arms, each taking its FIRST qualifying row in the candle. One fire per candle, max."""
    out = {}
    for i, r in enumerate(rows):
        if 'A_v0_m02_S150' not in out and r['sec'] >= 150 and pA[i] >= 0.5 \
                and (pA[i] / be(r['own']) - 1) >= 0.02:
            out['A_v0_m02_S150'] = (r, float(pA[i]))
        if 'B_raw25_S60' not in out and r['sec'] >= 60 and r['pe'] >= 0.5 \
                and (r['pe'] / be(r['own']) - 1) >= 0.25:
            out['B_raw25_S60'] = (r, r['pe'])
        if 'C_fixed15' not in out and r['pe'] >= 0.5 \
                and (platt(r['pe']) / pad_cost(r['own']) - 1) >= 0.15:
            out['C_fixed15'] = (r, r['pe'])
        if '_RAW0' not in out and r['pe'] >= 0.5 and (r['pe'] / be(r['own']) - 1) >= 0.25:
            out['_RAW0'] = (r, r['pe'])
        if pD is not None and 'D_ef4gb_t000' not in out and r['pe'] >= 0.5 and pD[i] >= 0.0:
            out['D_ef4gb_t000'] = (r, r['pe'])
        if pD is not None and thr_d2 is not None and 'D2_ef4gb_q95' not in out \
                and r['pe'] >= 0.5 and pD[i] >= thr_d2:
            out['D2_ef4gb_q95'] = (r, r['pe'])
        if pE is not None and r['pe'] >= 0.5:
            for arm, key in (('E1_nightly_q90', 'q90'), ('E2_nightly_q95', 'q95')):
                if arm not in out and pE[i] >= thrE[key]:
                    out[arm] = (r, r['pe'])
            if e3thr is not None:
                tp, tsx = e3thr(r['ts'])
                if 'E3_trail_1h_q90' not in out and tp is not None and pE[i] >= tp:
                    out['E3_trail_1h_q90'] = (r, r['pe'])
                if 'E4_trail_1h_q90_strict' not in out and tsx is not None and pE[i] >= tsx:
                    out['E4_trail_1h_q90_strict'] = (r, r['pe'])
            if e5thr is not None and 'E5_causal_q90_strict' not in out and pE[i] >= e5thr:
                out['E5_causal_q90_strict'] = (r, r['pe'])
    return out


def _ref_tape():
    """Chainlink 1 s ref for London's z. tape1s only; the RTDS oracle capture will replace it once the
    TWAP60 topic is known and a match check has been run."""
    c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    return {int(t): float(p) for t, p in
            c.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL')}


def _edge_fixed(p, a): return platt(p) - be(a)


def _edge_raw(p, a): return p - be(a)


def db():
    d = sqlite3.connect(DB)
    d.execute('CREATE TABLE IF NOT EXISTS fires(epoch INT, arm TEXT, ts_ms INT, day TEXT, sec INT, '
              'up INT, p REAL, ask REAL, fill REAL, opp_fill REAL, win INT, pnl REAL, '
              'PRIMARY KEY(epoch, arm))')
    d.execute('CREATE TABLE IF NOT EXISTS seen(epoch INT PRIMARY KEY, at INT)')
    # D2's threshold is the q-quantile of the frozen model's predictions on the PREVIOUS day, so the
    # day's predictions have to be kept. ~330k floats a day; the prune keeps three days, which is all
    # the rule needs (day k reads day k-1).
    d.execute('CREATE TABLE IF NOT EXISTS preds(day TEXT, pr REAL)')
    d.execute('CREATE INDEX IF NOT EXISTS preds_day ON preds(day)')
    # E3's trailing window needs the nightly model's predictions WITH timestamps.
    d.execute('CREATE TABLE IF NOT EXISTS epreds(ts_ms INT, day TEXT, pr REAL)')
    d.execute('CREATE INDEX IF NOT EXISTS epreds_ts ON epreds(ts_ms)')
    # arm S: the trailing-24 h edge history of each profile's OWN fires
    d.execute('CREATE TABLE IF NOT EXISTS sedges(ts_ms INTEGER, prof TEXT, edge REAL)')
    d.execute('CREATE INDEX IF NOT EXISTS sedges_ts ON sedges(ts_ms)')
    return d


def run_once():
    global ALL52, STRICT, REF
    M = freeze_model(); MD = load_D()
    ALL52 = [str(x) for x in np.load(ROWS, allow_pickle=True)['names']]
    REF = _ref_tape()
    STRICT = json.load(open(STRICT_F)) if os.path.exists(STRICT_F) else {}
    d = db()
    done = {e for (e,) in d.execute('SELECT epoch FROM seen')}
    hi = d.execute('SELECT max(epoch) FROM seen').fetchone()[0]
    # A candle is only scorable once it has resolved, so the high-water mark lets us skip the bulk of the
    # log. But `seen` only records RESOLVED candles, and a straggler can resolve after a later one does -
    # a transient gap in one gamma mirror is enough. A bare `epoch > hi` would then skip that candle
    # forever and silently lose it. One hour of lookback costs nothing and makes the skip recoverable.
    cand, vo, nk = load_candles(min_epoch=(hi - 3600 if hi else None))
    todo = [e for e in cand if e not in done]
    n = 0; qcache = {}; ecache = {}; e3buf = {}
    for ep in sorted(todo):
        rows = build_rows(cand[ep], ep, vo[ep], nk)
        if not rows: 
            d.execute('INSERT OR REPLACE INTO seen VALUES(?,?)', (ep, int(time.time()))); continue
        X = np.stack([r['x'] for r in rows])
        pA = score_A(X, M)
        pD = score_D(X, MD) if MD is not None else None
        opp = {(r['ts'], 1 - r['up']): r['q'] for r in rows}
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        if pD is not None:
            d.executemany('INSERT INTO preds VALUES(?,?)', [(day, float(v)) for v in pD])
            prev = (dt.datetime.fromtimestamp(ep, dt.timezone.utc) - dt.timedelta(days=1)).strftime('%m-%d')
            if prev not in qcache:
                v = [x for (x,) in d.execute('SELECT pr FROM preds WHERE day=?', (prev,))]
                qcache[prev] = float(np.quantile(v, Q_D2)) if len(v) >= 1000 else None
            thr_d2 = qcache[prev]
        else: thr_d2 = None
        if day not in ecache: ecache[day] = load_E(day)
        ME = ecache[day]
        pE = score_E(X, ME) if ME is not None else None
        thrE = ME['thr'] if ME is not None else None
        e3thr = None
        e5thr = (ME.get('thr_strict', {}) or {}).get('q90') if ME else None
        if e5thr is None and ME is not None:
            e5thr = STRICT.get(day)
        if ME is not None:
            if day not in e3buf:
                # cross-boundary seed: the previous day's last hour re-scored under TODAY's model, so the
                # window matches what EF-6 measured instead of mixing two models at the day boundary.
                seed = ME.get('seed') or []
                prior = [(int(a), float(b)) for a, b in seed]
                prior += [(int(a), float(b)) for a, b in d.execute(
                    'SELECT ts_ms, pr FROM epreds WHERE day=? ORDER BY ts_ms', (day,))]
                e3buf[day] = sorted(prior)
            # add THIS candle's rows before scoring it. A threshold at grid edge E still only uses rows
            # with ts < E, so same-candle rows earlier than E are legitimately in the window and rows at
            # or after E are excluded - no lookahead. Appending after the candle (the first version of
            # this) made late-candle thresholds blind to the candle's own early rows, which matched
            # neither ef6.py's backtest nor V's streaming lane. Found by the parity harness.
            newp = [(int(r['ts']), day, float(v)) for r, v in zip(rows, pE)]
            d.executemany('INSERT INTO epreds VALUES(?,?,?)', newp)
            e3buf[day].extend((t_, p_) for t_, _, p_ in newp)
            e3buf[day].sort()
            buf = e3buf[day]

            def e3thr(t, _b=buf):
                lo = t - E3_W_MS
                v = [p for (x, p) in _b if lo <= x < t]
                return float(np.quantile(v, E3_Q)) if len(v) >= 500 else None
            # 60 s grid: one threshold per minute, not one per row
            gcache = {}

            def e3thr(t, _b=buf, _g=gcache):
                k = t // E3_GRID_MS
                if k not in _g:
                    edge = k * E3_GRID_MS
                    v = [p for (x, p) in _b if edge - E3_W_MS <= x < edge]
                    if len(v) >= 500:
                        sv = np.sort(np.asarray(v))
                        _g[k] = (float(np.quantile(sv, E3_Q)), strict_above(sv, E3_Q))
                    else: _g[k] = (None, None)
                return _g[k]
        sel = pick(rows, pA, pD, thr_d2, pE, thrE, e3thr, e5thr)
        # ---- arm S: rank this candle's own fire against the profile's trailing 24 h, then append ----
        for prof, key, arm, efn in (('FIXED', 'C_fixed15', 'S_fixed_top20', _edge_fixed),
                                    ('RAW', '_RAW0', 'S_raw_top20', _edge_raw)):
            # NOT `cand` - that is the outer candle dict in this same function, and shadowing it made
            # the second candle crash on `cand[ep]` with NoneType.
            c0 = sel.get(key)
            if c0 is None: continue
            r0, p0 = c0
            e0 = efn(r0['pe'], r0['own'])
            lo_ts = r0['ts'] - S_WINDOW_MS
            hist = [x for (x,) in d.execute(
                'SELECT edge FROM sedges WHERE prof=? AND ts_ms >= ? AND ts_ms < ?',
                (prof, lo_ts, r0['ts']))]
            if len(hist) >= S_MIN and e0 >= float(np.quantile(np.asarray(hist), S_Q)):
                sel[arm] = (r0, p0)
            d.execute('INSERT INTO sedges VALUES(?,?,?)', (r0['ts'], prof, float(e0)))
        # ---- arm F: fixed15's own fire, kept only when |London z| clears the cut ----
        cF = sel.get('C_fixed15')
        if cF is not None:
            r0, p0 = cF
            zt = london_z_at(REF, ep, int(r0['ts'] // 1000))
            if zt is not None:
                zz = zt if r0['up'] else -zt          # sign to the side being bought
                for arm, cut in F_CUTS.items():
                    if abs(zz) >= cut: sel[arm] = (r0, p0)
        sel.pop('_RAW0', None)
        for arm, (r, p) in sel.items():
            q = r['q']
            pnl = STAKE * per1(r['win'], q) if q == q else 0.0
            d.execute('INSERT OR REPLACE INTO fires VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ep, arm, r['ts'], day, r['sec'], r['up'], float(p), r['own'],
                       (None if q != q else float(q)),
                       (lambda v: None if v != v else float(v))(opp.get((r['ts'], r['up']), float('nan'))),
                       int(r['win']), pnl))
            n += 1
        d.execute('INSERT OR REPLACE INTO seen VALUES(?,?)', (ep, int(time.time())))
    d.execute('DELETE FROM sedges WHERE ts_ms < ?', (int(time.time() * 1000) - 3 * S_WINDOW_MS,))
    keepd = sorted({x for (x,) in d.execute('SELECT DISTINCT day FROM preds')})[-3:]
    if keepd:
        d.execute(f"DELETE FROM preds WHERE day NOT IN ({','.join('?'*len(keepd))})", keepd)
        d.execute(f"DELETE FROM epreds WHERE day NOT IN ({','.join('?'*len(keepd))})", keepd)
    d.commit()
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} evaluated {len(todo)} new candles, {n} fires recorded')
    return d


def report(d=None):
    d = d or db()
    import random
    print(f'\nEF-3 PRE-REGISTERED SHADOW - PAPER, no order path. Decision rule fixed 09-28 14:0x by V.')
    hdr = (f'  {"arm":24s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"fires":>7}{"fills":>7}{"fill%":>7}'
           f'{"win%":>7}{"days+":>7}{"run":>5}{"permP":>8}')
    print(hdr)
    S = {}
    for arm in ARMS:
        rs = d.execute('SELECT day,win,pnl,fill,opp_fill FROM fires WHERE arm=? ORDER BY ts_ms',
                       (arm,)).fetchall()
        allday = sorted({r[0] for r in d.execute('SELECT day FROM fires')})
        fl = [r for r in rs if r[3] is not None]
        tagr = ' [RETIRED - tie-degenerate rule, history only]' if arm in RETIRED else ''
        if not fl:
            print(f'  {arm:24s}    (no fills yet){tagr}'); continue
        cum = peak = mdd = 0.; run = worst = 0; byd = collections.defaultdict(float)
        for day, win, pnl, q, oq in fl:
            cum += pnl; peak = max(peak, cum); mdd = max(mdd, peak - cum)
            run = run + 1 if pnl < 0 else 0; worst = max(worst, run)
            byd[day] += pnl
        rng = random.Random(41)
        Wf = lambda s: sum(per1(a, b) * cost(b) for a, b in s) / sum(cost(b) for a, b in s) if s else float('nan')
        real = Wf([(w, q) for _, w, _, q, _ in fl])
        sims = []
        for _ in range(300):
            acc = []
            for _, w, _, q, oq in fl:
                if rng.random() < 0.5:
                    if oq is None: continue
                    acc.append((1 - w, oq))
                else: acc.append((w, q))
            if acc: sims.append(Wf(acc))
        pp = (sum(1 for x in sims if x >= real) / len(sims)) if sims else float('nan')
        S[arm] = dict(tot=cum, mdd=mdd, n=len(rs), nf=len(fl), fill=len(fl) / len(rs),
                      pos=sum(1 for v in byd.values() if v > 0), days=len(byd), run=worst, perm=pp,
                      byd=dict(byd))
        wr = sum(r[1] for r in fl) / len(fl)
        S[arm]['win'] = wr
        tagr = ' [RETIRED]' if arm in RETIRED else ''
        print(f'  {arm:24s}{cum:>+8.1f}{mdd:>7.1f}{(cum/mdd if mdd>0 else 99.9):>7.2f}{len(rs):>7}'
              f'{len(fl):>7}{100*len(fl)/len(rs):>6.1f}%{100*wr:>6.1f}%'
              f'{f"{S[arm][chr(112)+chr(111)+chr(115)]}/{S[arm][chr(100)+chr(97)+chr(121)+chr(115)]}":>7}{worst:>5}{pp:>8.3f}' + tagr)
        print(f'      per day $:  ' + '  '.join(f'{x} {byd.get(x, 0.0):+7.1f}' for x in allday))
    C = S.get('C_fixed15')
    full = sorted({r[0] for r in d.execute('SELECT day FROM fires')})
    fwd = [x for x in full if x > PREREG_DAY]
    print(f'\n  days in the db: {full}')
    print(f'  backfill (<= {PREREG_DAY}, IN-SAMPLE for arm A - context only, NOT the decision): '
          f'{[x for x in full if x <= PREREG_DAY]}')
    print(f'  forward days (the decision runs on these): {fwd or "none yet"}')
    if C and len(fwd) >= 3:
        for arm in ('A_v0_m02_S150', 'B_raw25_S60'):
            a = S.get(arm)
            if not a: continue
            # recompute on forward days only - S[] above spans the whole db
            a = {**a, 'tot': sum(v for k, v in a['byd'].items() if k > PREREG_DAY),
                 'pos': sum(1 for k, v in a['byd'].items() if k > PREREG_DAY and v > 0)}
            ck = [('$ total > C', a['tot'] > C['tot']), ('DD <= C', a['mdd'] <= C['mdd']),
                  ('positive >= 2 of 3 days', a['pos'] >= 2), ('fill% >= C', a['fill'] >= C['fill']),
                  ('opposite-ask flip p < 0.05', a['perm'] < 0.05)]
            print(f'  {arm}: ' + '  '.join(f'[{"OK" if v else "no"}] {k}' for k, v in ck))
            print(f'    -> {"QUALIFIES - report to V, then the owner" if all(v for _, v in ck) else "does not qualify"}')
    else:
        print(f'  decision rule NOT evaluated: needs >= 3 full FORWARD days, have {len(fwd)}.')
    return S


def selftest():
    """Prove build_rows reproduces ef2_rows.npz exactly, so arm A is scored on the EF-3 feature table."""
    z = np.load(ROWS, allow_pickle=True)
    ep_all = z['ep']; eps = sorted(set(ep_all.tolist()))
    import random; random.seed(7)
    pick_eps = set(random.sample(eps, 25))
    cand, vo, nk = load_candles(pick_eps)
    bad = 0; checked = 0
    for ep in sorted(pick_eps):
        if ep not in cand: continue
        mine = build_rows(cand[ep], ep, vo[ep], nk)
        m = ep_all == ep
        Xr, qr, yr = z['X'][m], z['q'][m], z['y'][m]
        if len(mine) != len(Xr):
            print(f'  epoch {ep}: ROW COUNT {len(mine)} vs {len(Xr)}'); bad += 1; continue
        Xm = np.stack([r['x'] for r in mine])
        qm = np.array([r['q'] for r in mine], dtype=np.float32)
        ym = np.array([r['win'] for r in mine], dtype=np.int8)
        if not np.allclose(Xm, Xr, atol=1e-5, equal_nan=True): print(f'  epoch {ep}: X differs'); bad += 1
        elif not np.allclose(qm, qr, atol=1e-6, equal_nan=True): print(f'  epoch {ep}: q differs'); bad += 1
        elif not (ym == yr).all(): print(f'  epoch {ep}: y differs'); bad += 1
        checked += 1
    print(f'selftest: {checked} epochs compared against ef2_rows.npz, {bad} mismatched')
    if bad or checked < 20:
        raise SystemExit('SELFTEST FAILED - do not trust arm A until build_rows matches ef2_rows.py')
    print('selftest PASSED - build_rows is row-for-row identical to the EF-3 feature table')


if __name__ == '__main__':
    if '--selftest' in sys.argv: selftest()
    elif '--report' in sys.argv: report()
    else: report(run_once())
