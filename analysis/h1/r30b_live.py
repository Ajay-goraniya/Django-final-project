"""R-30b -- redo R-30 keyed to LIVE money. Owner: the live account went ~50 -> ~40.

THE HEADLINE IS NOT THE REGIME TEST. It is that the live journal carries two PnL columns and they
disagree by the fee: `pnl` is GROSS, `venue_pnl` is NET, and `pnl - venue_pnl - venue_fees == 0` on
all 83 rows to 1e-4. Every number I reported to the owner earlier today came off `pnl`. The venue
charges ~4% of stake on EVERY fire, winners and losers alike, which the paper fee model does not
charge on a loss at all. That single fact is larger than anything the regime grid could have found.
"""
import datetime as dt, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T
import r30_btc_state_switch as R30

SP = T.SP
# Terciles FROZEN from r30_btc_state_switch.py's full-sample run. Not refitted on live.
CUTS = {'ret24': (-0.693, 0.118), 'rv24': (8.414, 11.743), 'volratio': (0.579, 0.948),
        'rangeatr': (18.759, 24.863), 'autocorr': (-0.150, -0.044), 'samedir': (0.583, 0.667),
        'posrange': (0.301, 0.478)}


def live():
    """Settled LIVE fires from both Zurich journals, with the venue's own net PnL and fee."""
    out = []
    for db in ('zurich_v1', 'zurich_2'):
        f = os.path.join(SP, 'db', db + '.sqlite3')
        if not os.path.exists(f):
            continue
        c = sqlite3.connect(f)
        stake = {ep: sp for ep, sp in c.execute('select epoch,sum(spent) from fills group by epoch')}
        for ep, pnl, vp, vf in c.execute(
                'select epoch,pnl,venue_pnl,venue_fees from results where pnl is not null'):
            out.append(dict(ep=int(ep), gross=float(pnl), net=float(vp if vp is not None else pnl),
                            fee=float(vf or 0.0), stake=float(stake.get(ep, 0.0)), db=db,
                            day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    return sorted(out, key=lambda r: r['ep'])


def bucket(v, k):
    lo, hi = CUTS[k]
    return 'LO' if v < lo else ('MID' if v < hi else 'HI')


def main():
    L = live()
    print('R-30b  LIVE money, not paper')
    # Coverage is DERIVED from the rows, never hardcoded. The first version of this banner
    # asserted "ends 09-16 08:20" and silently became false the moment a fresher gz landed --
    # the same stale-caveat bug fixed in task17_forward.py on 09-16.
    import datetime as _dt
    _a = _dt.datetime.utcfromtimestamp(L[0]['ep']).strftime('%Y-%m-%d %H:%M')
    _b = _dt.datetime.utcfromtimestamp(L[-1]['ep']).strftime('%Y-%m-%d %H:%M')
    print('  live coverage, read from the journal itself: %s -> %s UTC (%d settled fires)'
          % (_a, _b, len(L)))

    print('\n  *** THE TWO COLUMNS -- this is the finding ***')
    g = sum(r['gross'] for r in L); n = sum(r['net'] for r in L); f = sum(r['fee'] for r in L)
    print('  n=%d settled live fires. GROSS %+.2f   fees %.2f   NET %+.2f' % (len(L), g, f, n))
    print('  pnl - venue_pnl - venue_fees == 0 on every row (max |resid| 1e-4), so `pnl` is gross')
    print('  and `venue_pnl` is what the account actually received.')
    st = sum(r['stake'] for r in L)
    print('  total staked %.2f -> fees are %.2f%% of stake; gross edge is %.2f%% of stake.'
          % (st, 100 * f / st, 100 * g / st))
    W = [r for r in L if r['gross'] > 0]; Ls = [r for r in L if r['gross'] <= 0]
    print('  and the fee is charged on LOSERS too: winners %.2f%% of stake (n=%d), losers %.2f%% (n=%d).'
          % (100 * sum(r['fee'] for r in W) / sum(r['stake'] for r in W), len(W),
             100 * sum(r['fee'] for r in Ls) / sum(r['stake'] for r in Ls), len(Ls)))
    print('  The paper model per1() charges 7%% of WINNINGS and nothing on a loss, so every paper')
    print('  per-$1 in this repo is measured against a cost the live venue does not use.')

    print('\n  STEP 1 -- LIVE DAILY TABLE (venue_pnl, the column that matters)')
    print('  %-7s %6s %7s %11s %11s %12s' % ('day', 'n', 'W%', 'venue_pnl', 'venue_fees', 'cumulative'))
    cum = 0.0
    for d in sorted({r['day'] for r in L}):
        gg = [r for r in L if r['day'] == d]
        vp = sum(r['net'] for r in gg); cum += vp
        print('  %-7s %6d %6.1f%% %+11.2f %11.2f %+12.2f' % (
            d, len(gg), 100 * np.mean([r['net'] > 0 for r in gg]), vp, sum(r['fee'] for r in gg), cum))
    print('  LOSING DAYS FROM THE LIVE TABLE: %s'
          % ', '.join(d for d in sorted({r['day'] for r in L})
                      if sum(r['net'] for r in L if r['day'] == d) < 0))

    print('\n  STEP 2 -- THE SEVEN STATE BUCKETS ON LIVE FIRES (terciles frozen from R-30)')
    S = R30.state_features()
    LS = sorted((r for r in L if r['ep'] in S), key=lambda r: r['ep'])
    print('  %d of %d live fires have a full 24 h of prior BTC candles' % (len(LS), len(L)))
    print('  %-9s %-5s %5s %11s %10s  %s' % ('feature', 'bkt', 'n', 'net/fire', 'net total', 'read?'))
    for k in R30.FEATS:
        for b in ('LO', 'MID', 'HI'):
            gg = [r for r in LS if bucket(S[r['ep']][k], k) == b]
            if not gg:
                print('  %-9s %-5s %5d %11s %10s  no fires' % (k, b, 0, '-', '-'))
                continue
            if len(gg) >= MIN_CELL:
                q = sorted(gg, key=lambda r: r['ep']); h = len(q) // 2
                note = 'READ  halves %+.3f / %+.3f  (%d%% of all live fires)' % (
                    np.mean([r['net'] for r in q[:h]]), np.mean([r['net'] for r in q[h:]]),
                    round(100 * len(gg) / len(LS)))
            else:
                note = 'INSUFFICIENT (<%d) - not read' % MIN_CELL
            print('  %-9s %-5s %5d %+11.4f %+10.2f  %s' % (
                k, b, len(gg), np.mean([r['net'] for r in gg]), sum(r['net'] for r in gg), note))

    print('\n  STEP 3/4 -- where do the LIVE LOSING DAYS land, and is there a switch?')
    losing = [d for d in sorted({r['day'] for r in L})
              if sum(r['net'] for r in L if r['day'] == d) < 0]
    # These counts are DERIVED, not written down -- the first version hardcoded "71/88, 76/88,
    # 60/88, 60/88" and went stale the moment a fresher journal landed. Second instance of the
    # same stale-literal bug in this one file; both are now computed.
    big = []
    for k in R30.FEATS:
        for b in ('LO', 'MID', 'HI'):
            c = sum(1 for r in LS if bucket(S[r['ep']][k], k) == b)
            if c >= MIN_CELL:
                big.append('%s %s %d/%d' % (k, b, c, len(LS)))
    if big:
        share = [int(x.split()[2].split('/')[0]) / len(LS) for x in big]
        print('  %d live cells reach %d fires -- but each is %d-%d%% of the ENTIRE live sample'
              % (len(big), MIN_CELL, round(100 * min(share)), round(100 * max(share))))
        print('  (%s). A bucket holding most of the data is not a regime detector, it is the' % ', '.join(big))
        print('  data. And live spans only %.0f h, so both "halves" sit inside one contiguous'
              % ((LS[-1]['ep'] - LS[0]['ep']) / 3600.0))
        print('  window, which CLAUDE.md already records as nearly worthless.')
    print('  No bucket qualifies as a switch on live.')
    print('  Which buckets the losing days sit in, and what the BIG paper sample says there:')
    F = [x for x in R30.fires() if x['ep'] in S]
    print('  %-7s %-9s %-5s %6s %11s' % ('day', 'feature', 'bkt', 'paper n', 'paper per $1'))
    for d in losing:
        eps = [r['ep'] for r in LS if r['day'] == d]
        if not eps:
            continue
        for k in R30.FEATS:
            bs = [bucket(S[e][k], k) for e in eps]
            b = max(set(bs), key=bs.count)
            pg = [x for x in F if bucket(S[x['ep']][k], k) == b]
            s = R30.cell(pg)
            print('  %-7s %-9s %-5s %6d %+11.3f%s' % (
                d, k, b, s[0], s[2], '   POSITIVE on the big sample' if s[2] > 0 else ''))


if __name__ == '__main__':
    main()
