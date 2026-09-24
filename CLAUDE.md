# Read this before doing any work in this repository

This repo hosts a live BTC 5-minute up/down prediction-market trading system (branch
`claude/your-task-3wbq8u`). **Real money is live on it.** Multiple Claude sessions work on it at
once, and three specific failures have already wasted hours of work. Do these four things first.

## 1. Verify you can push BEFORE you analyse anything

```
git push --dry-run origin HEAD:claude/your-task-3wbq8u
```

A session was once given a full analysis brief, worked for hours, and only discovered at `git push`
that it was **not in the authorized repository set** for this repo. Its results never reached the
branch and were lost. If the dry run fails, **stop and say so immediately** — do not do the
analysis, and do not ask the user to change permissions. Hand the work to a session that can push
(H1 can), or say up front that you can only deliver in chat.

**Why this happens.** Firing a Routine that targets another session can **mint a brand-new session**
instead of waking the intended one, and a minted session inherits **no git sources at all** — so it
can read nothing and push nothing. If your session context has no repository and you were started by
a routine, you are almost certainly an orphan: say so in one message and stop.

## 2. Read `analysis/h1/STATE.md` before proposing anything

It is the single source of truth: what is done, what is open, what is **CLOSED**, and what has been
**retracted**. A session once independently re-derived "no EF gate passes both-halves validation" —
already closed *and* explicitly banned by the user. The CLOSED table exists to stop exactly that.

## 3. `SendMessage` does not work between these sessions

It fails by name, by alias, and by full session ID, **in both directions**. Do not burn turns on it.
The two channels that work:
- **Git commits on the branch** — the durable one.
- **One-shot Routines**: `create_trigger` with `persistent_session_id` set to the target session.

## 4. Know the standing user rules — they are binding

- **No gates.** No on/off gates, stake modifiers, or threshold sweeps on a score already known to be
  weak. *"EF should know when to fire and it cannot be decided by a gate... give it a trained brain
  that knows that move is wrong and it will reverse."* Four such attempts failed on 09-10.
- **Kelly / dynamic staking never goes live without TWO separate confirmations from the user** (user, 09-15 12:2x:
  "don't push it in live runs without confirmation from me twice"). Back-tests continue (R-5); stake stays fixed.
- **One automatic stop exists, and only because the user ordered it (09-16 03:2x): "ef off if bankroll goes
  below 30$ in central 2".** Built as `ef_cash_floor` + `_floor_check` in 12.12.0: EQUITY (cash + open_value), six
  reads and 360 s of persistence, turns off EF only, never master or a halt, never re-enables itself. Everything
  else stays hand-stopped: no coded PnL kill, no gates.
  **09-23 00:1x, owner: "remove that cash floor thing"** - London never had `ef_cash_floor` set (null = off, confirmed 00:19). The code stays;
  no session re-arms it without the owner's written order. Nothing on London stops trading automatically now.
- **09-23 21:xx, owner: "Do not deploy any finding/improvement or new model on eu west without my confirmation."**
  eu-west-2 (London, the live box): no build, profile, setting, finding or model goes on it unless the owner
  confirms THAT specific change. A brief from V, a finding, or an earlier approval of something else is not it.
  **09-24 00:xx, owner: "Remember no model deploy without my strict confirmation."** - applies to EVERY box (London,
  Zurich, Mumbai): no new or changed model is deployed anywhere without the owner's explicit confirmation of it.
