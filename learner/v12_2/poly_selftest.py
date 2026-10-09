"""Pre-flight checks for a new host. Run before the first live start.

    python3 poly_selftest.py            # everything
    python3 poly_selftest.py --feeds    # endpoint reachability and lag only

Checks what the deployment actually depends on and prints what it measured,
so an unusable host is identified before money is involved rather than after.
"""
import argparse, asyncio, json, os, sys, time, urllib.request
import poly_feeds as F

OK, BAD = '  ok  ', ' FAIL '


def line(status, label, detail=''):
    print(f'[{status}] {label}' + (f'  {detail}' if detail else ''), flush=True)


def check_rest():
    good = []
    for host in F.REST_HOSTS:
        try:
            t0 = time.time()
            urllib.request.urlopen(urllib.request.Request(
                host.rstrip('/') + '/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=2',
                headers=F.UA), timeout=10).read(200)
            line(OK, f'REST {host}', f'{1000*(time.time()-t0):.0f}ms')
            good.append(host)
        except Exception as e:
            line(BAD, f'REST {host}', f'{type(e).__name__}')
    if not good:
        line(BAD, 'REST overall', 'no candle source reachable; the chart and seeding will be empty')
    return bool(good)


async def check_ws(seconds=8):
    health = F.FeedHealth(('spot', 'perp', 'depth'))
    tasks = []
    for name in ('spot', 'perp', 'depth'):
        tasks.append(asyncio.create_task(F.run_stream(name, lambda j: None, health)))
    await asyncio.sleep(seconds)
    for t in tasks:
        t.cancel()
    ok = True
    for name in ('spot', 'perp', 'depth'):
        lag = health.event_lag(name)
        age = health.arrival_age(name)
        if age is None:
            line(BAD, f'WS {name}', 'no data'); ok = False
        else:
            detail = f'host={health.host.get(name)} msgs={health.msgs.get(name)} lag={1000*lag:.0f}ms' if lag is not None else f'host={health.host.get(name)}'
            bad = health.stale((name,))
            line(OK if not bad else BAD, f'WS {name}', detail + ('' if not bad else f'  {bad[name]}'))
            ok = ok and not bad
    if health.clock_skew_s < -0.5:
        line(BAD, 'clock', f'local clock is {abs(health.clock_skew_s):.1f}s behind the exchange; fix NTP')
        ok = False
    else:
        line(OK, 'clock', f'skew {health.clock_skew_s:.3f}s')
    return ok


def check_geoblock():
    try:
        r = json.load(urllib.request.urlopen('https://polymarket.com/api/geoblock', timeout=10))
    except Exception as e:
        line(BAD, 'geoblock', f'could not reach the check ({type(e).__name__}); live start will refuse')
        return False
    blocked = r.get('blocked')
    if blocked is False:
        line(OK, 'geoblock', 'this host is permitted to trade')
        return True
    line(BAD, 'geoblock', f'blocked={blocked}; live start will refuse, paper is unaffected')
    return False


def check_credentials():
    names = ['POLYMARKET_PRIVATE_KEY', 'POLYMARKET_WALLET_ADDRESS', 'RELAYER_API_KEY', 'RELAYER_API_KEY_ADDRESS']
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        line(BAD, 'credentials', 'missing: ' + ', '.join(missing))
        return False
    line(OK, 'credentials', 'all four present (values not printed)')
    return True


def check_sdk():
    try:
        import importlib.metadata as m
        v = m.version('polymarket-client')
        if v != '0.10.0':
            line(BAD, 'sdk', f'polymarket-client {v}; this build pins 0.10.0')
            return False
        line(OK, 'sdk', 'polymarket-client 0.10.0')
        return True
    except Exception as e:
        line(BAD, 'sdk', f'{type(e).__name__}: install requirements-live.txt')
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feeds', action='store_true', help='endpoint checks only')
    a = ap.parse_args()
    print('Polymarket v12.2 pre-flight\n')
    results = [check_rest(), asyncio.run(check_ws())]
    if not a.feeds:
        results += [check_sdk(), check_credentials(), check_geoblock()]
    print()
    if all(results):
        print('All checks passed.')
        return 0
    print('One or more checks failed. Read the lines marked FAIL above.')
    print('Paper mode runs regardless of the geoblock and credential checks.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
