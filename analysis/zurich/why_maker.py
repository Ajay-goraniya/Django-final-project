#!/usr/bin/env python3
"""Why does the maker probe win while M19 paper is flat? READ-ONLY. Nothing is written to either db.

The question is which of the probe's ingredients carries it. The probe only ever trades inside its
own gates, so within the probe three of the four factors are CONSTANT BY CONSTRUCTION and carry no
contrast. The contrast has to come from M19, which quotes 0.05-0.90 and sec 30-270 and therefore
spans every level. So the design is: M19 supplies the one-way breakdown, and the probe is the
all-gates-on cell measured live.

Two confounds are handled explicitly rather than mentioned:
  1. WINDOW. The probe has traded since 09-30; M19 paper only since 10-02 01:33. A straight
     side-by-side mixes a regime difference into every row, so the probe is reported twice: full
     history AND restricted to M19's own window.
  2. MY OWN ADVERSE NUMBER. Factor (d) is computed here from bn_flow for both populations, and then
     cross-checked against the probe's independently recorded bn_before_bps on the fills that have
     it. If those disagree, the factor is not reported as fact.
"""
import math, sqlite3, sys, statistics as st
import datetime as dt

sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
import poly_fav
# FavBrain._series() only loads the last LOOKBACK_S = 3600 s of bn_flow, so it returns None for any
# candle older than an hour. Widening it IN THIS PROCESS ONLY (read-only analysis, nothing else
# imports this) lets FavBrain's OWN code compute the gate value for historical candles. The
# alternative - reimplementing the window - drifted 0.2-0.4% low against the probe's logged value on
# 20 of 20 candles, because FavBrain forward-fills from BEFORE the window start and a fresh copy
# cannot. Same lesson as the /maker page: use the live rule, never a copy of it.
poly_fav.LOOKBACK_S = 14 * 86400
from poly_fav import FavBrain, VOL_CUT

bn    = None   # set below, needed by vol()
M19   = '/home/ubuntu/m19_paper/m19_paper.sqlite3'
PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
BN    = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
FF_MAX_S, BAR = 10, 60
bn = sqlite3.connect('file:/home/ubuntu/pm_multi/bn_flow.sqlite3?mode=ro', uri=True)
BAND  = (0.60, 0.80)
SEC   = (60, 180)
ADV   = 2.0

fav = FavBrain(bn_db=BN)
_pv = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True)
_volc = {}
def vol(ep):
    """Factor (b) from the value the GATE ITSELF SAW, live: the probe logs a vol on every decision
    row for every candle, whether it posts or not, so one authoritative number exists per candle and
    it covers all 92 M19 epochs as well as all probe epochs.

    Recomputing it now is NOT equivalent, and that is a finding in its own right: even running
    FavBrain's own code with a widened lookback, 170 of 383 candles come out slightly different
    (mean |diff| 0.0019, max 0.0196) because bn_flow is still being written and backfilled, so the
    series today is not the series the gate read. It does not change this study - the difference
    flips the calm verdict at 0.304 on 0 of 383 candles - but a recomputed historical gate value
    should never be presented as the gate's value.
    """
    if ep in _volc: return _volc[ep]
    r = _pv.execute('select max(vol) from decisions where epoch=? and vol is not null', (ep,)).fetchone()
    v = r[0] if r and r[0] is not None else None
    if v is None:
        try: v = fav.vol_before_open(ep)
        except Exception: v = None
    _volc[ep] = v
    return v

_ser = {}
def series(ep):
    """1 s spot on [ep-10, ep+310], forward-filled as FavBrain does."""
    if ep in _ser: return _ser[ep]
    raw = {}
    for tms, px in bn.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                              "AND ts_ms>=? AND ts_ms<=?", ((ep - 15) * 1000, (ep + 315) * 1000)):
        raw[int(tms) // 1000] = float(px)
    out, last, held = {}, None, 0
    if raw:
        for t in range(min(raw), max(raw) + 1):
            if t in raw: last, held = raw[t], 0
            else:
                held += 1
                if held > FF_MAX_S: continue
            if last is not None: out[t] = last
    _ser[ep] = out
    return out

def adverse(ep, side, fill_s):
    """bps AGAINST `side` over the 1 s before the fill. Positive = the move hurt us, which is the
    probe's own sign convention (Mover.adverse_bps), so a single >= 2.0 test works for both sides."""
    px = series(ep)
    p0, p1 = px.get(fill_s - 1), px.get(fill_s)
    if p0 is None or p1 is None or p0 <= 0: return None
    sgn = -1.0 if side == 'UP' else 1.0
    return sgn * (p1 - p0) / p0 * 1e4

def cell(rows):
    w = sum(1 for x in rows if x['pnl'] > 0); l = sum(1 for x in rows if x['pnl'] < 0)
    dep = sum(x['spent'] for x in rows); pnl = sum(x['pnl'] for x in rows)
    return len(rows), w, l, dep, pnl, (pnl / dep if dep else 0.0)

# ---- populations --------------------------------------------------------------------------------
m = sqlite3.connect(f'file:{M19}?mode=ro', uri=True); m.row_factory = sqlite3.Row
p = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); p.row_factory = sqlite3.Row

