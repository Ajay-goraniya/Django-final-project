#!/usr/bin/env python3
"""P1 collector: Predict.fun BTC 5m best bid/ask both sides, every 1 s, into its own sqlite.
READ-ONLY. It imports no broker, signs nothing, and places nothing. Discovery and order book only.

STATUS 10-01: NOT RUNNING, because Zurich cannot read the API. Every data path answers HTTP 401:
    /v1/markets?limit=1   401        /v1/search?query=...   401
and no PREDICT_JWT or PREDICT_API_KEY exists anywhere on this box (deploy.env, the engine's
environment: none). The network is FINE - IPv4 resolves and curl completes the TLS handshake and
gets a real 401 back, so this is an authorisation wall, not a reachability problem. (My first guess
was the known IPv6-only-DNS trap on this host; it was wrong - api.predict.fun has A records and
curl -4 returns the same 401.)
So this file is the collector, finished and ready, waiting on ONE thing: a READ-ONLY Predict
credential placed in the environment as PREDICT_JWT or PREDICT_API_KEY by the owner. I will not ask
for its value and it must never be committed. Start it with:
    ( set -a; . <the env file>; set +a; nohup python3 predict_quotes.py > quotes.log 2>&1 & )
It refuses to start on a 401 rather than hammering the venue with requests it cannot serve.
"""
import os, sqlite3, sys, time, datetime as dt

sys.path.insert(0, '/home/ubuntu/claude-work/repo/learner/v12_2')
import predict_venue as P

DB = '/home/ubuntu/predict_p1/predict_quotes.sqlite3'
PERIOD = 1.0
HOURS = float(os.environ.get('P1_HOURS', '48'))


def db():
    d = sqlite3.connect(DB, timeout=30)
    d.executescript("""
    create table if not exists quote(
      ts_ms integer, epoch integer, market_id text,
      up_ask real, up_ask_sz real, up_bid real, up_bid_sz real,
      dn_ask real, dn_ask_sz real, dn_bid real, dn_bid_sz real,
      primary key(ts_ms, epoch));
    create index if not exists ix_quote_ep on quote(epoch);
    create table if not exists health(ts integer, note text);""")
    d.commit(); return d


def top(levels):
    """(price, size) of the best level, or (None, None). levels() already sorts the book side."""
    if not levels: return None, None
    p, s = levels[0][0], levels[0][1]
    return float(p), float(s)


def preflight():
    r = P.get_json('/v1/markets', {'limit': 1})
    if r is None:
        print('PREFLIGHT FAILED: /v1/markets returned nothing. Zurich sees HTTP 401 on every Predict '
              'data path and no PREDICT_JWT / PREDICT_API_KEY is set. Put a READ-ONLY credential in '
              'the environment and start again; refusing to poll a venue that will not answer.',
              flush=True)
        return False
    return True


def main():
    if not preflight(): sys.exit(2)
    d = db(); v = P.PredictVenue(); end = time.time() + HOURS * 3600
    n = err = 0; last_h = 0.0
    print(f'predict_quotes: collecting for {HOURS} h into {DB}', flush=True)
    while time.time() < end:
        t0 = time.time()
        try:
            ep = int(t0 // P.CANDLE_S) * P.CANDLE_S
            snap = v.snapshot(ep)
            if snap:
                mid = snap.get('market_id') or snap.get('mid')
                ua, uas = top(snap.get('up_asks')); ub, ubs = top(snap.get('up_bids'))
                da, das = top(snap.get('down_asks')); db_, dbs = top(snap.get('down_bids'))
                d.execute('insert or replace into quote values(?,?,?,?,?,?,?,?,?,?,?)',
                          (int(t0 * 1000), ep, str(mid) if mid else None,
                           ua, uas, ub, ubs, da, das, db_, dbs))
                d.commit(); n += 1
        except Exception as e:
            err += 1
            if err <= 5: print(f'{dt.datetime.now(dt.UTC):%H:%M:%S} {type(e).__name__}: {e}', flush=True)
        if t0 - last_h > 300:
            last_h = t0
            d.execute('insert into health values(?,?)', (int(t0), f'rows {n} errors {err}')); d.commit()
            print(f'{dt.datetime.now(dt.UTC):%H:%M:%S} alive, rows {n}, errors {err}', flush=True)
        time.sleep(max(0.0, PERIOD - (time.time() - t0)))
    print(f'done: {n} rows, {err} errors', flush=True)


if __name__ == '__main__':
    main()
