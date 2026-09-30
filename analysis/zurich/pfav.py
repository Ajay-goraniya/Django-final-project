#!/usr/bin/env python3
"""Arm PFAV - PASSIVE favourite, PAPER ONLY, forward shadow. Owner said YES 09-30 09:4x to a paper
passive-FAV; NOT to live. This module places no orders, touches no engine setting and never reads or
writes master. It only scores candles and writes rows into the shadow's fires table.

RULE, exactly as V specified (frozen before the first row):
  window     sec 60-180
  favourite  the side whose best BID is in [0.60, 0.80]   (BID, not ask - this is a maker arm)
  post       a virtual bid AT that best bid from the first qualifying second; RE-JOIN if the best bid
             rises and is still in band; cancel at 180 s
  fill       the first public-tape print after our post, either on our token at price <= our bid, or on
             the OTHER token at >= 1 - bid (the mint mirror), with >= SH shares in that second.
             Tape timestamps are data-api's, which run ~2.2 s ahead of candle seconds, so sec = ts - 2.2 - epoch.
  money      no fee, no rebate, $10, held to gamma settlement
  arms       PFAV (SH>=14, TOUCH fill: a print at <= our bid), PFAV50 (SH>=50, queue-depth check),
             PFAV_THRU (SH>=14 but the print must trade STRICTLY THROUGH our bid - < bid on our token,
             or > 1-bid on the other), PFAV_taker (taker FAV on the SAME candles, for pairing)
  WHY THRU    V's strict 20-day test (STRICT_PFAV_CALM.txt, M5) BROKE the account: -335 to -778 over
             09-11..30, 0-2 days positive. M2 was lenient. A print AT our bid does not prove our order
             filled - we would be behind the queue at that level. A print THROUGH it proves the level
             was consumed past us. PFAV_THRU is the honest fill and is expected to be worse, not better.
  +1c        every PFAV arm also stores pnl_1c: the same trade paying one cent more (bid + 0.01), in
             its OWN column. It is NOT folded into pnl_part, which already means "partial fill" for the
             FAV family - one column with two meanings across arm families is how silent errors start.
  vol        Binance 1 s trailing 5-min, cuts 0.304/0.466, logged so calm and all both report

WHY A SEPARATE MODULE: ef3_shadow scores from decide_log; PFAV needs the 1 s book (best bid) and the
public tape. Bolting it into build_rows would have put a second data contract inside the function whose
row-for-row parity every other registered arm depends on. It writes to the same fires table, so the
daily report picks the arms up with no change there.
"""
import sqlite3, sys, math, time, datetime as dt

SHADOW = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
BOOKS  = '/home/ubuntu/pm_multi/multi_market.sqlite3'
TAPE   = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
GAMMA  = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
BN_DB  = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
LAG, S0, S1, LO, HI = 2.2, 60, 180, 0.60, 0.80
STAKE = 10.0
VOL_LOW, VOL_MID, VOL_MIN_PTS, FF_MAX = 0.304, 0.466, 240, 60


