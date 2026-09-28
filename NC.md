# NC - New Changes (owner's list)

Findings the owner asked to record. Nothing here is deployed on London (eu-west-2) without the owner's
confirmation of that specific change (CLAUDE.md rule, 09-23).

## NC-1 - REVERSAL on Polymarket: trade only up to 240 s into the candle (09-23)

- **Why:** Polymarket settles on TWAP60 (average of the last 60 s vs the 60 s before the open), not on the plain
  candle close. A reversal that happens in the last minute only moves part of that average, so late REVERSAL
  bets stop paying. Predict.fun settles on the plain candle, so it is not affected the same way.
- **Result (8-day Polymarket replay, exact fee, graded on Polymarket's own outcome):**

  | window | trades | per $1 | w/o top 3 | all checks | losing days |
  |---|---|---|---|---|---|
  | 0-240 s | 394 | +0.215 | +0.144 | PASS (shuffle p=0.001, beats cheap-side null) | 1 of 9 |
  | 0-200 s | 323 | +0.144 | +0.063 | FAIL (shuffle, null) | 3 of 9 |
  | 200-240 s | 71 | +0.538 | +0.304 | PASS | 1 of 9 |
  | after 240 s | 65 | about -0.03 without one lucky 1c ticket | | | |

- **Meaning:** keep REVERSAL's trades up to 240 s; do not cut at 200 s (200-240 s is its best window);
  never trade it after 240 s. London's order engine already refuses orders after 240 s, so no code change is needed.
- **Limits:** the replay assumes every order fills (live, 40-60% of first tries are refused). Zurich's live
  shadow REVERSAL is weaker so far (32 trades, +0.034/$1) - confirm at 60 trades before any live use.
- **Status:** tested on replay, not deployed. REVERSAL stays OFF on London.
- **Full grid (every bucket, Polymarket replay, 459 graded REVERSAL):**

  | bucket | n | right | per $1 | w/o top 3 |
  |---|---|---|---|---|
  | 0-60 s | 36 (<60) | 66.7% | +0.098 | -0.016 |
  | 60-120 s | 123 | 62.6% | +0.077 | +0.001 |
  | 120-180 s | 119 | 65.5% | +0.202 | +0.014 |
  | 180-200 s | 45 (<60) | 64.4% | +0.213 | -0.056 |
  | 200-240 s | 71 | 83.1% | +0.538 | +0.304 |
  | 240-300 s | 65 | 49.2% | +1.769 (one 0.010 ticket) | -0.034 |

  0-240 s by day: 09-08 -0.153 | 09-09 +0.032 | 09-10 +0.176 | 09-11 +0.255 | 09-12 +0.846 | 09-13 +0.643 |
  09-14 +0.283 | 09-15 +0.067 | 09-16 +0.043. Costs: +1c +0.185, +2c +0.157, +5c +0.086.
  Predict.fun (Mumbai 8796): 43 trades, too few to compare.
- **Reproduce** (save as a .py next to `analysis/h1/verify.py`'s repo root; args `--rows lanes_twap60.csv --venues venues.sqlite3 --lo 0 --hi 240`):

```python
"""REVERSAL <240 s on the 8-day Polymarket replay, through analysis/h1/verify.py's gates (V, 09-23).
Input: lanes_twap60.csv (replay_lanes_1s.py --open twap60) + venues.sqlite3 (q = both asks at 1 Hz, outcome = Polymarket
resolution). Exact fee 0.07p(1-p) inside the stake; $1 per fire."""
import sys, csv, sqlite3, bisect, argparse, numpy as np, datetime as dt
sys.path.insert(0, 'analysis/h1'); import verify as V
ap = argparse.ArgumentParser(); ap.add_argument('--rows', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--lo', type=float, default=0); ap.add_argument('--hi', type=float, default=240); a = ap.parse_args()
vc = sqlite3.connect(a.venues); Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')]; QT = [q[0] for q in Q]
OUT = {int(e): x.upper() for e, x in vc.execute('select epoch,actual from outcome') if x}
def asks(ts):
    i = bisect.bisect_left(QT, ts - 5); best = None
    for j in range(i, min(len(Q), i + 11)):
        if abs(Q[j][0] - ts) <= 5 and Q[j][1] is not None and Q[j][2] is not None and (best is None or abs(Q[j][0] - ts) < abs(best[0] - ts)): best = Q[j]
    return (float(best[1]), float(best[2])) if best else None
R = []
for r in csv.DictReader(open(a.rows)):
    if r['kind'] != 'REVERSAL' or r['win'] in ('', 'None') or not (a.lo <= float(r['sec']) < a.hi): continue
    q = asks(int(r['ts']))
    if not q: continue
    R.append(dict(ep=int(r['epoch']), ts=int(r['ts']), side=r['side'], ask=float(r['ask']), up=q[0], dn=q[1], act=r['actual'].upper(), win=int(r['win'])))
R.sort(key=lambda r: r['ts'])
pay = lambda ask, win: (1 / (ask * (1 + 0.07 * (1 - ask))) - 1) if win else -1.0
per = np.array([pay(r['ask'], r['win']) for r in R]); n = len(R); h = n // 2
F = V.Finding(f'REVERSAL {a.lo:.0f}-{a.hi:.0f}s, Polymarket 8-day replay', per.mean(), n)
F.grading(replay_actual={r['ep']: r['act'] for r in R}, venues_outcome={r['ep']: OUT[r['ep']] for r in R if r['ep'] in OUT})
days = {}
for r, x in zip(R, per): days.setdefault(dt.datetime.utcfromtimestamp(r['ep']).strftime('%m-%d'), []).append(x)
F.sample({'all': n}); F.halves(per[:h].mean(), per[h:].mean())
y = np.array([1 if r['act'] == 'UP' else 0 for r in R]); pred = np.array([1.0 if r['side'] == 'UP' else 0.0 for r in R])
AU = np.array([r['up'] for r in R]); AD = np.array([r['dn'] for r in R])
def pnl(y_, p_, _):
    ask = np.where(p_ == 1, AU, AD); win = (p_ == y_)
    return float(np.mean(np.where(win, 1 / (ask * (1 + 0.07 * (1 - ask))) - 1, -1.0)))
F.permutation(y, pred, np.zeros(n), pnl, draws=1000)
F.costs({k: np.mean([pay(min(.999, r['ask'] + k), r['win']) for r in R]) for k in (0, .01, .02, .05)})
cheap = np.mean([pay(min(r['up'], r['dn']), (r['act'] == 'UP') == (r['up'] <= r['dn'])) for r in R])
F.null(per.mean(), cheap, 'buy the cheaper side at the same second')
opp = np.mean([pay(r['dn'] if r['side'] == 'UP' else r['up'], r['act'] != r['side']) for r in R])
F.null(per.mean(), opp, 'buy the OTHER side at the same second')
top = np.sort(per)[::-1]
print('concentration: all %+.3f | w/o top1 %+.3f | w/o top3 %+.3f | w/o top10 %+.3f' % (per.mean(), top[1:].mean(), top[3:].mean(), top[10:].mean()))
print('by day (n, per$1):', ' '.join(f'{d} {len(v)} {np.mean(v):+.3f}' for d, v in sorted(days.items())), '| losing days', sum(np.mean(v) < 0 for v in days.values()), '/', len(days))
F.verdict()
```

## NC-2 - TWAP settlement study (09-24) - PROVEN NOT PROFITABLE: the TWAP maths is right, but it adds no money to EF

Data: 2,274 candles 09-08..09-16. Polymarket's own `priceToBeat`/`finalPrice` per candle (gamma API, public after
the candle settles), Binance 1 s klines, Polymarket 1 Hz asks, `venues.outcome`.

- **A. Ground truth.** `finalPrice >= priceToBeat` matches Polymarket's resolution **2179/2179**. The price to beat of
  a candle = the previous candle's final TWAP (TWAP60 of Chainlink ending at the open). Polymarket does NOT publish it
  live - only after settlement - but it can be computed live from the Chainlink stream (London already does: `line_open`).
- **A. Which Binance proxy predicts the settlement.** Binance TWAP60 close vs TWAP60 open agrees with Polymarket
  **96.7%**; the plain Binance candle (close vs open) only **87.0%**. Every disagreement of the TWAP proxy is in a
  near-tie candle (|TWAP move| < 1 bp: 21% wrong, n=349); above 1 bp it is **0% wrong** (n=1,925).
  Chainlink sits about **$25 below Binance** (p10/p90 $-51/$-12) and that gap drifts only $2 (p50) / $6 (p90) within a candle.
- **B. Fair-probability maths (no fitted parameters, sigma = trailing Binance volatility, 4 windows 300-3600 s).**
  The TWAP-aware formula beats the plain close-vs-open formula at **every second of the candle, every window**
  (log loss e.g. 120 s 0.528 vs 0.557; 240 s 0.314 vs 0.446; 270 s 0.218 vs 0.953 - the plain formula collapses after
  240 s because it ignores the locked-in part of the average). **But Polymarket's own price beats both at every
  second** (120 s 0.495; 240 s 0.240; 270 s 0.124). The market already prices TWAP, and more.
- **C. Money: fire when the TWAP fair price beats Polymarket's ask** (15-239 s, first second EV >= bar, exact fee,
  1 s decision lag, graded on Polymarket). Full grid, 24 cells: TWAP model -0.066..+0.004 per $1 (best cell n=1390,
  +0.004, dies at +2c: -0.066); plain model -0.129..-0.036, worse in every cell. **No cell makes money.**
