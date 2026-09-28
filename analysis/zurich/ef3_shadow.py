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
from ef2_model import per1, cost, be
from ef3 import platt, pad_cost, STAKE

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
FITS, ROWS = '/home/ubuntu/pm_ef2/ef2_fits.npz', '/home/ubuntu/pm_ef2/ef2_rows.npz'
DB = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
MODEL = '/home/ubuntu/pm_ef3/ef3_model_A.json'
SEC_LO, SEC_HI, TICK, DELAY_MS = 15, 240, 0.01, 250
DYN = (1000, 5000, 30000)
ARMS = ('A_v0_m02_S150', 'B_raw25_S60', 'C_fixed15')

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


def pick(rows, pA):
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
    return out


def db():
    d = sqlite3.connect(DB)
    d.execute('CREATE TABLE IF NOT EXISTS fires(epoch INT, arm TEXT, ts_ms INT, day TEXT, sec INT, '
              'up INT, p REAL, ask REAL, fill REAL, opp_fill REAL, win INT, pnl REAL, '
              'PRIMARY KEY(epoch, arm))')
    d.execute('CREATE TABLE IF NOT EXISTS seen(epoch INT PRIMARY KEY, at INT)')
    return d


def run_once():
    M = freeze_model()
    d = db()
    done = {e for (e,) in d.execute('SELECT epoch FROM seen')}
    hi = d.execute('SELECT max(epoch) FROM seen').fetchone()[0]
    # A candle is only scorable once it has resolved, so the high-water mark lets us skip the bulk of the
    # log. But `seen` only records RESOLVED candles, and a straggler can resolve after a later one does -
    # a transient gap in one gamma mirror is enough. A bare `epoch > hi` would then skip that candle
    # forever and silently lose it. One hour of lookback costs nothing and makes the skip recoverable.
    cand, vo, nk = load_candles(min_epoch=(hi - 3600 if hi else None))
    todo = [e for e in cand if e not in done]
    n = 0
    for ep in sorted(todo):
        rows = build_rows(cand[ep], ep, vo[ep], nk)
        if not rows: 
            d.execute('INSERT OR REPLACE INTO seen VALUES(?,?)', (ep, int(time.time()))); continue
        X = np.stack([r['x'] for r in rows])
        pA = score_A(X, M)
        opp = {(r['ts'], 1 - r['up']): r['q'] for r in rows}
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        for arm, (r, p) in pick(rows, pA).items():
            q = r['q']
            pnl = STAKE * per1(r['win'], q) if q == q else 0.0
            d.execute('INSERT OR REPLACE INTO fires VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ep, arm, r['ts'], day, r['sec'], r['up'], float(p), r['own'],
                       (None if q != q else float(q)),
                       (lambda v: None if v != v else float(v))(opp.get((r['ts'], r['up']), float('nan'))),
                       int(r['win']), pnl))
            n += 1
        d.execute('INSERT OR REPLACE INTO seen VALUES(?,?)', (ep, int(time.time())))
    d.commit()
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} evaluated {len(todo)} new candles, {n} fires recorded')
    return d


def report(d=None):
    d = d or db()
    import random
    print(f'\nEF-3 PRE-REGISTERED SHADOW - PAPER, no order path. Decision rule fixed 09-28 14:0x by V.')
    hdr = f'  {"arm":16s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"fires":>7}{"fills":>7}{"fill%":>7}{"days+":>7}{"run":>5}{"permP":>8}'
    print(hdr)
    S = {}
    for arm in ARMS:
        rs = d.execute('SELECT day,win,pnl,fill,opp_fill FROM fires WHERE arm=? ORDER BY ts_ms',
                       (arm,)).fetchall()
        fl = [r for r in rs if r[3] is not None]
        if not fl:
            print(f'  {arm:16s}    (no fills yet)'); continue
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
        print(f'  {arm:16s}{cum:>+8.1f}{mdd:>7.1f}{(cum/mdd if mdd>0 else 99.9):>7.2f}{len(rs):>7}'
              f'{len(fl):>7}{100*len(fl)/len(rs):>6.1f}%{f"{S[arm][chr(112)+chr(111)+chr(115)]}/{S[arm][chr(100)+chr(97)+chr(121)+chr(115)]}":>7}{worst:>5}{pp:>8.3f}')
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
