# D1 — where the Polymarket paper lane loses, and two owner-requested changes tested on it. 2026-09-22 (V). FINAL.
Data: `analysis/aws/task118_drawdown_fills.csv` (Mumbai relay, md5 a1e65e54 verified): 1,537 fills, 8795 + 8796, 09-16 18:35 →
09-22 00:05 UTC. Per-fill economics use **8795 EF only (742 fills)**; 8796 rows carry EF+REV combined pnl. Graded on
results.actual (Polymarket's own resolution). Plus Zurich paper 09-21 (68 fills, owner's export) and Zurich live 09-15..17 (158).

## The lane
742 fills · hit 53.2% · +$488 · +0.222/$1 · every day positive (09-19 +20 and 09-21 +31 are the weak days).
Max drawdown −$56 on **09-21 11:45 → 18:40** (58 fills, 29% hit). Longest loss streak 11 (09-19 07:55).
**Zurich vs Mumbai, same candles 09-21:** 67 shared, same side on 64, Zurich 30/67 right, Mumbai 33/67. Same call, same
result. Zurich paper's bad first day was the day, not the box. The open question from the interim is closed.

## Where it fails / where it earns — full grids, H1 | H2 (verify.py run on the two that pass)
| model p − market p (our side) | n | hit | per $1 | H1 \| H2 |
|---|---|---|---|---|
| 0.10–0.15 | 266 | 48% | +0.023 | +0.10 \| −0.04 |
| 0.15–0.20 | 341 | 55% | +0.233 | +0.24 \| +0.23 |
| 0.20–0.30 | 116 | 57% | +0.501 | +0.61 \| +0.37 |
| ≥0.30 | 19* | 58% | +1.115 | |
**gap ≥0.15: n=476, +0.334/$1, H1 +0.383 | H2 +0.279, sweep monotone, null (gap<0.15) +0.023 → verify.py PASSES all checks.**
Holds inside every ask band (interim table). corr(gap, EV)=0.84 — it is the EV idea done on the market's price, not on cheapness.

| engine EV threshold in force | n | per $1 | H1 \| H2 |
|---|---|---|---|
| 0.25 | 530 | +0.265 | +0.33 \| +0.19 |
| 0.15 | 212 | +0.116 | +0.16 \| +0.08 |
| fires that exist only because thr dropped to 0.15 | 182 | +0.059 (+$32 total) | +0.13 \| +0.01 |
The frequency knob adds trades and almost no money; it carried the 09-19 drawdown (interim) and is flat since.

Model confidence: p 0.50–0.55 realises 0.45 and still earns +0.23 both halves (cheap ask). Not the failure point on Mumbai.
rv60: <0.3 earns +0.08/+0.11, 0.3–0.6 earns +0.39; halves mixed, non-monotone → not a finding. Drawdowns sit in low-vol
(09-19) AND high-vol (09-21, rv60 0.76) windows: volatility is not the switch.

## Owner change 1 — "fine if the model stops trading when it has drawdowns"
Rule tested: equity − running peak ≤ −X → skip the next N candles (or rest of UTC day), peak resets on resume. Whole grid.
| lane | baseline pnl / per$1 / maxDD | X=15,N=24 | X=21,N=24 | X=30,N=24 |
|---|---|---|---|---|
| Mumbai 8795 (742) | +488 / +0.222 / −56 | +515 / +0.263 / −18 (7 halts, H1 +.31 H2 +.21) | +480 / +0.237 / −24 | +476 / +0.230 / −31 |
| Zurich paper 09-21 (68) | −1 / −0.005 / −44 | +2 / +0.015 / −18 | +20 / +0.122 / −22 | +8 / +0.054 / −30 |
| Zurich LIVE (155) | −45 / −0.084 / −109 | −21 / −0.048 / −18 | −24 / −0.062 / −24 | −23 / −0.051 / −32 |
Every X caps the hole at ≈X by construction. PnL is roughly unchanged on paper (−3% to +5%) and less negative live. Short halts
(N=6/12) and day-halts lose money on some lanes; N=24 (2 h) is the only column positive-or-neutral everywhere. **It bounds
drawdowns; it does not create profit.** Note: this is the coded PnL stop CLAUDE.md said we would never add; the owner has now
asked for it (09-22). Still paper-first, and it is one confirmation, not two.

## Owner change 2 — "based on Polymarket rules when it fires"
At fire time compute the settlement quantity (T0 ruler): line_open = TWAP60 before open, projected closing TWAP60 with remaining
seconds at the current price, Brownian sd → mechanical P(our side settles). Buckets fixed first.
| mechanical P(side) at fire | n | hit | per $1 | H1 \| H2 |
|---|---|---|---|---|
| <0.4 | 220 | 42% | +0.028 | −0.00 \| +0.06 |
| 0.4–0.6 | 332 | 52% | +0.240 | +0.36 \| +0.12 |
| ≥0.6 | 190 | 68% | +0.415 | +0.53 \| +0.30 |
**P(side) ≥0.4: n=522, +0.304/$1, H1 +0.422 | H2 +0.190, sweep monotone (−0.11, +0.16, +0.18, +0.29, +0.42), beats the lane
(+0.222) → verify.py PASSES.** The lane buys against the current line 82% of the time; the fires where the rule already says
our side is <40% are the ones that earn nothing. Per day the dropped set: +4, −14, +29, −26, +20, −1.
Combined with the stop: rule + X=21,N=24 → n=488, +$457, +0.317/$1, maxDD −23, both halves positive.
**Live caveat:** on the 158 live fills the rule keeps 55 at −0.259/$1. Live's loss is fills and retries (E1), not selection;
neither change fixes live by itself.

## Verdict
1. Two selection facts pass every gate on 742 paper fills: model−market gap ≥0.15 (+0.33/$1) and Polymarket-rule P(side) ≥0.4
   (+0.30/$1). Both are the signal knowing when NOT to fire. Both are paper-at-the-quote numbers.
2. A drawdown stop at $15–30 with a 2 h halt caps the hole at that size and leaves pnl within ±5%. It is a brake, not an engine.
3. The 0.15 EV threshold is the source of the flat fires. That is the engine's own frequency lever measured, not a new gate.
Nothing ships from this file. Next: paper on Zurich with (rule ≥0.4) + (stop 21/24) as arm B against the current lane, ≥60
fills, then the owner decides. Scripts: scratchpad mumbai_analyze.py, dd_stop.py, rule_confirm.py. Token budget D1: ~120k.