- **Verdict:** a pure TWAP fair-price model has no edge against Polymarket's price - do not build it as a signal.
  What TWAP is good for:
  1. **Labels:** anything trained or graded on the Binance candle (close >= open) is wrong on 13% of candles; the
     Binance TWAP60 proxy is wrong on 3.3%, all of them near-ties. Models should be trained on the TWAP label.
  2. **Timing:** after 240 s the average is part-locked - the reason late REVERSAL fails (NC-1).
  3. **Near-ties (< 1 bp)** are unreadable even with the right formula (21% proxy error) - that is where EF's
     losses concentrate (H1: near-tie candles -0.144/$1).
- **Follow-up 1 - EF's label is already right.** v10 was trained on Polymarket's resolved outcome (Chainlink TWAP),
  not the Binance candle (`learner/build_features.py`). Its move/fair-value *features* use the plain close-vs-open maths,
  but see follow-up 2 - swapping them for TWAP versions is not expected to help.
- **Follow-up 2 - does the TWAP fair price add anything to Polymarket's own price?** Walk-forward by day, logistic on
  logit(market) vs logit(market)+logit(TWAP fair), log loss at 8 points in the candle: adding TWAP makes it **worse at
  every point** (+0.0002 .. +0.0228; e.g. 120 s 0.5068 -> 0.5076, 255 s 0.1584 -> 0.1812). The plain formula also adds
  nothing. **Polymarket's price already contains everything the TWAP maths knows.**
