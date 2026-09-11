"""Task 17.2 - cumulative forward ledger for the FROZEN 11.2 model.

Forward means: candles AFTER the replay that produced the +0.266 headline. Nothing here is
re-fitted and the frozen artifact is never reloaded from anything but models/. Each run processes
only candles newer than the last one recorded, so the ledger accumulates instead of being rewritten.

State lives in task17_forward_state.json (last processed epoch + every forward fire), so a rerun is
idempotent and the history cannot be silently restated.

Grading: the engine's `candles` table (Predict.fun's settling source).
"""
import numpy as np, json, os, sys, sqlite3, datetime as dt, joblib
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1/models')
import task16_market_prior_ef as T, task11_2_direction_model as M
from ef11_2_predict import feats_at, SECS, EV_MARGIN

H1 = '/home/user/Django-final-project/analysis/h1'
STATE = f'{H1}/task17_forward_state.json'
LEDGER = f'{H1}/task17_forward_11_2.md'
# The replay that produced +0.266 ended here. Anything strictly after is forward evidence.
REPLAY_LAST_EPOCH = 1789078800


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return dict(last_epoch=REPLAY_LAST_EPOCH, fires=[])


def main():
    st = load_state()
    m = joblib.load(f'{H1}/models/ef11_2_gbm_seed0.joblib')
    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = T.engine_actual(), T.venue_books()
    t12 = M.trailing12(paths, paths[:, 0])
    idx = {int(c) // 1000: i for i, c in enumerate(cids)}

    new_eps = sorted(e for e in (set(books) & set(act) & set(Pmap)) if e > st['last_epoch'])
    print('forward candles available since epoch %d: %d' % (st['last_epoch'], len(new_eps)))
    added = 0
    for ep in new_eps:
        i = idx.get(ep)
        if i is None or np.isnan(t12[i]):
            continue
        p_arr, a = Pmap[ep], act[ep]
        for S in SECS:
            pu = float(m.predict_proba(feats_at(p_arr, S, t12[i]).reshape(1, -1))[0, 1])
            side = 'UP' if pu >= 0.5 else 'DOWN'
            p = pu if side == 'UP' else 1 - pu
            au, ad, su, sd = T.book_at(books[ep], S)
            ask = au if side == 'UP' else ad
            size = su if side == 'UP' else sd
            if ask is None or not (0.02 < ask < 0.98) or size is None or size * ask < T.MIN_NOTIONAL:
                continue
            if p * (1 / ask) * (1 - T.FEE) - 1 < EV_MARGIN:
                continue
            ts = dt.datetime.utcfromtimestamp(ep)
            op, px = p_arr[0], p_arr[S]
            st['fires'].append(dict(epoch=ep, day=ts.strftime('%Y-%m-%d'), hour=ts.hour,
                                    wknd=ts.weekday() >= 5, S=S, side=side, ask=ask,
                                    bi=T.bucket(abs(px - op) / op * 1e4),
                                    hit=bool(side == a), pnl=T.pnl(side == a, ask)))
            added += 1
            break
    if new_eps:
        st['last_epoch'] = max(new_eps)
    json.dump(st, open(STATE, 'w'), indent=1)

    f = st['fires']
    n = len(f)
    print('forward fires added this run: %d   cumulative: %d' % (added, n))
    if not f:
        return
    pn = np.array([x['pnl'] for x in f]); h = n // 2
    verdict = ('VERDICT: >= 100 forward fires reached — read the halves and run verify.py'
               if n >= 100 else 'ACCUMULATING — %d of 100 forward fires. NOT READABLE YET.' % n)
    # How surprising is the forward hit rate if the replay's 62.7% were the truth? Reported as
    # context only - it is NOT a verdict, and n is far below the bar.
    from math import comb
    k = int(sum(x['hit'] for x in f))
    p0 = 0.627
    tail = sum(comb(n, j) * p0 ** j * (1 - p0) ** (n - j) for j in range(0, k + 1))
    days = sorted({x['day'] for x in f})
    lines = []
    lines.append('# Task 17.2 — forward ledger, frozen 11.2 model\n')
    lines.append('Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never '
                 'refitted. Forward = candles strictly after epoch %d, the last candle of the replay '
                 'that produced the +0.266 headline. Engine grading. EV margin %.2f.\n'
                 % (REPLAY_LAST_EPOCH, EV_MARGIN))
    lines.append('_Last updated %s UTC._\n' % dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M'))
    lines.append('## %s\n' % verdict)
    lines.append('| | n | hit | per-fire | total |')
    lines.append('|---|---|---|---|---|')
    lines.append('| **forward, all** | %d | %.1f%% | **%+.3f** | %+.2f |'
                 % (n, 100 * np.mean([x['hit'] for x in f]), pn.mean(), pn.sum()))
    if n >= 2:
        lines.append('| first half | %d | — | %+.3f | %+.2f |' % (h, pn[:h].mean(), pn[:h].sum()))
        lines.append('| second half | %d | — | %+.3f | %+.2f |' % (n - h, pn[h:].mean(), pn[h:].sum()))
    lines.append('\n**Replay baseline to beat: +0.266/fire, 62.7% hit (weekday-only, n=91).**\n')
    lines.append('Forward hit rate is %d of %d. If the replay\'s 62.7%% were the true rate, seeing '
                 '%d or fewer hits in %d fires has probability **%.4f**. That is context, **not a '
                 'verdict** — n is far below the 60-fire bar, let alone 100, and a run this short '
                 'can do this by chance. It is recorded so the trend is visible from the start '
                 'rather than discovered at fire 100.\n' % (k, n, k, n, tail))
    lines.append('## By UTC day\n')
    lines.append('| day | n | hit | per-fire | total | weekend |')
    lines.append('|---|---|---|---|---|---|')
    for day in days:
        g = [x for x in f if x['day'] == day]
        v = np.array([x['pnl'] for x in g])
        lines.append('| %s | %d | %.0f%% | %+.3f | %+.2f | %s |'
                     % (day, len(g), 100 * np.mean([x['hit'] for x in g]), v.mean(), v.sum(),
                        'yes' if g[0]['wknd'] else 'no'))
    lines.append('\n## Fire-distance profile (forward)\n')
    lines.append('| bps at fire | n | share | per-fire |')
    lines.append('|---|---|---|---|')
    for i, l in enumerate(T.LBL):
        g = [x for x in f if x['bi'] == i]
        if g:
            lines.append('| %s | %d | %.0f%% | %+.3f |'
                         % (l, len(g), 100 * len(g) / n, np.mean([x['pnl'] for x in g])))
    wk = [x for x in f if x['wknd']]
    lines.append('\n**Weekend forward fires: %d.** %s\n'
                 % (len(wk), 'The replay had none, so these are the first weekend evidence for this '
                             'fire set.' if wk else 'Still none — the replay had none either, so '
                             'there is still no weekend evidence for this fire set.'))
    open(LEDGER, 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:14]))


if __name__ == '__main__':
    main()
