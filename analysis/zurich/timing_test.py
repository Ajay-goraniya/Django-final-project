"""Is Raw's edge TIMING - i.e. is the money in WHEN it fires? READ-ONLY. Nothing here touches the engine.

V's spec: the same raw-arm candles, fire at a RANDOM second in the fire window, 1000 draws, for Raw's
side and for the cheap side; then the same on random candles.

That control, run as specified, says a random second is worth +0.499/$1 against Raw's own second at
+0.078, p(random >= own) = 1.000. It is not a finding. It is lookahead:

    Raw names its side at a median second 99 of the candle. A draw at second 20 buys THAT SIDE at
    second 20's ask - a price from before the signal existed. Nobody at second 20 knew which side Raw
    would name. The control is Raw's information traded at a pre-signal price, so of course it wins.

The mechanism is visible in the prices. A loss costs the stake whatever was paid, so only WINNER prices
move per$1, and the payout is 5/px:

    WINNERS  mean px: own second 0.459  random second 0.372   shares per $5: 11.2 -> 17.5
    LOSERS   mean px: own second 0.447  random second 0.291   shares per $5: 11.6 -> 32.6

Early in a candle the book has not converged, so a side that ends up winning is often cheap. Picking it
then requires knowing which side wins, which is the lookahead.

The implementable version of the same question is delay: a random second at or AFTER Raw's own second.
That is reported here as the answer, paired candle by candle, and it runs the other way.

Pricing. The controls are priced from `tape1s` (1 Hz). The real fills come from the executor's book
read, and the two are NOT interchangeable - tape1s at the fire second sits +0.050 (median) above the
price actually filled, and it reads above the 0.61 cap on 50 candles Raw won 68% of. So every number
below is tape-to-tape: the baseline is Raw's own second priced from tape1s too, never the fill price.
The fill-price figure (+0.2653/$1) is context, not the baseline.

Grading: `results.actual`. The venues snapshot on the branch ends 09-16 and covers 0 of these 339
epochs, so there is no cross-check available here and none is claimed.
"""
import sqlite3, random, statistics as st, math

DB = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
RAW_WINDOWS = [(1790127365.0, 1790170418.0), (1790172444.0, float('inf'))]
LO, HI, STAKE, DRAWS, CAP = 15, 240, 5.0, 1000, 0.61

def load():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
    res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
    tape = {int(r['ts']): (float(r['up_ask']), float(r['dn_ask'])) for r in c.execute(
        'SELECT ts,up_ask,dn_ask FROM tape1s WHERE up_ask IS NOT NULL AND dn_ask IS NOT NULL')}
    f = []
    for r in c.execute("SELECT o.epoch,o.ts,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe FROM orders o "
                       "JOIN fills f ON f.order_id=o.id WHERE o.kind='EF' AND o.status='FILLED' "
                       "GROUP BY o.id ORDER BY o.ts"):
        if not any(a <= r['ts'] < b for a, b in RAW_WINDOWS) or not r['sh']: continue
        act = res.get(r['epoch'])
        if act is None: continue
        s = c.execute("SELECT side FROM signals WHERE epoch=? AND kind='EF' LIMIT 1", (r['epoch'],)).fetchone()
        if not s or not s[0]: continue
        f.append(dict(e=r['epoch'], ts=int(r['ts']), sec=int(r['ts']) - r['epoch'], side=s[0], actual=act,
                      fill=r['sp'] / r['sh'], shares=r['sh'], cost=(r['sp'] or 0.) + (r['fe'] or 0.)))
    c.close()
    return f, res, tape

