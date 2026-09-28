#!/usr/bin/env python3
"""EF-10: parameter adjustment of RAW on its own knobs. READ-ONLY. Master OFF. No veto, no brain.

V/owner 09-28: adjust raw's parameters using the evidence we have. Full grid, never the best cell alone,
then WALK-FORWARD selection so the table is not read as a result.

  EV bar        0.10 0.15 0.20 0.25 0.30 0.40
  earliest sec  0 30 60 90            latest sec  180 210 240
  ask band      min 0.05 0.15 0.25    max 0.55 0.65 0.80
  price cap     ask, ask+1c, ask+2c                       -> 6*4*3*3*3*3 = 1,944 cells

PRICE CAP is the order's limit price, so it sets BOTH what you would pay and what the FAK can fill at:
EV is judged at be(cap) and the fill requires the own-side ask at the first row >= t+250 ms to be <= cap,
filling AT that later ask. Judging EV at the ask while paying up to ask+2c would be scoring a trade at a
price it was never going to get.

RAW AS IT RUNS TODAY is reported separately and is NOT a grid cell: ev 0.25 judged at be(ask), no second
bounds beyond the logged 15-240, no ask band, fill cap +1 tick. The grid's widest band (0.05-0.80) already
excludes fires raw takes, so the honest baseline is raw's own settings rather than the nearest cell.
"""
import sys, os, sqlite3, collections, itertools, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost, be
from ef3 import STAKE
from ef3_shadow import outcomes

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
TICK, DELAY_MS = 0.01, 250
EVS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
EARLY, LATE = (0, 30, 60, 90), (180, 210, 240)
AMIN, AMAX, CAPS = (0.05, 0.15, 0.25), (0.55, 0.65, 0.80), (0, 1, 2)
CACHE = '/home/ubuntu/pm_ef3/ef10_rows.npz'
OUT = '/home/ubuntu/claude-work/repo/analysis/zurich/EF10_grid.csv'


def build():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True); return {k: z[k] for k in z.files}
    vo = outcomes()
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    by = collections.defaultdict(list)
    for ts, ep, side, p, ua, da in c.execute(
            'SELECT ts_ms,epoch,side,p,up_ask,dn_ask FROM decide_log WHERE p IS NOT NULL AND side IS NOT NULL '
            'AND up_ask IS NOT NULL AND dn_ask IS NOT NULL ORDER BY ts_ms'):
        if ep not in vo: continue
        by[ep].append((int(ts), side, float(p), float(ua), float(da)))
    EP, TS, OWN, PS, SEC, LAT, WIN, DAY = [], [], [], [], [], [], [], []
    for ep in sorted(by):
        rs = by[ep]
        ts_a = np.array([r[0] for r in rs]); ua = np.array([r[3] for r in rs]); da = np.array([r[4] for r in rs])
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'); out = vo[ep]
        for ts, side_l, p_l, u, d in rs:
            sec = ts // 1000 - ep
            if not (15 <= sec <= 240): continue
            j = int(np.searchsorted(ts_a, ts + DELAY_MS, 'left'))
            for sd_, own, arr in (('UP', u, ua), ('DOWN', d, da)):
                if not (0.01 < own < 0.99): continue
                lat = float(arr[j]) if j < len(rs) else np.nan
                EP.append(ep); TS.append(ts); OWN.append(own); SEC.append(sec)
                PS.append(p_l if sd_ == side_l else 1.0 - p_l)
                LAT.append(lat); WIN.append(1.0 if sd_ == out else 0.0); DAY.append(day)
    d = dict(ep=np.array(EP, np.int64), ts=np.array(TS, np.int64), own=np.array(OWN),
             ps=np.array(PS), sec=np.array(SEC, np.int16), lat=np.array(LAT),
             win=np.array(WIN), day=np.array(DAY))
    np.savez(CACHE, **d); return d


def segments(ep):
    """row index ranges per candle, rows already in (epoch, ts) order"""
    b = np.flatnonzero(np.r_[True, ep[1:] != ep[:-1]])
    return b, np.r_[b[1:], len(ep)]


