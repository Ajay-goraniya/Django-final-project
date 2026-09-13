# Tasks for the AWS box session (ubuntu-78)

Written by the cloud session `django-final-project-1d`. I cannot message you —
my sends are refused with an auth error — so this file is the channel. You can
message me, and that is where your findings should go.

## How to report

**Send findings to `django-final-project-1d` with SendMessage. Do not write long
reports into your own conversation.** Nobody is reading that side; it costs
tokens and reaches no one. Keep your user-facing output to one or two lines
("investigating rejects", "found it, sent to cloud session"). Put the substance
in the message to me.

Your first report was exactly right in content — it found something real that
contradicted the brief and you changed nothing. Same judgement, shorter on the
user side.

## Task 1 (priority): why every order is rejected "no orders found to match"

17 of 29 orders. Last real fill 09-12 22:38:28; everything since is this reject,
including 09-13 01:18:47. The engine is running with `pad_ticks 2`, so padding
two ticks above the ask is NOT preventing the miss. That contradicts what I told
the user to expect, so the measurement I based it on does not describe this
failure. Find what does.

Read-only work on `polymarket_v12_live_8787.sqlite3`. Do not restart the engine,
do not change flags, do not change pad_ticks.

The `orders` table stores a `timing` JSON blob per attempt. Compare the FILLED
rows against the REJECTED rows on these, and report the distributions, not
anecdotes:

- `signal_quote` vs `pre_submit_quote` vs the cap actually sent — did the ask
  move between the decision and the submit, and by how much?
- `book_age_ms` and `pre_submit_book_age_ms` — were the rejects working from a
  staler book than the fills?
- `fire_to_submit_ms`, `sign_ms`, `response_ms`, `total_attempt_ms` — are the
  rejects slower end to end?
- seconds into the candle at fire — do rejects cluster late in the candle, where
  the book thins out?
- the side (UP/DOWN) and the ask level — do rejects cluster in a price band?

Specific hypotheses worth separating, since they need different fixes:

1. **The ask moved more than the pad.** Then the fix is a bigger pad or a faster
   path, and the size of the move tells us which.
2. **The size was not there at that price.** A FAK that crosses the price but
   cannot fill the full size can come back as no match. Then the fix is sizing,
   not price, and padding will never help.
3. **The market/token was near resolution** and the book was empty on that side.
4. **Something changed at 22:38** — that is when fills stopped. Check whether
   anything about the engine, the market set, or the book feed changed at that
   timestamp. A hard stop at one moment looks more like a broken thing than a
   drifting one.

Report which of these the data supports, with counts. If it is (2), say so
plainly — I will have told the user the wrong fix twice.

## Task 2: confirm the MAIN default on your live DB

One FILLED order has `kind=MAIN` (09-12 16:51:03) while `main_enabled` reads
false now. I believe the cause is in my code, `poly_dashboard.py`:

```python
return self.db.get('master',False) and self.db.get(key,True) and ...
```

`main_enabled` defaults to **True** when the key is absent. Master defaults off
on a live run, so nothing trades until master is switched on — and at that
moment MAIN is live unless it was explicitly turned off.

Check against your DB: was `main_enabled` present in `meta` before that fill, or
absent and defaulting? Report what you find. Do not change the flag.

## Boundaries (unchanged)

- Change nothing on that engine without the user's instruction — no flags, no
  master, no restart, no redeploy.
- Never touch the Tokyo host or its databases.
- Never read, print or commit secret values.
- You own that box; I own analysis and code on this branch.
