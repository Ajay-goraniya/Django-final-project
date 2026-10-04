"""Predict.fun venue adapter for the v12 engine — 12.17.0.

Owner, 09-16 22:2x: *"we are moving to predict, not polymarket anymore ... i like the
signal logics and everything we have now it does so well in this, but when it comes to
execution and fees predict is way cheaper, with almost 98% fill rate."*

So the signal stays exactly as it is — `btc_model_v10.py`, `poly_lanes.py` and
`poly_core.py` are not touched by this file — and only the venue changes: where the
book comes from, and what a "token" is.

Everything here is lifted from the engine that already trades Predict.fun in
production (`learner/btc_model_build11.py`), not invented:

* discovery   `GET /v1/markets?first=&status=OPEN&marketVariant=CRYPTO_UP_DOWN`,
              paged by `cursor`, ranked to the exact candle  (build11:9843-9900)
* bootstrap   `GET /v1/markets/{id}/orderbook`                (build11:9965-9975)
* stream      `wss://ws.predict.fun/ws`, `{"method":"subscribe",
              "params":["predictOrderbook/{market_id}"]}`, frames
              `{"type":"M","topic":"predictOrderbook/..","data":{..}}`
                                                              (build11:10262-10380)

**The one structural difference from Polymarket, and it matters.** Polymarket quotes two
independent token books, UP and DOWN, each with its own spread. Predict quotes ONE
YES-centric ladder, and the NO side is its exact complement — build11:9440-9445 builds
DOWN as `asks = 1 - bids` and `bids = 1 - asks`. So on Predict:

    ask_dn == 1 - bid_up    and    ask_up == 1 - bid_dn

identically, by construction. `p_venue` therefore comes from a single ladder rather than
from two books that can disagree, and the two sides can never both be cheap. Nothing in
this file hides that: it emits both sides so the unchanged engine can price either, and
`complement()` is the only place the relationship is expressed.

This adapter is **read-only**. It resolves markets and feeds books; it signs nothing and
sends no orders, so an engine using it runs against `PaperBroker` and cannot place a live
trade even if master is on. Live execution on Predict is a separate build and a separate
decision by the owner.

No credential is read, printed or logged here beyond handing an opaque bearer token from
the environment to the HTTP layer; discovery works unauthenticated where the venue allows
it, and `PREDICT_JWT`/`PREDICT_API_KEY` are only used if already present in the process
environment.
"""
import json, math, os, time, urllib.parse, urllib.request

BASE = os.environ.get('PREDICT_BASE', 'https://api.predict.fun')
WS = os.environ.get('PREDICT_WS', 'wss://ws.predict.fun/ws')
SEARCH_LIMIT = 100
MAX_PAGES = 3
TIMEOUT = 6.0
CANDLE_S = 300
# build11:585. Declared, not measured — R-31 measures what the venue actually takes.
FEE_RATE = 0.02
UA = {'User-Agent': 'btc-model-v12/predict', 'Accept': 'application/json'}


def _auth_headers():
    """Bearer only if the operator already put one in the environment."""
    h = dict(UA)
    tok = os.environ.get('PREDICT_JWT') or os.environ.get('PREDICT_API_KEY')
    if tok:
        h['Authorization'] = 'Bearer ' + tok
    return h


def get_json(path, params=None, timeout=TIMEOUT):
    url = BASE.rstrip('/') + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=_auth_headers())
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def flatten_markets(payload):
    """build11:9596. The listing has been seen as a bare list, {data:[..]} and
    {items:[..]}; accept all three rather than guessing one."""
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ('data', 'items', 'markets', 'results'):
        v = payload.get(key)
        if isinstance(v, list):
            return [m for m in v if isinstance(m, dict)]
    return []


