"""Binance feed endpoints, per-stream failover and honest staleness measurement.

Why this module exists
----------------------
v12.1 measured feed health as "time since we last received a message".  That is
an ARRIVAL age.  It answers "is the socket alive", not "is the data current".
A venue or network that is lagging keeps delivering messages, so the arrival age
stays near zero while every price in them is seconds old.  The decision gate
then passes on stale inputs and the dashboard reports the feed as LIVE.

Every stream here therefore carries two independent numbers:

  arrival_age_s  now - (time we last received anything)      -> socket liveness
  event_lag_s    (time we received it) - (its own event time) -> data freshness

A stream is usable only when BOTH are inside their limits.  They fail in
different ways and neither substitutes for the other.

Endpoints are lists, not constants, because reachability is host-dependent.
Measured from the build container on 2026-09-12: every REST host under
api.binance.com / fapi.binance.com answers HTTP 451, while
data-api.binance.vision serves the identical /api/v3 payloads; on websockets
data-stream.binance.vision and fstream.binance.com both connect, but
stream.binance.com resets and fstream-mm.binance.com refuses.  A deployment in
another region will draw a different line, so each stream tries its candidates
in order and remembers which one worked.
"""
import asyncio, json, os, time, urllib.request

UA = {"User-Agent": "learner-v10/1.0"}


def _env_list(name, default):
    raw = os.environ.get(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()] or list(default)


# REST base URLs for candle seeding/backfill, first reachable wins.
REST_HOSTS = _env_list("BINANCE_REST_HOSTS", [
    "https://data-api.binance.vision",   # serves /api/v3 and is not geo-filtered
    "https://api.binance.com",
    "https://api-gcp.binance.com",
])

# Websocket candidates per logical stream, tried in order.
WS_STREAMS = {
    "spot":  _env_list("BINANCE_WS_SPOT", [
        "wss://data-stream.binance.vision/ws/btcusdt@aggTrade",
        "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
    ]),
    "perp":  _env_list("BINANCE_WS_PERP", [
        "wss://fstream.binance.com/ws/btcusdt@trade",
        "wss://fstream.binance.com/stream?streams=btcusdt@trade",
    ]),
    "depth": _env_list("BINANCE_WS_DEPTH", [
        "wss://fstream.binance.com/ws/btcusdt@depth20@100ms",
        "wss://fstream.binance.com/stream?streams=btcusdt@depth20@100ms",
    ]),
    "chart": _env_list("BINANCE_WS_CHART", [
        "wss://data-stream.binance.vision/ws/btcusdt@kline_5m",
        "wss://stream.binance.com:9443/ws/btcusdt@kline_5m",
    ]),
}

# Limits. Arrival covers a dead or half-open socket; lag covers stale data.
#
# The arrival limit has to be per stream, because these streams are not the same
# shape.  depth is periodic at 100ms; spot and perp are event driven and go quiet
# whenever nobody trades.  Measured over 100s on a live connection:
#
#     stream   median   p95     p99     max
#     spot       0ms    690ms  1483ms  2617ms
#     perp       0ms    302ms   886ms  2433ms
#     depth    103ms    148ms   253ms   520ms
#
# v12.1 applied one flat 2.0s arrival limit to all three, which is below the
# observed maximum gap on both event-driven streams.  That alone makes a healthy
# feed intermittently register as stale and blocks firing for no reason.  The
# defaults below give the event streams roughly 2.5x their observed worst gap
# and keep depth tight, since a periodic stream that stops really has stopped.
MAX_ARRIVAL_AGE_S = float(os.environ.get("FEED_MAX_ARRIVAL_AGE_S", "6.0"))
ARRIVAL_LIMITS = {
    "spot":  float(os.environ.get("FEED_MAX_ARRIVAL_SPOT_S", "6.0")),
    "perp":  float(os.environ.get("FEED_MAX_ARRIVAL_PERP_S", "6.0")),
    "depth": float(os.environ.get("FEED_MAX_ARRIVAL_DEPTH_S", "2.0")),
    "venue": float(os.environ.get("FEED_MAX_ARRIVAL_VENUE_S", "5.0")),
}
MAX_EVENT_LAG_S   = float(os.environ.get("FEED_MAX_EVENT_LAG_S", "2.5"))
# Force a reconnect rather than waiting out the websocket ping timeout.
STALL_RECONNECT_S = float(os.environ.get("FEED_STALL_RECONNECT_S", "8.0"))


def rest_json(path, timeout=8, hosts=None):
    """GET path from the first REST host that answers. Returns (json, host)."""
    errors = []
    for host in (hosts or REST_HOSTS):
        url = host.rstrip("/") + path
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read()), host
        except Exception as e:
            errors.append(f"{host}: {type(e).__name__}")
    return None, "; ".join(errors)


