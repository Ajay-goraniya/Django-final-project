#!/usr/bin/env python3
"""NC-16 / EF_CHAINLINK_DIV - a second box's read of London's number. READ-ONLY. Master OFF, nothing live.

London's candidate: div = (Chainlink ref - Binance spot)/Binance in bps; when div <= -3 at sec 45, buy DOWN at
the ask. London reports +0.24/$1 on 167 tape candles, beating a cheapness-matched null at -0.115, 5 of 6 days
positive - but a rolling version dies, there is no mechanism, and London's 10 real fills in it lost -0.30.

Zurich's independent data: the engine's own 1 Hz tape (tape1s) carries ref_px (the venue's RTDS
crypto_prices_chainlink topic, poly_feeds.py:90-94), spot_px (Binance), up_ask and dn_ask in the SAME row, and
the hourly research-archive export has been copying all four since 09-22 19:30. So the 1 Hz div log V asked
for in point (1) already exists and is already durable - nothing new had to be built for it.

Labels are the venue's own resolution (gamma outcomePrices). Buy-at-the-ask, matching London's construction so
the two numbers are comparable; a 1 s-later fill variant is reported beside it as the fill-risk check, since a
1 Hz tape cannot run ef_persist's 250 ms simulator.

The thing this script is really testing is whether the rule is a SIGNAL or a LEVEL. Part 5 of EF_FIRE_TIME
measured the divergence as a drifting offset - negative on more than 90% of seconds, mean moving from -0.25 bps
over the first 20k seconds to -2.21 bps across the full span - so a FIXED -3 threshold fires at a rate that
depends on where the offset happens to be sitting. Every table below is therefore reported three ways:
fixed -3, de-meaned against the past-only 600 s median, and per day with the fire rate exposed.
"""
import sys, sqlite3, math, random, collections, statistics as st, datetime as dt, numpy as np

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
SEC, THR, RATE = 45, 3.0, 0.07
cost = lambda q: 1 + RATE * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)
f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%m-%d %H:%M')