def main():
    f, res, tape = load()
    N = len(f)
    ask = lambda e, s, sd: (lambda t: None if not t else (t[0] if sd == 'UP' else t[1]))(tape.get(e + s))

    def leg(x, sec, side=None, actual=None, cap=CAP):
        a = ask(x['e'] if isinstance(x, dict) else x, sec, side or x['side'])
        if a is None or not (0. < a <= cap): return None
        sh = STAKE / a; cost = STAKE + 0.07 * sh * a * (1 - a)
        win = (side or x['side']) == (actual if actual is not None else x['actual'])
        return ((sh if win else 0.) - cost, cost)

    def per1(rows):
        rows = [r for r in rows if r]
        return (sum(a for a, _ in rows) / sum(b for _, b in rows) if rows else None), len(rows)

    rp = sum((x['shares'] if x['side'] == x['actual'] else 0.) - x['cost'] for x in f)
    rc = sum(x['cost'] for x in f)
    print(f'raw-arm graded fires {N}, win rate {100*sum(x["side"]==x["actual"] for x in f)/N:.1f}%, '
          f'fire second p50 {int(st.median([x["sec"] for x in f]))}')
    print(f'ACTUAL FILLS (executor book read, context only): per$1 {rp/rc:+.4f}, mean px '
          f'{st.mean([x["fill"] for x in f]):.4f}')
    gap = [ask(x['e'], x['sec'], x['side']) - x['fill'] for x in f if ask(x['e'], x['sec'], x['side'])]
    print(f'tape1s at the fire second MINUS the fill: p50 {st.median(gap):+.3f} mean {st.mean(gap):+.3f} '
          f'(n {len(gap)}) -- why the baseline below is NOT the fill number')

    base, nb = per1([leg(x, x['sec']) for x in f])
    print(f"\nBASELINE, Raw's side at Raw's OWN second, tape1s, px<={CAP}: {base:+.4f} (n {nb}/{N})")

    def draws(pick, label, baseline):
        v = []
        for i in range(DRAWS):
            rng = random.Random(14000 + i)
            s, _ = per1([pick(rng, x) for x in f])
            if s is not None: v.append(s)
        v.sort()
        print(f'  {label:<46} mean {st.mean(v):+.4f}  p05 {v[int(.05*len(v))]:+.4f}  '
              f'p95 {v[int(.95*len(v))]:+.4f}  p(>=own second) {sum(1 for x in v if x >= baseline)/len(v):.3f}')

    print("V's control as specified - CONFOUNDED BY LOOKAHEAD, do not read as timing:")
    draws(lambda rng, x: leg(x, rng.randint(LO, HI)), "Raw's side, random second (may PRECEDE signal)", base)
    def cheap(rng, x, sec=None):
        sec = rng.randint(LO, HI) if sec is None else sec
        a = tape.get(x['e'] + sec)
        if not a: return None
        sd = 'UP' if a[0] < a[1] else 'DOWN'
        return leg(x, sec, side=sd)
    draws(lambda rng, x: cheap(rng, x), 'cheap side, random second', base)
    lo_e, hi_e = min(x['e'] for x in f), max(x['e'] for x in f)
    pool = [e for e in res if lo_e <= e <= hi_e and res[e] is not None]
    print(f'  random candles in the same span ({len(pool)} graded):')
    def rc_(rng, mode):
        e = rng.choice(pool); sec = rng.randint(LO, HI); a = tape.get(e + sec)
        if not a: return None
        sd = ('UP' if a[0] < a[1] else 'DOWN') if mode == 'cheap' else ('UP' if rng.random() < .5 else 'DOWN')
        return leg(e, sec, side=sd, actual=res[e])
    draws(lambda rng, x: rc_(rng, 'cheap'), 'cheap side, random candle + random second', base)
    draws(lambda rng, x: rc_(rng, 'coin'), 'coin-flip side, random candle + random second', base)

    print('\nWHY: only winner prices move per$1 (a loss costs the stake at any price), payout is 5/px:')
    for lbl, sub in (('WINNERS', [x for x in f if x['side'] == x['actual']]),
                     ('LOSERS', [x for x in f if x['side'] != x['actual']])):
        o = [a for a in (ask(x['e'], x['sec'], x['side']) for x in sub) if a and a <= CAP]
        r = []
        for i in range(200):
            rng = random.Random(13000 + i)
            r += [a for a in (ask(x['e'], rng.randint(LO, HI), x['side']) for x in sub) if a and a <= CAP]
        print(f'  {lbl:<8} n {len(sub):>3}  mean px own {st.mean(o):.4f} random {st.mean(r):.4f}   '
              f'shares/$5 own {st.mean([5/a for a in o]):6.2f} random {st.mean([5/a for a in r]):6.2f}')

    print('\nTHE ANSWER - delay only, never earlier than Raw fired, so no lookahead.')
    draws(lambda rng, x: leg(x, rng.randint(x['sec'], max(x['sec'], HI))), 'random delay 0..(240-fire)s', base)
    print('  Paired on candles priced at BOTH seconds, NO price cap so neither arm is censored:')
    mid = f[0]['ts'] + (f[-1]['ts'] - f[0]['ts']) / 2
    for d in (15, 30, 60, 120):
        pr = [(leg(x, x['sec'], cap=1.0), leg(x, x['sec'] + d, cap=1.0), x) for x in f]
        pr = [(a, b, x) for a, b, x in pr if a and b]
        own = sum(a[0] for a, b, x in pr) / sum(a[1] for a, b, x in pr)
        dl = sum(b[0] for a, b, x in pr) / sum(b[1] for a, b, x in pr)
        disc = [a[0] - b[0] for a, b, x in pr if abs(a[0] - b[0]) > 1e-9]
        w = sum(1 for y in disc if y > 0)
        p = sum(math.comb(len(disc), k) for k in range(w, len(disc) + 1)) / 2 ** len(disc)
        h = []
        for lo, hi, lbl in ((f[0]['ts'], mid, 'h1'), (mid, f[-1]['ts'] + 1, 'h2')):
            s = [(a, b) for a, b, x in pr if lo <= x['ts'] < hi]
            h.append(f"{lbl} {sum(a[0] for a,b in s)/sum(a[1] for a,b in s):+.3f} vs "
                     f"{sum(b[0] for a,b in s)/sum(b[1] for a,b in s):+.3f} (n{len(s)})")
        print(f'    +{d:>3}s  n {len(pr):>3}  own {own:+.4f}  delayed {dl:+.4f}  own better on '
              f'{w}/{len(disc)} ({100*w/len(disc):.0f}%)  sign-test p {p:.1e}   {h[0]} | {h[1]}')

if __name__ == '__main__':
    main()
