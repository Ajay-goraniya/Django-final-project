# Improvements backlog
Running list. Not explanations for the user - working notes. Newest first. Status: OPEN / DONE / DROPPED.

## From the 09-11 process audit and the day's live run

1. OPEN - **Pin the decision second.** Two copies of the same model disagreed on the SIDE of 2 of 27 candles
   (~18 pts each at $10) purely because their loops sampled at different instants; median second identical
   (62 s), so it is jitter not bias. The real executor must decide at a fixed offset into the candle, not
   "whenever the loop comes round". Also means any paper number is cadence-dependent.

2. OPEN - **Never report a zero-slippage lane beside a live one.** The v12 lane fills at the observed ask
   with slippage exactly 0.0 on 40/40 by construction. Its PnL is an upper bound. Tag such runs in the fair
   table (e.g. "paper, no fill model") so they are never read like-for-like against live.

3. OPEN - **Re-run the independent-witness quote audit at n>=100.** At n=40 the lane's ask ran 1.25c cheaper
   than the 1 Hz logger, -1.36 se (not significant). Same direction as the stale-quote artifact. Re-test.

4. OPEN - **Reproduce a decision from raw inputs** (H1 Task 25). Rebuild features from polybook + klines, run
   the frozen model, check p/side/EV match the lane's recorded `feat`. Never yet done end to end.

5. OPEN - **fair.py must print UNAVAILABLE, not zeros,** when the Tokyo API fails. At 18:04 six 502s made the
   Tokyo row read 0/0 +0.0, which looks like "no trades" rather than "no data". Misleading in a table the
   user reads every hour.

6. OPEN - **Tokyo dashboard 502s are now a pattern**, not noise: three separate bouts on 09-11, each clearing
   after 2-3 retries. Root-cause it before the v12 deploy; a control surface that intermittently refuses is a
   liability when "stop now" has to work.

7. OPEN - **Lane flags reverted once with no restart** (14:40: master OFF, all three kinds back to
   manual_enabled TRUE, uptime 8.1 h). Cause unknown. Until understood, every check must verify per-kind
   flags, not just master_status. Find the writer.

8. REFUTED 09-11 22:12 (4 flips, cumulative real about -1.35, meets the pre-committed review condition; redesign with dead zone + min dwell, written before applied) - **Re-arm criterion oscillates and has no dead zone.** 19:12 armed on +0.002 per $1, a hair above zero. Review condition pre-committed 19:12: 4+ flips by Sunday night with cumulative real PnL < +1.00 = refuted, redesign with a dead zone (arm > +0.05, disarm < -0.05, min 2 h dwell), designed before applied. Original note: Armed 16:12 on +0.129, re-paused 17:12 on -0.038 - one hour live.
   Net +0.07 so it cost nothing this time, but an hourly flip churns the lane and pays the spread both ways.
   If it flips again without net progress, redesign - and pre-commit the redesign, do not fit it mid-flight.
   Candidate: require the 40-fire window to agree with the 20, or a minimum dwell time once armed.

9. OPEN - **The two venues now disagree about regime** (Predict.fun last-20 -0.038 vs Polymarket +0.089).
   The trigger follows Tokyo's own venue, which is correct, but a Polymarket lane will need its own trigger.

10. OPEN - **Polymarket executor belongs inside build11** as a venue backend behind the existing dashboard,
    /api/controls, lane semantics, ladder and kill rules. Reimplement the good parts of the handed-over v12
    file (trade schema with quote_age_ms/fill/slippage/fee; paper-default live guards; ambiguous-submit
    disables the lane) - do not lift the file. See v12_polymarket/DO_NOT_MERGE.md.

11. DONE 09-11 20:41 (verified against PyPI 0.10.0: package `polymarket`, SecureClient.create/get_closed_only_mode/place_market_order all match) - **Verify `polymarket-client` / `from polymarket import SecureClient`** before any live arming. The
    requirements pin and the import do not obviously match; a wrong guess surfaces at the first live order.

12. OPEN, FIRST READING NEGATIVE (H1 21b, 09-11 21:00: certifiable n=61 -0.062/$1; fresh-quote -0.141 vs stale-quote +0.232) - **Quote-age certification is the Polymarket go/no-go**, not crossing cost. Only 23 of 427 v10 paper
    asks matched the collector at the same second. book_age_ms now logged; H1 re-runs at n>=60, UP and DOWN
    separately. No real money before that closes.

13. OPEN - **Design for the side skew, not a flat venue edge.** Polymarket UP is 3.33c cheaper, DOWN 2.62c
    dearer (matched 1 Hz, n=43,552, both halves). Lane advantage moves with the model's side mix; a DOWN-heavy
    day shrinks or inverts it. Put it in the lane design, not in a post-mortem.

14. OPEN - **Engine startup should restore intended lane state, not just "safe startup"**, and should
    persist/replay the operator's last explicit intent so a restart cannot silently re-arm or disarm.

15. OPEN - **Stop hook keeps firing on `learner/live_backup/tokyo_orders.json`** every health check. Either
    commit it on a schedule or move it out of the working tree; it generates a commit per check for no signal.

16. OPEN - **Tokyo order timestamps read ~37 min ahead of true UTC.** At 21:15:02 UTC (container clock, agrees
    with the routine scheduler) the engine's /api/orders showed fills stamped 21:45, 21:50, 21:52 "utc". Either
    the Tokyo host clock is fast or the utc field is mislabelled. Relative comparisons on ts_ms still hold, but
    anything that aligns engine time to exchange candles or to the collector must be checked. Root-cause
    before the v12 deploy.

