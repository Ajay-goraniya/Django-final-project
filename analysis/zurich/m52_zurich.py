#!/usr/bin/env python3
"""M52 - the owner's LADDER rule on Zurich's own Polymarket 1 Hz bid+ask. READ-ONLY.

ladder() BELOW IS BYTE-IDENTICAL to analysis/v/maker2/m52_ladder.py (e438a57) - spliced in from
that file, not retyped. The S60/B60/B80 setup selection (including the floor-to-10c start level for
the second leg) is also copied from that script's run(). Only the candle dict, the session split and
the reporting are mine (no pandas on this box).

HIS RULE: levels 0.60/0.70/0.80/0.90. Buy a side at the ask when its ask >= the current level; stop
= level-0.10, sold at the bid; after a stop the next level is +0.10 and the ladder re-buys only when
the ask reaches it; max level 0.90, so at most 4 buys from 0.60. Stake x grow on each re-buy.
This CORRECTS M47/M49/M50B, where the mark stayed fixed and the same stop/re-buy pair could repeat.
Polymarket only: polybook + pm_multi btc5, venues.outcome + gamma labels, taker 0.07p(1-p) plus a
zero-fee column. No Predict.fun data is read.
"""
import math, sqlite3, collections
import datetime as dt
import numpy as np

SESS = [('ASIA', 0, 7), ('EU', 7, 13), ('US', 13, 20), ('LATE', 20, 24)]
fee = lambda x: 0.07 * x * (1 - x)

