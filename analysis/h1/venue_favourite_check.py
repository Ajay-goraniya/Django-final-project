"""The queued check: does the VENUE's favourite track the Binance price leader late in the candle?

This settles the one thing Task 15 could not. Task 14 measured the venue's implied favourite at
t>=237 winning only 49.4% in the near-zero bucket (n=77). Task 15 measured the Binance PRICE LEADER
winning ~0.60 in the same bucket on 72k candles, and I tested and REJECTED the obvious explanation
(that the two studies bucket on different variables - they agree, 0.614 vs 0.595).

Two candidates were left: (a) the venue's favourite diverges from the Binance leader precisely in
near-zero candles, or (b) noise at n=77. This measures (a) directly on the same candles.

Engine grading (candles table). Buckets fixed in advance, same as Tasks 14-16.
"""
import numpy as np, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import task16_market_prior_ef as T

SECS = [237, 270, 290]
MIN_N = 60


def main():
    d = np.load(f'{T.SP}/build/paths.npz')
    P = {int(c) // 1000: p for c, p in zip(d['cid'], d['paths'].astype(float))}
    act, books = T.engine_actual(), T.venue_books()
    eps = sorted(set(books) & set(act) & set(P))
    print('candles with venue book + engine outcome + kline path: %d' % len(eps))

    for S in SECS:
        rows = []
        for ep in eps:
            p = P[ep]
            op, px = p[0], p[S]
            au, ad, _, _ = T.book_at(books[ep], S)
            if au is None or ad is None:
                continue
            imp = au / (au + ad)                      # venue implied P(UP)
            rows.append(dict(bi=T.bucket(abs(px - op) / op * 1e4),
                             leader='UP' if px >= op else 'DOWN',
                             fav='UP' if imp >= 0.5 else 'DOWN',
                             a=act[ep]))
        print()
        print('=' * 96)
        print('t=%d  n=%d   does the venue favourite = the Binance price leader?' % (S, len(rows)))
        print('=' * 96)
        print('%-8s %6s %10s | %11s %11s | %s'
              % ('bps', 'n', 'agree', 'leader wins', 'favourite wins', 'gap (fav - leader)'))
        print('-' * 96)
        for i, lbl in enumerate(T.LBL):
            c = [r for r in rows if r['bi'] == i]
            if not c:
                continue
            agree = np.mean([r['fav'] == r['leader'] for r in c])
            lw = np.mean([r['leader'] == r['a'] for r in c])
            fw = np.mean([r['fav'] == r['a'] for r in c])
            tag = '' if len(c) >= MIN_N else '  << n<60'
            print('%-8s %6d %9.0f%% | %10.3f %11.3f | %+17.3f%s'
                  % (lbl, len(c), 100 * agree, lw, fw, fw - lw, tag))
        agree = np.mean([r['fav'] == r['leader'] for r in rows])
        print('-' * 96)
        print('%-8s %6d %9.0f%% | %10.3f %11.3f | %+17.3f'
              % ('ALL', len(rows), 100 * agree,
                 np.mean([r['leader'] == r['a'] for r in rows]),
                 np.mean([r['fav'] == r['a'] for r in rows]),
                 np.mean([r['fav'] == r['a'] for r in rows]) - np.mean([r['leader'] == r['a'] for r in rows])))


if __name__ == '__main__':
    main()
