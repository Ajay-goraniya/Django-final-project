#!/usr/bin/env python3
"""FAV - the 'calm favourite' EF brain, STAGED FOR Zurich 8787 BUT NOT DEPLOYED.

Destination is /home/ubuntu/pm_paper_zurich/poly_fav.py. Writing there was refused (Production Deploy),
so this file sits in the repo and the 8787 engine has NOT been changed. FAV is NOT live.

THE RULE IS FROZEN AND NOTHING IS TUNED - byte-for-byte the FAV arm in analysis/zurich/ef3_shadow.py:
    vol gate   Binance 1 s trailing-5-min vol measured STRICTLY BEFORE the open, < 0.304, from bn_flow,
               forward-filled across trade-less seconds with a 60 s cap, >= 240 of the 300 s present
    favourite  own ask > opp ask
    band       0.65 <= own ask <= 0.85
    window     60 <= sec <= 180
    once       the FIRST qualifying pass in a candle, one order per candle
    price      FAK at the ask; the engine's pad_ticks=1 already caps at ask + 1 tick
    stake      the engine's fixed stake ($5.00); this module never sizes anything

THIS IS THE OPPOSITE SIDE FROM build11 EF. poly_ef.EF_MAX_ASK is 0.60 because that brain buys "the side
the book has written off"; FAV buys the FAVOURITE at 0.65-0.85. FAV therefore cannot be a profile of that
brain - it is a third, separate ef_engine value whose band deliberately sits above EF_MAX_ASK.

MASTER IS NOT THIS MODULE'S BUSINESS. It never reads, writes or infers master and never places an order:
it returns a decision, and the engine's existing executor decides routing. With master off every decision
becomes a PaperBroker fill exactly as today.
"""
import math, sqlite3, time

BN_DB        = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
VOL_CUT      = 0.304
VOL_MIN_PTS  = 240
FF_MAX_S     = 60
SEC_LO, SEC_HI = 60, 180
BAND_LO, BAND_HI = 0.65, 0.85
CACHE_TTL_S  = 20


class FavBrain:
    def __init__(self, bn_db=BN_DB):
        self.bn_db = bn_db
        self._px, self._at = {}, 0.0
        self.fired_epoch = None
        self.block = ''
        self.last = {}

    def _series(self):
        now = time.monotonic()
        if self._px and (now - self._at) < CACHE_TTL_S: return self._px
        raw = {}
        try:
            c = sqlite3.connect(f'file:{self.bn_db}?mode=ro', uri=True)
            cut = int(time.time()) - 3600
            for tms, px in c.execute("SELECT ts_ms, px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                                     "AND ts_ms >= ? ORDER BY ts_ms", (cut * 1000,)):
                raw[int(tms) // 1000] = float(px)
            c.close()
        except Exception:
            return self._px
        out, last, held = {}, None, 0
        if raw:
            for t in range(min(raw), max(raw) + 1):
                if t in raw: last, held = raw[t], 0
                else:
                    held += 1
                    if held > FF_MAX_S: continue
                if last is not None: out[t] = last
        self._px, self._at = out, now
        return out

    def vol_before_open(self, epoch, px=None):
        px = self._series() if px is None else px
        w = [px[t] for t in range(epoch - 300, epoch) if t in px]
        if len(w) < VOL_MIN_PTS: return None
        m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
        if not m: return None
        mu = sum(m) / len(m)
        return math.sqrt(sum((x - mu) ** 2 for x in m) / len(m)) * 1e4

    def watch(self, epoch, sec, up_ask, dn_ask, px=None):
        if epoch == self.fired_epoch: self.block = 'fired'; return None
        if not (SEC_LO <= sec <= SEC_HI): self.block = f'sec {sec} outside window'; return None
        if up_ask is None or dn_ask is None: self.block = 'no two-sided quote'; return None
        ua, da = float(up_ask), float(dn_ask)
        if not (0.01 < ua < 0.99 and 0.01 < da < 0.99): self.block = 'quote out of range'; return None
        if ua == da: self.block = 'no favourite (asks equal)'; return None
        side = 'UP' if ua > da else 'DOWN'
        own = max(ua, da)
        if not (BAND_LO <= own <= BAND_HI): self.block = f'fav ask {own:.2f} outside band'; return None
        v = self.vol_before_open(epoch, px)
        if v is None: self.block = 'vol unavailable (<240 s of bn_flow)'; return None
        if v >= VOL_CUT: self.block = f'vol {v:.3f} >= {VOL_CUT}'; return None
        self.block = ''
        self.last = dict(epoch=epoch, sec=sec, side=side, ask=own, vol=v)
        self.fired_epoch = epoch
        p = own      # FAV is a MARKET rule with no model; the favourite's ask is not a model output
        return dict(kind='EF', side=side, p=round(p, 4),
                    probability_up=(p if side == 'UP' else 1.0 - p),
                    sec=int(sec), engine='fav', how='CALM_FAVOURITE',
                    price_rule='lane_cap', max_ask=BAND_HI, threshold=0.0,
                    fav=dict(vol=round(v, 4), vol_cut=VOL_CUT, own_ask=round(own, 4),
                             opp_ask=round(min(ua, da), 4)),
                    reason=f'FAV:CALM {side} fav ask {own:.2f} opp {min(ua,da):.2f} '
                           f'vol {v:.3f} < {VOL_CUT} sec {int(sec)}')
