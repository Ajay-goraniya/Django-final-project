#!/usr/bin/env python3
"""FAV - the 'calm favourite' EF brain (owner, 09-30 00:4x: "Deploy this on Zurich 8787 with master off").

THE RULE IS FROZEN AND NOTHING HERE IS TUNED. It is the FAV arm registered in the forward shadow
(analysis/zurich/ef3_shadow.py), and a replay of the engine's own decide_log through this module
reproduces the shadow's FAV decisions byte-for-byte on candle, side, sec and ask (40/40):
    vol gate   Binance 1 s trailing-5-min vol measured STRICTLY BEFORE the open, < 0.304, from bn_flow,
               forward-filled across trade-less seconds with a 60 s cap, >= 240 of the 300 s present
    favourite  own ask > opp ask
    band       0.65 <= own ask <= 0.85
    window     60 <= sec <= 180
    once       the first qualifying pass in a candle, one order per candle
    price      FAK at the ask; the engine's pad_ticks=1 already caps at ask + 1 tick
    stake      the engine's own fixed stake; this module never sizes anything

THIS IS THE OPPOSITE SIDE FROM build11 EF. poly_ef.EF_MAX_ASK is 0.60 because that brain buys "the side
the book has written off"; FAV buys the FAVOURITE at 0.65-0.85. FAV therefore cannot be a profile or a
parameter of that brain - it is a third, separate ef_engine value whose band sits entirely above
EF_MAX_ASK, and switching to it REPLACES what EF does rather than tuning it.

STATELESS ON FIRING, DELIBERATELY. poly_lanes._try_ef already owns once-per-candle (self.ef.fired), the
retry budget (self.ef.attempts) and the blocked set. If this module ALSO latched a fired epoch it would
veto the lane's own legitimate retries after a failed submit. The only state here is a short cache of the
1 s price series, so a 250 ms decision loop does not re-read the recorder database on every pass.

MASTER IS NOT THIS MODULE'S BUSINESS. It never reads, writes or infers master and never places an order:
it returns a decision and the engine's existing executor decides routing. With master off every decision
becomes a PaperBroker fill exactly as before.
"""
import math, sqlite3, time

BN_DB        = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
VOL_CUT      = 0.304      # frozen 09-22/23 Binance tercile; do NOT recompute forward
VOL_MIN_PTS  = 240        # of the 300 s before the open
FF_MAX_S     = 60         # longest trade-less run the 1 s series will bridge
SEC_LO, SEC_HI = 60, 180
BAND_LO, BAND_HI = 0.65, 0.85
CACHE_TTL_S  = 20
LOOKBACK_S   = 3600       # only the last hour is ever needed for a 300 s window


