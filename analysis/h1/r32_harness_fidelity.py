"""R-32 (ask 3) -- does the replay harness reproduce the RUNNING lane's decisions?

V: "If the harness disagrees with the running lane, say so first - the EF numbers are worthless
until it agrees." So this is run before anything is read off the EF grid.

GROUND TRUTH is the Zurich live journals' `diagnostics` rows carrying a `lane` field: the real
MAIN/REVERSAL decisions the engine made, with side, sec and the two asks it saw. Compared against
`replay_lanes_1s.py`'s placements on the SAME candle epochs.

The comparison is limited by the venue tape, not by the journals: the journals hold 728 lane rows
(09-14 23:45 -> 09-17 12:15) but `venues.q` stops at 09-16 17:25, so only the rows inside that
window can be replayed at all. That split is reported before any agreement number, because a
fidelity rate computed on a silently truncated sample is worthless.
"""
import csv, json, os, sqlite3, sys, collections, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
JOURNALS = ('zurich_v1', 'zurich_2', 'zurich_3')


def journal_lanes():
    """Real lane decisions the engine actually made."""
    out = []
    for z in JOURNALS:
        p = os.path.join(D, z + '.sqlite3')
        if not os.path.exists(p):
            continue
        for ep, det in sqlite3.connect(p).execute(
                "select epoch,detail from diagnostics where detail like '%\"lane\"%'"):
            try:
                j = json.loads(det)
            except Exception:
                continue
            if not j.get('lane'):
                continue
            out.append(dict(src=z, ep=int(ep), lane=j['lane'], side=j.get('side'),
                            sec=j.get('sec'), au=j.get('ask_up'), ad=j.get('ask_dn')))
    return out


def replay_rows(path):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['kind'] not in ('MAIN', 'REVERSAL'):
                continue
            out.append(dict(ep=int(r['epoch']), lane=r['kind'], side=r['side'],
                            sec=int(r['sec']), ask=float(r['ask']),
                            win=int(r['win']) if r['win'] != '' else None))
    return out


def main(csv_path):
    J = journal_lanes()
    vmax = sqlite3.connect(os.path.join(D, 'venues.sqlite3')).execute(
        'select max(epoch) from q').fetchone()[0]
    inside = [r for r in J if r['ep'] <= vmax]
    outside = [r for r in J if r['ep'] > vmax]

    print('R-32  harness fidelity: replay vs the RUNNING lane')
    print('  journal lane rows total %d over %d candles, %s -> %s'
          % (len(J), len({r['ep'] for r in J}),
             dt.datetime.utcfromtimestamp(min(r['ep'] for r in J)),
             dt.datetime.utcfromtimestamp(max(r['ep'] for r in J))))
    print('  venue tape ends %s, so:' % dt.datetime.utcfromtimestamp(vmax))
    for lab, g in (('REPLAYABLE', inside), ('NOT replayable (no venue tape)', outside)):
        print('    %-32s %4d rows  (MAIN %d, REVERSAL %d)'
              % (lab, len(g), sum(1 for r in g if r['lane'] == 'MAIN'),
                 sum(1 for r in g if r['lane'] == 'REVERSAL')))

    R = replay_rows(csv_path)
    rep = collections.defaultdict(list)
    for r in R:
        rep[(r['ep'], r['lane'])].append(r)
    jr = collections.defaultdict(list)
    for r in inside:
        jr[(r['ep'], r['lane'])].append(r)

    print('\n  PLACEMENT AGREEMENT on candles where BOTH placed the same lane')
    print('  %-9s %7s %7s %9s %12s %12s %11s' % (
        'lane', 'journal', 'replay', 'both', 'side agree', 'med |dsec|', 'replay only'))
    for lane in ('MAIN', 'REVERSAL'):
        jk = {k for k in jr if k[1] == lane}
        rk = {k for k in rep if k[1] == lane}
        both = jk & rk
        agree, dsec = 0, []
        for k in both:
            a, b = jr[k][0], rep[k][0]
            if a['side'] == b['side']:
                agree += 1
            if a['sec'] is not None:
                dsec.append(abs(int(a['sec']) - b['sec']))
        n = len(both)
        flag = '' if n >= MIN_CELL else '   INSUFFICIENT (<%d) - not read' % MIN_CELL
        print('  %-9s %7d %7d %9d %11s %12s %11d%s' % (
            lane, len(jk), len(rk), n,
            ('%.1f%%' % (100.0 * agree / n)) if n else '-',
            ('%.0f' % np.median(dsec)) if dsec else '-',
            len(rk - jk), flag))

    print('\n  THE COVERAGE QUESTION: does the replay fire where the engine fired?')
    for lane in ('MAIN', 'REVERSAL'):
        jk = {k for k in jr if k[1] == lane}
        rk = {k for k in rep if k[1] == lane}
        if not jk:
            print('  %-9s journal placed none inside the tape' % lane)
            continue
        print('  %-9s engine placed %d, replay reproduced %d (%.1f%%), replay invented %d'
              % (lane, len(jk), len(jk & rk), 100.0 * len(jk & rk) / len(jk), len(rk - jk)))


if __name__ == '__main__':
    main(sys.argv[1])
