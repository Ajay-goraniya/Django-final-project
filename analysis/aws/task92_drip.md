# Task 92 — is the drip per-connection or venue-wide?

Probe: `analysis/aws/ws_gap_probe.py 3600`, own socket, beside the engine on the AWS Mumbai box.
Window **00:41:05 – 01:41:03 UTC, 2026-09-15**, 3,465 per-second lines, **12 reconnects** on the probe socket.
Engine: build 12.8.10, PID 109303, master OFF throughout (publish() still runs, so WAIT_CENSUS keeps filling).
Raw per-second output: `analysis/aws/task92_probe.log`.

## Alignment table — engine WAIT_CENSUS minutes with stale share > 2%

58 census minutes fell inside the probe window. **Exactly one** exceeded 2% stale.

| minute end (UTC) | window_s | stale % | stale n | probe secs | probe maxgap (ms) | probe events | probe reconnect in minute |
|---|---|---|---|---|---|---|---|
| 01:07:49 | 62 | 17.55% | 7,054 | 61 | 3,310 | 34,627 | **YES** |

The other 57 census minutes were at or under 2% stale.

## Probe gap distribution over the hour

- maxgap_ms: p50 414, p90 2,230, p99 2,590, max 3,310
- seconds with a gap > 750 ms: 32.3%; seconds with a gap > 2 s: 448
- during the 57 CLEAN engine minutes (stale ≤ 2%): maxgap p50 412, p90 2,229, max 3,139 (n = 3,277 s)

## Reading

The probe's gap profile is **identical inside and outside the engine's stale minutes** (p50 412 vs 414, p90 2,229 vs
2,230). A second socket on the same box sees the same multi-second gaps whether or not the engine is reporting
stale — so the gaps are **venue-wide / path-wide, not per-connection**, and a silence watchdog in `venue()` would
not have prevented them.

The single stale minute did coincide with a probe reconnect, which is one observation, not a finding: with 12
reconnects in the hour and only one stale minute above 2%, most probe reconnects produced no engine staleness at all.

**Caveat on the reconnect column, stated rather than hidden:** the probe log writes `# reconnect <ExcName>` with no
timestamp. Each reconnect is attributed to the wall-clock second of the next per-second line that follows it, and a
census minute is marked YES if any so-attributed reconnect falls inside it. That is an approximation of ±1 second at
best and cannot be tightened from this log.

**Caveat on the probe's own subscription:** `ws_gap_probe.py` subscribes to the current candle's tokens *and* the
next candle's, and the next-candle token is illiquid (~2.25 s cadence). The p90 of 2,230 ms is therefore set by that
token, not by the active book — the same artefact V identified earlier. The comparison inside-vs-outside stale
minutes is unaffected, because both arms carry the same artefact.
