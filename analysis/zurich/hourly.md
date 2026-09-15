19:12 UTC 09-15 | results n=52 W29/L23 pnl +37.21
fills 54 / rejects 86 / unknown 0 | cash 80.95 open 0.06 (venue_state; 2 fills ungraded) | stake 5.0 master on halt null | fire_to_submit median since 17:31: 132 ms (n=21; first two were 41/23 - retries at attempt 2+ raise it) | RECONCILE_STUCK 9 (one per reject, first pass)
snapshot: this commit (zurich_2 2,407,065 B)

## RTT vs attempt / idle gap, both journals, 09-14 23:49 -> 09-15 19:2x, n=160 orders with network_roundtrip_ms (med / p90 ms)
(a) attempt 1: n=125 264 / 323 | attempt 2+: n=35 247 / 298  -> attempt 1 is 17 ms slower at the median.
(b) gap since previous POST, attempt-1 only: <30 s n=20 262 / 297 | 30-120 s n=5 243 / 302 (insufficient) | >120 s n=99 267 / 331.
Hypothesis (idle pool drop -> fresh TLS ~40 ms inside attempt-1 RTT): NOT supported. >120 s idle vs <30 s idle differ by 5 ms at the median (267 vs 262); a 40 ms handshake would show as ~300+ in the idle cell. The 17 ms attempt-1 premium is present even at <30 s gaps (262 vs 247), so it is not the connection either.
Verdict: no idle-connection penalty in the data; the order RTT floor is ~245-265 ms regardless of attempt or gap. If the pool did drop, the SDK reconnects outside the measured window or the handshake is smaller than 40 ms on the warm path.
