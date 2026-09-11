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
- **"Don't do unnecessary or unuseful work, go in a right direction not wrong."**
- **"Rain or sun"**: a finding must work every day, or you identify *when* it works and switch only
  then. A regime switch is itself a threshold — define buckets FIRST, test them all, report the full
  grid, **never the best cell**.
- Answers to the user are **short and plain**: *"summarise it, I'm not reading all."*

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

`verdict()` returns True only if nothing FAILED. Run `python3 analysis/h1/verify.py` to see it
reject a real false finding from 09-10 and accept a real true one. **In that rejection every other
check passes and only the grading check fires** — which is why they are run as a set, and why
grading is first.

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
produced a large, entirely fake edge. Grade with `candles.actual` or Tokyo's `financial_result`.

## Boundaries

- **Never** touch the Tokyo host, another session's container, or its live databases.
- **Never** handle, print, request or commit secret values.
- Session H1 writes **only** under `analysis/h1/`. `learner/NOTES_v11.md` and `learner/NOTES_v12.md`
  belong to session V. Pull with `--rebase` before every push.
- Binance: `data.binance.vision` daily zips can lag a day, and `api.binance.com` is **geo-blocked**
  from these containers. **`data-api.binance.vision` serves the same `/api/v3` endpoints and works** —
  see `analysis/h1/fetch_rest_klines.py`.
