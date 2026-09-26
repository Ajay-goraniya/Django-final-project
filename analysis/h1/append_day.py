"""Append a REST-fetched day of 1s closes to paths.npz (Task 15 part 1).

data.binance.vision never published 2026-09-10, so the day came from data-api.binance.vision via
fetch_rest_klines.py. Same shape as the daily zips: (ts_ms, close) per second.
"""
import json, numpy as np, sys

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
SEC = 300


def build(rows):
    """(ts_ms, close) -> (cid[], paths[n,300]) on whole 5-minute boundaries, gaps forward-filled."""
    by_sec = {}
    for ts, c in rows:
        by_sec[ts // 1000] = c
    if not by_sec:
        return np.zeros(0, np.int64), np.zeros((0, SEC), np.float32)
    lo, hi = min(by_sec), max(by_sec)
    start = lo - (lo % SEC)
    cids, out, last = [], [], None
    for c0 in range(start, hi - SEC + 2, SEC):
        row, ok = [], 0
        for s in range(c0, c0 + SEC):
            v = by_sec.get(s)
            if v is None:
                v = last
            else:
                ok += 1
            last = v
            row.append(v)
        if ok < SEC * 0.9 or row[0] is None:   # a candle must be mostly real, not mostly fill
            continue
        cids.append(c0 * 1000)
        out.append(row)
    return np.array(cids, np.int64), np.array(out, np.float32)


if __name__ == '__main__':
    rows = json.load(open(sys.argv[1]))
    cid_new, p_new = build(rows)
    print('new day: %d candles from %d rows' % (len(cid_new), len(rows)))
    d = np.load(f'{SP}/build/paths.npz')
    cid, p = d['cid'], d['paths']
    print('existing: %d candles, last cid %d' % (len(cid), cid[-1]))
    keep = ~np.isin(cid_new, cid)
    cid_new, p_new = cid_new[keep], p_new[keep]
    cid2 = np.concatenate([cid, cid_new])
    p2 = np.concatenate([p, p_new])
    order = np.argsort(cid2)
    cid2, p2 = cid2[order], p2[order]
    assert len(np.unique(cid2)) == len(cid2), 'duplicate candle ids'
    assert not np.isnan(p2).any(), 'NaN in paths'
    np.savez_compressed(f'{SP}/build/paths.npz', cid=cid2, paths=p2)
    print('appended %d new -> %d total, last cid %d' % (len(cid_new), len(cid2), cid2[-1]))
