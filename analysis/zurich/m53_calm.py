#!/usr/bin/env python3
"""M53 split by the FROZEN FAV calm definition (owner request 10-06 13:4x). READ-ONLY.
Calm comes from ef3_shadow's OWN _vol_bn - no new threshold, no tuning, nothing re-implemented."""
import sys, sqlite3, math, io, contextlib, collections, statistics as st, datetime as dt
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
with contextlib.redirect_stdout(io.StringIO()):
    import ef3_shadow as S
    S.ALL52, S.STRICT = None, None
    BN = S._bn_1s()
CUT = S.FAV_CUT_LOW
STAKE, FEE = 5.0, 0.07
be = lambda a: a*(1+FEE*(1-a))
def calm_of(ep):
    v = S._vol_bn(BN, ep)
    return (None if v is None else (v < CUT)), v
def report(tag, rows):
    """rows: list of (ep, pnl). Returns nothing; prints calm / not-calm side by side."""
    buckets = {True: [], False: [], None: []}
    for ep, p in rows:
        c, _ = calm_of(ep)
        buckets[c].append((ep, p))
    out = []
    for key, nm in ((True, 'CALM (vol<%.3f)' % CUT), (False, 'NOT-CALM'), (None, 'no-vol (excluded)')):
        b = buckets[key]
        if key is None:
            if b: out.append(f'    {nm:22s} n {len(b):4d}  (no Binance 1 s vol - frozen rule gives NO fire)')
            continue
        if not b: out.append(f'    {nm:22s} n    0'); continue
        v = [p for _e, p in b]
        w = sum(1 for p in v if p > 0); l = len(v)-w
        per = sum(v)/(STAKE*len(v))
        t = (st.mean(v)/st.stdev(v)*math.sqrt(len(v))) if len(v) > 1 and st.stdev(v) > 0 else 0.0
        g = collections.defaultdict(float)
        for e, p in b: g[dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d')] += p
        gd = sum(1 for x in g.values() if x > 0)
        flag = '  INSUFFICIENT (n<60)' if len(v) < 60 else ''
        out.append(f'    {nm:22s} n {len(v):4d}  {w}W-{l}L  ${sum(v):+8.2f}  per $1 {per:+.4f}  '
                   f't {t:+5.2f}  green {gd}/{len(g)}{flag}')
    print(f'  {tag}')
    for o in out: print(o)

SW = 1791257400
m53 = sqlite3.connect('file:/home/ubuntu/m53/m53.sqlite3?mode=ro', uri=True)
print(f'FROZEN CALM DEFINITION: calm == Binance 1 s log-return std over [open-300, open) x1e4 < '
      f'{CUT} (ef3_shadow FAV_CUT_LOW), needing >=240 of 300 seconds; fewer => NO fire, never a fallback.')
print()
print('(1) FORWARD M53, candles since 2026-10-06 03:30Z')
for col, lab in ((('fill3_unc','pnl3_unc'), 'PRIMARY uncapped'), (('fill3','pnl3'), '0.80-capped secondary')):
    rows = [(e, p) for e, p in m53.execute(
        f'select epoch,{col[1]} from dec where epoch>=? and src=? and {col[0]}=1 and win is not null',
        (SW, 'clob_ws'))]
    report(f'{lab}: settled {len(rows)}', rows)
print()
print('(2) RETROSPECTIVE 09-29..10-05, same rule - ** LOOK-AHEAD-BIASED data-api version **')
print('    (its prints are the data-api tape, whose timestamps run a median +3.0 s behind the ws')
print('     match time, so it may select a later, better-informed print than any live arm can see)')
sh = sqlite3.connect('file:/home/ubuntu/pm_ef3/ef3_shadow.sqlite3?mode=ro', uri=True)
mm = sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro', uri=True)
bk = collections.defaultdict(dict)
for ts, ep, ua, da in mm.execute("select ts,epoch,up_ask,dn_ask from books where market='btc5'"):
    bk[int(ep)][int(ts)-int(ep)] = (ua, da)
retro = []
for ep, up, ask, sec, win in sh.execute("select epoch,up,ask,sec,win from fires where arm='PFAV_taker' "
                                        "and fill is not null and epoch<? order by epoch", (SW,)):
    d = bk.get(int(ep))
    if not d: continue
    v = d.get(int(sec)+3)
    if not v: continue
    a = v[0] if up else v[1]
    if a is None: continue
    a = float(a)
    if a >= 0.99: continue
    retro.append((int(ep), STAKE*(1.0/be(a)-1.0) if win else -STAKE))
report(f'retrospective +3s: n {len(retro)}', retro)
print()
print('(3) RETROSPECTIVE-ON-FORWARD-CANDLES (the honest comparison from M53_DIAG_1006)')
tp = sqlite3.connect('file:/home/ubuntu/pm_ef3/tape_btc5.sqlite3?mode=ro', uri=True)
UP = {}
for ep, a in sqlite3.connect('file:/home/ubuntu/m29/venues.sqlite3?mode=ro', uri=True)\
        .execute('select epoch,actual from outcome where actual is not null'): UP[int(ep)] = (a == 'UP')
for ep, o in sqlite3.connect('file:/home/ubuntu/pm_ef3/gamma_zurich.sqlite3?mode=ro', uri=True)\
        .execute("select epoch,outcome from mkt where outcome is not null and asset='btc'"): UP[int(ep)] = (o == 'UP')
LAG, S0, S1, LO, HI = 2.2, 60, 180, 0.60, 0.80
rof = []
for (ep,) in tp.execute('select distinct epoch from tape where epoch>=?', (SW,)):
    mk = mm.execute("select token_up,token_dn from markets where market='btc5' and epoch=?", (ep,)).fetchone()
    if not mk or ep not in UP: continue
    tu, td = mk; cand = []
    for ts, asset, price in tp.execute("select ts,asset,price from tape where epoch=? and is_taker=1 "
                                       "and side='BUY' order by ts", (ep,)):
        s = (ts-LAG)-ep
        if not (S0 <= s <= S1): continue
        p = float(price)
        if not (LO <= p <= HI): continue
        sd = 'UP' if asset == tu else ('DOWN' if asset == td else None)
        if sd is None: continue
        cand.append((s, ts, p, sd))
    if not cand: continue
    s, ts, p, sd = sorted(cand)[0]
    win = 1 if ((sd == 'UP') == UP[ep]) else 0
    d = bk.get(int(ep)); a = None
    if d:
        v = d.get(int(s)+3)
        if v: a = v[0] if sd == 'UP' else v[1]
    if a is None or float(a) >= 0.99: continue
    a = float(a)
    rof.append((int(ep), STAKE*(1.0/be(a)-1.0) if win else -STAKE))
report(f'retro method on forward candles: n {len(rof)}', rof)
