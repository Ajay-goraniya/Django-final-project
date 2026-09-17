# Brief for GPT-Astra (third session on this project)

Read this first, then `analysis/h1/STATE.md`, then `learner/NOTES_v12.md`. Do not start work before both.

## What this is
A live BTC 5-minute up/down prediction-market trading system. Real money is on it right now.
Branch `claude/your-task-3wbq8u` is the only channel between sessions - inter-session messaging does not
work here, in any direction. Commit and push; the others read your commits. Pull with --rebase before
every push.

## Who owns what (do not write outside your lane)
| path | owner |
|---|---|
| `analysis/astra/` | you |
| `analysis/h1/` | H1 (research) |
| `learner/NOTES_v11.md`, `NOTES_v12.md`, `NOTES_polymarket.md` | V (live operations) |
| the Tokyo host, its databases, any other session's container | nobody but V. Never touch. |

Ask V for anything live by writing into `analysis/astra/REQUEST.md` and pushing. V polls it.

## The four rules that have already cost this project hours
1. **Check what a label means before you use it.** Predict.fun settles on Binance close >= open.
   Polymarket settles on a Chainlink 60-second TWAP. They disagree on ~10% of candles. Grading one
   venue's trades with the other's answer invented a large fake edge on 09-10.
2. **Never pair a fresh price with an older quote.** A quote even 5 seconds stale manufactures edge when
   the rule selects on cheapness. This killed five separate candidates.
3. **No gates.** No on/off gates, stake modifiers or threshold sweeps on a score already known to be weak.
   The user's words: a model should know the move is wrong and reverse, not be switched off by a threshold.
4. **Rain or sun.** A finding must work every day, or you identify when it works and switch only then -
   with the buckets defined before you look, the full grid reported, never the best cell.

## Before you report any finding
Run it through `analysis/h1/verify.py`. Nine checks: grading, sample size, both halves, permutation,
sweep monotonicity, costs, the obvious null, quote age, and McNemar on discordant pairs. `verdict()` is
True only if nothing failed. Under 60 graded fires in a bucket is "insufficient" - mark it, do not read it.
Accuracy is not PnL. Walk-forward only. Real data only. Retract your own claims when data reverses them.

Standing prior, from `analysis/h1/2026-09-11_0855_evidence_ladder.md`: every candidate so far decayed
toward zero as the evidence got more honest, and both that reached a live verdict failed it. Divide any
per-fire number built on recorded quotes by at least 3 before treating it as an expectation, and assume
the both-halves check is the binding constraint, not the headline level.

## Never
Handle, print or commit secret values. Deploy anything. Change live settings. Retrain or overwrite the
frozen model in `analysis/h1/models/`. Re-derive something the CLOSED table in STATE.md already settled.

## Output to the user
Short and plain. The user's instruction: "summarise it, I'm not reading all."
