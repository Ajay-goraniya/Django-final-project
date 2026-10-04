# Task 83 — the wire to the venue, measured from the AWS Mumbai box. AWS-authored, committed unedited by V.

> Provenance: AWS session (`session_0128m2knBcqiTyAVoh7h994A`), 01:0x UTC 09-14, sent to V by cross-session
> message; V committed it verbatim. Measurement only; no recommendation in it, by V's instruction.

Task 83 — four blocks, numbers only, no recommendation. One correction to your standing line: the Monday series is no longer "empty, master off" — the user had me archive the journal and ARM master at 01:03:22 UTC, so the live journal is fresh and trading. Block 1 therefore comes from the archive at /home/ubuntu/polymarket_v12_journal_archive_20260914_010249/, read-only.

BLOCK 1 — what we already paid for (live journal, orders since 09-13 00:00 UTC, n=87: 38 FILLED, 48 REJECTED, 1 UNKNOWN). Fields present in timing_json: attempt, signal_ts_ms, quote_wait_ms, quote_read_ms, book_age_ms, decision_ms, signal_quote, sign_ms, final_recheck_ms, pre_submit_book_age_ms, fire_to_submit_ms, submit_ms, response_ms, network_roundtrip_ms, total_attempt_ms, snapshot_age_s, believed_tick, since_tick_change_s, last_tick_change. All ms.
network_roundtrip_ms  ALL  n=87 p50=348.0 p90=616.8 p95=956.3 max=1201.2
  FILLED    n=38 p50=346.6 p90=370.1 p95=560.3 max=1198.8
  REJECTED  n=48 p50=348.4 p90=625.3 p95=956.3 max=1015.1
  UNKNOWN   n=1  1201.2
sign_ms               ALL  n=87 p50=7.2 p90=7.9 p95=8.2 max=8.7
  FILLED    n=38 p50=7.4 p90=7.9 p95=8.0 max=8.7
  REJECTED  n=48 p50=7.2 p90=7.9 p95=8.2 max=8.2
fire_to_submit_ms     ALL  n=87 p50=18.4 p90=361.5 p95=422.6 max=785.7
  FILLED    n=38 p50=17.0 p90=59.2 p95=360.6 max=785.7
  REJECTED  n=48 p50=18.8 p90=400.8 p95=437.9 max=529.7
submit_ms is identical to network_roundtrip_ms in every row (same field, both populated), and orders.latency equals it too. Note the split: p50 FILLED vs REJECTED on the wire is 346.6 vs 348.4 — 1.8 ms apart. The tail differs (p90 370 vs 625), and fire_to_submit_ms p90 differs far more (59 vs 401).

BLOCK 2 — clean wire from the box (ap-south-1b, public IP 3.7.253.12).
clob.polymarket.com/time, ONE connection reused, 50 GETs: p50=137.0 p90=157.1 p95=161.5 min=132.9 max=360.4 mean=147.8 ms.
  handshake reported separately: TCP connect p50=0.9 (min 0.7 max 1.2), TLS handshake p50=5.4 (min 4.2 max 8.2), both x10 fresh.
ws-subscriptions-clob.polymarket.com:443 TCP connect x50 (IPv4 172.64.153.51): p50=0.8 p90=1.1 p95=1.3 min=0.4 max=1.4 ms.
  one full WS open: TCP 0.8 ms, TLS 5.3 ms, HTTP/1.1 101 Switching Protocols upgrade round trip 326.2 ms, CF-RAY a3ab7d7c5f973d26-BOM.
clob.polymarket.com:443 TCP connect x50 (IPv4 104.18.34.205): p50=0.8 p90=0.9 p95=0.9 min=0.4 max=1.2 ms.
IPv6 is published for both hosts but 0/50 connects succeeded from this box (OSError) — the box has no working IPv6 route; everything above is IPv4.

BLOCK 3 — where it terminates.
clob.polymarket.com A: 104.18.34.205, 172.64.153.51 — 104.16-31.x and 172.64-71.x, both Cloudflare.
ws-subscriptions-clob.polymarket.com A: 104.18.34.205, 172.64.153.51 — the same two IPs, same Cloudflare ranges.
polymarket.com AAAA/A: same anycast set (2606:4700:440d::6812:22cd / 2606:4700:4408::ac40:9933).
cf-ray colo on every response: BOM (clob a3ab7aafdac33d06-BOM, polymarket.com a3ab7ab0f94c84d7-BOM, ws a3ab7d7c5f973d26-BOM). server: cloudflare.
mtr -rwc 20 -4 clob.polymarket.com: 5 hops, 0.0% loss throughout — 1) 242.8.229.135 et al (AWS fabric) 0.8/avg 3.6, 2) 240.3.120.6 avg 1.1, 3) 162.158.226.4 / 99.83.89.197 avg 3.3, 4) 162.158.226.93 avg 3.2, 5) 104.18.34.205 last 0.8 avg 0.9 best 0.8 worst 1.3.
mtr to the ws host: same shape, 5 hops, last hop 172.64.153.51 avg 1.3 ms.
Plainly: **the edge is 0.8–1.3 ms from this box and it is Cloudflare's BOM colo.** Everything beyond hop 5 is inside Cloudflare and is not measured by any of the above. The 137 ms warm GET and the 348 ms order round trip are edge→origin→edge plus origin work; no region choice can be argued from these numbers alone, because they do not show where the origin is or how Cloudflare routes to it.

BLOCK 4 — geo pre-check exactly as --live runs it.
GET https://polymarket.com/api/geoblock → {"blocked":false,"ip":"3.7.253.12","country":"IN","region":"MH"}

Standing watch: build 12.8.8, PID 93603, master TRUE (user, 01:03:22), halt null, EF on, MAIN/REV off, stake 3.0, venue cash 37.529, fresh journal 0 orders / 0 results as of 01:06. Per-candle submissions/retries/DEADLINEs/rejects will be reported from the new journal as they appear.
