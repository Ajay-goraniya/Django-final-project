# User asks to H1 (per V's standing note, 19:48 UTC 09-10)

| date/time UTC | ask | what was done |
|---|---|---|
| 09-10 ~19:30 | "how's binary tree research going?" | Answered from the ledger: base rates confirmed (41.7% flip at t=20 s on 72,331 candles), prefix table has no early information, all three prescriptive forms failed, the book already prices the path. |
| 09-10 ~19:50 | "are you sure you're talking about binary tree? candle 0 1, 1 0 idea? EF should know when to fire and it cannot be decided by a gate — even a child knows that. It can only be decided if you give it a trained brain that knows that move is wrong and it will reverse because this this this and that. Don't do unnecessary or unuseful work, go in a right direction not wrong." | Confirmed same object (sign(price−open) sampled every second = the 0/1 path). Accepted the correction: gate framing is dead and further gate variants are banned. Recorded the direction change below. |

## Direction correction accepted (09-10 19:50, from the user)

**The user's point, restated so it is not lost:** a gate is a threshold bolted onto a weak signal. What
they want is the *direction model itself* to know a move is wrong and will reverse, with reasons.
That is Task 11.2 (retrain the forecaster) and Task 12a (a learned tree as the direction model), not
any further gate/sizing variant.

**Banned from here unless the user reverses it:** more on/off gates, more stake modifiers, more
threshold sweeps on an existing weak score. Three of those failed today and a fourth would be
fitting, not testing.

**What the data says the "trained brain" must overcome**, and this is the load-bearing constraint:

1. The path alone does not beat the price — staking on P(win) − ask returns *less* per unit than flat
   staking, with 141/182 fires showing positive paper edge. The book prices the path.
2. Adding path features to the engine's own 35 features makes prediction **worse** out of sample
   (Task 8, negative in all six configurations).
3. **New, 09-10 19:45:** a confidence model trained on the engine's own feature dict has **no
   predictive power on the v11 twins** — OOS AUC **0.4746**, below random, in both halves. See
   `2026-09-10_1945_task11_1_confidence.md`.

So the brain cannot be built from the current feature set. It needs information the book does not
already have — deeper book state, trade-flow aggression, cross-venue lead/lag, the venue's own quote
path — not a better model over the same inputs.

## 2026-09-11 00:05 UTC — user relays a THIRD session's stranded work + "be aware of those common issues"
The user pasted output from a third session (not H1, not V) that had been given the same
`learner/H1_BRIEF.md` retro tasks. Its recurring failure modes, verbatim in substance:
1. **`SendMessage` failed** to reach V by name, alias and full session ID — same as H1 found.
2. **`git push` DENIED**: that session was not in the authorized repository set for
   `Ajay-goraniya/django-final-project`. Its `learner/H1_RESPONSE.md` never reached the branch —
   **confirmed: the file is not on the branch**. Its analysis was stranded and it asked the user to
   either grant push access or relay by hand.
3. **It duplicated work already done.** Its EF gate study concluded no gate passes both-halves
   validation — which H1 had already established and the user had already banned outright.
User instruction: *"be aware of those comman issues."*
**H1 action taken:** did not ask the user to change any permission. Rescued the one non-duplicate
claim it had (EF/REVERSAL same-candle conflict) by re-deriving it from the snapshots H1 already has,
and pushed it (`ef_rev_conflict.py`, note below). Operational issues recorded in STATE.md so the
next session does not repeat them.
