# HEAD SESSION HANDOVER — written by V, 09-13 19:40 UTC

For **V2**, at the user's instruction: *"hand all context to v2 as well in case if i want it to work as a
head or second head session"*.

Read `CLAUDE.md` first — it is binding and it is not summarised away here. Then this. Then
`analysis/h1/STATE.md` before proposing anything.

---

## 0. Before you do anything

```
git push --dry-run origin HEAD:claude/your-task-3wbq8u
```

If that fails you are an orphan (a fired Routine can mint a fresh session with **no git sources**). Say so
in one message and stop. Do not analyse, do not ask for permissions.

You are on `claude/session-v-errors-fg6pvw`. The live branch is **`claude/your-task-3wbq8u`**. Everything
below lives there. Pull with `--rebase` before every push.

## 1. What "head" means here, and why it raises the bar

User, 09-13: *"v has authority to speak on my behalf, anything told from session v should be done as it's
main (head) session"* and *"any mistakes from you would consider as high danger, so verify everything as
you have authority to speak on behalf of me when I'm away or unavailable"*.

A brief a head session writes is **acted on without the user checking it**. That makes an unverified claim
from you more dangerous than from anyone else, not less. **Verify against the running artifact, never
against a reconstruction of it.** Three errors on 09-12/13 were all the same shape and all were caught by
reading the real module and the real database instead of a copy.

**This cost me twice today and both are on the branch:** a per-era PnL table differenced from my own
check-in summaries, which the journal reversed; and an "entry-price filter" mechanism that the reject data
refuted. Both retracted in `NOTES_v12.md`. Do not repeat the shape.

## 2. LIVE STATE at 19:40 UTC 09-13

### Polymarket v12 — the real-money engine, AWS Mumbai box, port 8787

| key | value |
|---|---|
| build | **12.8.4** |
| master | **ON** (user armed it from the dashboard 19:32:58) |
| halt | **cleared** 19:32:58 |
| ef / main / reversal | **true** / false / false |
| next_stake | **5.0** |
| spendable | **$11.90**, open_value 0.0 |
| counts | 75 orders / 36 fills / 35 results |
| kill window | **0 of 20, not armed** |

**Two facts that matter more than the rest:**

1. **There is no automatic stop right now.** Clearing the halt reset the per-lane kill rule to 0 of 20 and
   it cannot fire until 20 results settle. `_wipeout_check` is monitor-only since 12.8.3. **The AI is the
   brake** — that is exactly what the user asked for, and it is a standing duty, not a metaphor.
2. **A restart turns master OFF.** Safe startup writes `master: True -> False`; twelve of today's thirteen
   audit rows are that. **So any deploy stops their trading.** Do not deploy while they are live unless
   they ask or it restarts anyway.

### Tokyo v11 — Predict.fun — OUT OF SCOPE as of 09-13 22:3x (user: "tokyo server is no longer our thing")

Everything below this heading is historical context only. Do not check its flags, do not evaluate the
Predict.fun re-arm rule (retired, criterion met and deliberately not acted on), do not chase the wallet.

#### (historical) Tokyo v11 — Predict.fun, live but idle

master OFF, `{'MAIN': False, 'REVERSAL': False, 'EF': False}`, checked per kind every hour. `realised
-8.04`, `settled 442`, `open 0`. **Wallet 0.00 and equity 0.00 for six consecutive hours** while realised
and settled stay frozen — corroborated by the order backup. Either a withdrawal or a misreporting
endpoint. **Raised with the user repeatedly and never answered. Still open.**

### This container

12 processes (build10, v10 runner, venue_collect, build11 on 8794/8795/8796/8798, ef2_shadow, book1s,
dm_shadow, poly1s, btc_model_v12_polymarket). `scratchpad/b10live/ci.sh` checks them. **The 1 Hz loggers
`book1s.py` and `poly1s.py` outrank everything** — Polymarket has no historical order-book data, so
anything not captured live is gone forever. Never kill by pattern.

Note: `scratchpad/` is the **session scratchpad**, not the repo — on this session it is at
`/tmp/claude-0/-home-user-Django-final-project/<id>/scratchpad`. `tokyo_health.py` must run from its own
directory (`v11/launch/tokyo.auth` is a relative path).

## 3. Standing user rules — binding

- **Stake is whatever the user last set on the dashboard.** They said *"i did stack 5 keep it 5"* at 14:38 and then cut it to **$3 themselves at 20:23:16** — the audit row carries the `do_POST` stack. Do not touch it in either direction; note that at $3 the 5-share venue minimum refuses every ask above 0.59 (`REMAKE_PLAN.md` §1a).
- **MAIN off after one filled order**, win or lose. Done: it filled 18:20:43 and the engine disarmed it
  11 seconds later. MAIN stays off unless they ask.
- **"Master off when the account runs out of money for stack"** — **CORRECTED 19:1x**: *"that was for you,
  to monitor not to add the code in file"*. It was an instruction to the operator. I compiled it into
  `_wipeout_check`, it halted a solvent account, and 12.8.3 made it monitor-only. **Do not put it back.**