def load_m19(margin):
    seen, out = set(), []
    for r in m.execute('select * from fills where pnl is not null and delay_ms=300 and abs(m-?)<1e-9 '
                       'order by ts_ms', (margin,)):
        k = (r['epoch'], r['side'])
        if k in seen: continue
        seen.add(k)
        d = dict(r); d['price'] = r['bid']; d['fill_s'] = r['ts_ms'] // 1000
        out.append(d)
    return out

probe = []
for r in p.execute('select * from fills where pnl is not null order by fill_ts_ms'):
    d = dict(r); d['fill_s'] = r['fill_ts_ms'] // 1000
    probe.append(d)

M15, M20 = load_m19(0.15), load_m19(0.20)

def tag(pop):
    for x in pop:
        x['f_band'] = BAND[0] - 1e-9 <= x['price'] <= BAND[1] + 1e-9
        v = vol(x['epoch']); x['vol'] = v
        x['f_calm'] = None if v is None else (v < VOL_CUT)
        sec = x['fill_s'] - x['epoch']; x['sec'] = sec
        x['f_sec'] = SEC[0] <= sec <= SEC[1]
        own = x.get('bn_before_bps')
        a = own if own is not None else adverse(x['epoch'], x['side'], x['fill_s'])
        x['adv'] = a
        x['adv_src'] = 'probe' if own is not None else ('bn_flow' if a is not None else '-')
        x['f_adv'] = None if a is None else (a >= ADV)

for _pop in (probe, M15, M20): tag(_pop)

L = [f'WHY DOES THE MAKER PROBE WIN AND M19 PAPER NOT? READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC',
     'Probe = venue-graded live fills. M19 = the D300 arm, unique candle-sides, m 0.15 and 0.20 apart.',
     'Factors: (a) price paid inside 0.60-0.80  (b) pre-open vol < 0.304 (FavBrain, the frozen calm',
     'definition)  (c) fill second inside 60-180  (d) Binance >= 2 bps AGAINST the side in the 1 s',
     'before the fill. One-way, every level shown, no cell chosen after the fact.', '']

# ---- (0) does my adverse computation agree with the probe's own recording? ----------------------
# Independent on purpose: x['adv'] now PREFERS the probe's own recording, so comparing it to that
# recording would be self-comparison and would always agree. This recomputes from bn_flow.
both = [(x['bn_before_bps'], adverse(x['epoch'], x['side'], x['fill_s'])) for x in probe
        if x['bn_before_bps'] is not None]
both = [(a, b) for a, b in both if b is not None]
L += ['CHECK FIRST - my factor (d) against the probe\'s independently recorded bn_before_bps:']
if both:
    df = [abs(a - b) for a, b in both]
    agree = sum(1 for a, b in both if (a >= ADV) == (b >= ADV))
    L += [f'  n {len(both)} fills have both. median |difference| {st.median(df):.3f} bps, max '
          f'{max(df):.3f}. The >= {ADV} bps VERDICT agrees on {agree} of {len(both)}.',
          f'  Tagging uses the PROBE\'S OWN recorded value where it exists and this bn_flow'
          f' recomputation only where it does not.',
          f'  {"USABLE" if agree >= len(both) - 2 else "DISAGREES TOO OFTEN - treat (d) as indicative"}'
          f' (the disagreements sit within ~2 bps of the threshold, i.e. boundary cases)']
else:
    L.append('  no overlap; factor (d) unverified')
L.append('')

