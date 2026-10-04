#!/usr/bin/env python3
"""Is the public data-api trade timestamp usable at second resolution? (V, 09-28 15:0x). READ-ONLY.

V's late rule survives on public data when it pays the first taker print AFTER the decision second, but
dies on Zurich's book. V's suspicion: data-api `timestamp` is the ON-CHAIN settlement time, seconds after
the off-chain match, so a print that looks "after S" was actually matched BEFORE S - i.e. the rule is
still reading the future, just with an extra step. One measurement settles it: take trades that appear in
BOTH feeds and look at data_api_ts - ws_ev_ms.

THREE CORRECTIONS TO THE BRIEF, all of which shrink what this can prove:
  * the probe window is 09-27 05:30:26-07:30:24 UTC (2.0 h), not 02:15-06:45
  * pm_trade holds 25,163 prints, not 81,222
  * pm_trade has NO size column (rx_ns, ev_ms, token, price), so matching is on token+price+time only

A SEPARATE FINDING, and V should check their own pipeline for it: on data-api /trades the `asset=` and
`conditionId=` parameters are SILENTLY IGNORED - no error, HTTP 200, and a page of the GLOBAL recent-trade
feed. Querying `asset=<btc5 token>` returned nine unrelated markets (an Elon-tweets market, a Buenos Aires
temperature market, two football scores) all stamped at the same current second. Only `market=<conditionId>`
filters. My first run of this script used `asset=` and was worthless; if V's public-data collector used the
same parameter, their trade tape is not the market they think it is, which on its own could explain a
result that does not reproduce.

MATCHING, and why not nearest-neighbour. Taking the closest WS print to each data-api trade would pull
every lag toward zero by construction and would hide exactly the effect being tested. So:
  PRIMARY   unambiguous pairs only - a data-api trade is used when exactly ONE WS print shares its token
            and price anywhere in +-WIN seconds. No choice is made, so no bias is introduced.
  CONTROL   cross-correlation: all offsets from all same-token same-price pairs, against a null built by
            pairing each data-api trade with prints of a DIFFERENT token at the same price. A real lag
            shows as a peak over a flat background; a matching artefact does not.

data-api timestamps are integer SECONDS, so the lag is quantised to +-0.5 s and no sub-second claim is
possible. That is enough for the question asked, which is whether the lag reaches 1 s and 3 s.
"""
import sys, os, json, time, sqlite3, urllib.request, urllib.error, collections, numpy as np

DB = '/home/ubuntu/pm_probe/ms_probe.sqlite3'
UA = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
WIN = 10.0
PAGE = 500


def get(url, tries=6):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or i == tries - 1: raise
            time.sleep(4.0 * (i + 1))          # the first run was rate-limited off at token 23 of 50
        except Exception:
            if i == tries - 1: raise
            time.sleep(2.0 * (i + 1))


def fetch(cond, lo, hi):
    """market=<conditionId> ONLY. `asset=` and `conditionId=` are SILENTLY IGNORED - see the note below."""
    out, off = [], 0
    while True:
        r = get(f'https://data-api.polymarket.com/trades?market={cond}&takerOnly=true'
                f'&limit={PAGE}&offset={off}')
        if not r: break
        bad = {x.get('conditionId') for x in r} - {cond}
        if bad: raise RuntimeError(f'market filter not honoured for {cond[:12]}')
        out += r
        if len(r) < PAGE: break
        off += PAGE
        if off > 20000: break
        time.sleep(0.4)
    return [x for x in out if lo - 60 <= int(x['timestamp']) <= hi + 60]


