Zurich VERIFY (live journal ro + /proc, 23:58 UTC 09-14):
1. pid 8347 since 23:49:12 UTC: --live --mode pnl --capital 50 --host 0.0.0.0 --port 8787 --db polymarket_v12_live_zurich.sqlite3 --quote-age-ms 2000. build 12.8.9.
2. master TRUE (audit 23:50:42 old False->True, do_POST/apply). halt: no key = null. ef on, main/rev off.
3. stake_settings fixed 3.0; next_stake 3.0 (audit 23:50:39 do_POST). No write needed.
4. ev_settings ABSENT -> exec path on CLI 2000 ms. NOT written by me: Journal.__init__ (poly_core.py:39-44) re-set()s lane/model_hash/build and runs _migrate_signals_multilane on every open, so a second Journal on the live db is not side-effect-free; sandbox also still denies ~1 in 3 db reads. User sets quote age 750 on the controls EV panel (audited, bounds 0-2000).
5. venue cash 68.42, open_value 0.0 (23:58:23). orders 0, signals 0, results 0. candles 289.
6. First AMBIENT_AGE 23:49:22 age_up/dn 41.1 ms. Decide rows: 14 'Waiting for fresh UP and DOWN books', 26 warm-up, 3 'outside decision window'. feed_counters 23:49:27: applied 1200, dropped_stale 0, no_asks/no_bids 1232 (warm-up).
7. Dashboard is HTTP Basic (poly_dashboard.py:542); password untouched.
ACK: Zurich holds the Mumbai-box role, same rules (pull --rebase; REMAKE_PLAN s7 all 7 rows, Row 6 first, DEPLOYED.md verbatim; never arm/stake; halt/PnL watched not coded; no secrets; artifact not reconstruction; retract on reversal; <=15 lines). push --dry-run still fails -> reports verbatim. Hourly 6-liner from 00:5x UTC; hand-stop only on cash < stake.
BLOCKER: this session's sandbox now denies RemoteTrigger (Routine) too - V gets nothing from me unless the user relays or allows it.