# ---------------- byte-identical from analysis/v/maker2/m52_ladder.py ----------------
def ladder(s,ask,bid,win,i0,L,fin,fout,pay,grow,cut=295):
    cash=0.0; staked=0.0; stake=1.0; n=0; pos=False; sh=0
    for j in range(i0,len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if L>0.905: break
            if k>=L-1e-9 and k<0.99:
                if n>0: stake*=grow
                sh=stake/k; cash-=stake+sh*fin(k); staked+=stake; pos=True; n+=1; stop=L-0.10
        elif b<=stop+1e-9:
            cash+=sh*(b-fout(b)); pos=False; L=round(L+0.10,2)
    if pos and win: cash+=sh*pay
    return cash,staked,n
# ---------------- end byte-identical ----------------

acc = collections.defaultdict(dict)
pb = sqlite3.connect('file:/home/ubuntu/m30/pb.sqlite3?mode=ro', uri=True)
for tms, ep, au, bu, ad, bd in pb.execute(
        "select ts_ms, epoch, ask_up, bid_up, ask_dn, bid_dn from pb "
        "where status='live websocket' order by ts_ms"):
    acc[int(ep)][int(tms) // 1000 - int(ep)] = (au, ad, bu, bd)
mm = sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro', uri=True)
for ts, ep, ua, ub, da, db_ in mm.execute(
        "select ts, epoch, up_ask, up_bid, dn_ask, dn_bid from books "
        "where market='btc5' order by ts"):
    acc[int(ep)][int(ts) - int(ep)] = (ua, da, ub, db_)
UP = {}
for ep, a in sqlite3.connect('file:/home/ubuntu/m29/venues.sqlite3?mode=ro', uri=True)\
        .execute('select epoch, actual from outcome where actual is not null'):
    UP[int(ep)] = (a == 'UP')
for ep, o in sqlite3.connect('file:/home/ubuntu/pm_ef3/gamma_zurich.sqlite3?mode=ro', uri=True)\
        .execute('select epoch, outcome from mkt where outcome is not null'):
    UP[int(ep)] = (o == 'UP')
CP = {}
f = lambda v: np.nan if v is None else float(v)
for ep, d in acc.items():
    if ep not in UP: continue
    s = sorted(x for x in d if 0 <= x <= 300)
    if len(s) < 40: continue
    CP[ep] = (np.array(s),
              np.array([f(d[x][0]) for x in s]), np.array([f(d[x][1]) for x in s]),
              np.array([f(d[x][2]) for x in s]), np.array([f(d[x][3]) for x in s]), UP[ep])
print(f'{len(CP)} Polymarket candles with a book and a venue label', flush=True)

def block(fin, fout, pay, setup, grow):
    # setup selection copied from m52_ladder.py run()
    r, st, days, hrs, nb, hitask = [], [], [], [], [], []
    for e, (s, au, ad, bu, bd, w) in CP.items():
        if setup == 'S60':
            a, sa, na = ladder(s, au, bu, w, 0, 0.60, fin, fout, pay, grow)
            b, sb, nbb = ladder(s, ad, bd, not w, 0, 0.60, fin, fout, pay, grow)
            if na + nbb == 0: continue
            hitask.append(np.nan)
        else:
            T = 0.60 if setup == 'B60' else 0.80
            hit = np.where(((au >= T) | (ad >= T)) & (s <= 280) & ~np.isnan(au) & ~np.isnan(ad))[0]
            if not len(hit): continue
            i = hit[0]
            if not (au[i] < 0.99 and ad[i] < 0.99): continue
            Lu = math.floor(au[i] * 10 + 1e-9) / 10; Ld = math.floor(ad[i] * 10 + 1e-9) / 10
            a, sa, na = ladder(s, au, bu, w, i, max(Lu, 0.1), fin, fout, pay, grow)
            b, sb, nbb = ladder(s, ad, bd, not w, i, max(Ld, 0.1), fin, fout, pay, grow)
            hitask.append(au[i] + ad[i])
        r.append(a + b); st.append(sa + sb); nb.append(max(na, nbb))
        t = dt.datetime.fromtimestamp(e, dt.UTC)
        days.append(t.strftime('%m-%d')); hrs.append(t.hour)
    return (np.array(r), np.array(st), days, np.array(hrs), np.array(nb), np.array(hitask))

def fmt(r, st, days, hrs, nb, hitask):
    n = len(r); h = n // 2
    gd = collections.defaultdict(float)
    for d, v in zip(days, r): gd[d] += v
    cum = np.cumsum(r)
    t_ = r.mean() / r.std() * math.sqrt(n) if r.std() > 0 else 0.0
    return (f'n {n} $/candle {r.mean():+.4f} per $ staked {r.sum()/st.sum():+.4f} t{t_:+6.2f} '
            f'halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} '
            f'green {sum(1 for x in gd.values() if x>0)}/{len(gd)} '
            f'win-candles {(r>0).mean():.0%} worst {r.min():+.2f} '
            f'max buys/side {nb.max()} (mean {nb.mean():.2f}) '
            f'maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}')

ROWS = (('S60', (1.10, 2.0, 1.0)), ('B60', (2.0, 1.0)), ('B80', (2.0, 1.0)))
L = ['M52 - THE OWNER\'S LADDER (60/70/80/90, stop 10 below, next level only after a stop).',
     'POLYMARKET. READ-ONLY. ' + f'{dt.datetime.now(dt.UTC):%F %T} UTC.',
     'ladder() spliced byte-identical from analysis/v/maker2/m52_ladder.py (e438a57); the S60/B60/B80',
     'setup selection is copied from that script\'s run(). Candle dict, session split and reporting',
     'are mine. venues.outcome + gamma labels; taker 0.07p(1-p) and a zero-fee column.',
     'This corrects M47/M49/M50B: there the mark never moved, so one stop/re-buy pair could repeat;',
     'here each stop advances the level by 10c and the ladder tops out at 0.90 (max 4 buys from 0.60).',
     '']
store = {}
for tag, fin, fout, pay in (('POLY fee', fee, fee, 1.0), ('POLY 0fee', lambda x: 0, lambda x: 0, 1.0)):
    for setup, grows in ROWS:
        for gr in grows:
            out = block(fin, fout, pay, setup, gr)
            store[(tag, setup, gr)] = out
            L.append(f'  {tag:9s} {setup} x{gr:.2f}: ' + fmt(*out))
    L.append('')
L.append('  BY SESSION ($/candle, n)')
L.append(f'  {"row":22s} ' + ' | '.join(f'{nm:>16s}' for nm, _, _ in SESS))
for tag in ('POLY fee', 'POLY 0fee'):
    for setup, grows in ROWS:
        for gr in grows:
            r, st, days, hrs, nb, hitask = store[(tag, setup, gr)]
            cells = []
            for nm, lo, hi in SESS:
                m = (hrs >= lo) & (hrs < hi)
                cells.append(f'{r[m].mean():+.4f} n{m.sum()}' if m.sum() else f'{"-":>16s}')
            L.append(f'  {tag:9s} {setup} x{gr:.2f}        ' + ' | '.join(f'{c:>16s}' for c in cells))
L.append('')
L.append('  PER DAY ($/candle), POLY fee')
dayset = sorted({d for d in store[('POLY fee', 'S60', 1.10)][2]})
L.append(f'  {"day":10s} ' + ' '.join(f'{d:>8s}' for d in dayset))
for setup, grows in ROWS:
    for gr in grows:
        r, st, days, hrs, nb, hitask = store[('POLY fee', setup, gr)]
        per = collections.defaultdict(list)
        for d, v in zip(days, r): per[d].append(v)
        L.append(f'  {setup} x{gr:.2f} ' + ' '.join(
            f'{np.mean(per[d]):+8.3f}' if d in per else f'{"-":>8s}' for d in dayset))
for setup in ('B60', 'B80'):
    _, _, _, _, _, ha = store[('POLY fee', setup, 1.0)]
    ha = ha[~np.isnan(ha)]
    L += ['', f'  {setup} THE ENTRY, before any rule: mean COMBINED ask at the trigger {ha.mean():.4f} '
          f'for a payout of exactly 1.00 (n {len(ha)})',
          f'  -> buy-both starts {1.0-ha.mean():+.4f} per candle on $2 = '
          f'{(1.0-ha.mean())/ha.mean():+.4f} per $ staked, guaranteed, before fees and before stops.']
L += ['', '  Stake schedule is 1, g, g^2, ... so the largest single stake on a side is g^(buys-1):',
      '  at max buys/side 4 that is 8 at x2.00 and 1.33 at x1.10; at 2 buys, 2 and 1.10.']
print('\n'.join(L))