def market_epoch(item):
    """The 5-minute epoch a market settles on, or None.

    Tries the explicit timestamps first and only then the slug, because a slug is
    a string the venue is free to restyle while `closeTime` is contractual.
    """
    for key in ('closeTimeMs', 'closeTime', 'endTimeMs', 'endTime',
                'resolutionTimeMs', 'expiresAtMs', 'expiresAt'):
        v = item.get(key)
        if v is None:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(n) or n <= 0:
            continue
        secs = n / 1000.0 if n > 1e11 else n
        # The market ENDS at the epoch boundary; the candle it settles is the one
        # that opened 300 s earlier.
        return int(secs // CANDLE_S) * CANDLE_S - CANDLE_S
    for key in ('slug', 'categorySlug', '_category_slug', 'ticker'):
        s = str(item.get(key) or '')
        if not s:
            continue
        tail = s.rsplit('-', 1)[-1]
        if tail.isdigit() and len(tail) >= 9:
            return int(tail) // CANDLE_S * CANDLE_S
    return None


def rank_markets(items, ep):
    """build11:9634. Open BTC up/down markets for exactly this candle."""
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        status = str(m.get('status') or m.get('state') or 'OPEN').upper()
        if status not in ('OPEN', 'ACTIVE', 'TRADING', ''):
            continue
        if m.get('closed') or m.get('resolved'):
            continue
        if market_epoch(m) != int(ep):
            continue
        out.append(m)
    return out


def outcome_token(item, direction):
    """build11:9397. UP is YES; the id may be onChainId, tokenId or id."""
    outs = item.get('outcomes') or item.get('marketOutcomes') or []
    want = {'UP', 'YES'} if direction == 'UP' else {'DOWN', 'NO'}
    chosen = None
    if isinstance(outs, list):
        for o in outs:
            if not isinstance(o, dict):
                continue
            label = str(o.get('name') or o.get('label') or o.get('title')
                        or o.get('side') or '').strip().upper()
            if label in want:
                chosen = o
                break
        if chosen is None and len(outs) >= 2:
            chosen = outs[0 if direction == 'UP' else 1]
    if not isinstance(chosen, dict):
        return None
    tid = chosen.get('onChainId') or chosen.get('tokenId') or chosen.get('id')
    return None if tid is None else str(tid)


def levels(raw):
    """Normalise a ladder to [(price, size)], dropping anything unusable.

    Accepts [{'price','size'|'quantity'|'amount'}] and [[price, size]].
    """
    out = []
    for lv in raw if isinstance(raw, list) else []:
        if isinstance(lv, dict):
            p = lv.get('price')
            q = lv.get('size', lv.get('quantity', lv.get('amount')))
        elif isinstance(lv, (list, tuple)) and len(lv) >= 2:
            p, q = lv[0], lv[1]
        else:
            continue
        try:
            p = float(p); q = float(q)
        except (TypeError, ValueError):
            continue
        if math.isfinite(p) and math.isfinite(q) and 0.0 < p < 1.0 and q > 0.0:
            out.append((p, q))
    return out


def complement(asks, bids):
    """build11:9440. The NO book is the YES book reflected through 1.0.

    A NO ask is a YES bid: someone bidding 0.40 for UP is offering DOWN at 0.60.
    """
    return (sorted((round(1.0 - p, 8), q) for p, q in bids),
            sorted(((round(1.0 - p, 8), q) for p, q in asks), reverse=True))


def book_events(up_token, down_token, data, now_ms=None):
    """Turn one `predictOrderbook` payload into BookCache `book` events.

    `poly_core.BookCache.apply` is untouched by this port: it is fed the same
    shape it already accepts from Polymarket, so the book, the freshness rules
    and the clock-skew correction behave identically on both venues.
    """
    if not isinstance(data, dict):
        return []
    asks = levels(data.get('asks'))
    bids = levels(data.get('bids'))
    if not asks and not bids:
        return []
    try:
        stamp = int(data.get('updateTimestampMs') or data.get('timestamp')
                    or (now_ms if now_ms is not None else time.time() * 1000))
    except (TypeError, ValueError):
        return []
    dn_asks, dn_bids = complement(asks, bids)

    def ev(token, a, b):
        return {'event_type': 'book', 'asset_id': str(token), 'timestamp': str(stamp),
                'asks': [{'price': str(p), 'size': str(q)} for p, q in a],
                'bids': [{'price': str(p), 'size': str(q)} for p, q in b]}

    return [ev(up_token, asks, bids), ev(down_token, dn_asks, dn_bids)]


class PredictVenue:
    """Market discovery and book snapshots for one BTC 5-minute candle.

    Deliberately holds no socket and no thread: the engine owns its event loop,
    and this object is a resolver plus a message translator, so it can be unit
    tested against recorded payloads with no network at all.
    """

    def __init__(self, get=get_json):
        self._get = get
        self.market = {}     # ep -> (market_id, up_token, down_token)
        self.info = {}       # ep -> the raw listing item
        self.error = ''

    def resolve(self, ep):
        """Return (market_id, up_token, down_token) for `ep`, or None."""
        ep = int(ep)
        hit = self.market.get(ep)
        if hit:
            return hit
        items, after = [], None
        for _ in range(MAX_PAGES):
            params = {'first': SEARCH_LIMIT, 'status': 'OPEN',
                      'marketVariant': 'CRYPTO_UP_DOWN'}
            if after:
                params['after'] = after
            payload = self._get('/v1/markets', params)
            if payload is None:
                self.error = 'markets: no response'
                break
            items.extend(flatten_markets(payload))
            if rank_markets(items, ep):
                break
            after = payload.get('cursor') if isinstance(payload, dict) else None
            if not after:
                break
        cands = rank_markets(items, ep)
        if not cands:
            # build11:9885 keeps search as a compatibility fallback only; it is
            # rate limited far harder than the listing, so it is tried once.
            payload = self._get('/v1/search', {'query': 'BTC Up or Down 5m',
                                               'includeResolved': 'false',
                                               'limit': SEARCH_LIMIT})
            cands = rank_markets(flatten_markets(payload), ep)
        for m in cands:
            mid = m.get('id') or m.get('marketId')
            up = outcome_token(m, 'UP')
            dn = outcome_token(m, 'DOWN')
            if mid is None or not up or not dn or up == dn:
                continue
            self.market[ep] = (str(mid), up, dn)
            self.info[ep] = m
            self.error = ''
            return self.market[ep]
        if not self.error:
            self.error = 'no open BTC 5m market for this candle'
        return None

    def snapshot(self, ep):
        """REST bootstrap for a candle's book, as BookCache events.

        build11 takes exactly one of these per market and then lives on the
        socket; polling an existing ladder is what its comment at :9962 warns
        against, so this is called on subscribe, not on a timer.
        """
        m = self.resolve(ep)
        if not m:
            return []
        mid, up, dn = m
        payload = self._get('/v1/markets/%s/orderbook' % mid)
        if isinstance(payload, dict):
            data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
            return book_events(up, dn, data)
        return []

    def subscribe_frame(self, ep, request_id=1):
        """build11:10262. The socket subscribe for this candle's ladder."""
        m = self.resolve(ep)
        if not m:
            return None
        return json.dumps({'jsonrpc': '2.0', 'id': int(request_id),
                           'method': 'subscribe',
                           'params': ['predictOrderbook/%s' % m[0]]})

    def on_message(self, msg):
        """Translate one raw socket frame into BookCache events.

        Unknown frames — acks, heartbeats, wallet events, anything the venue adds
        later — return [] rather than raising. 12.15.3 taught us that a frame the
        parser cannot read must never tear down the feed the money is priced on.
        """
        if isinstance(msg, (bytes, bytearray)):
            msg = msg.decode('utf-8', 'replace')
        if not str(msg).strip():
            return []
        try:
            frame = json.loads(msg)
        except ValueError:
            return []
        if not isinstance(frame, dict):
            return []
        topic = str(frame.get('topic') or '')
        if not topic.startswith('predictOrderbook/'):
            return []
        data = frame.get('data')
        if not isinstance(data, dict):
            return []
        mid = topic.split('/', 1)[1]
        for ep, (m, up, dn) in self.market.items():
            if str(m) == mid:
                return book_events(up, dn, data)
        return []

    def prune(self, before_ep):
        for ep in [e for e in self.market if e < before_ep]:
            self.market.pop(ep, None)
            self.info.pop(ep, None)
