# AWS box tasks — from session V

I cannot message you (auth error); this file is the channel. Send findings to
`V` with SendMessage. Keep your own user-facing output to one or two lines —
nobody reads that side. Short messages to me too; the user is watching tokens.

## User instructions 09-13 — these are authorisations, not suggestions

Verbatim: *"you or that session can fix codes and everything and restart or
refresh things, make sure the order is set to 3$ fixed"* and *"let it run ef"*
and *"keep the ef onn there don't turn it off"*.

So, changed from the earlier read-only brief:

- **You may edit code, restart and redeploy the engine on that box.** You no
  longer need to come back to the user for those. Verify before you restart, and
  say what you did in your next message.
- **Stake stays $3 fixed.** Confirm `stake_settings` reads fixed $3 after any
  restart, and say so.
- **EF stays enabled.** Never turn it off, never turn master off, never "pause
  to be safe". If something looks alarming, report it and keep EF running.
- MAIN and REVERSAL stay off unless the user says otherwise.
- Still off limits: the Tokyo host and its databases, and secret values.

The user wants bugs fixed and PnL by morning. Prefer a small verified fix now
over a large unverified one.

## Task 5 - OPEN (do first): deploy 12.3.1

`git pull` — 12.3.1 is on the branch and fixes two bugs you found:

1. **Tick grid off by one.** `order_plan` used `D(float)`, so `D(0.28)/D(0.01)`
   was 28.000000000000002 and ceil made it 29 — a free tick on 35 of 99 prices.
   Now goes through `str()`.
2. **MAIN/REVERSAL seeded ON.** The dashboard's first-run loop persists its
   defaults; it wrote all three lanes True, so master-on armed everything. They
   seed False now. Your existing DB already has the keys, so this only protects
   fresh ones — check yours still reads main/reversal false after restart.

Deploy it: same DB (`12.3.0 -> 12.3.1` migration is additive, history is kept),
same flags, same $3 stake, EF on, master on. Before restarting, check nothing is
mid-flight. After: confirm build reads 12.3.1, EF on, master on, stake $3,
main/reversal off, and that settled history and PnL survived. Report those six
things in one short message.

Run the three test suites from the package first if you want — 114 pass here.

## Task 3 - OPEN: is the tick size actually 0.01?

Your finding: two plans are unreproducible at tick 0.01, `signals` has an ask of
0.439 and eight one-decimal asks. If tick is 0.001 on some markets then
`pad_ticks` means different things on different candles.

Get the venue's declared tick per market and compare against what `BookCache.terms`
holds. Report: how many distinct ticks, which markets, and any disagreement
between engine and venue. A disagreement is a bug above the pad — tell me and I
will fix it, or fix it yourself now that you are cleared to.

## Task 4 - OPEN: the book desynchronisation

Your staleness split (book_age_ms median 85.6 filled vs 129.1 rejected, with
latency otherwise identical) is the only discriminating field, and n=29 is under
the bar. Get the sample up and nail the mechanism.

1. Re-report the split at 60+ and at 100 graded attempts, full distributions.
2. The 610 `"Waiting for fresh UP and DOWN books"` diagnostics rows — when do
   they cluster, how long is each gap, do rejects follow a gap more than fills?
3. Do rejects follow a websocket reconnect, a sequence gap, or a silent depth
   period? If so the fix is in `poly_feeds.py` and it is the highest-value fix
   on the table — it is the difference between orders that land and orders that
   miss.

You are cleared to fix the feed layer now. Verify before you restart.

## Settled, for the record

- Task 1 (why the rejects): answered. The pad never engaged — 11 of 11 fills at
  or better than the quoted ask, two filling better than our book showed. My
  slippage advice is retracted in `V12_2_CHANGES.md`; the measurement behind it
  compared two fields that are identical by construction.
- Task 2 (MAIN default): confirmed, and you were right that the seeding loop,
  not the `allowed()` fallback, was the cause. Fixed in 12.3.1.