- **Follow-up 3 (09-24) - the near-tie idea also fails.** Retrained EF brain that sees the distance to the line (Binance
  TWAP60 now vs at the open, signed; |dist|; < 1 bp flag), walk-forward by day, 8 days / 1,077 EF candles, same EV bar
  0.15, Polymarket-graded, $10: fixed15 +$818 paper / +$256 held (refused if the ask runs) vs distance-aware +$505 / +$152.
  Worse; days split 3-3 (one tie). Premise wrong at fire time: fixed15's near-tie (< 1 bp) trades made +$239 on 57. The
  fitted weights on distance are ~0.
- **FINAL STATUS: PROVEN NOT PROFITABLE - CLOSED.** Neither a TWAP fair-price model, TWAP features, nor distance-to-line
  improves EF or makes money. Keep only: TWAP labels for any training (v10 already uses them) and the 240 s REVERSAL rule
  (NC-1). Not deployed anywhere; London unchanged.

## NC-3 - Handle HTTP 425 (matching-engine restart) (09-24) - recorded, NOT built

- **What Polymarket does** (docs, "Matching Engine Restarts"): during a restart every order endpoint returns **HTTP 425
  (Too Early)**. After each restart the engine is **post-only for 2 minutes** - non-post-only orders (our FAK) are
  rejected. Restarts are announced ~2 days ahead on Telegram t.me/polytradingapis and Discord #trading-apis.
- **What our engine does now** (`poly_live.py` `post()`): 425 is a 4xx, so it is booked as a plain venue rejection. It
  is safe (no money at risk, no ambiguous order), but a restart looks like a run of EF refusals and wastes the retries.
- **Change to build later:** on 425 -> mark "venue restarting", skip that candle's retries, back off, and do not send
  FAK for 2 min after the first non-425 answer (post-only window); log it as its own reason, not as an EF refusal.
- **Status:** not built, not deployed. Low priority. Needs the owner's confirmation before building and before London.

## NC-4 - Master survives restarts; only the owner (or a session on his order) turns it off (09-24)

- **Owner's rule:** a server restart, crash, overload or deploy must NOT change the master switch. If master was ON
  before, it is ON after; if OFF, it stays OFF. Only the owner (or a session acting on his written order) flips it.
  The EF / MAIN / REVERSAL switches follow the same rule. Goal: London can run for weeks unattended.
