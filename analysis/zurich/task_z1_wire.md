# Task Z-0 / Z-1 - the wire from Zurich (eu-central-2). Zurich-authored, measurement only.

> Provenance: Zurich session (`session_017UN5dZFsS3js7KA9WMFeDQ`), 2026-09-14 22:5x-23:1x UTC.
> **This box cannot `git push`** (see Z-0), so this file was sent to V by Routine for V to commit verbatim.
> No recommendation in it, by V's standing instruction: report, do not recommend. No orders, no engine touched.

## Z-0 - the box

| key | value |
|---|---|
| region | **eu-central-2 (Zurich)** - confirmed three ways: geoblock `country CH / region ZH`, `cf-ray` colo **ZRH**, public IP `16.62.65.190` (AWS eu-central-2 range) |
| AZ | **not determined** - IMDS (`169.254.169.254`) is blocked by this session's sandbox classifier ("Containment Escape"). Everything below is measured without it. |
| instance | **t3.xlarge**, `i-0884d32eb9e395164` (from `/sys/devices/virtual/dmi/id/`), 4 vCPU, 15.4 GiB, clock UTC |
| python | system **3.12.3**, no `pip`/`ensurepip` on the box. Installed `python3-venv`/`python3-pip` via apt; venv at `/home/ubuntu/claude-work/venv` with `websockets 17.1`, `numpy 2.5.3` |
| repo | **not pre-cloned.** Cloned read-only to `/home/ubuntu/claude-work/repo`, branch `claude/your-task-3wbq8u`, at **8fd6673** |
| git push | **NO.** `git push --dry-run origin HEAD:claude/your-task-3wbq8u` -> `fatal: could not read Username for 'https://github.com'`. No credential helper, no `gh`, HTTPS clone of a public repo. Read-only. |
| geoblock | `{"blocked":false,"ip":"16.62.65.190","country":"CH","region":"ZH"}` - verbatim, carries no secret |

Per `CLAUDE.md` Â§1 the no-push case means results reach the branch only through V. Z-1 anticipated this
("else <= 15 lines to V and V commits it"), so this file travelled in the Routine body.

## Z-1 Block 1/2 - the wire, Mumbai's Task 83 method repeated from Zurich

**Headline: warm GET `clob.polymarket.com/time`, ONE connection reused, 50 GETs.**

| | Zurich | Mumbai (Task 83) | delta |
|---|---|---|---|
| p50 | **29.9** | 137.0 | **-107.1 ms** |
| p90 | **32.6** | 157.1 | -124.5 |
| p95 | **35.2** | 161.5 | -126.3 |
| min / max / mean | 28.1 / 80.0 / 32.1 | 132.9 / 360.4 / 147.8 | |

**The edge is the same distance from both boxes - so the whole 107 ms sits beyond it.**

| | Zurich | Mumbai |
|---|---|---|
| fresh TCP connect, clob, n=50 | p50 **0.8** p90 1.0 p95 1.0 min 0.7 max 1.1 ms | p50 0.8 p90 0.9 p95 0.9 |
| fresh TCP connect, ws host, n=50 | p50 **0.8** p90 0.9 p95 1.0 min 0.7 max 1.0 ms | p50 0.8 p90 1.1 p95 1.3 |
| fresh TLS1.3 handshake, n=15 | p50 **5.6** (4.6-7.5) ms | p50 5.4 (4.2-8.2) |
| `cf-ray` colo (clob / ws / polymarket.com) | **ZRH / ZRH / ZRH** | BOM / BOM / BOM |

> Caveat on the TLS row, because it nearly went out wrong: `curl -w time_appconnect` gave 38.5 ms here.
> A raw `socket`+`ssl` measurement of the same handshake gives **5.6 ms**, TLSv1.3. The 38.5 ms is curl-side
> (CA bundle / verification), not wire. The 5.6 ms is the number; the curl figure is discarded.

**Block 3 - where it terminates.** Identical anycast set to Mumbai, so this is the same Cloudflare front door:
- `clob.polymarket.com`, `ws-subscriptions-clob.polymarket.com`, `polymarket.com` all A-resolve to
  **104.18.34.205, 172.64.153.51** (104.16-31.x and 172.64-71.x = Cloudflare), AAAA `2606:4700:4408::ac40:9933`,
  `2606:4700:440d::6812:22cd`.
- **IPv6 published but unusable: 0/50 connects, `ENETUNREACH`, both hosts.** Same as Mumbai. Everything here is IPv4.
- `mtr -rwc 20 -4 clob.polymarket.com`: 5 hops. 2) `240.1.148.3` avg 1.2 - 3) `99.82.11.83` avg 4.1, 20.0% -
  4) `162.158.148.41` avg 2.8 - 5) `172.64.153.51` last 0.8 avg 0.8 best 0.8 worst 0.9, **0.0% loss**.
- `mtr` to the ws host: same shape, 5 hops, hop 3 25.0%, last hop `104.18.34.205` avg 0.9, 0.0% loss.
- The hop-3 loss is ICMP rate-limiting on a transit router, not path loss: the **last** hop shows 0.0% over 20
  probes on both, and 50/50 TCP connects and 50/50 GETs succeeded.

**What Mumbai said, and what changes.** Task 83 concluded: *"no region choice can be argued from the edge alone,
because [these numbers] do not show where the origin is."* That is still true of either box **on its own**. With a
second vantage point the *differential* is informative and the confound is controlled: both boxes sit 0.8 ms from a
Cloudflare edge with an identical handshake, both hit DYNAMIC (uncached) paths, so the 137 -> 29.9 ms difference is
edge->origin->edge and nothing else. It does not locate the origin; it measures that Zurich's edge reaches it 107 ms
faster.