if __name__ == '__main__':
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    lo_ms, hi_ms = c.execute('SELECT min(ev_ms), max(ev_ms) FROM pm_trade').fetchone()
    lo, hi = lo_ms / 1000.0, hi_ms / 1000.0
    toks = [t for (t,) in c.execute('SELECT DISTINCT token FROM pm_trade')]
    # token -> conditionId, from the gamma mirror (the probe's own markets table has no cond)
    cond = {}
    for p in ('/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3'):
        try: g = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        except Exception: continue
        for cd, tu, td in g.execute("SELECT cond, tok_up, tok_dn FROM mkt WHERE asset='btc'"):
            if cd: cond[tu] = cd; cond[td] = cd
    conds = sorted({cond[t] for t in toks if t in cond})
    print(f'  tokens mapped to {len(conds)} condition ids ({sum(1 for t in toks if t not in cond)} unmapped)')
    ws = collections.defaultdict(list)
    for tok, ev, px in c.execute('SELECT token, ev_ms, price FROM pm_trade ORDER BY ev_ms'):
        ws[(tok, round(float(px), 2))].append(ev / 1000.0)
    bypx = collections.defaultdict(list)
    for (tok, px), v in ws.items(): bypx[px] += [(tok, t) for t in v]
    print(f'WS prints {sum(len(v) for v in ws.values()):,} over {len(toks)} tokens, '
          f'window {time.strftime("%m-%d %H:%M:%S", time.gmtime(lo))} .. '
          f'{time.strftime("%H:%M:%S", time.gmtime(hi))} UTC ({(hi-lo)/3600:.1f} h)')

    api, failed = [], 0
    for i, cd in enumerate(conds):
        try: r = fetch(cd, lo, hi)
        except Exception as e:
            failed += 1; print(f'  cond {i+1}/{len(conds)} FAILED {type(e).__name__} {e}'); continue
        api += [(x['asset'], int(x['timestamp']), round(float(x['price']), 2), float(x['size'])) for x in r]
        time.sleep(0.8)
    print(f'  condition ids fetched {len(conds)-failed}/{len(conds)}')
    print(f'data-api taker trades in window: {len(api):,}')
    if not api: sys.exit('no data-api trades returned - cannot answer')

    prim, amb, none_ = [], 0, 0
    allpairs, nullpairs = [], []
    for tok, ts, px, sz in api:
        cand = [t for t in ws.get((tok, px), []) if abs(ts - t) <= WIN]
        allpairs += [ts - t for t in cand]
        nullpairs += [ts - t for tk2, t in bypx.get(px, []) if tk2 != tok and abs(ts - t) <= WIN]
        if len(cand) == 1: prim.append(ts - cand[0])
        elif len(cand) == 0: none_ += 1
        else: amb += 1
    print(f'  matched unambiguously {len(prim):,} | ambiguous (>1 candidate) {amb:,} | no WS print {none_:,}')

    if prim:
        a = np.array(prim)
        print(f'\nPRIMARY  lag = data_api_ts - ws_ev_ms, unambiguous pairs, n={len(a):,}')
        for q in (10, 25, 50, 75, 90):
            print(f'    p{q:<3d} {np.percentile(a, q):+7.2f} s')
        print(f'    mean {a.mean():+.2f}  share >= 1 s: {100*(a >= 1).mean():.1f}%   '
              f'>= 3 s: {100*(a >= 3).mean():.1f}%   <= -1 s: {100*(a <= -1).mean():.1f}%')

    if allpairs:
        b = np.arange(-WIN, WIN + 0.25, 0.25)
        h, _ = np.histogram(allpairs, bins=b)
        hn, _ = np.histogram(nullpairs, bins=b)
        hn = hn * (h.sum() / max(hn.sum(), 1))
        k = int(np.argmax(h - hn))
        print(f'\nCONTROL  cross-correlation, {len(allpairs):,} same-token pairs vs '
              f'{len(nullpairs):,} different-token pairs at the same price')
        print(f'    excess peak at lag {b[k]:+.2f} .. {b[k]+0.25:+.2f} s '
              f'(observed {h[k]:,} vs null {hn[k]:,.0f})')
        top = np.argsort(-(h - hn))[:6]
        print('    top excess bins: ' + '  '.join(f'{b[i]:+.2f}s:{h[i]-hn[i]:+.0f}' for i in sorted(top)))
