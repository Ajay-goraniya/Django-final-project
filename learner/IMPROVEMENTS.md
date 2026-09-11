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

8. OPEN (2 data points now) - **Re-arm criterion oscillates and has no dead zone.** 19:12 armed on +0.002 per $1, a hair above zero. Review condition pre-committed 19:12: 4+ flips by Sunday night with cumulative real PnL < +1.00 = refuted, redesign with a dead zone (arm > +0.05, disarm < -0.05, min 2 h dwell), designed before applied. Original note: Armed 16:12 on +0.129, re-paused 17:12 on -0.038 - one hour live.
   Net +0.07 so it cost nothing this time, but an hourly flip churns the lane and pays the spread both ways.
   If it flips again without net progress, redesign - and pre-commit the redesign, do not fit it mid-flight.
   Candidate: require the 40-fire window to agree with the 20, or a minimum dwell time once armed.

9. OPEN - **The two venues now disagree about regime** (Predict.fun last-20 -0.038 vs Polymarket +0.089).
   The trigger follows Tokyo's own venue, which is correct, but a Polymarket lane will need its own trigger.

10. OPEN - **Polymarket executor belongs inside build11** as a venue backend behind the existing dashboard,
    /api/controls, lane semantics, ladder and kill rules. Reimplement the good parts of the handed-over v12
    file (trade schema with quote_age_ms/fill/slippage/fee; paper-default live guards; ambiguous-submit
    disables the lane) - do not lift the file. See v12_polymarket/DO_NOT_MERGE.md.

11. OPEN - **Verify `polymarket-client` / `from polymarket import SecureClient`** before any live arming. The
    requirements pin and the import do not obviously match; a wrong guess surfaces at the first live order.

12. OPEN - **Quote-age certification is the Polymarket go/no-go**, not crossing cost. Only 23 of 427 v10 paper
    asks matched the collector at the same second. book_age_ms now logged; H1 re-runs at n>=60, UP and DOWN
    separately. No real money before that closes.

13. OPEN - **Design for the side skew, not a flat venue edge.** Polymarket UP is 3.33c cheaper, DOWN 2.62c
    dearer (matched 1 Hz, n=43,552, both halves). Lane advantage moves with the model's side mix; a DOWN-heavy
    day shrinks or inverts it. Put it in the lane design, not in a post-mortem.

14. OPEN - **Engine startup should restore intended lane state, not just "safe startup"**, and should
    persist/replay the operator's last explicit intent so a restart cannot silently re-arm or disarm.

15. OPEN - **Stop hook keeps firing on `learner/live_backup/tokyo_orders.json`** every health check. Either
    commit it on a schedule or move it out of the working tree; it generates a commit per check for no signal.
