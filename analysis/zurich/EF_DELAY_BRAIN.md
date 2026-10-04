# Training EF to beat the price we GET, not the price it SEES

V/owner: improve the MODEL, not the execution. Root cause (NC-10/NC-13): EF's edge is real at the decision
ask and gone ~0.25 s later once the makers have repriced.

Read-only, Zurich data only, London untouched, nothing live. `analysis/zurich/ef_delay_brain.py`.
**This is not NC-12** — nothing here ranks or selects by the existing calibrated edge; the model predicts
the delayed outcome directly.

## Data and how the sub-second asks were obtained

Signals = every `decide_log` pass with **raw EV ≥ 0.15** (so every fire is included, since the live bar is
0.25): **35,855 passes on 622 candles, 5 days**, graded on the **venue's own gamma resolution**.

No interpolation and no 1 Hz fallback was needed. The engine writes ~4 decide rows/s, and consecutive rows
for the same candle are p50 **257 ms** apart with 98.2% under 300 ms, so the row ladder itself supplies the
delays. For a row at *t*, the delayed ask is the first same-candle row at ts ≥ t+D, taking its
`up_ask`/`dn_ask` **for our side** — using the both-side columns rather than that row's own `ask` keeps the
delayed price independent of whichever side the later pass happened to pick.

| requested | **achieved lag** p10/p50/p90 | mean ask move |
|---|---|---|
| +250 ms | 253 / **259** / 288 ms | **+0.43c** |
| +500 ms | 507 / **517** / 561 ms | +0.60c |
| +1000 ms | 1015 / **1034** / 1118 ms | +0.73c |

Features are decision-time only: 32 of the engine's own 44 `decide_log` features (absolute price levels
dropped — on a 5-day sample a split on a raw BTC level selects a calendar day), plus logit(ask),
logit(p_raw) and sec/300. Ridge, walk-forward by day, fit on prior days only, scored on 4 test days.

## 1. The root cause, measured

Today's EF (first pass with raw EV ≥ 0.25) on 263 scored candles, priced at the delayed ask:

| | +250 ms | +500 ms | +1000 ms |
|---|---|---|---|
| **EF today** | **+0.059** | **−0.021** | **−0.055** |

**EF crosses from profit to loss between 250 ms and 500 ms.** That is NC-10/NC-13 quantified on our own
data, and it is the thing to fix.

## 2. The delay brain — full sweep, never the best cell

| arm | n | hit | per$1 @+250 | @+500 | @+1000 | H1@250 | H2@250 | perm p@250 |
|---|---|---|---|---|---|---|---|---|
| EF today (raw EV≥0.25) | 263 | 51.7% | +0.059 | −0.021 | −0.055 | +0.033 | +0.084 | 0.091 |
| brain pred ≥ −0.10 | 397 | 54.4% | +0.045 | +0.026 | +0.013 | +0.021 | +0.070 | 0.043 |
| brain pred ≥ −0.05 | 380 | 53.7% | +0.036 | +0.017 | +0.003 | +0.004 | +0.067 | 0.079 |
| **brain pred ≥ 0** | 356 | 55.6% | **+0.077** | **+0.045** | **+0.035** | +0.043 | +0.111 | 0.014 |
| brain pred ≥ +0.05 | 341 | 55.7% | +0.069 | +0.044 | +0.020 | +0.037 | +0.101 | 0.028 |
| brain pred ≥ +0.10 | 320 | 55.6% | +0.069 | +0.060 | +0.068 | +0.046 | +0.092 | 0.033 |

The brain stays positive at every delay where EF today does not. But the paired test says **that is not
because it picks better moments**:

| delay | shared candles | brain | EF today | discordant | brain | EF today |
|---|---|---|---|---|---|---|
| +250 ms | 198 | +0.108 | **+0.130** | 123 | −0.024 | **+0.013** |
| +500 ms | 196 | **+0.062** | +0.050 | 122 | **−0.047** | −0.065 |
| +1000 ms | 197 | **+0.048** | +0.028 | 123 | **−0.041** | −0.073 |

On the candles both trade the brain is **worse** at 250 ms and only marginally better later. Its headline
number comes from elsewhere:

| | n | +250 ms | +500 ms | +1000 ms |
|---|---|---|---|---|
| brain-only candles | 158 | +0.038 | +0.025 | +0.018 |
| **EF-only candles (brain refuses)** | 65 | **−0.160** | **−0.230** | **−0.302** |

**The value is the veto, not the selection.**

## 3. The veto — and this one passes the gates

Split today's EF fires by what the delay model says about them:

| cell | n | hit | +250 ms | +500 ms | +1000 ms | H1 | H2 | perm p |
|---|---|---|---|---|---|---|---|---|
| **EF fires the model KEEPS (pred ≥ 0)** | **130** | **58.5%** | **+0.201** | **+0.142** | **+0.106** | +0.167 | +0.236 | **0.001** |
| EF fires the model VETOES (pred < 0) | 133 | 45.1% | −0.081 | −0.180 | −0.212 | +0.010 | −0.170 | 0.719 |
| EF fires, all | 263 | 51.7% | +0.059 | −0.021 | −0.055 | +0.033 | +0.084 | 0.091 |

- **n 130 ≥ 60** ✔
- **both halves positive** (+0.167 / +0.236) ✔
- **permutation p = 0.001** — a flip pays the OPPOSITE side's delayed ask (the c299e19 correction) ✔
- **positive at all three delays**, which is the whole point ✔
- the vetoed half is its own confirmation: 45.1% hit, negative and worsening with delay, perm p 0.719, and
  its halves split +0.010 / −0.170. The two sets are genuinely different populations, not a lucky cut.

### The one gate it fails, stated plainly

The veto threshold sweep is **NOT monotone**: −0.20 → +0.150, −0.10 → +0.184, −0.05 → +0.161,
**0.00 → +0.201**, +0.05 → +0.162, +0.10 → +0.164, +0.20 → +0.216 (at +250 ms). It dips either side of the
value V specified and peaks there and at the far end.

That is the shape CLAUDE.md warns about, so the exact threshold is not established. But it differs from
NC-12 in a way that matters: **every threshold across the whole swept range is positive at all three
delays** (+0.057 to +0.216 at +1000 ms), whereas NC-12's tier sweep collapsed to +0.056 at the 100% end.
The *direction* is robust; the exact bar is not.

## Verdict

1. **The root cause is confirmed and now has a number**: EF today is +0.059 at +250 ms and −0.055 at
   +1000 ms. The edge dies inside one second.
2. **A delay-aware model does not choose moments better** — on shared candles it is worse at 250 ms.
3. **It does work as a veto**: the half of EF's fires it refuses are worth −0.081 / −0.180 / −0.302 per $1,
   and the half it keeps are +0.201 / +0.142 / +0.106, on n 130 with both halves positive and perm p 0.001.
4. What I would put forward is therefore narrow and cheap: **a veto on EF's own fires, not a new fire
   rule.** It needs no change to how EF decides, only a gate on what it sends.
5. What it still needs before anyone acts: more days (5 day buckets, 4 scored), a monotone threshold sweep,
   and a London-execution pass — every number above is at the delayed ask with no fill model on top.