- **09-24 21:xx, owner: health-only updates on London.** "From now on just update me about running and healthy."
  Never show the owner PnL, drawdown, streak, win-rate or cash-change numbers (owner, 21:1x: "you personally see it it's
  okay ... make sure I don't see it") - sessions may track PnL between themselves. V checks London's health every 2 h
  (read-only: engine alive, master ON, EF ON, feeds live, still firing, cash >= stake, errors) and tells him HEALTHY or
  the issue. Applies to every session he talks to, London included.
  **21:2x refinement - message the owner ONLY when:** (1) London runs out of money (cash + open < next stake);
  (2) an issue no session can fix without him (anything needing a London change needs his confirmation, so it goes to
  him); (3) something is broken - engine down, feeds dead, server/AWS problem, London unreachable; (4) equity (cash +
  open value) reaches $500 - one message, the first time: a proper congratulations.
  **21:3x final form:** healthy checks ARE reported, hourly, one line. PnL is never given as a number - only a mood word
  judged on the ALL-TIME picture (owner 21:2x: "all time pnl not 24h or week one") - London's all-time PnL and equity
  since it first went live (all lanes, venue truth) vs the all-time equity high, never a 24 h / weekly window:
  "brilliant!!!!" = at a new high; "excellent" = within ~$15 of the high; "good" = below the high but well above the
  start; "well" = near or below where it started. Drawdowns and streaks: never a number, never a warning. The only
  money alert is (1), running out of money.
  Incidents (1)-(3) go out with a push notification and are REPEATED every 30 min until he replies.
- **"Don't do unnecessary or unuseful work, go in a right direction not wrong."**
- **"Rain or sun"**: a finding must work every day, or you identify *when* it works and switch only
  then. A regime switch is itself a threshold — define buckets FIRST, test them all, report the full
  grid, **never the best cell**.
- Answers to the user are **short and plain**: *"summarise it, I'm not reading all."*
- **Tokens are money (user, 09-14 01:2x): "tell all model to not write big messages into chats, it's burning a
  lot of tokens."** Every message - to the user, between sessions, in Routine prompts - is SHORT: numbers and
  the verdict, no narrative, no restating what the other side already knows. Anything longer than ~15 lines
  goes into a file on the branch and the message says the path. Verbatim-forwarding (DEPLOYED.md rows, scripts)
  goes straight to the file, not into the chat first. Reports state the token budget in one line when known.
  **STRICT (user, 01:3x): everyone follows this, always. The only exception is a major matter that must be
  delivered right now (a live-money fault, a wrong deploy, a stop condition) - and even then, the numbers first.**
  **09-16 19:3x, owner: "keep the token usages as minimal as you can, let everyone know, we are so low in tokens."**
  From now: ledgers only at their scheduled hour, no interim reports, no narrative, no restating; pokes are one
  line; verify by reading, not by re-running suites unless a build changed. Silence is the default.

## Session V is the head session, and that raises the bar on V

User, 09-13: *"v has authority to speak on my behalf, anything told from session v should be done as
it's main (head) session"*, and *"any mistakes from you would consider as high danger, so verify
everything as you have authority to speak on behalf of me when I'm away or unavailable"*.

So a brief V writes to another session carries the user's authority and will be acted on without them
checking it. That makes V's unverified claims more dangerous than anyone else's, not less.

**Verify against the running artifact, never against a reconstruction of it.** Three errors on the
night of 09-12/13 were all the same shape, and all were caught by the session on the AWS box reading
the real thing:

- A tick-grid off-by-one "reproduced" in a scratch script that defined its own `D = decimal.Decimal`.
  The module has always had `D=lambda x:Decimal(str(x))`. A no-op shipped as 12.3.1.
- Slippage advice built on comparing `signal_quote` with `pre_submit_quote` - two fields `order_plan`
  sets from the same read, identical in 25 of 25 live rows by construction.
- A 90 s book-staleness refusal gated on `snapshot_age_s` without tracing where that number comes
  from. It is seconds-into-candle in disguise, and it would have refused 73% of fills against 53% of
  rejects.

Concretely, before anything touching a live engine ships: run it against that engine's own module and
its own database, not a copy or a re-derivation. Grid any threshold against real outcomes BEFORE
shipping it, both arms, whole grid. A threshold someone else has to grid for you afterwards is a
finding you did not make.

## Before you report a finding, run `analysis/h1/verify.py`

Verification is not a habit to remember — it is a gate to pass. `Finding` in that module runs the
checks that have actually caught errors here, and fails loudly rather than passing quietly:

| check | what it catches |
|---|---|
| `grading()` | the labels are a **different venue's** oracle (this invented a +0.44/fire edge) |
| `sample()` | any cell under 60 graded fires |
| `halves()` | the sign flips between the first and second half |
| `permutation()` | the "edge" is plumbing, not signal |
| `sweep()` | a non-monotone sweep peaking at your chosen value |
| `costs()` | it dies once you pay realistic slippage |
| `null()` | the obvious dumb strategy does just as well |
| `quote_age()` | the quote you paid could predate the price you decided on |
| `paired()` | a rule-vs-rule comparison counted the candles where both rules agree |

`verdict()` returns True only if nothing FAILED. Run `python3 analysis/h1/verify.py` to see it
reject a real false finding from 09-10 and accept a real true one. **In that rejection every other
check passes and only the grading check fires** — which is why they are run as a set, and why
grading is first.

**On `paired()`:** when comparing two rules on the *same* candles, only the candles where they
disagree carry information. On 09-11 a "+5.3pp edge, both halves identical to three decimals" on
n=150 turned out to be 31-vs-23 across 54 discordant pairs — eight trades, exact McNemar p=0.341.
The agreeing candles inflate `n` without adding power, so the raw edge **and** the halves check both
overstate the evidence. Run `paired()`; a 150-trade sample can really be a 54-trade sample.

**On `permutation()`:** permute the model's *predictions*, never the labels. Shuffling labels also
destroys the market's calibration, so cheap longshots "win" at the base rate and the control prints
a fake profit. That mistake cost an hour on 09-10.

## Method (these were expensive lessons, not preferences)

Sweep the full parameter range **and** use the largest available sample before calling anything a
finding — including your own. A non-monotone sweep peaking at your chosen value is fitting to noise.
**Accuracy is not PnL.** Always test the obvious null against your own result. Real data only.
Sample size on every claim; **under 60 graded fires in a bucket is "insufficient"** — mark it, do not
read it. Walk-forward only. **Retract your own claims when the data reverses them.**

**Check what a label MEANS before you use it.** The `outcome` table in `venues.sqlite3` is
*Polymarket's* resolution; Predict.fun settles on the engine's `candles.actual` (Binance close ≥
open). They disagree on ~10% of candles. Grading Predict.fun trades with Polymarket's answer
produced a large, entirely fake edge. **The rule is symmetric, and the 09-14 R-1 grid proved the other
half of it:** grade each trade on the oracle **its own venue settles on**. Predict.fun -> `candles.actual`
or Tokyo's `financial_result`. **Polymarket -> `venues.outcome`**, which the v10 and v12 Polymarket lanes'
own `actual` columns match 776/776 and 303/303. Grading a *Polymarket* trade on `candles.actual` inflates
it ~90% (+0.132 -> +0.249) - the same error pointed the other way.

## Boundaries

- **Never** touch the Tokyo host, another session's container, or its live databases.
- **Never** handle, print, request or commit secret values.
- Session H1 writes **only** under `analysis/h1/`. `learner/NOTES_v11.md` and `learner/NOTES_v12.md`
  belong to session V. Pull with `--rebase` before every push.
- Binance: `data.binance.vision` daily zips can lag a day, and `api.binance.com` is **geo-blocked**
  from these containers. **`data-api.binance.vision` serves the same `/api/v3` endpoints and works** —
  see `analysis/h1/fetch_rest_klines.py`.