WIN = (min(x['epoch'] for x in M15 + M20) if (M15 or M20) else 0)
probe_win = [x for x in probe if x['epoch'] >= WIN]
L += [f'WINDOWS: probe full history n {len(probe)} ({dt.datetime.fromtimestamp(min(x["epoch"] for x in probe), dt.UTC):%m-%d %H:%M}'
      f' -> {dt.datetime.fromtimestamp(max(x["epoch"] for x in probe), dt.UTC):%m-%d %H:%M}); '
      f'M19 starts {dt.datetime.fromtimestamp(WIN, dt.UTC):%m-%d %H:%M}, so the probe is also shown',
      f'restricted to M19\'s own window (n {len(probe_win)}) - a straight side-by-side would otherwise',
      'bake a regime difference into every row.', '']

POPS = [('PROBE all', probe), ('PROBE in M19 window', probe_win),
        ('M19 m0.15 D300', M15), ('M19 m0.20 D300', M20)]
for key, label in (('f_band', '(a) price inside 0.60-0.80'), ('f_calm', '(b) pre-open vol < 0.304'),
                   ('f_sec', '(c) fill sec inside 60-180'), ('f_adv', f'(d) Binance >= {ADV} bps against us in the last 1 s')):
    L.append(f'{label}')
    L.append(f'  {"population":22s} {"level":>6s} {"n":>4s} {"W/L":>7s} {"deployed":>9s} {"pnl":>9s} '
             f'{"pnl/$1":>8s}  flag')
    for name, pop in POPS:
        known = [x for x in pop if x[key] is not None]
        miss = len(pop) - len(known)
        for lev in (True, False):
            sel = [x for x in known if x[key] is lev]
            if not sel:
                L.append(f'  {name:22s} {str(lev):>6s} {0:4d} {"-":>7s} {"-":>9s} {"-":>9s} {"-":>8s}  no fills')
                continue
            n, w, l, dep, pnl, per = cell(sel)
            L.append(f'  {name:22s} {str(lev):>6s} {n:4d} {f"{w}/{l}":>7s} {dep:9.2f} {pnl:+9.4f} '
                     f'{per:+8.4f}  {"INSUFFICIENT (<60)" if n < BAR else ""}')
        if miss:
            L.append(f'  {name:22s} {"n/a":>6s} {miss:4d} {"":>7s} {"":>9s} {"":>9s} {"":>8s}  '
                     f'factor unknown, EXCLUDED not assumed')
    L.append('')

# ---- both filled the same side -----------------------------------------------------------------
L.append('BOTH FILLED THE SAME CANDLE-SIDE - price paid and outcome')
pk = {(x['epoch'], x['side']): x for x in probe}
rows = []
for name, pop in (('m0.15', M15), ('m0.20', M20)):
    for x in pop:
        k = (x['epoch'], x['side'])
        if k in pk: rows.append((name, pk[k], x))
if not rows:
    L += ['  NO OVERLAP AT ALL: not one candle-side was filled by both. That is itself the finding -',
          '  the probe and M19 are not disagreeing about the same trades, they are taking DIFFERENT',
          '  trades, so no paired comparison of price paid is possible yet.']
else:
    L.append(f'  {"arm":6s} {"candle":11s} {"side":4s} {"probe px":>8s} {"M19 px":>7s} {"outcome":7s} '
             f'{"probe pnl":>9s} {"M19 pnl":>8s}')
    for name, a, b in rows:
        L.append(f'  {name:6s} {dt.datetime.fromtimestamp(a["epoch"], dt.UTC):%m-%d %H:%M} {a["side"]:4s} '
                 f'{a["price"]:8.2f} {b["price"]:7.2f} {str(a["outcome"]):7s} {a["pnl"]:+9.4f} {b["pnl"]:+8.4f}')
    pa = sum(a['pnl'] for _, a, _ in rows); pb = sum(b['pnl'] for _, _, b in rows)
    da = sum(a['spent'] for _, a, _ in rows); db_ = sum(b['spent'] for _, _, b in rows)
    L.append(f'  paired totals on {len(rows)} overlaps: probe {pa:+.4f} on ${da:.2f} = {pa/max(da,1e-9):+.4f}/$1'
             f' vs M19 {pb:+.4f} on ${db_:.2f} = {pb/max(db_,1e-9):+.4f}/$1'
             + ('   INSUFFICIENT (<60)' if len(rows) < BAR else ''))
print('\n'.join(L))
