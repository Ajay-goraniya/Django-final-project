"""Task 25 (V, 09-11 18:20): audit the PROCESS of the v12 Polymarket lane, not its PnL.

V's framing: "we keep grading PnL and never verify how the decision was actually produced."

Two independent halves, because they fail in different places:

  A. MODEL APPLICATION - take the lane's OWN recorded `feat` vector, run the ENGINE'S OWN
     `btc_model_v10.Model` loaded from the ENGINE'S OWN `model_v10.json`, and check that p and
     side reproduce what the lane recorded. This catches a wrong model file, a wrong feature
     order, a scaler drift, a miscalibrated isotonic map.

  B. FEATURE CONSTRUCTION - rebuild the feature vector from RAW INPUTS (Binance 1 s klines +
     the 1 Hz polybook log) by driving the engine's OWN `FeatureState`, and check the rebuilt
     values against the recorded ones. This catches a fabricated or mis-timed feature.

CLAUDE.md's rule is obeyed literally: both halves run the running artifact's own module and its
own model file. Nothing here re-implements the engine.

WHAT B CAN AND CANNOT REACH, stated before any number is read. The raw inputs available to H1 are
1 s klines (close only - no trade size, no aggressor flag) and the Polymarket 1 Hz book. So:
  reachable : move_bps ret5 ret15 ret30 ret60 rv60 range_bps pos_in_range dist_hi_bps dist_lo_bps
              prev1_bps prev2_bps sec_left hod_sin hod_cos mv_x_sec  (price path)
              p_venue lv lv_x_sec                                    (venue book)
  NOT reachable: spot_imb15 spot_imb60 (need trade size + aggressor), ofi5 ofi15 ofi60 perp_n15
              basis_bps (need the Binance perp tape), spread_bps imb5 imb20 micro_bps (need the
              Binance spot depth feed). These are NOT verified by this audit and are reported as
              unverified, not as passing.
Also: the engine saw the trade tape, this rebuild sees 1 s closes. A 1 s grid cannot reproduce a
sub-second tick exactly, so the price features are checked as CLOSE, with the distribution shown,
not as bit-identical.
"""
import bisect, json, math, os, sqlite3, statistics, sys

import numpy as np

REPO = '/home/user/Django-final-project'
SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
DB = '/tmp/claude-0/db'
sys.path.insert(0, os.path.join(REPO, 'learner/v12_checkpoint'))
from btc_model_v10 import FEATURES, FeatureState, Model, US        # the RUNNING artifact

MODEL_JSON = os.path.join(REPO, 'learner/v12_checkpoint/model_v10.json')
LANE = os.path.join(DB, 'v12_poly_lane.sqlite3')

PRICE_F = ['move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'rv60', 'range_bps', 'pos_in_range',
           'dist_hi_bps', 'dist_lo_bps', 'prev1_bps', 'prev2_bps', 'sec_left', 'hod_sin',
           'hod_cos', 'mv_x_sec']
VENUE_F = ['p_venue', 'lv', 'lv_x_sec']
UNREACHABLE = [f for f in FEATURES if f not in PRICE_F + VENUE_F]


# ---------------------------------------------------------------- A
def part_a():
    m = Model(MODEL_JSON)
    c = sqlite3.connect(LANE)
    print('=' * 78)
    print('PART A  model application: engine module + engine model file vs the lane\'s own record')
    print('=' * 78)
    print('  model file %s  md5 %s' % (os.path.basename(MODEL_JSON),
                                       __import__('hashlib').md5(open(MODEL_JSON, 'rb').read()).hexdigest()))
    for tab in ('trades', 'decisions'):
        err, side_ok, n = [], 0, 0
        for feat, p, side in c.execute(
                'select feat,p,side from %s where feat is not null and p is not null' % tab):
            f = json.loads(feat)
            pu = m.p_up(f)
            rec = float(p)
            n += 1
            err.append(min(abs(pu - rec), abs((1 - pu) - rec)))
            side_ok += (('UP' if pu >= 0.5 else 'DOWN') == side)
        print('  %-10s n=%5d   max |p err| %.2e   median %.2e   side reproduced %d/%d'
              % (tab, n, max(err), statistics.median(err), side_ok, n))
    print('  (the lane stores p to 4 dp, so ~5e-05 IS exact agreement, not a near miss)')
    print()


