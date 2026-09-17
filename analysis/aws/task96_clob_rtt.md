# Task 96 — CLOB round-trip geography from AWS Mumbai (2026-09-16 00:4x UTC)

20 samples each, curl `%{time_connect} %{time_starttransfer}`, ms.

| endpoint | connect p50 | connect p90 | TTFB p50 | TTFB p90 | TTFB max |
|---|---|---|---|---|---|
| `/time` | 1.8 | 2.3 | 165.4 | 195.9 | 798.3 |
| `/book?token_id=…` | 1.6 | 2.3 | 165.6 | 176.6 | 194.8 |

`mtr -rwn -c 12 -m 12 clob.polymarket.com`, 5 hops total:
1. 242.8.228.5 (+6 AWS fabric addrs) 0.0% loss, avg 2.0 ms
2. 240.3.120.6 0.0%, avg 1.1 ms
3. 162.158.226.4 25.0% loss, avg 6.3 ms (Cloudflare; ICMP de-prioritised, not a path loss)
4. 162.158.226.93 0.0%, avg 12.4 ms
5. 104.18.34.205 0.0%, avg 0.9 ms — Cloudflare edge, terminal hop

Verdict: TCP connect to the edge is ~1.7 ms; the entire 165 ms TTFB is edge→origin→edge behind Cloudflare
and is invisible to traceroute. `/book` and `/time` are identical (165.4 vs 165.6 p50), so the cost is the
path to origin, not query work. The one 798 ms and one 500 ms sample on `/time` are the same tail the
websocket lag probe measured; `/book` showed no such excursion in 20 samples.