class FeedHealth:
    """Per-stream arrival age and event lag, with the host that is serving it."""

    def __init__(self, names=("spot", "perp", "depth", "venue")):
        self.arrival = {n: 0.0 for n in names}   # wall clock of last message
        self.lag = {n: None for n in names}      # seconds behind the event time
        self.msgs = {n: 0 for n in names}
        self.host = {n: None for n in names}
        self.reconnects = {n: 0 for n in names}
        self.clock_skew_s = 0.0                  # local minus venue, see note()

    def note(self, name, event_ms=None, now=None):
        """Record one received message. event_ms is the message's own timestamp."""
        now = time.time() if now is None else now
        self.arrival[name] = now
        self.msgs[name] = self.msgs.get(name, 0) + 1
        if event_ms:
            lag = now - float(event_ms) / 1000.0
            # A negative lag means our clock is behind the exchange's. Keep the
            # magnitude as skew and clamp the lag at zero rather than reporting a
            # feed as impossibly fresh.
            if lag < 0:
                self.clock_skew_s = min(self.clock_skew_s, lag)
                lag = 0.0
            self.lag[name] = lag

    def arrival_age(self, name, now=None):
        last = self.arrival.get(name) or 0.0
        if not last:
            return None
        return (time.time() if now is None else now) - last

    def event_lag(self, name):
        return self.lag.get(name)

    def limit_for(self, name, override=None):
        if override is not None: return override
        return ARRIVAL_LIMITS.get(name, MAX_ARRIVAL_AGE_S)

    def stale(self, names, max_arrival=None, max_lag=None):
        """Return the streams that fail either check, with the reason."""
        max_lag = MAX_EVENT_LAG_S if max_lag is None else max_lag
        bad = {}
        for n in names:
            limit = self.limit_for(n, max_arrival)
            age = self.arrival_age(n)
            if age is None:
                bad[n] = "no data yet"
                continue
            if age > limit:
                bad[n] = f"no message for {age:.1f}s (limit {limit:.0f}s)"
                continue
            lag = self.event_lag(n)
            if lag is not None and lag > max_lag:
                bad[n] = f"data {lag:.1f}s behind its event time"
        return bad

    def snapshot(self, names=None):
        names = names or list(self.arrival)
        return {
            "arrival_age_s": {n: (round(self.arrival_age(n), 3) if self.arrival_age(n) is not None else None) for n in names},
            "event_lag_s": {n: (round(self.lag[n], 3) if self.lag.get(n) is not None else None) for n in names},
            "messages": {n: self.msgs.get(n, 0) for n in names},
            "host": {n: self.host.get(n) for n in names},
            "reconnects": {n: self.reconnects.get(n, 0) for n in names},
            "clock_skew_s": round(self.clock_skew_s, 3),
            "limits": {"max_arrival_age_s": {n: self.limit_for(n) for n in names}, "max_event_lag_s": MAX_EVENT_LAG_S},
        }


async def run_stream(name, handler, health, event_key=("E", "T"), urls=None):
    """Keep one logical stream connected, failing over between candidate hosts.

    A stream that stops delivering is force-reconnected after STALL_RECONNECT_S
    instead of waiting for the websocket ping timeout, which can leave a
    half-open TCP connection hanging for the better part of a minute.
    """
    import websockets
    candidates = list(urls or WS_STREAMS.get(name) or [])
    if not candidates:
        raise ValueError(f"no websocket endpoint configured for {name}")
    i = 0
    while True:
        url = candidates[i % len(candidates)]
        try:
            async with websockets.connect(url, ping_interval=15, ping_timeout=10,
                                          open_timeout=15, max_size=2 ** 22) as w:
                health.host[name] = url.split("/")[2]
                while True:
                    try:
                        msg = await asyncio.wait_for(w.recv(), STALL_RECONNECT_S)
                    except asyncio.TimeoutError:
                        raise ConnectionError(f"no message for {STALL_RECONNECT_S:.0f}s")
                    j = json.loads(msg)
                    if isinstance(j, dict) and "data" in j and "stream" in j:
                        j = j["data"]           # combined-stream envelope
                    stamp = None
                    for k in event_key:
                        if isinstance(j, dict) and j.get(k):
                            stamp = j[k]
                            break
                    handler(j)
                    health.note(name, stamp)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            health.reconnects[name] = health.reconnects.get(name, 0) + 1
            i += 1                              # next attempt uses the next host
            nxt = candidates[i % len(candidates)]
            print(f"[{name}] reconnect ({type(e).__name__}: {str(e)[:60]}) -> {nxt.split('/')[2]}", flush=True)
            await asyncio.sleep(2)