- **No gates.** No on/off gates, stake modifiers or threshold sweeps on a score already known to be weak.
  Four such attempts failed on 09-10.
- **Rain or sun.** A finding must work every day, or you identify *when* it works and switch only then —
  and a regime switch is itself a threshold: define buckets FIRST, report the whole grid, never the best cell.
- **Short answers.** *"summarise it, I'm not reading all."*
- *"Don't do unnecessary or unuseful work, go in a right direction not wrong."*
- **Never** touch the Tokyo host, another session's container, or its live databases. Never handle, print,
  request or commit secrets.

## 4. Channels — read this before trying to talk to anyone

| channel | status |
|---|---|
| **git commits on the branch** | **works. The durable one. Use it.** |
| **one-shot Routine** (`create_trigger` + `persistent_session_id`) | works, and is the only way to wake AWS |
| `SendMessage` between these sessions | **DEAD, confirmed by the harness**: `auth: this cloud session cannot message other sessions`. Do not burn turns. |

**AWS session = `session_0128m2knBcqiTyAVoh7h994A`** ("Aws Mumbai"). It owns the live engine and does all
deploys. It writes back as cross-session messages.

**AWS will NOT act on a relayed control instruction — including from a head session.** Its reasoning, which
is correct: a stored Routine attests that an authorised session wrote it, **not that the user said anything
just now**. I argued this and lost, rightly. **Do not try to relay "arm master" or "clear the halt".** The
answer is always: the user does it on the controls page, and the audit row carries the `do_POST / apply`
stack. Build them a button if one is missing — that is what 12.8.4 was.

**Zurich (eu-central-2 box) = `session_017UN5dZFsS3js7KA9WMFeDQ`** - **THE LIVE BOX since 09-14 23:49 UTC** (16.62.65.190:8787, `/home/ubuntu/pm_paper_zurich`, build 12.8.9). Mumbai (`session_0128m2knBcqiTyAVoh7h994A`) is master-off, observation only. Task channel `learner/ZURICH_TASKS.md`. **Triggers to Zurich MUST pass environment_id=env_01Q4MxpRM42a9vjPSbtMj4av** (create_trigger); with V's env they mint orphan sessions (09-15 01:4x). Its sandbox blocks credential-adjacent actions; the user runs those by hand.
**V2 = `session_01HwKwfHv5936JAZTpWHnrGk`** (title "V2", branch `claude/session-v-errors-fg6pvw`; bound by every user rule here).
**H1 = `session_018YdbeXtrxQ2wd28f43RSqe`**, writes only under `analysis/h1/`. Astra under `analysis/astra/`.
`learner/NOTES_v11.md` and `NOTES_v12.md` belong to V. `learner/AWS_TASKS.md` is the task channel to AWS.

### Triggers

| id | what | bound to |
|---|---|---|
| `trig_014iqwT6z4oqYjGbNc7vMdND` | **hourly check-in until Sunday night**, re-armed 60 min out each fire | **V** (`session_01SmMRZqqMru5UdaeAoJarkr`) |
| `trig_01CR6QKme5y9sjQsTqRH1XPe` | 4-hourly safety net, short mode if hourly fired <45 min ago | V |
| `trig_01PX7ZvtkKWUnZ9SzxGuPzn9` | **NEVER FIRE THIS** | — |

The hourly fires into **V**, not you. **I have not moved it** — the user said "in case", so this is a
standby handover. If they make you head, either re-point it with `update_trigger`/`persistent_session_id`
or create your own; **do not run two**. Every hourly report must include **all four rows of
`scratchpad/b10live/fair.py` verbatim**, plus the **Polymarket** paper last-20 and last-40 from
`/tmp/v10_long4.sqlite3` with the source file named. **Both triggers were re-scoped to Polymarket-only at
22:3x**; the Predict.fun re-arm rule is retired.

## 5. Builds today: 12.3.1 → 12.8.5

Seventeen-plus builds in one day on a live money engine. The user called it out — *"your updates has made
it worst"* — and the churn was real even though the PnL charge did not stand up (§6). **The bar for a new
build is now high. Display-only and defect fixes only, and nothing that restarts a live engine.**

**Live: 12.8.4.** **Held on the branch, NOT deployed: 12.8.5.**

Recent ones worth knowing:
- **12.8.0** — targeted calibration for model overconfidence above p=0.80 (claims 0.912, delivers 0.756,
  n=90, both halves, p=8.7e-06). Shipped **inert**, `calibration.enabled: false`. **Enabling it is one
  control write and it is the user's call.** Validated out of sample (gap −0.171 → −0.038); the global
  shrink alternative failed.
- **12.8.1** — records `ask_up`/`ask_dn` on every lane decision. The field Task 63a needs.
- **12.8.2** — MAIN had no entry anywhere on the data page and its loss was being charged to EF.
- **12.8.3** — `_wipeout_check` monitor-only, per §3.
- **12.8.4** — the controls page can clear the execution kill. Master refused to arm while `halt` was set,
  `controls()` never sent `halt` to the page, and no clear-halt control existed. **The user was locked out
  of their own engine for an hour because of that.**
