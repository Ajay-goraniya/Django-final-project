# Z-7 CLOB round-trip geography from Zurich, 2026-09-16 00:3x UTC, read-only (engine untouched). curl -4, ms, 20 samples each.
/time  reused connection: TTFB med 35.4 / p90 42.6 (HTTP 200). Fresh connections: TCP connect med 2.4 / p90 3.4, TLS 49.2, TTFB med 87.1 / p90 95.4.
/book?token_id=…14754024 (current candle UP, 3,471 B, HTTP 200), fresh connections: connect med 1.8 / p90 2.0, TTFB med 67.3 / p90 72.1.
mtr -rwc 20 -4: hop1 242.4.68.x (AWS fabric) 1.1 avg | hop2 240.1.148.3 1.3 | hop3 99.82.11.83 3.4 (10% ICMP loss) | hop4 162.158.148.39 2.4 | hop5 104.18.34.205 0.8 avg, 0% loss = Cloudflare edge (cf-ray ZRH).
Read: edge 0.8-2.4 ms; a warm /time is 35 ms edge->origin->edge (Mumbai Task 83: 137); /book adds ~30 ms of origin work over /time. Fresh TLS costs ~50 ms once, not per request.
Compare AWS Task 96 (Mumbai) cell-for-cell; the region gap on the warm path is ~100 ms in Zurich's favour, unchanged since Z-1.
