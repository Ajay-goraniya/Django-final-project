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