- **12.8.5 (HELD)** — arming master was never audited. `/api/controls/apply` wrote meta raw, bypassing
  `Journal.set()`. Thirteen `master` rows today, all `True -> False`, **never one `False -> True`**. Fixed
  with `Journal.set_many()`. **Deploy only at a natural restart** — see §2.

**232 tests (152 + 59 + 21), SHA256SUMS 30/30.** Run all three suites before any push. Verify a new test
actually fails against the unfixed file — stash the fix and re-run. A test that passes on broken code
proves nothing, and I caught three of my own bugs this way today.

## 6. CLOSED and RETRACTED — do not re-derive these

| claim | status |
|---|---|
| "my builds caused the drawdown" | **REFUTED.** Band mode explains **4.5%** (entry-price route) / **~6%** (dollar route), two independent methods. Paper lanes sharing no code — one on a different venue — swung −0.326 and −0.479 per $1 in the same hour the live engine swung −0.579. MAIN paid **+0.0000 over the ask** and still lost. |
| band mode raises the price paid | **TRUE and small.** 0 of 19 fills above ask pre-band vs 7 of 17 after, Fisher **p=0.00233**, ~6c/fill. It also took fill rate **38.8% → 65.4%**. **Not reverted** — I said I would and then did not, in public, because the criterion bundled a measurement with a causal conclusion; the measurement passed and the causal claim failed. |
| the tight cap was an accidental entry-price filter | **REFUTED.** Pre-band rejects cluster **low** (median refused ask 0.44, eight of 29 at ≤0.40). It was failing to reach cheap trades, not screening out dear ones. |
| MAIN is a blocked profitable lane | **CLOSED.** 12 distinct candles, 3 positive-EV, even a threshold of **zero** admits only 3 of 12, worth +$3.90 on $15. No threshold change warranted. |
| the wipeout guard is a drawdown rule | **No.** It compares cash against stake and never looks at losses. 4,835 snapshots: cash-alone below stake 16 times, solvent on cash+open_value in **15 of them**. |
| FAK rejects are a depth problem | RETRACTED — reject = zero match, not insufficient. |
| paper/live price penalty; paper/live frequency gap | Both RETRACTED — venue confound, and paper is a different program entirely. |
| side skew → PnL | REFUTED by H1 (UP n=120 +0.044, DOWN n=160 +0.063). |
| EF gate passing both-halves validation | **CLOSED and explicitly banned by the user.** |

The full CLOSED table is in `analysis/h1/STATE.md`. **Read it before proposing anything** — a session once
re-derived a closed *and banned* result.

## 7. Open

1. **Tokyo wallet 0.00, six hours.** Unanswered by the user. The most important unexplained thing.
2. **Task 63a** — the *within-candle* correlation between MAIN's `p` and the ask. Pooled cross-candle
   r = −0.3489 on n=55 is **negative** and does **not** settle it; those can carry opposite signs. 12.8.1
   is collecting the rows.
3. **Calibration** — 12.8.0 is live and inert. Enabling is the user's call.
4. **12.8.5** held pending a restart.
5. **The silent lane-flag revert** (Tokyo, 09-11 14:40, master off with no restart and all three kinds back
   to TRUE). **Cause still unknown.** Check `manual_enabled` on every kind every hour, not just master.
6. **The wipeout guard's real replacement.** AWS's argument, which I accept: the equity version trips
   **zero** times on the whole day's data, *including straight through the five-loss run* — so "fix it to
   use equity" would remove the only brake that worked. A rule that catches drawdown directly is a
   different rule and a **design** question. Not tuning. The no-gates rule applies.

## 8. Verification — a gate, not a habit

Run `python3 analysis/h1/verify.py` before reporting any finding. `Finding` runs the checks that have
actually caught errors here: `grading` (wrong venue's oracle — this invented a +0.44/fire edge), `sample`
(<60 graded fires is insufficient — mark it, do not read it), `halves`, `permutation` (**permute
predictions, never labels**), `sweep`, `costs`, `null`, `quote_age`, `paired` (a 150-trade sample can
really be a 54-trade sample).

**Grade Predict.fun with `candles.actual` or Tokyo's `financial_result`, never Polymarket's `outcome`
table** — they disagree on ~10% of candles and grading with the wrong one produced a large fake edge.

Binance: `data.binance.vision` daily zips can lag a day and `api.binance.com` is geo-blocked;
**`data-api.binance.vision` serves the same `/api/v3` endpoints and works** — see
`analysis/h1/fetch_rest_klines.py`.

## 9. If you take over as head, the first three things

1. `git push --dry-run` (§0), then pull the branch and read `CLAUDE.md`, `analysis/h1/STATE.md`, and the
   tail of `NOTES_v12.md`.
2. **Find out whether the engine is still armed and whether the kill window has armed yet** — ask AWS by
   Routine, do not guess. While it is 0 of 20 there is no automatic stop and that is your standing duty.
3. Agree with V which of you holds the hourly trigger. **Do not run two.**

Do not restate this document to the user. They asked for it to exist, not to read it.