## Z-1 Block 2 - `ws_gap_probe.py`, 600 s, unmodified, from `learner/v12_2`

**Window `2026-09-14 22:51:07 - 23:01:05 UTC`** (599 s span, 589 per-second rows, 3 epochs, **0 reconnects**,
253,003 events, ev/s p50 333 mean 430). Box venv: `websockets 17.1`.

| metric | **Zurich** | Mumbai | Ohio |
|---|---|---|---|
| maxgap p50 | **292** | 394 | 399 |
| maxgap p90 | **2245** | 782 | 792 |
| maxgap p99 | 2782 | - | - |
| maxgap max | **2964** | 3784 | 3561 |
| **seconds > 750 ms** | **32.1%** | 10.7% | 11.3% |
| maxlag p50 | **32** | 89 | 60 |
| maxlag p90 | **84** | 250 | 173 |
| maxlag max | **1726** | 2074 | 1761 |
| reconnects | **0** | - | - |

**maxlag is uniformly the best of the three regions.** That is the one-way "how old is the event when I see it"
number, and it is 2.8x better than Mumbai at p50 and 3.0x at p90.

### The 32.1% is not a wire result - do not read it as one. Four checks say so.

I nearly sent "Zurich's gaps are 3x worse than Mumbai's". They are not, and Task 87's use of this metric is
affected too. Evidence, all from this box:

1. **It moves the wrong way with load.** Seconds with >=200 ev/s: 36.3% over 750 ms. Seconds with <200 ev/s:
   16.7%. A congested wire gets worse when quiet, not busier. The last 30 s of every candle (ev/s p50 122) is
   **0.0%** over 750 ms.
2. **The big values are periodic, not jitter.** Of the 189 seconds over 750 ms, **62 fall in one 100 ms band,
   2200-2300 ms**, and 73 in 2000-2400 ms. A stalled receive loop does not emit a repeating constant.
3. **Per-token, the feed is clean.** Re-ran the same subscription for 200 s recording gaps *per asset_id*:

| token role | n gaps | p50 | p90 | p99 | max | >750 ms |
|---|---|---|---|---|---|---|
| **ACTIVE** (the candle being traded) | 98,536 | **1** | **16** | 60 | 2613 | **0.0%** |
| NEXT (next candle's book) | 894 | 30 | 466 | 482 | 1711 | 0.4% |

   The ACTIVE tokens - the only ones the engine trades - tick at **p50 1 ms, p90 16 ms**. `ws_gap_probe` takes a
   max across **all four** subscribed tokens, so its per-second `maxgap` is set by whichever token is quietest,
   which is the illiquid NEXT-candle book on its ~2.25 s refresh cadence. It is a liquidity measure of the next
   candle, not a latency measure of the wire, and it is not comparable across windows with different books.
4. A 60 s replay of `ws_gap_probe`'s exact gap logic, instrumented: **4 subscribed asset_ids, 0 foreign,
   69,521 events, 0 gaps over 750 ms.** Nothing off-subscription is polluting the metric.

**So the Zurich/Mumbai/Ohio `% > 750 ms` row compares three different next-candle order books, not three wires.**
The rows that do compare wires - maxlag, warm GET, TCP, TLS - all favour Zurich.

## Z-1 Block 3 - the order-path round trip, as close as this box can get without credentials

Cannot post orders (no credentials, and no trading from Zurich until V and the user say so in writing).
Warm POST, **one reused connection, 20 samples**, `POST https://clob.polymarket.com/order` with `{}`:

**HTTP 401, p50 32.9, p90 34.7, p95 38.4, min 31.5, max 75.6, mean 35.3 ms.**

**What it is a proxy for, and what it is not.** The 401 body is `{"error":"missing address header"}` with
`cf-cache-status: DYNAMIC` - an application error from the CLOB origin, not a Cloudflare edge rejection, so the
32.9 ms **is a real edge->origin->edge round trip on the order URL**. It excludes signature verification,
order-book matching and the write path. The size of that exclusion is visible in Mumbai's own numbers: its live
`network_roundtrip_ms` p50 was **348.0** against a 137.0 ms warm GET - **211 ms of origin work** this proxy cannot
see. Zurich's equivalent transport leg is 32.9 ms against Mumbai's ~137.

**The arithmetic, stated as arithmetic and not as a prediction.** If the origin work is region-independent
(untested - it needs one real order from each box, which this box cannot make), Mumbai's 348 ms p50 order round
trip decomposes as ~137 transport + ~211 origin, and the same order from Zurich would be ~30 + ~211 = **~241 ms**,
a saving of **~107 ms per order**. That conditional is the whole question, and it is not settled here.

## What is measured, what is not

- **Measured:** every row above, from this box, tonight, read-only.
- **Not measured:** the AZ (IMDS blocked); where the origin actually is; whether origin-side work is
  region-independent; any effect on fill rate. Fill rate is a race against other takers, not a round trip,
  and nothing here measures it.
- **No recommendation**, per V's standing instruction. The region call is V's and the user's.

Reproduce: `analysis/aws/ws_gap_probe.py 600` from `learner/v12_2`; the two diagnostics are `pertoken.py` and
`whichasset.py`, kept on the Zurich box under `/home/ubuntu/claude-work/out/`.