def bn_series():
    raw = {}
    try:
        c = sqlite3.connect(f'file:{BN_DB}?mode=ro', uri=True)
        for tms, px in c.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL ORDER BY ts_ms"):
            raw[int(tms) // 1000] = float(px)
    except Exception:
        return {}
    out, last, held = {}, None, 0
    if raw:
        for t in range(min(raw), max(raw) + 1):
            if t in raw: last, held = raw[t], 0
            else:
                held += 1
                if held > FF_MAX: continue
            if last is not None: out[t] = last
    return out


def vol_at(px, ep):
    w = [px[t] for t in range(ep - 300, ep) if t in px]
    if len(w) < VOL_MIN_PTS: return None
    m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
    if not m: return None
    mu = sum(m) / len(m)
    return math.sqrt(sum((x - mu) ** 2 for x in m) / len(m)) * 1e4


def score(ep, bk, tape, toks, win_tok, px):
    """Return dict arm -> (side_up, bid, sec, filled, won, pnl) for this candle, or {}."""
    up_tok, dn_tok = toks
    rows = {int(t): (ub, db_) for t, ub, db_ in bk}
    out = {}
    # --- the passive post: first second in window whose best bid is in band, re-joining on a rise
    post = None                      # (sec, side_up, bid)
    for s in range(S0, S1 + 1):
        r = rows.get(ep + s)
        if not r: continue
        ub, db_ = r
        for is_up, b in ((1, ub), (0, db_)):
            if b is None: continue
            b = float(b)
            if not (LO <= b <= HI): continue
            if post is None or (is_up == post[1] and b > post[2] and LO <= b <= HI):
                post = (s, is_up, b) if post is None else (post[0], is_up, b)
            break
        if post: break
    if post is None: return out
    sec0, is_up, bid = post
    # re-join: track the best bid on OUR side while it rises and stays in band
    for s in range(sec0, S1 + 1):
        r = rows.get(ep + s)
        if not r: continue
        b = r[0] if is_up else r[1]
        if b is None: continue
        b = float(b)
        if b > bid and LO <= b <= HI: bid = b
    our_tok = up_tok if is_up else dn_tok
    oth_tok = dn_tok if is_up else up_tok
    # --- fills: per second, maker shares on our token at <= bid, or the mint mirror on the other
    # SIDE MATTERS. A resting BUY is filled when someone SELLS into it, and the tape row that evidences
    # it is the MAKER BUY print - that is a buy-side resting order being hit. Counting SELL prints as
    # well would treat "someone sold down there" as proof our bid filled, which it is not.
    # analysis/v/maker2/passive_fav.py does exactly this (`if sd != 'BUY': continue`); my first version
    # omitted it and counted both sides.
    per = {}; thru = {}
    for ts, asset, price, size, is_taker, side in tape:
        s = (ts - LAG) - ep
        if not (sec0 <= s <= S1): continue
        if is_taker: continue                       # PASSIVE arm fills against MAKER prints
        if side != 'BUY': continue
        sec = int(s)
        if asset == our_tok and price <= bid + 1e-9: per[sec] = per.get(sec, 0.0) + size
        elif asset == oth_tok and price >= (1.0 - bid) - 1e-9: per[sec] = per.get(sec, 0.0) + size
        # STRICTLY through: < our bid on our token, > 1-bid on the other. Equality does not count.
        if asset == our_tok and price < bid - 1e-9: thru[sec] = thru.get(sec, 0.0) + size
        elif asset == oth_tok and price > (1.0 - bid) + 1e-9: thru[sec] = thru.get(sec, 0.0) + size
    won = 1.0 if our_tok == win_tok else 0.0
    for arm, need, src in (('PFAV', 14.0, per), ('PFAV50', 50.0, per), ('PFAV_THRU', 14.0, thru)):
        hit = next((s for s in sorted(src) if src[s] >= need), None)
        if hit is None: out[arm] = (is_up, bid, sec0, 0, won, 0.0, 0.0)
        else:
            pnl  = (STAKE / bid - STAKE) if won else -STAKE            # no fee, no rebate
            p1c  = (STAKE / min(bid + 0.01, 0.99) - STAKE) if won else -STAKE
            out[arm] = (is_up, bid, hit, 1, won, pnl, p1c)
    # --- taker FAV on the SAME candle, for pairing: first TAKER buy in window/band
    tk = sorted(((ts - LAG) - ep, asset, price) for ts, asset, price, size, is_taker, side in tape
              if is_taker and side == 'BUY')
    ft = next(((s, a, p) for s, a, p in tk if S0 <= s <= S1 and LO <= p <= HI), None)
    if ft:
        s, a, p = ft
        w2 = 1.0 if a == win_tok else 0.0
        cost = p + 0.07 * p * (1 - p)
        c1 = min(p + 0.01, 0.99); c1 = c1 + 0.07 * c1 * (1 - c1)
        out['PFAV_taker'] = (1 if a == up_tok else 0, p, int(s), 1, w2,
                             (STAKE / cost - STAKE) if w2 else -STAKE,
                             (STAKE / c1 - STAKE) if w2 else -STAKE)
    return out


def main():
    px = bn_series()
    sh = sqlite3.connect(SHADOW)
    have = {r[1] for r in sh.execute('PRAGMA table_info(fires)')}
    if 'pnl_1c' not in have:
        sh.execute('ALTER TABLE fires ADD COLUMN pnl_1c REAL'); sh.commit()
    bkc = sqlite3.connect(f'file:{BOOKS}?mode=ro', uri=True)
    tpc = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
    gmc = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)
    done = {e for (e,) in sh.execute("SELECT DISTINCT epoch FROM fires WHERE arm='PFAV'")}
    eps = [e for (e,) in tpc.execute('SELECT DISTINCT epoch FROM tape ORDER BY epoch') if e not in done]
    n = 0
    for ep in eps:
        g = gmc.execute("SELECT tok_up,tok_dn,outcome FROM mkt WHERE asset='btc' AND epoch=?", (ep,)).fetchone()
        if not g or not g[2]: continue                       # unsettled: wait, do not guess
        up_tok, dn_tok, oc = g
        win_tok = up_tok if oc == 'UP' else dn_tok
        bk = bkc.execute("SELECT ts,up_bid,dn_bid FROM books WHERE market='btc5' AND epoch=?", (ep,)).fetchall()
        if not bk: continue
        tape = tpc.execute('SELECT ts,asset,price,size,is_taker,side FROM tape WHERE epoch=?', (ep,)).fetchall()
        if not tape: continue
        res = score(ep, bk, tape, (up_tok, dn_tok), win_tok, px)
        if not res: continue
        v = vol_at(px, ep)
        day = dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%m-%d')
        for arm, (is_up, bid, sec, filled, won, pnl, p1c) in res.items():
            sh.execute('INSERT OR REPLACE INTO fires(epoch,arm,ts_ms,day,sec,up,p,ask,fill,opp_fill,win,pnl,sh,vwap,pnl_part,pnl_1c)'
                       ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (ep, arm, (ep + sec) * 1000, day, sec, is_up, (v if v is not None else None), bid,
                        (bid if filled else None), None, int(won), pnl,
                        (STAKE / bid if filled else 0.0), (bid if filled else None), pnl, p1c))
            n += 1
        sh.commit()
    print(f'{dt.datetime.now(dt.UTC):%H:%M:%S} PFAV scored {len(eps)} candle(s), wrote {n} row(s)')


if __name__ == '__main__':
    main()