def outcomes():
    out = {}
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.update({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: pass
    return out


def tape():
    rows = {}
    for src in (ARCH, LIVE):
        try:
            c = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
            for ts, s, r, ua, da in c.execute(
                    'SELECT ts,spot_px,ref_px,up_ask,dn_ask FROM tape1s '
                    'WHERE spot_px IS NOT NULL AND ref_px IS NOT NULL'):
                rows[int(ts)] = (float(s), float(r), ua, da)
        except Exception as e: print(f'  (tape source {src}: {e})')
    return rows


def W(sel):
    if not sel: return float('nan')
    return sum(per1(w, q) * cost(q) for w, q in sel) / sum(cost(q) for w, q in sel)


def halves(sel):
    h = len(sel) // 2
    return W(sel[:h]), W(sel[h:])


def perm_opp(ent, draws=500, seed=23):
    """Sign flip priced at the OPPOSITE side's real ask at the same second - V's control."""
    if not ent: return float('nan')
    real = W([(e['win'], e['q']) for e in ent])
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        s = []
        for e in ent:
            if rng.random() < 0.5:
                if e['opp'] is None or not (0.01 < e['opp'] < 0.99): continue
                s.append((1 - e['win'], e['opp']))
            else: s.append((e['win'], e['q']))
        if s: sims.append(W(s))
    if not sims: return float('nan')
    return sum(1 for x in sims if x >= real) / len(sims)


if __name__ == '__main__':
    vo = outcomes(); tp = tape()
    ts_all = sorted(tp)
    print(f'tape rows with BOTH feeds {len(tp)}, {f(ts_all[0])} -> {f(ts_all[-1])} '
          f'= {(ts_all[-1]-ts_all[0])/3600:.1f} h; gamma-graded 5m candles {len(vo)}')

    dv = {t: (tp[t][1] - tp[t][0]) / tp[t][0] * 1e4 for t in ts_all}
    win_ = collections.deque(); divz = {}
    for t in ts_all:                                     # past-only rolling median, 600 s
        while win_ and win_[0][0] < t - 600: win_.popleft()
        divz[t] = dv[t] - (np.median([v for _, v in win_]) if len(win_) >= 60 else np.nan)
        win_.append((t, dv[t]))

    rows = []
    for ep in sorted({t // 300 * 300 for t in ts_all}):
        t = ep + SEC
        if t not in tp or ep not in vo: continue
        s, r, ua, da = tp[t]
        if ua is None or da is None: continue
        if not (0.01 < ua < 0.99 and 0.01 < da < 0.99): continue
        nxt = tp.get(t + 1)
        rows.append(dict(ep=ep, t=t, div=dv[t], divz=divz.get(t, float('nan')), ua=ua, da=da,
                         out=vo[ep], day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'),
                         ua1=(nxt[2] if nxt else None), da1=(nxt[3] if nxt else None)))
    print(f'scannable candles at sec {SEC} with both feeds, both asks and a venue outcome: {len(rows)}')
    d = np.array([r['div'] for r in rows])
    print(f'  div at sec {SEC}: mean {d.mean():+.2f}  p10 {np.percentile(d,10):+.2f}  p50 {np.percentile(d,50):+.2f}  '
          f'p90 {np.percentile(d,90):+.2f}  sd {d.std():.2f}   |   frac <= -3: {100*np.mean(d<=-THR):.1f}%,  '
          f'frac >= +3: {100*np.mean(d>=THR):.1f}%')

    def arm(sel, side_key):
        ent = []
        for r in sel:
            side = 'DOWN' if side_key == 'DOWN' else 'UP'
            q = r['da'] if side == 'DOWN' else r['ua']
            o = r['ua'] if side == 'DOWN' else r['da']
            ent.append(dict(win=1 if r['out'] == side else 0, q=q, opp=o, r=r, day=r['day'], ep=r['ep'],
                            q1=(r['da1'] if side == 'DOWN' else r['ua1'])))
        return ent

    def line(lab, ent):
        if not ent:
            print(f'  {lab:34s}{0:6d}      -       -       -       -      -'); return
        sel = [(e['win'], e['q']) for e in ent]
        h1, h2 = halves(sel)
        f1 = [(e['win'], e['q1']) for e in ent if e['q1'] is not None and 0.01 < e['q1'] < 0.99]
        print(f'  {lab:34s}{len(ent):6d}{100*np.mean([e["win"] for e in ent]):7.1f}%{W(sel):+9.3f}'
              f'{(h1 if h1==h1 else 0):+8.3f}{(h2 if h2==h2 else 0):+8.3f}{perm_opp(ent):7.3f}'
              f'{np.mean([e["q"] for e in ent]):7.3f}{(W(f1) if f1 else float("nan")):+9.3f}'
              f'{len({e["day"] for e in ent}):5d}' + ('  *n<60' if len(ent) < 60 else ''))

    HDR = (f'  {"arm":34s}{"n":>6}{"win%":>7}{"per$1":>9}{"H1":>8}{"H2":>8}{"permP":>7}{"ask":>7}'
           f'{"per$1@+1s":>9}{"days":>5}')
    print(f'\n{"="*116}\n1. LONDON\'S CELL AS SPECIFIED - fixed threshold at sec {SEC}\n{"="*116}')
    print(HDR)
    lo = [r for r in rows if r['div'] <= -THR]
    hi = [r for r in rows if r['div'] >= THR]
    line(f'div <= -{THR:.0f}  -> buy DOWN', arm(lo, 'DOWN'))
    line(f'div >= +{THR:.0f}  -> buy UP   (mirror)', arm(hi, 'UP'))
    line('ALL candles -> buy DOWN (null)', arm(rows, 'DOWN'))
    line('ALL candles -> buy UP   (null)', arm(rows, 'UP'))

    print(f'\n  CHEAPNESS-MATCHED NULL - London\'s own control. The fired set buys DOWN at a mean ask of '
          f'{np.mean([r["da"] for r in lo]):.3f} if it fires at all;\n  the null buys DOWN on every NON-firing '
          f'candle whose DOWN ask sits in the same range.')
    if lo:
        q10, q90 = np.percentile([r['da'] for r in lo], [10, 90])
        nul = [r for r in rows if r['div'] > -THR and q10 <= r['da'] <= q90]
        print(HDR)
        line(f'null: ask in [{q10:.2f},{q90:.2f}], no signal', arm(nul, 'DOWN'))

    print(f'\n{"="*116}\n2. THE SAME RULE ON THE DE-MEANED DIVERGENCE (past-only 600 s median)\n{"="*116}')
    print(HDR)
    zl = [r for r in rows if r['divz'] == r['divz'] and r['divz'] <= -THR]
    zh = [r for r in rows if r['divz'] == r['divz'] and r['divz'] >= THR]
    line(f'div_z <= -{THR:.0f} -> buy DOWN', arm(zl, 'DOWN'))
    line(f'div_z >= +{THR:.0f} -> buy UP', arm(zh, 'UP'))

    print(f'\n{"="*116}\n3. PER DAY - the fire rate is the tell\n{"="*116}')
    print(f'  {"day":8s}{"candles":>9}{"mean div":>10}{"fires <=-3":>12}{"fire rate":>11}{"per$1":>9}'
          f'{"win%":>7}{"fires_z":>9}{"per$1_z":>9}')
    for dy in sorted({r['day'] for r in rows}):
        dd = [r for r in rows if r['day'] == dy]
        fl = [r for r in dd if r['div'] <= -THR]
        fz = [r for r in dd if r['divz'] == r['divz'] and r['divz'] <= -THR]
        e1 = arm(fl, 'DOWN'); e2 = arm(fz, 'DOWN')
        print(f'  {dy:8s}{len(dd):9d}{np.mean([r["div"] for r in dd]):+10.2f}{len(fl):12d}'
              f'{100*len(fl)/len(dd):10.1f}%'
              f'{(W([(e["win"],e["q"]) for e in e1]) if e1 else float("nan")):+9.3f}'
              f'{(100*np.mean([e["win"] for e in e1]) if e1 else float("nan")):6.1f}%'
              f'{len(fz):9d}{(W([(e["win"],e["q"]) for e in e2]) if e2 else float("nan")):+9.3f}')
    print('\n  If the fire count tracks the day\'s mean divergence rather than anything about the market, the'
          '\n  rule is selecting a BASIS REGIME and not a signal - which is what "the rolling version dies" means.')

    print(f'\n{"="*116}\n4. SWEEPS - a real effect should strengthen as the threshold tightens, and should not '
          f'live at one second only\n{"="*116}')
    print(f'  threshold sweep on div (buy DOWN):')
    print(f'    {"thr":>6}{"n":>7}{"win%":>8}{"per$1":>9}{"ask":>7}')
    for thr in (2.0, 2.5, 3.0, 3.5, 4.0):
        e = arm([r for r in rows if r['div'] <= -thr], 'DOWN')
        print(f'    {-thr:>6.1f}{len(e):7d}'
              f'{(100*np.mean([x["win"] for x in e]) if e else float("nan")):7.1f}%'
              f'{(W([(x["win"],x["q"]) for x in e]) if e else float("nan")):+9.3f}'
              f'{(np.mean([x["q"] for x in e]) if e else float("nan")):7.3f}'
              + ('  *n<60' if len(e) < 60 else ''))
    print(f'\n  second sweep at div <= -{THR:.0f} (is sec 45 special, or is any second the same?):')
    print(f'    {"sec":>6}{"n":>7}{"win%":>8}{"per$1":>9}{"ask":>7}')
    for S2 in (15, 30, 45, 60, 90, 120, 180, 240):
        e = []
        for ep in sorted({t // 300 * 300 for t in ts_all}):
            t = ep + S2
            if t not in tp or ep not in vo: continue
            sp_, rp_, ua_, da_ = tp[t]
            if ua_ is None or da_ is None or not (0.01 < ua_ < 0.99 and 0.01 < da_ < 0.99): continue
            if (rp_ - sp_) / sp_ * 1e4 > -THR: continue
            e.append(dict(win=1 if vo[ep] == 'DOWN' else 0, q=da_, opp=ua_,
                          day=dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'), ep=ep))
        print(f'    {S2:>6}{len(e):7d}'
              f'{(100*np.mean([x["win"] for x in e]) if e else float("nan")):7.1f}%'
              f'{(W([(x["win"],x["q"]) for x in e]) if e else float("nan")):+9.3f}'
              f'{(np.mean([x["q"] for x in e]) if e else float("nan")):7.3f}'
              + ('  *n<60' if len(e) < 60 else ''))