class FavBrain:
    """One instance per engine."""

    def __init__(self, bn_db=BN_DB):
        self.bn_db = bn_db
        self._px, self._at = {}, 0.0
        self.block = ''
        self.last = {}
        self.feed_error = None

    # ---- the 1 s Binance series, same construction as the shadow's _bn_1s -------------------------
    def _series(self):
        now = time.monotonic()
        if self._px and (now - self._at) < CACHE_TTL_S:
            return self._px
        raw = {}
        try:
            c = sqlite3.connect(f'file:{self.bn_db}?mode=ro', uri=True)
            cut = (int(time.time()) - LOOKBACK_S) * 1000
            for tms, px in c.execute("SELECT ts_ms, px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                                     "AND ts_ms >= ? ORDER BY ts_ms", (cut,)):
                raw[int(tms) // 1000] = float(px)
            c.close()
            self.feed_error = None
        except Exception as e:
            # keep the previous series rather than pretend the feed is empty; an empty series would read
            # as "vol unavailable" and silently stop FAV instead of reporting a broken recorder.
            self.feed_error = type(e).__name__
            return self._px
        out, last, held = {}, None, 0
        if raw:
            for t in range(min(raw), max(raw) + 1):
                if t in raw:
                    last, held = raw[t], 0
                else:
                    held += 1
                    if held > FF_MAX_S:
                        continue          # a real outage stays a hole, so the 240 s gate refuses the candle
                if last is not None:
                    out[t] = last
        self._px, self._at = out, now
        return out

    def vol_before_open(self, epoch, px=None):
        """1 s log-return std over [epoch-300, epoch), x1e4. None = not enough data = NO FIRE."""
        px = self._series() if px is None else px
        w = [px[t] for t in range(epoch - 300, epoch) if t in px]
        if len(w) < VOL_MIN_PTS:
            return None
        m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
        if not m:
            return None
        mu = sum(m) / len(m)
        return math.sqrt(sum((x - mu) ** 2 for x in m) / len(m)) * 1e4

    # ---- the decision ------------------------------------------------------------------------------
    def watch(self, epoch, sec, up_ask, dn_ask, px=None):
        """EF-shaped decision dict, or None with self.block set. No order, no master read."""
        if epoch is None:
            self.block = 'no candle epoch'; return None
        if not (SEC_LO <= sec <= SEC_HI):
            self.block = f'sec {sec} outside {SEC_LO}-{SEC_HI}'; return None
        if up_ask is None or dn_ask is None:
            self.block = 'no two-sided quote'; return None
        ua, da = float(up_ask), float(dn_ask)
        if not (0.01 < ua < 0.99 and 0.01 < da < 0.99):
            self.block = 'quote out of range'; return None
        if ua == da:
            self.block = 'no favourite (asks equal)'; return None
        side = 'UP' if ua > da else 'DOWN'
        own, opp = max(ua, da), min(ua, da)
        if not (BAND_LO <= own <= BAND_HI):
            self.block = f'fav ask {own:.2f} outside {BAND_LO}-{BAND_HI}'; return None
        v = self.vol_before_open(epoch, px)
        if v is None:
            self.block = ('vol unavailable: bn_flow ' + self.feed_error) if self.feed_error \
                         else f'vol unavailable (<{VOL_MIN_PTS} s of bn_flow)'
            return None
        if v >= VOL_CUT:
            self.block = f'vol {v:.3f} >= {VOL_CUT}'; return None
        self.block = ''
        self.last = dict(epoch=epoch, sec=int(sec), side=side, ask=own, vol=v)
        # p is the market's own favourite price. FAV is a MARKET rule with NO model, so the favourite's
        # ask is the honest probability estimate; it is not a model output and must not be read as one.
        p = own
        return dict(kind='EF', side=side, p=round(p, 4),
                    probability_up=(p if side == 'UP' else 1.0 - p),
                    sec=int(sec), engine='fav', how='CALM_FAVOURITE',
                    price_rule='lane_cap', max_ask=BAND_HI, threshold=0.0,
                    fav=dict(vol=round(v, 4), vol_cut=VOL_CUT, own_ask=round(own, 4), opp_ask=round(opp, 4)),
                    reason=f'FAV:CALM {side} fav ask {own:.2f} opp {opp:.2f} '
                           f'vol {v:.3f} < {VOL_CUT} sec {int(sec)}')

    # ---- fire-time recheck -------------------------------------------------------------------------
    def still_valid(self, side, up_ask, dn_ask):
        """Does the call still hold on the current book, at submit time?

        This exists because poly_lanes.still_valid('EF', ...) re-applies the build11 GATE TABLE, which a
        FAV decision was never judged on and would essentially always fail - the order would be released
        as SIGNAL_CHANGED and never submitted. So FAV supplies its own recheck, and it rechecks FAV's own
        premise: is our side still the favourite, and still inside the band? Vol is a per-candle number
        measured before the open and cannot change; sec is not re-tested because the order is already in
        flight. If the favourite has flipped, the reason for the trade is gone.
        """
        if up_ask is None or dn_ask is None:
            return False
        ua, da = float(up_ask), float(dn_ask)
        if not (0.01 < ua < 0.99 and 0.01 < da < 0.99):
            return False
        if ua == da:
            return False
        live = 'UP' if ua > da else 'DOWN'
        if live != side:
            return False
        own = max(ua, da)
        return BAND_LO <= own <= BAND_HI