17. OPEN - **The EV-at-cap recheck is charged against the SAME threshold that triggered the fire, so any
    signal with less than one tick of EV headroom is skipped.** First live signal, 21:21:16: FIRE UP p=0.623
    ask=0.52 ev=0.1579, then at cap 0.53 (pad 1 tick) ev fell to 0.1368 and failed the threshold -> state
    SKIPPED, zero attempts, no order sent. The guard is correct in spirit (do not pay a pad that destroys the
    edge) but as written it rejects a large fraction of fires: on a 0.52 ask one tick costs ~2.1pp of EV, so
    only signals clearing the threshold by more than that can ever reach the book. Options to consider
    (design first, pre-commit, then test): (a) pad 0 and accept lower fill probability; (b) compare the capped
    EV against a separate, lower execution floor rather than the signal threshold; (c) size the pad from the
    EV headroom actually available. Do NOT just lower the threshold.

18. PARKED 09-11 22:30 (support per the user: VPS AND account holder must both be in non-restricted areas; reopens when the user is in one, Tokyo host only) - previously CLOSED 22:00 (user is UK-resident; UK is close-only on frontend AND API, so no live Polymarket lane - reopens only on a genuine change of residence) - originally BLOCKED BY VENUE 21:46 - **Live Polymarket execution is impossible from this container: geoblock.**
    First real submission was rejected with "Trading restricted in your region" from egress IP 160.79.106.135
    (Columbus OH, US, Google LLC). US origins are excluded by Polymarket's ToS. Any live Polymarket execution
    must run from a host in a permitted jurisdiction, and the user's own eligibility is a separate question.
    Do not attempt to route around it. Everything upstream of the venue is verified working: auth, SDK calls,
    the pad-0 EV fix, and the ambiguous-submit guard that disabled the lane.

19. FIXED 09-11 23:20 - **Monitoring counted processes, not liveness. A whole hour was lost silently.**
    After the 22:12 worker restart the two Polymarket paper runners kept running with DEAD websockets: every
    feed 57 minutes stale, no fires recorded, but the process count stayed at 12 so the keepalive never fired.
    Twins B and TE had died outright and were also missed. My error: the watcher checked the wrong thing.
    Fix applied: the health watch now alerts if processes drop below 10 OR if any runner's worst feed age
    exceeds 300 s OR if either 1 Hz logger's newest row is over 300 s old. Lesson generalises - a liveness
    check must measure the OUTPUT, not the existence of the thing producing it. The same flaw would hide a
    wedged live lane, which is the version that costs money.

20. OPEN, HIGH - **4.8 GB of L2 order-book history exists only in this ephemeral container.**
    week_data/depth/l2 (3.5 GB Binance, 08-29..09-06) and week_data/predictfun/polymarket_l2 (1.3 GB) are
    excluded by .gitignore:30 and untracked, as is week_data/deliver/ with its pre-split archives. A container
    recycle loses all of it. Polymarket depth cannot be re-downloaded at any price (no historical book
    endpoint); Binance depth only partly. Decide a destination (object storage, or split parts committed to a
    data branch) and move it before the weekend test. This outranks every trading item on this list.

## v12 checkpoint code review (09-12 01:50) - poly_core.py / poly_live.py / btc_model_v12_polymarket.py

21. BUG, WILL FAIL HERE - **chart_seed() calls api.binance.com, which is geo-blocked from these containers.**
    btc_model_v12_polymarket.py line 183 uses https://api.binance.com/api/v3/klines for the 288-candle chart
    seed. Verified just now: that host returns **HTTP 451** from this container, while
    https://data-api.binance.vision returns 200 on the identical path. The call is wrapped in an
    isinstance(data,list) check so it fails silently - the chart simply never seeds and nobody is told.
    Every other Binance endpoint in the file already uses data-stream.binance.vision. One-line fix: swap the
    host. Known issue in this project (repo CLAUDE.md documents the geo-block); the checkpoint author would
    not have hit it on their own machine.

22. RISK, cannot be settled without a real fill - **order id compared against a locally computed EIP-712
    hash, and a mismatch HALTS the lane.** poly_core.py:173 does `if r.get('id')!=oid` where `oid` is
    `client.journal_hash` (keccak of the typed data, computed in poly_live.py's TrackedClient._sign_order)
    and `r['id']` is `str(response.order_id)` from the SDK. If Polymarket's order_id is that hash in the same
    string form, this is a strong integrity check. If it differs by case, 0x prefix, or representation, the
    FIRST live order halts the whole lane with "Order hash mismatch". Consequence is heavy for a formatting
    difference. Suggest: log both values and compare case-insensitively on the hex body before halting, or
    downgrade the first occurrence to REVIEW rather than halt.

23. MINOR - **halt_check's slippage query silently drops orphan fills.** poly_core.py:113 inner-joins fills to
    orders; a fill whose order row is missing (crash between order() and fill()) is excluded from the
    20-fill slippage window rather than flagged. Verified with a synthetic DB. The window then measures fewer
    than 20 real fills while believing it has 20.

24. OK, checked and sound - order_plan() guards hold up under probing: cap>=1 is rejected (ask 0.99 with a
    1-tick pad raises "price cap outside market"), the fee reserve uses the worst executable level not just
    the top, the padded-price EV recheck is the conservative inherited v10 rule, and the venue minimum is
    enforced against the CAP (more conservative than against the ask). No division-by-zero reachable in
    cost=max(cap+f, cap/(1-f/cap)) for rate<1.

25. GOOD, worth keeping in the build11 port - live mode pre-checks polymarket.com/api/geoblock and refuses to
    start unless blocked is explicitly False; live starts with master=False so it must be armed by hand; the
    reconcile path only counts CONFIRMED taker trades belonging to this order id; a submit timeout records
    UNKNOWN and never resubmits (covered by their test_timeout_never_resubmits_on_restart).
