"""Verify a claim relayed from a third session: when REVERSAL opposes EF on the SAME candle,
REVERSAL wins alone but the COMBINED position is net negative.

That session could not push (no write access), so its analysis was stranded and unverified.
This re-derives the claim from the snapshots, per source (twins are different configurations of
the same engine over overlapping candles, so pooling them would double-count).

All PnL normalised to $1 per fire - the twins stake $10 and Tokyo stakes $1-$2, and a units mismatch
already caused one false alarm on 09-10.
"""
import sqlite3, json, numpy as np

DBD = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
LB = '/home/user/Django-final-project/learner/live_backup'


def from_trades(db):
    """(candle, kind) -> per-$1 pnl, from a twin's trades table (filled/shadow-executable rows)."""
    c = sqlite3.connect(f'{DBD}/{db}')
    out = {}
    for cid, kind, d, pnl, stake, corr in c.execute(
            'select candle_id, kind, direction, pnl, stake, correct from trades '
            'where pnl is not null and stake is not null and stake > 0'):
        out.setdefault(cid, {})[kind] = (d, pnl / stake, bool(corr))
    return out


def from_tokyo():
    out = {}
    for r in json.load(open(f'{LB}/tokyo_orders.json')):
        if r.get('filled') and r.get('pnl') is not None and r.get('stake'):
            out.setdefault(r['candle_id'], {})[r['kind']] = (
                r['direction'], r['pnl'] / r['stake'], bool(r.get('correct')))
    return out


def report(name, src):
    both = {c: v for c, v in src.items() if 'EF' in v and 'REVERSAL' in v}
    if not both:
        print('-- %-22s no candle with both EF and REVERSAL' % name); return
    opp = {c: v for c, v in both.items() if v['EF'][0] != v['REVERSAL'][0]}
    agr = {c: v for c, v in both.items() if v['EF'][0] == v['REVERSAL'][0]}
    print('-- %s: %d candles with BOTH lanes (%d opposing, %d agreeing)'
          % (name, len(both), len(opp), len(agr)))
    for lbl, grp in (('OPPOSING', opp), ('AGREEING', agr)):
        if not grp:
            continue
        ef = np.array([v['EF'][1] for v in grp.values()])
        rv = np.array([v['REVERSAL'][1] for v in grp.values()])
        comb = ef + rv
        tag = '' if len(grp) >= 60 else '   << n<60, INSUFFICIENT'
        print('   %-9s n=%3d | EF %+7.2f (%+.3f/fire, %2.0f%% hit) | REV %+7.2f (%+.3f/fire, %2.0f%% hit) | COMBINED %+7.2f (%+.3f/fire)%s'
              % (lbl, len(grp), ef.sum(), ef.mean(), 100 * np.mean([v['EF'][2] for v in grp.values()]),
                 rv.sum(), rv.mean(), 100 * np.mean([v['REVERSAL'][2] for v in grp.values()]),
                 comb.sum(), comb.mean(), tag))


if __name__ == '__main__':
    print('Claim under test: REVERSAL opposing EF on the same candle wins alone,')
    print('but the combined position is net NEGATIVE. All figures per $1 per fire.')
    print()
    for db in ('predict_pnl.sqlite3', 'build11.sqlite3', 'twin_c_thr1.sqlite3'):
        report(db.replace('.sqlite3', ''), from_trades(db))
    report('TOKYO real fills', from_tokyo())
