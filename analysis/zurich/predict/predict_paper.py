#!/usr/bin/env python3
"""PAPER lane for Predict.fun on Zurich. Owner 10-01: "Don't make it live, just paper on Zurich."

PLACES NOTHING. It imports no broker, holds no trading key, and writes only its own table. Every
figure it produces is a counterfactual priced off recorded quotes.

THE RULE, exactly as V specified it:
  fires      every C_fixed15 fire (London's model), from the shadow via ef_fire
  price      Predict's OWN best ask on the fire's side at fire_ts + DELAY_MS (236 ms, measured on
             Tokyo). Predict's prices differ systematically from Polymarket's (R-31b: +10c at cheap
             asks, -10c at rich), so Polymarket's ask CANNOT stand in for it - that substitution is
             the cross-venue grading error CLAUDE.md bans.
  size       shares = STAKE / ask, CAPPED by the displayed ask size at that instant
  fee        2% of shares, ON WINNERS ONLY (R-31)
  grading    Binance close >= open, i.e. the engine's candles.actual - Predict's own settlement rule,
             NOT Polymarket's resolution. The two disagree on ~21% of candles.
  control    the SAME fire priced at the Polymarket ask with Polymarket's fee, side by side, so the
             venues are compared on identical fires rather than on different sets of candles.

Winner:  shares*(1 - ask) - 0.02*shares   Loser: -shares*ask
"""
import sqlite3, sys, time, datetime as dt

QUOTES = '/home/ubuntu/predict_p1/predict_quotes.sqlite3'
ENGINE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
STAKE = 5.0
DELAY_MS = 236
FEE = 0.02
POLY_RATE = 0.07
ARM = 'C_fixed15'

poly_cost = lambda q: 1 + POLY_RATE * (1 - q)
poly_per1 = lambda w, q: (w / q - poly_cost(q)) / poly_cost(q)


def actual(engine, epoch):
    """Predict's rule, computed rather than borrowed: UP iff the Binance close >= the open.

    V and CLAUDE.md both write this as "candles.actual", but that column does not exist - the engine's
    candles table carries open/high/low/close/volume. So the rule is evaluated here, from open and
    close, which is what "Binance close >= open" actually means. The alternative, results.actual, is
    POLYMARKET's resolution for the v12 lane and the two disagree on ~21% of candles; using it here
    would be the cross-venue grading error, with Predict's prices and Polymarket's answers."""
    r = engine.execute('select open, close from candles where epoch=?', (epoch,)).fetchone()
    if not r or r[0] is None or r[1] is None: return None
    return 'UP' if float(r[1]) >= float(r[0]) else 'DOWN'


def quote_at(q, epoch, ts_ms, side):
    """Predict's best ask + its displayed size on `side`, at the first quote at or after ts_ms."""
    col = 'up_ask' if side == 'UP' else 'dn_ask'
    sz = 'up_ask_sz' if side == 'UP' else 'dn_ask_sz'
    r = q.execute(f'select {col}, {sz}, ts_ms from quote where epoch=? and ts_ms>=? '
                  f'and {col} is not null order by ts_ms limit 1', (epoch, ts_ms)).fetchone()
    return (r[0], r[1], r[2]) if r else (None, None, None)


def main():
    q = sqlite3.connect(f'file:{QUOTES}?mode=rw', uri=True); q.row_factory = sqlite3.Row
    q.executescript("""
    create table if not exists paper(
      epoch integer primary key, fire_ts_ms integer, side text, p real,
      predict_ask real, predict_ask_sz real, quote_ts_ms integer, shares real, capped integer,
      actual text, win integer, predict_pnl real,
      poly_ask real, poly_pnl real);""")
    q.commit()
    e = sqlite3.connect(f'file:{ENGINE}?mode=ro', uri=True)
    # No quotes yet means the collector has not run (it cannot, until a read-only key exists). Say so
    # and stop. Pricing fires without Predict quotes is precisely the substitution R-31b forbids, so
    # there is no degraded mode worth having here.
    has_q = q.execute("select count(*) from sqlite_master where type='table' and name='quote'").fetchone()[0]
    nq = q.execute('select count(*) from quote').fetchone()[0] if has_q else 0
    if not nq:
        print('NO PREDICT QUOTES YET - predict_quotes.py has never collected (it is blocked on a '
              'read-only key; every data path is HTTP 401 from Zurich). Nothing to price. This lane '
              'will not substitute Polymarket asks for Predict asks, so it stops here.', flush=True)
        return
    fires = q.execute('select * from ef_fire where arm=? order by fire_ts_ms', (ARM,)).fetchall()
    done = {r[0] for r in q.execute('select epoch from paper')}
    n = skipped_noquote = skipped_nograde = 0
    for f in fires:
        if f['epoch'] in done: continue
        act = actual(e, f['epoch'])
        if act is None: skipped_nograde += 1; continue
        pa, psz, qts = quote_at(q, f['epoch'], f['fire_ts_ms'] + DELAY_MS, f['side'])
        if pa is None or not (0.01 < pa < 0.99):
            skipped_noquote += 1; continue
        want = STAKE / pa
        sh = min(want, float(psz)) if psz else want       # capped by what is actually shown
        win = int(f['side'] == act)
        ppnl = sh * (1 - pa) - FEE * sh if win else -sh * pa
        poly = f['ask']
        polypnl = STAKE * poly_per1(win, poly) if poly and 0.01 < poly < 0.99 else None
        q.execute('insert or replace into paper values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (f['epoch'], f['fire_ts_ms'], f['side'], f['p'], pa, psz, qts, sh,
                   int(sh < want - 1e-9), act, win, ppnl, poly, polypnl))
        n += 1
    q.commit()
    r = q.execute('select count(*), coalesce(sum(predict_pnl),0), coalesce(sum(poly_pnl),0), '
                  'coalesce(sum(win),0), coalesce(sum(capped),0), coalesce(sum(shares*predict_ask),0) '
                  'from paper').fetchone()
    print(f'{time.strftime("%F %T", time.gmtime())} paper +{n} rows (no-quote {skipped_noquote}, '
          f'ungraded {skipped_nograde})', flush=True)
    if r[0]:
        print(f'  PREDICT paper: n {r[0]}, wins {r[3]}, staked ${r[5]:.2f}, pnl {r[1]:+.4f} '
              f'({r[1]/max(r[5],1e-9):+.4f}/$1), size-capped on {r[4]}', flush=True)
        print(f'  POLYMARKET control, SAME fires: pnl {r[2]:+.4f}', flush=True)
        print('  NB graded on Binance close>=open (Predict\'s rule), not Polymarket\'s resolution.',
              flush=True)


if __name__ == '__main__':
    main()