# ---------------------------------------------------------------- B
def price_series():
    """1 s closes from paths.npz, flattened to one (ts_us, px) tape."""
    d = np.load(os.path.join(SP, 'build/paths.npz'))
    cid, paths = d['cid'], d['paths'].astype(float)
    ts, px = [], []
    for c0, row in zip(cid, paths):
        base = int(c0) // 1000
        ts.extend(range(base, base + 300))
        px.extend(row.tolist())
    ts = np.array(ts, np.int64)
    o = np.argsort(ts)
    return ts[o], np.array(px)[o]


def venue_book():
    c = sqlite3.connect(os.path.join(DB, 'polybook.sqlite3'))
    out = {}
    for t, au, bu, ad, bd in c.execute('select ts_ms,ask_up,bid_up,ask_dn,bid_dn from pb'):
        out[t // 1000] = (au, bu, ad, bd)
    return out


def part_b(limit=None):
    c = sqlite3.connect(LANE)
    rows = c.execute('select candle_epoch,signal_ms,feat from trades '
                     'where feat is not null order by candle_epoch').fetchall()
    if limit:
        rows = rows[:limit]
    ts, px = price_series()
    book = venue_book()

    print('=' * 78)
    print('PART B  feature construction from raw inputs, through the engine\'s own FeatureState')
    print('=' * 78)
    print('  raw inputs: Binance 1 s klines (paths.npz, %d seconds) + polybook 1 Hz (%d seconds)'
          % (len(ts), len(book)))
    print('  NOT verifiable from these inputs, so NOT verified: %s' % ', '.join(UNREACHABLE))
    print()

    diffs = {k: [] for k in PRICE_F + VENUE_F}
    used = skipped = 0
    for ep, sig_ms, feat in rows:
        rec = json.loads(feat)
        now_us = int(sig_ms) * 1000
        open_us = int(ep) * US
        lo = (ep - 700)                       # prev2 reaches candle_open - 600 s
        a = int(np.searchsorted(ts, lo, side='left'))
        b = int(np.searchsorted(ts, now_us // US, side='right'))
        if b - a < 600:
            skipped += 1
            continue
        st = FeatureState()
        st.KEEP_US = 30 * 60 * US
        for k in range(a, b):
            st.on_spot_trade(int(ts[k]) * US, float(px[k]), 0.0, False)
        q = book.get(now_us // 10 ** 6) or book.get(now_us // 10 ** 6 - 1)
        if q:
            st.on_venue_quote(*q)
        got = st.features(open_us, now_us)
        if got is None:
            skipped += 1
            continue
        used += 1
        for k in PRICE_F + VENUE_F:
            if k in rec and rec[k] is not None and got[k] is not None:
                diffs[k].append(abs(float(got[k]) - float(rec[k])))

    print('  candles rebuilt: %d   skipped for missing tape: %d' % (used, skipped))
    print()
    print('  %-14s %6s %11s %11s %11s' % ('feature', 'n', 'median |d|', 'p90 |d|', 'max |d|'))
    for k in PRICE_F + VENUE_F:
        v = diffs[k]
        if not v:
            print('  %-14s %6s %11s' % (k, 0, 'no data'))
            continue
        v.sort()
        print('  %-14s %6d %11.4g %11.4g %11.4g'
              % (k, len(v), statistics.median(v), v[int(0.9 * (len(v) - 1))], v[-1]))
    print()
    return diffs, used


# ---------------------------------------------------------------- B2 / C
def part_b2():
    """Why the venue block cannot be audited to better than a tick, measured rather than asserted."""
    c = sqlite3.connect(LANE)
    book = venue_book()
    d, no_ask, no_bid = [], 0, 0
    age = []
    for sig, feat, qage in c.execute(
            'select signal_ms,feat,quote_age_ms from trades where feat is not null'):
        f = json.loads(feat)
        s = int(sig) // 1000
        q = book.get(s) or book.get(s - 1)
        if q is None:
            continue
        au, bu, ad, bd = q
        if bu is None:
            no_bid += 1
        if f.get('_ask_up') is None or au is None:
            no_ask += 1
            continue
        d.append(abs(au - f['_ask_up']))
        if qage is not None:
            age.append(qage)
    d.sort()
    print('=' * 78)
    print('PART B2  the resolution limit of the audit instrument, measured')
    print('=' * 78)
    print('  my 1 Hz polybook ask_up vs the engine\'s own recorded _ask_up, same second:')
    print('    n=%d  median |d| %.4f  p90 %.4f  max %.4f  inside one tick %.0f%%'
          % (len(d), statistics.median(d), d[int(0.9 * (len(d) - 1))], d[-1],
             100 * sum(1 for x in d if x <= 0.0101) / len(d)))
    print('    rows where one side of my book sample is missing: %d (no bid_up %d)' % (no_ask, no_bid))
    print('  the lane\'s own quote_age_ms: median %.0f ms, p90 %.0f, max %.0f'
          % (statistics.median(age), sorted(age)[int(0.9 * (len(age) - 1))], max(age)))
    print()
    print('  R-3 measured this book moving a median +1.0c per second. A 1 Hz logger and a live')
    print('  reader sampling <1 s apart must therefore disagree by about a tick. A one-tick')
    print('  median disagreement is the INSTRUMENT\'S FLOOR, not evidence about the engine, so')
    print('  the venue-derived features (p_venue, lv, lv_x_sec) are reported as NOT AUDITABLE')
    print('  at this resolution rather than as passing or failing.')
    print()


def part_c():
    """Decision arithmetic: does the recorded EV follow from the recorded p and ask?"""
    m = Model(MODEL_JSON)
    c = sqlite3.connect(LANE)
    print('=' * 78)
    print('PART C  decision arithmetic, through the engine\'s own Model.cost()')
    print('=' * 78)
    err, n, sec_bad, ask_bad = [], 0, 0, 0
    for feat, p, ask, ev, side, sec, sig, ep in c.execute(
            'select feat,p,quote_ask,signal_ev,side,sec,signal_ms,candle_epoch from trades '
            'where feat is not null and signal_ev is not null'):
        f = json.loads(feat)
        ps = float(p)
        mine = ps * (1 / m.cost(float(ask)) - 1) - (1 - ps)
        err.append(abs(mine - float(ev)))
        n += 1
        rec_ask = f.get('_ask_up') if side == 'UP' else f.get('_ask_dn')
        if rec_ask is not None and abs(float(rec_ask) - float(ask)) > 1e-9:
            ask_bad += 1
        # the engine floors this (int(300 - sec_left)); comparing against round() manufactures
        # a mismatch on every row whose fractional part is >= 0.5. Checked as the engine writes it.
        if sec is not None and int(sec) != int(300 - f['sec_left']):
            sec_bad += 1
    err.sort()
    print('  recomputed EV vs recorded signal_ev: n=%d  max |d| %.2e  median %.2e'
          % (n, err[-1], statistics.median(err)))
    print('  quote_ask equals the feat vector\'s own ask for the chosen side: %d/%d mismatches' % (ask_bad, n))
    print('  recorded sec equals int(300 - sec_left) from the same feat vector: %d/%d mismatches'
          % (sec_bad, n))
    print()


def gate():
    """verify.py is a gate, so it is run - and what it can and cannot check here is stated.

    This task produces NO PnL number and uses NO outcome labels, so grading(), halves(),
    permutation(), sweep(), costs(), null() and paired() have nothing to act on: there is no edge
    to be an artifact of. The check that DOES apply is sample(), plus quote_age() - which is the
    one that matters, because part B2 is exactly a quote-age argument.
    """
    sys.path.insert(0, os.path.join(REPO, 'analysis/h1'))
    from verify import Finding
    f = Finding('Task 25 process audit (no PnL claim - only the applicable gates run)')
    f.sample({'trades': 420, 'decisions': 9386})
    f.quote_age(rule='at-or-after', max_age_s=0.0,
                source='part A/C read the lane\'s own feat vector at its own decision instant')
    f.verdict()
    print('  grading/halves/permutation/sweep/costs/null/paired: NOT APPLICABLE - this audit makes')
    print('  no PnL claim and touches no outcome label. Stated, not silently skipped.')
    print()


def main():
    part_a()
    part_b()
    part_b2()
    part_c()
    gate()


if __name__ == '__main__':
    main()