def run_cell(mask, lat, cap_px, own, win, day, starts, ends, BIG, hc=0.0):
    idx = np.where(mask, np.arange(len(mask)), BIG)
    first = np.minimum.reduceat(idx, starts)
    first = first[first < BIG]
    if not len(first): return None
    q = np.where(lat[first] <= cap_px[first] + 1e-12, lat[first], np.nan)
    fl = np.isfinite(q)
    if not fl.any(): return None
    # hc is a cost haircut on the price PAID, not on the fill test: the order still fills where it filled,
    # you just pay a cent more for it.
    pnl = STAKE * per1(win[first][fl], np.minimum(q[fl] + hc, 0.99))
    cum = np.cumsum(pnl); mdd = float(np.max(np.maximum.accumulate(cum) - cum))
    dd = day[first][fl]
    byd = collections.defaultdict(float)
    for a, b_ in zip(dd, pnl): byd[a] += b_
    return dict(tot=float(cum[-1]), mdd=mdd, n=len(first), nf=int(fl.sum()),
                fill=float(fl.mean()), byd=dict(byd), pos=sum(1 for v in byd.values() if v > 0))


if __name__ == '__main__':
    D = build()
    ep, ts, own, ps, sec, lat, win, day = (D[k] for k in ('ep', 'ts', 'own', 'ps', 'sec', 'lat', 'win', 'day'))
    o = np.lexsort((ts, ep))
    ep, ts, own, ps, sec, lat, win, day = (x[o] for x in (ep, ts, own, ps, sec, lat, win, day))
    days = sorted(set(day.tolist())); nd = len(days)
    starts, ends = segments(ep)
    BIG = len(ep) + 10
    print(f'EF-10 raw parameter grid. rows {len(ep):,}  candles {len(starts):,}  days {days}')
    base_ok = ps >= 0.5
    evc = {c: ps / be(np.minimum(own + c * TICK, 0.99)) - 1.0 for c in CAPS}
    capx = {c: np.minimum(own + c * TICK, 0.99) for c in CAPS}

    # raw as it runs today: ev 0.25 at be(ask), no bounds, no band, fill cap +1 tick
    braw = base_ok & ((ps / be(own) - 1.0) >= 0.25)
    B = run_cell(braw, lat, capx[1], own, win, day, starts, ends, BIG)
    print(f'  RAW TODAY  $ {B["tot"]:+8.1f}  DD {B["mdd"]:6.1f}  {B["n"]/nd:6.1f}/day  '
          f'fill {100*B["fill"]:5.1f}%  days+ {B["pos"]}/{len(B["byd"])}')
    floor = B['n'] / nd

    rows = []
    for evb, e, l, amn, amx, c in itertools.product(EVS, EARLY, LATE, AMIN, AMAX, CAPS):
        m = base_ok & (sec >= e) & (sec <= l) & (own >= amn) & (own <= amx) & (evc[c] >= evb)
        r = run_cell(m, lat, capx[c], own, win, day, starts, ends, BIG)
        if r is None: continue
        r.update(ev=evb, e=e, l=l, amn=amn, amx=amx, cap=c, fpd=r['n'] / nd)
        rows.append(r)
    with open(OUT, 'w') as f:
        f.write('ev,early,late,ask_min,ask_max,cap_ticks,total,dd,fires_day,fill_pct,days_pos,days,fires,fills\n')
        for r in rows:
            f.write(f'{r["ev"]},{r["e"]},{r["l"]},{r["amn"]},{r["amx"]},{r["cap"]},{r["tot"]:.1f},'
                    f'{r["mdd"]:.1f},{r["fpd"]:.1f},{100*r["fill"]:.1f},{r["pos"]},{len(r["byd"])},'
                    f'{r["n"]},{r["nf"]}\n')
    tot = np.array([r['tot'] for r in rows])
    print(f'  {len(rows):,} cells scored -> {OUT}')
    print(f'  DISTRIBUTION of $: min {tot.min():+.1f}  p25 {np.percentile(tot,25):+.1f}  '
          f'median {np.median(tot):+.1f}  p75 {np.percentile(tot,75):+.1f}  max {tot.max():+.1f}')
    print(f'  cells beating RAW TODAY on $: {int((tot > B["tot"]).sum()):,} of {len(rows):,} '
          f'({100*(tot > B["tot"]).mean():.1f}%)')
    ok = [r for r in rows if r['fpd'] >= floor]
    print(f'  cells with fires/day >= raw ({floor:.1f}): {len(ok):,}; of those, beating raw on $: '
          f'{sum(1 for r in ok if r["tot"] > B["tot"]):,}')

    # ---- walk-forward: day D trades the cell that was best on days < D by ($ - DD), freq floor ----
    print(f'\n  WALK-FORWARD (day D uses the cell best on days < D by $ - DD, fires/day >= raw)')
    wf, chosen = [], []
    for i, dcur in enumerate(days):
        if i == 0: continue
        prev = set(days[:i])
        best, bk = None, None
        for r in rows:
            if r['fpd'] < floor: continue
            sub = sum(v for k, v in r['byd'].items() if k in prev)
            if sub == 0 and not any(k in prev for k in r['byd']): continue
            seq = [r['byd'].get(k, 0.0) for k in days[:i]]
            cum = np.cumsum(seq); mdd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
            sc = sub - mdd
            if best is None or sc > best: best, bk = sc, r
        if bk is None: continue
        wf.append(bk['byd'].get(dcur, 0.0))
        chosen.append((dcur, bk['ev'], bk['e'], bk['l'], bk['amn'], bk['amx'], bk['cap'], bk['byd'].get(dcur, 0.0)))
    for d_, ev_, e_, l_, mn_, mx_, c_, v in chosen:
        print(f'    {d_}: ev {ev_:.2f} sec {e_}-{l_} ask {mn_:.2f}-{mx_:.2f} cap +{c_}c  -> $ {v:+7.1f}')
    # +1c: re-score the SAME chosen cells and the baseline with a cent of cost
    wf1, b1 = [], []
    B1 = run_cell(braw, lat, capx[1], own, win, day, starts, ends, BIG, hc=0.01)
    for d_, ev_, e_, l_, mn_, mx_, c_, _v in chosen:
        m = base_ok & (sec >= e_) & (sec <= l_) & (own >= mn_) & (own <= mx_) & (evc[c_] >= ev_)
        r1 = run_cell(m, lat, capx[c_], own, win, day, starts, ends, BIG, hc=0.01)
        wf1.append(r1['byd'].get(d_, 0.0) if r1 else 0.0)
        b1.append(B1['byd'].get(d_, 0.0) if B1 else 0.0)
    if wf:
        cum = np.cumsum(wf); mdd = float(np.max(np.maximum.accumulate(cum) - cum))
        bd = [B['byd'].get(d_, 0.0) for d_, *_ in chosen]
        bc = np.cumsum(bd); bmdd = float(np.max(np.maximum.accumulate(bc) - bc))
        print(f'  WALK-FORWARD total $ {cum[-1]:+.1f}  DD {mdd:.1f}  days+ {sum(1 for v in wf if v>0)}/{len(wf)}')
        print(f'  RAW TODAY same days $ {bc[-1]:+.1f}  DD {bmdd:.1f}  days+ {sum(1 for v in bd if v>0)}/{len(bd)}')
        c1 = np.cumsum(wf1); m1 = float(np.max(np.maximum.accumulate(c1) - c1))
        d1 = np.cumsum(b1); n1 = float(np.max(np.maximum.accumulate(d1) - d1))
        print(f'  +1c  WALK-FORWARD $ {c1[-1]:+.1f}  DD {m1:.1f}  days+ {sum(1 for v in wf1 if v>0)}/{len(wf1)}'
              f'   |   RAW TODAY $ {d1[-1]:+.1f}  DD {n1:.1f}  days+ {sum(1 for v in b1 if v>0)}/{len(b1)}')