- **What the code does today (checked 09-24, build 13.0.3 on London):** already this. Since 12.24.3 master is no
  longer forced OFF at boot (`btc_model_v12_polymarket.py` ~line 77, owner: "if master off it's paper and if master on
  it's live"); it lives in the meta table like the lane switches and survives any restart. It is seeded OFF only on a
  brand-new database (`poly_dashboard.Dashboard.__init__`). London runs under systemd `Restart=always`.
- **Who changed it is recorded:** master and the lane switches are AUDITED controls - every write stores old value,
  new value and the calling code, so "the owner / a session / a restart" can always be told apart. A restart writes
  nothing to master.
- **Where master can still go OFF without the owner:** (1) a deploy that points the engine at a NEW database file;
  (2) a session briefed to park it (a safe-start deploy did this on 09-16 03:40). Both need a written owner order under
  the current rules. No automatic stop exists (cash floor removed 09-23).
- **Verified on London 09-24 19:24 (read-only):** `pm-london.service` is enabled, `Restart=always`,
  `WantedBy=multi-user.target` -> it starts on a full server reboot and after any crash; `--db polymarket_v12_london_1.sqlite3`
  is a fixed file; master is ON in meta. Master audit since 09-22: only dashboard (owner) writes; **none at the 7 restarts**
  since 09-23 - master stayed ON through all of them. The dashboard is served by the same process, so it comes back too.
- **Two small open items (recorded, not done - owner 09-24: "no need to annoy London now"):**
  1. The boot banner still prints "(master OFF = shadow paper)" - a static label, not a write. Reword it to show the
     real stored state (e.g. "master ON (from meta)") next time a London build is approved.
  2. The Claude bridge on London (tmux) does not survive a server reboot. Trading continues without it, but V cannot
     get London reports until it is restarted. Add a systemd unit or @reboot entry for it on the owner's go.
- **Still to add (owner's go):** a DEPLOY_LONDON.md line: "never park master on a restart/deploy unless the owner says so
  in writing".

## NC-5 - Event-driven decide loop (13.1.x decide_mode=event) on London (09-25) - TRIED LIVE, REVERTED TO POLL
- Zurich A/B (shadow): event made spot price 2.3x fresher at fire (spot_rx p50 ~50 vs ~115 ms) for 1.53x CPU.
  Shadow cannot show refusals, so it was tried live on the owner's go: London 13.1.2 event/50 ms from 14:05 UTC.
- London live, 30 EF candles on event vs poll (grade: venues.outcome): never filled 18/30 (60%) vs 9/30 equal-N (30%)
  and 60/172 over the prior 48 h (35%); Fisher p 0.037 / 0.014. Retry fills 3 vs 12. First-try fills equal (9 vs 9).
  Event's per-candle PnL looked better but rests on 12 fills - insufficient, not a finding.
- Owner: "Switch to old please". London decide_mode=poll 21:17:15 UTC (live meta, no restart; build stays 13.1.2).
  Zurich mirrored to poll.
- Likely cause (UNVERIFIED): event fires at the instant of the move, when makers pull quotes in the 50 ms hold, and
  the retries then chase a book that has already moved. Do not re-try event mode without a fill-rate answer to this.
- LESSON (Zurich 21:30): the shadow lane fills in-process - 348/348 EF orders filled all-time, 36/36 in its event
  window while London missed 60%. Any change whose cost lands on FILL behaviour is invisible on Zurich by construction;
  judge those only on London (or say up front that shadow cannot answer).

## NC-6 - Ubuntu needrestart auto-restarted pm-london (09-26 06:13) - owner: "No need" to block it
- unattended-upgrades (libexpat1/curl/libpcap) -> needrestart restarted the service; clean stop/start, meta intact,
  no order in flight. Post-restart zero-fill run checked: order shape identical, every reject a matching-engine
  "no orders found" (not auth/sign), book moved away within 1 s - no fault.
- Proposed fix (exclude pm-london from needrestart auto-restart) NOT applied: owner 09-26 11:3x "No need".
  Do not re-raise unless an auto-restart lands mid-order.

## NC-7 - Retry levers on London EF (09-26, read-only backtests on the London DB) - KEEP AS IS
- **No-EV retries** (buy the never-filled candles at the best ask +1s/+2s): 100 graded, 45% win, **-0.124/-0.163 per $1**; every bucket INSUFFICIENT. They lose. The EV re-check on retries stays.
  **RETRACTED 09-28 (London):** that test used tape-INFERRED sides, which match the logged side only 69% (195/283). With logged sides the
  never-filled candles would have won 65% (94/144, gamma), as PAD_GRID said. Superseded by NC-13. The fillwin/d_ask5 cells that fell back
  to inferred sides are retracted too.
- **Retry fills as they are** (attempt >=2, n54 INSUFFICIENT): 50% win vs 48% break-even, +0.03/$1. Dropping retries costs ~11 in total, and the halves disagree. No evidence either way; no change.
- The fill-side levers are now all closed: pad/cap (PAD_GRID_LONDON), speed (NC-5), size (R-14), no-EV retry and no-retry (this entry). Re-open only with a new mechanism, not a new threshold.

## NC-8 - MAIN / REVERSAL new EV logic, two windows (09-27) - NOTHING SHIPS
- Rules: R0 first call, R1 the lane's own p at breakeven, R2 walk-forward calibrated EV, R3 venue-only null. Priced with
  PAST-ONLY quotes (the old +-5 s nearest-row quote was lookahead: 52% of MAIN R1's picks used a future row).
- **MAIN dead** in both windows, all rules, all ages: W1 0-240 s R0 -0.017 paper / -0.10 London-exec; W2 R0 -0.140 / -0.228.
  "MAIN after 240 s" was the future quote (W1); W2 has too little tape after 240 s to say. No reason to lift the 240 s rule.
- **REVERSAL R1 0-240 s, London-exec**: W1 +0.065 (p05 below zero), W2 -0.023. Zurich live shadow +0.064 on 77. Not a finding.
- Calibration (R2) never beat its null (R3). Files: analysis/v/model/MAIN_REV_*.md, analysis/zurich/LANE_EV_ZURICH_W2.md.

## NC-9 - REVERSAL "brain" on Binance perp/flow/depth features (09-27) - NOT A FINDING
- Rebuilt perp, flow, depth and settlement-line features from data.binance.vision for 09-08..09-16 (parity with the live
  parquet: corr 1.000 on 4 features), plus 08-29..09-06 as training. Walk-forward AUC: brain 0.746 vs the venue-only null 0.750-0.754.
- As a REV filter: the best n>=60 cell is +0.150/$1 London-exec (n64), below its own null cell (+0.178); paired test 28 vs 27, p=1.0.
- The market price already carries what these features know. Open, and only window 2 can say: REV filtered by the calibrated venue
  price alone (+0.12..+0.18 on n59-65). File: analysis/v/model/REV_BRAIN_HIST.md.
- **09-27 01:3x, the last lead closed:** the price-calibrated REV filter, FROZEN on window 1 and tested on window 2 with no refit:
  n53 (<60), paper +0.062 (H1 +0.209 / H2 -0.080), London-exec -0.060/$1. The calibration transferred exactly (pred 0.660 = actual
  0.660), so the price is a true probability, and that is exactly why it does not pay after costs. REVERSAL stays off. File: analysis/zurich/REV_FROZEN_OOS.md.

## NC-10 - Paper vs live on London EF: cause found, no fix yet (09-27)
- **Cause (London's own data):** 104 of 263 EF candles never filled; they would have won 63% vs 52% for the fills, and hold
  ~80% of the paper profit. Winners' asks are gone before our FAK lands (the venue's 50 ms taker hold lets makers cancel).
- **Order-side fixes, all tested on London data and dead:** pad/cap (PAD_GRID_LONDON), speed (NC-5), resting/maker (R-18),
  no-EV retries and no retries (NC-7), size (R-14).
- **Fill-aware brain (10 decision-time features, leave-one-day-out):** AUC 0.419 [0.325, 0.509], anti-predictive.
  The one univariate hint ("fire only if the ask is flat or falling over the last 5 s") covers n=11 of 162 fills. That is
  insufficient, the sweep is non-monotone, and it would be a fire gate. Not a finding.
- Open paths: the ETH/SOL head-start shadow on Zurich (analysis/zurich/ETH_SOL_SHADOW.md); re-check the d_ask5 hint when London has more than 600 fills.
- **09-27 03:0x, market-making (two-sided resting bids) CLOSED on data** (owner called it): on 2,052 candles of the 1 Hz tape
  (09-08..09-16), bids at mid-1..5c posted at 0 s or 30 s. Both sides fill in 55-74% of candles (+2k each), one side fills in 26-44%,
  and those one-side fills LOSE 96% (591 of 613 at mid-2c). Net -9..-11c per candle in every cell, conservative or optimistic.
  The complement-book "back door" is also dead: the books mirror (up+dn ask = 1.01 in 96% of seconds), and the venue already mint-matches inside the FAK.

## NC-11 - "Fire before the crowd" and other markets (09-27) - nothing tradeable yet
- **Predicting Binance's next move** (8 days of spot+perp aggTrades, walk-forward): WHEN a ≥5 bps move comes is predictable (AUC 0.75-0.80),
  but its DIRECTION 100/250/500 ms ahead is chance (AUC 0.54/0.55/0.51). Small (≥2 bps) moves are directional, but worth +0.1-0.2 bps,
  i.e. +1-3 pp of resolution probability, the size of the Binance-to-Chainlink error. The perp leads spot by 2-5 ms, which is useless against ~230 ms.
  analysis/v/lead/BINANCE_LEAD.md.
- **BTC 15m** (1,343 candles, gamma labels, TWAP60 agreement 98.5%): EF loses in all 12 London-exec cells; the lead is smaller than on 5m
  and gone in 2-3 s. analysis/v/multi/btc15/BTC15_EF.md.
- **BTC 5m race, quantified:** after a signal, the fired side reprices +7c within 1 s. Paper +0.64/$1 at 0 s, +0.15 at 1 s late, about 0 at 2 s.
- **ETH/SOL 5m** (NC-10 file, ETH_SOL_EF.md): all cells lose London-exec. The live-book shadows on Zurich (since 03:33 09-27) are the open test.

## NC-12 - "Stable EF": selectivity + hybrid staking (09-27, Zurich, 490 fires / 9 days, gamma-graded) - NOT YET
- Top 20% of fires per day by calibrated edge (RAW): 6/day, 59% win, paper +0.225, London-exec +0.060, the only London-positive family.
  FIXED is London-negative at every tier. verify.py REJECTS it: random 6/day reaches p95 +0.262 (p=0.084), the sweep is non-monotone (peaks at 20%), and n=54.
- Staking is second order: once selective, all arms (fixed / tiered / half-Kelly capped / de-risk F) are within one point per $1.
- Hints (n<60): ask 0.25-0.35 loses in both profiles (16.7% win); sec 180-240 is the best bucket in both. Re-run at ~30 days. analysis/zurich/STABLE_EF.md.

## NC-13 - Predict.fun-style execution on London (owner: "fix the order failure", 09-28) - raises fills, not money
- **Why Predict.fun fills ~93%** (learner/btc_model_build11.py:603-650): EF is a MARKET BUY with a VWAP-band price tolerance
  (<0.10 +100%, 0.10-0.20 +70%, 0.20-0.30 +50%, 0.30-0.40 +20%, >=0.40 +10%) and up to 3 re-quoted replacements with no EV re-check.
  London caps at ask+1 tick and re-checks EV. 69% of London's 580 EF orders end "no orders found to match with FAK order".
- **Test (London's own DB, 326 EF candles, logged sides, gamma-graded; fill = our side's best ask <= cap in (submit, +3 s], 1 Hz tape):**

  | cap | fills | win | per $1 optimistic / pessimistic |
  |---|---|---|---|
  | +1c | 43% | 44% | +0.00 / -0.09 |
  | +3c | 49% | 46% | +0.06 / -0.06 |
  | +5c | 58% | 47% | +0.06 / -0.08 |
  | +10c | 70% | 50% | +0.06 / -0.13 |
  | +15c | 79% | 51% | +0.07 / -0.17 |
  | Predict bands | 59% | 47% | +0.04 / -0.12 |

  The halves flip at every cap (H1 +0.22..+0.33 optimistic, H2 -0.06..-0.15). Fills over the attempt-1 top-of-book size: 37 at +1c, 54 at +5c,
  79 at +15c (no depth archive, so the real price is worse than optimistic).
- **Why:** the extra fills are the candles whose ask stayed reachable; they win about what they cost (the added fills win ~56-60% at ~+5-15c).
  The 65% winners are the ones the book runs away from, and many stay out of reach even at +15c within 3 s. The venue takes ~230 ms to
  process our order, so the fill problem is the latency race (NC-5, NC-10), not the cap.
- **Verdict:** a wider cap copies Predict.fun's fill rate but not its money. Nothing changes on London. File (London box, local):
  analysis/london/PREDICT_STYLE_EXEC.md + pexec.py.


## NC-14 - TWAP physics vs the market, and where the fees bite (V, 09-28 night) - no edge, one structural fact
- **TWAP physics** (Brownian projection of the closing TWAP60 vs the opening TWAP60, Binance 1 s as the reference; 2,052 venue-graded
  candles 09-08..16; analysis/v/twap/twap_lock_binance.py): the market's price has a lower Brier than ours in EVERY window
  (0-15 s 0.233 vs 0.238 ... 240-270 s 0.071 vs 0.098). The trading grids are negative or flip halves in every window, at the quote and 5 s later.
  In the last 30 s the Binance stand-in is wrong on 21% of the still-contested candles, so the last-minute question is re-run on the
  real Chainlink feed by London (analysis/v/twap/twap_lock_ref.py). The early and mid-candle answer is final: the book already prices the TWAP rule.
- **Favourite/long-shot grid** (same data, first quote per candle per cell, both sides, venue-graded, full grid in the session log):
  favourites (ask >= 0.60) are priced fair (per $1 about -0.04..+0.03 in every time bucket); cheap shares lose in every cell and both halves
  (0.40-0.50: -0.04..-0.10; 0.20-0.30: -0.05..-0.21; 0.02-0.10: -0.05..-0.44 per $1). Cause: the taker fee is 0.07(1-p) per $1 and the
  1-tick spread is a bigger share of a cheap price. **EF buys cheap shares (ask <= 0.60), so it starts about 5-10% per $1 in the hole on
  every fire before any model edge.** No single cell is a finding (the best, 0-60 s at 0.90-0.98, is +0.03 on n95, one standard error).

## NC-15 - Overnight 09-28 (owner: "don't stop till you find a profitable version") - running log
- **Why speed cannot win (fact, not theory):** the BTC 5m market has Polymarket's taker-order delay ON (`itode: true`,
  learner/AWS_TASKS.md:419). A taker order is held (250 ms per the docs, reportedly 50 ms on crypto) and re-validated, and makers
  cancel inside the hold. The venue's own design protects makers from our strategy. That is the 69% "no orders found".
- **TWAP lock-in on the REAL Chainlink feed (London, 922 candles, alignment 99.57%): DEAD.** The market beats exact TWAP math in
  every window (270-296 s Brier 0.040 vs 0.063); every grid cell is negative at t-1, +1 s and +2 s. (analysis/london/TWAP_LOCK_REF_LONDON.txt, London box)
- **EV-bounded chase (fills + retries, London's own orders): not a finding.** It adds 25-55 fills (all n<60), pessimistic totals are about 0,
  and H2 is weak. The runaway winners run past even an EV=0 cap. (analysis/london/EV_CAP_CHASE.md, London box)
- **Regime grid (Zurich, fixed15 under London exec, 129 fires / 7 days): no bucket is robust.** All fires -0.021/$1. Weekdays n113 +0.065
  fail the cost test (+2c +0.018, +5c -0.036); weekends n16 -0.555 over 2 days, directionally the owner's point, but too thin. (analysis/zurich/EF_REGIME_GRID.md)
- **Delay brain (Zurich decide_log, 35,855 passes, 622 candles, gamma):** EF's edge is +0.059 at +250 ms and -0.055 at +1 s. A ridge
  trained on the delayed price works as a VETO on EF's own fires. Kept: n130, 58.5%, +0.201/+0.142/+0.106 at +250/500/1000 ms,
  halves +0.167/+0.236, perm p 0.001. Vetoed: n133, 45.1%, -0.081/-0.180/-0.212. The sweep is non-monotone but positive at every threshold.
  OPEN: fixed15 selection, the London-exec pass, and a test on London's real fills. (analysis/zurich/EF_DELAY_BRAIN.md)
- **Veto on London's REAL fills (fixed15, 75 scored, 09-25..28): not shippable.** KEEP n41 -0.020/$1 vs VETO n34 -0.197; the total favours the veto by ~$57,
  but the halves flip (on 09-25 the veto set won +55.9) and all cells are under 60. On Zurich, fixed15+veto fails (perm p 0.287); raw25+veto London-exec +0.035 on 4 days.
  v2 (7 days, 1 s label) keeps KEEP > VETO (perm p 0.000), but v1 and v2 agree on only 58.7% of candles, so "the veto" is not one stable object yet.
- **Mechanism found (Zurich v2, point 3):** EF fires at a transient DIP of the ask in its own read (+6c one row later vs +0.43c market drift) -
  a winner's curse on the ask. This is the order-failure mechanism behind NC-10/NC-13.
- **Book age at send, London REAL orders (analysis/london/BOOK_AGE_GRID.md): the one real-money split that separates.** Candle fill by book age
  <10/10-25/25-50/50-100/100-250/250-750 ms = 91/71/64/46/37/19%, monotone. Fills on books >=50 ms old lost -74.8 (H1 -33.4 / H2 -41.4, 5/6 days <=0;
  n53, under 60). The per$1 grid is non-monotone (profit sits in 25-50 ms); it is not an activity or sec-in-candle artefact. Age is traced to poly_core.BookCache.quote.
- **Drafts on the branch, OFF by default, NOT deployed:** dd774e9 poly_veto (meta ef_veto) and e6ccd97 fresh-book send (ev_settings.fire_book_age_ms:
  price an attempt only on our token's book no older than the limit; wait inside the budget; can never loosen quote_age). All suites pass.
- **EF persistence (wait K passes): DEAD** (analysis/zurich/EF_PERSIST.md). Waiting doubles fills and destroys the edge (raw25 K1 +0.071, K2 -0.137).
  The fills are ADVERSELY SELECTED by 10-29 pp (filled win 43.8% vs unfilled 54.8% at K1): makers leave the quote when content to sell us the loser.
  On this book, raising the fill rate raises it on the losers. That closes the EF execution side.
- **NEW STRUCTURAL LEAD - the 5m/15m dominance pair (TWAP rule, model-free):** the 15m market and the LAST 5m candle inside it settle on the SAME closing TWAP60.
  If L15 < L5, 15m UP + 5m DOWN pays 1 or 2, never 0; mirror if L15 > L5. Zurich books (analysis/zurich/ARB_5M_15M.md, 22.8 h): cost incl. fees < 1 on
  25/81 windows, median best cost 0.956 (4.4c/pair), p10 0.732; 0 zero-payoffs in 725 cells; both books tight (+1c). PUBLIC-TRADE cross-check (V,
  analysis/v/twap/ARB_TRADES_CHECK.txt, independent source): takers actually bought both legs within 3 s at cost < 1 in 19/91 windows (13 with lines
  >= $5 apart); dominance-pair payoff on gamma across all 91 windows {1: 68, 2: 23}, never 0. OPEN: simultaneous-fill (legging) risk - a ms probe of
  both books runs on Zurich until 06:45 UTC (ARB_LEGGING_MS.md) - plus the 5m leg's size, and more days.
- **Pair frequency, 7 BTC days on public trades (Zurich, analysis/v/twap/btc_day0..6.out):** traded cost<1 in 17/15/24/13/26/22/36 of 96 windows
  (09-20..26, 153/672 = 22.8%), EVERY day. Payoff over 672: 1->469, 2->202, 0->1. The one 0 (09-22 15:15) had lines $2.33 apart on the Binance
  proxy, inside its error, so the leg ORDER was wrong, not the rule. pair_bot now defaults to --min-gap 5 and uses the real Chainlink stream.
  SOL 6/91, all with gaps <= $0.12 (proxy noise; do not lean on it). ETH 15/91, never 0.
- **EF trigger source (Zurich, 785,924 passes, 1,015 candles): the fill-rate side is closed for good.** Book-triggered fires fill 82% but pay -0.007;
  model-triggered fill 36% and hold all the edge (+0.234). "Fire only on book moves" LOSES (raw25 +0.071 -> -0.021, fixed15 +0.061 -> -0.158); on candles
  both arms fill, both are negative. All 13,295 qualifying passes fill 85% and pay -0.059. EF's apparent edge sits in the fires the book will not fill.
  So the fresh-book-send draft (e6ccd97) is NOT recommended either: more fills on this book are more losing fills. (analysis/zurich/EF_TRIGGER_SOURCE.md)

- **RETRACT the pair frequency (V + Zurich, 05:3x-05:5x).** Zurich: its 25/81 was a stale 15m book (recorder resync bug, fixed); corrected
  5 of 105 windows with a fresh book and |gap| >= $5, 1-9 riskless seconds each, best cost 0.95-0.99. Mine: the public-trades check took the MIN
  of each leg independently over 3 s, and the legs move against each other, so it understated cost. 09-27 BTC, 87 windows with |gap| >= $5:
  W3min 13 windows / 132 s; same-second min 13 / 32 s; same-second MAX (what a taker actually risked) **1 window / 1 s, cost 0.9998**.
  The 7-day 153/672 (22.8%) used W3min and is inflated the same way. Structure (payoff never 0) stands; the edge is ~1-4c in a few
  seconds of a few windows a day. Not a profit engine at our size. (analysis/v/twap/ARB_TRADES_STRICT.txt, arb_trades_strict.py)
- **Pair CLOSED (Zurich ARB_LEGGING_MS, ms probe 02:15-06:45, 27.5 M book events).** Both legs <= cost for median **43 ms**; 9 of 11 intervals
  shorter than our 250 ms arrival; min touch p50 10 shares; 2 of 18 windows, and those were the two SMALLEST line gaps ($7-9 vs median $61),
  i.e. where the leg choice is least reliable. Fire-both simulation: both fill 54.5%, one leg only 9.1%, neither 36.4%. pair_bot paper: 1 pair,
  cost 0.9811, paid 1, +0.38 - the structure holds, the trade is not there at our speed. (analysis/zurich/ARB_LEGGING_MS.md)

## NC-16 - 09-28 09:5x, owner's direction: EF acts like everyone else; make the signal early
Owner (09:4x-09:5x): the venue's order hold is not the problem, it is the same for everyone. "Find the actual cause and fix... improve your
signal, make it early and see something that not everyone sees... the model acts the same as everyone... check the EF method we used in
the Predict.fun bots, it wasn't based on how everyone reacts."
- Facts checked in code: London's EF lane runs the SAME v10 model (`from btc_model_v10 import Model`, model_v10.json) the Predict.fun bots
  used. decide_v11 (Predict.fun) fired at ~20 s on the v11 path (NOTES_v12 11:23); London fires at the first pass EV clears the bar.
- model_v10.json coefficients: move_bps +1.663, **lv (the VENUE's own logit) +1.551**, mv_x_sec -0.982, everything else < 0.14. The
  model's second-largest input is Polymarket's own price - it agrees with the crowd by construction.
- Zurich EF_TRIGGER_SOURCE already showed the split: fires where p moved and the book stood still earn +0.234/$1; fires that chase a book
  dip pay -0.007; p chasing a rising ask -0.556. The edge is where the model disagrees with the market, not where it follows it.
- Briefs out 09:55: Zurich EF_FIRE_TIME (fire-second grid S x P, full grid; then part 4: spot-only walk-forward model vs venue mid at
  sec 20/30/45/60, disagreement cells). London: real fills by fire second and ask (read-only).
- train_summary.json: logit btc_only logloss 0.5364 / acc 72.0% vs btc+venue 0.5146 / 73.3%. The venue price adds ~1.3 pp of accuracy;
  the spot-only signal carries nearly all the skill and is the part the crowd does not already price.
- **London real fills by fire second (10:00, 205 settled, venue payout):** fire sec p10/50/90 = 48/126/203. Per $1: 15-30 n9* -0.03 | 30-60
  n18* +0.09 | 60-120 n65 -0.11 | 120-180 n64 +0.05 | 180-240 n49* +0.09. By fill price: <0.45 n87 +0.08 | 0.45-0.55 n86 -0.09 | >0.55 n32* +0.08.
  In the candles EF later bought, at sec 20-30 the CURRENT model gave our side p 0.40 (ask 0.36) - it did not favour that side yet; at the fire
  p 0.57, ask 0.45. So firing the same model earlier is a different, weaker bet, not the same bet cheaper. The early question now rests on
  the spot-only model (Zurich part 4), not on retiming v10.
- **Zurich EF_FIRE_TIME (10:16, 1,015 candles, sim fills):** baseline fires p50 at sec 126; only 5% by sec 30. Grid S x P: all 16 cells with
  S>=45 negative; 7 of 12 with S<=30 positive; P is ANTI-predictive down every column (S=15: P=0 +0.045, 0.55 +0.042, 0.70 -0.083).
  PLACEBO (fire at S on the model's SIDE, no p bar): S=15 +0.045/$1 on 732 sim fills of 853 fires, halves +0.021/+0.068, win 58%, mean ask
  0.54, fill 82-87%, ask reversion +0.6c (not selected dips). Baseline: 0.43 ask, 44% win, +7c reversion, 42% fill. The gain is WHEN, not the
  p bar. Caveats: sim fill rate unvalidated above ~42%; verify.py NOT A FINDING on the P=0.55 cells (they lose to their own placebo);
  the placebo is the candidate. Only London can measure real fills at sec 15. (analysis/zurich/EF_FIRE_TIME.md)
  verify.py on the S=15 placebo: NOT A FINDING - cost sensitivity +0c +0.045 / +1c +0.026 / +2c +0.007; sweep over S non-monotone
  (15 +0.045, 45 -0.044, 60 +0.008); does not beat fixed15 unfiltered (+0.061 sim); paired vs fixed15 McNemar p=0.21 (23 discordant).
  Reading: early timing is a real direction with the SAME order of edge as the current rule, not more, and 2c of slippage removes it.
- **Zurich part 4, spot-only walk-forward model vs the venue price (10:29): CLEAN NO on this feature set.** AUC spot-only vs venue mid alone:
  20s 0.687/0.714, 30s 0.691/0.732, 45s 0.709/0.744, 60s 0.703/0.768 - eight of eight lost, gap widens through the candle. Disagreement
  cells: one positive both-halves cell (S=60 p>=0.60 ask<=0.50, +0.091, 99 sim fills) is a specification artefact (flips sign with one
  feature; fills decay 50/34/15/0 by day). verify NOT A FINDING. Structural: move_bps alone correlates +0.717 with the venue mid - the crowd
  IS a move-follower, so a spot-move model carries no private information. What the crowd does not see must be an input the venue is not
  watching. Next tests: (a) Chainlink-reference vs Binance divergence early in the candle (settlement is Chainlink, the crowd prices Binance);
  (b) Binance flow-only model (perp aggressor flow, imbalance) vs venue mid. (analysis/zurich/EF_FIRE_TIME.md s.4)
- **London EF_CHAINLINK_DIV (10:38, 922 candles, 1 s ref_px + spot_px, venue labels).** Chainlink sits BELOW Binance in 98% of seconds
  (mean -2.25 bps, |div| p50 2.2 / p90 3.4, autocorr 30 s +0.49..0.61). Raw div carries no direction information (AUC 0.47; adding it to
  move_bps HURTS: 0.633 -> 0.592 at S20). The live cell is basis WIDENING -> buy DOWN at the 1 s tape ask: S45 X2.5 n323 +0.08 (H1 +0.05 /
  H2 +0.11), X3 n167 +0.26 (+0.09/+0.42), X3.5 n83 +0.41, X4 n54* +0.47, monotone in X; S60 X3 n166 +0.23 but H1 negative at X3.5-4.
  Perm p=0.00/0.01. Null always-DOWN -0.03. Win% FLAT ~50%: the money is cheap DOWN asks, no fill model, threshold on a de-meaned basis.
  CANDIDATE ONLY. Mechanism if real: the venue prices Binance, settles on Chainlink; when Binance runs above Chainlink the crowd overrates UP.
  Next (briefed 10:4x): rolling no-lookahead basis, cheapness-matched null, symmetric UP side, per day, div persistence to the close.
- **London Chainlink div part 2 (10:46, 975 candles):** rolling no-lookahead basis KILLS the sample (n<=52*, negative) - the raw cell is a
  slow basis REGIME (wide for >5 min), not a fresh divergence. It beats the cheapness-matched null (S45 X3 +0.242 vs -0.115; S60 +0.205 vs
  -0.092) and is positive 5/6 days (n 16/57/33/2/37/34). Basis persists to the close (corr +0.56) but does NOT act through settlement flips
  (corr -0.03) - so no mechanism: a persistent basis cancels out of Binance-move-vs-Binance-line. REAL London DOWN fills at <=0.45 with
  div<=-3: n10, -0.30/$1 vs +0.13 for the rest (INSUF, but the only real-money read and it points the other way). Verdict: candidate, no
  mechanism, needs a shadow with real fill accounting before it is anything.
- **Zurich part 5, flow-only (10:47): NO.** ofi60 correlates 0.64-0.69 with the venue mid (move_bps 0.717) - the venue already watches
  flow. AUC flow-only 0.641-0.698 vs mid 0.714-0.768; mid+flow is WORSE than mid alone at every second (-0.006..-0.019). No cell meets
  the precondition. Chainlink div on Zurich's 135 h / 437k s: de-meaned |corr| with mid 0.10-0.13 (the only independent input) and it
  predicts nothing (AUC 0.47-0.51, corr with next-60 s return sign-flipping). Reference drifts -0.25 -> -2.21 bps below Binance over the
  span (~$22 on BTC - the measured reason a Binance line proxy fails at small gaps). One sentence: every engine input that predicts the
  outcome is already in the price; the one input not in the price does not predict. Zurich offered venue print flow - DECLINED: that is
  "how everyone reacts", the owner's exclusion. Next: data the engine does not collect - cross-exchange lead (Coinbase/Kraken are Chainlink
  sources; the crowd watches Binance). Zurich: Chainlink vs Binance lead-lag on the 437k s. V: Coinbase ticks -> 1 s, public.
