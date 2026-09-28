#!/usr/bin/env python3
"""ARRIVAL-BASED fill for arm FAV (owner, 09-28: "be sure about fills at the time the order reaches
Polymarket"). READ-ONLY, nothing live.

The decision moment is not the moment the order can trade. London's measured round trip is ~245 ms and
the crypto taker hold has been 150 ms since 09-04, so the book that matters is ~400 ms after the
decision. V's rule, implemented literally:
    cap  = decision ask + 1 tick
    FILL only if the same-side ask at decision + LAG (the next decide_log pass at or after that
         instant, NEVER an earlier one) is <= cap, AND the size at that level covers our shares
    pay  that arrival ask, fee-exact

SHARES for the size gate are 10 / paid, V's literal words. Note this is STRICTER than reality: the
fee-exact share count is 10 / be(paid) and be(paid) > paid, so we require more size than we would
actually consume. Left deliberately strict - a fill gate should err toward not filling.

SIZE COVERAGE IS THE LIMIT HERE, and it is small. Polymarket ask sizes for the btc5 market exist only
in multi_market.books from 09-28 18:13 (the recorder started then): 67 candles, 5.5 h. So the price
condition is measured across the whole FAV backfill and the size condition only on that slice, reported
separately and marked INSUFFICIENT rather than blended into the headline. Sizes rarely bind at this
stake in any case - only 3.8% of btc5 book rows hold less than the ~14 shares $10 buys at 0.72.
"""
import sys, sqlite3, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
from ef2_model import per1, cost, be

LAGS = (250, 500, 1000)
BOOKS = '/home/ubuntu/pm_multi/multi_market.sqlite3'
STAKE = 10.0

bk = {}
try:
    c = sqlite3.connect(f'file:{BOOKS}?mode=ro', uri=True)
    for ts, ua, us, da, ds in c.execute(
            "SELECT ts, up_ask, up_ask_sz, dn_ask, dn_ask_sz FROM books WHERE market='btc5'"):
        bk[int(ts)] = (ua, us, da, ds)
except Exception as e:
    print('books unavailable:', e)
print(f'btc5 book/size rows: {len(bk):,}')

S.ALL52, S.STRICT = None, None
REF = S._ref_tape()
cand, vo, nk = S.load_candles()

rows_out = []
for ep in sorted(cand):
    if ep not in vo: continue
    rs = sorted(cand[ep], key=lambda r: r[0])
    ts_a = np.array([r[0] for r in rs])
    ua_a = np.array([r[3] for r in rs], dtype=float)
    da_a = np.array([r[4] for r in rs], dtype=float)
    v0 = S._vol_open(REF, ep)
    if v0 is None: continue
    built = S.build_rows(rs, ep, vo[ep], nk)
    fv = sorted((r for r in built if S.FAV_SEC[0] <= r['sec'] <= S.FAV_SEC[1]
                 and r['own'] > r['opp']
                 and S.FAV_BAND[0] <= r['own'] <= S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0 = fv[0]
    bucket = 'FAV' if v0 < S.FAV_CUT_LOW else ('FAV_mid' if v0 < S.FAV_CUT_MID else 'FAV_hi')
    cap = r0['own'] + S.TICK
    rec = dict(ep=ep, bucket=bucket, win=r0['win'], up=r0['up'], own=r0['own'], sec=r0['sec'])
    for lag in LAGS:
        j = int(np.searchsorted(ts_a, r0['ts'] + lag, side='left'))   # at or after arrival, never before
        paid = szok = None
        if j < len(rs):
            a = float(ua_a[j] if r0['up'] else da_a[j])
            if 0.01 < a < 0.99 and a <= cap + 1e-12:
                paid = a
                tsec = int(ts_a[j] // 1000)
                b = bk.get(tsec)
                if b is not None:
                    bask, bsz = (b[0], b[1]) if r0['up'] else (b[2], b[3])
                    if bask is not None and bsz is not None:
                        szok = bool(bask <= paid + 1e-12 and bsz >= STAKE / paid)
        rec[lag] = (paid, szok)
    rows_out.append(rec)

print(f'FAV decision rows: {len(rows_out)}  (candles with a qualifying favourite in 60-180 s)')
print()
hdr = 'arm       lag     fires  fill%   win% of fills    paid      $@10    per$1'
print(hdr); print('-' * len(hdr))
for arm in ('FAV', 'FAV_mid', 'FAV_hi'):
    sub = [r for r in rows_out if r['bucket'] == arm]
    allsub = rows_out if arm == 'FAV' else None
    for lag in LAGS:
        fl = [r for r in sub if r[lag][0] is not None]
        tot = sum(STAKE * per1(r['win'], r[lag][0]) for r in fl)
        wr = 100 * np.mean([r['win'] for r in fl]) if fl else 0
        pd = np.mean([r[lag][0] for r in fl]) if fl else 0
        print(f'{arm:9s} +{lag:<5d} {len(sub):5d} {100*len(fl)/max(len(sub),1):5.1f}%  {wr:5.1f}%        '
              f'{pd:.3f}  {tot:+8.1f}  {tot/(STAKE*max(len(sub),1)):+.3f}')
    print('-' * len(hdr))
# FAV_all = every favourite regardless of vol
for lag in LAGS:
    fl = [r for r in rows_out if r[lag][0] is not None]
    tot = sum(STAKE * per1(r['win'], r[lag][0]) for r in fl)
    wr = 100 * np.mean([r['win'] for r in fl]) if fl else 0
    pd = np.mean([r[lag][0] for r in fl]) if fl else 0
    print(f'{"FAV_all":9s} +{lag:<5d} {len(rows_out):5d} {100*len(fl)/max(len(rows_out),1):5.1f}%  {wr:5.1f}%        '
          f'{pd:.3f}  {tot:+8.1f}  {tot/(STAKE*max(len(rows_out),1)):+.3f}')

print()
print('SIZE GATE, only where btc5 ask sizes exist (09-28 18:13+). Marked INSUFFICIENT under 60 fires.')
print('arm       lag   fires_with_size  size_ok  would_be_rejected')
for arm in ('FAV', 'FAV_mid', 'FAV_hi'):
    for lag in (500,):
        sub = [r for r in rows_out if r['bucket'] == arm and r[lag][0] is not None and r[lag][1] is not None]
        ok = sum(1 for r in sub if r[lag][1])
        flag = '' if len(sub) >= 60 else '   <- INSUFFICIENT'
        print(f'{arm:9s} +{lag:<4d} {len(sub):10d}       {ok:5d}    {len(sub)-ok:5d}{flag}')
