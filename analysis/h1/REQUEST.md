# REQUEST from V — 2026-09-22 16:0x UTC — EF reversal lane: test it on everything you hold

Owner, 16:0x: "test test test and improve, use the data that we hold and everything, also you have h1 to help it holds
many old data too." Token rule applies: short files, numbers, whole grids.

## What exists (pull first; 12.22.0 on the branch, 3357a90+)
- `learner/v12_2/poly_ef.py` — the EF reversal lane: build11's legacy EF structure (old-side exhaustion, control transfer,
  settlement feasibility, real/fake classifier, 12 gates at the ANCHORS, 250 ms latch, one per candle), side contrarian to
  the move against the SETTLEMENT LINE (TWAP60 at the open), plus a Polymarket price rule: ask <= 0.60 and
  settlement_probability >= ask + 0.06 + fee. Not ported: perp lane, aged depth history, the online learner.
- `analysis/v/model/replay_lanes_1s.py` — drives the REAL `poly_lanes.LaneEngine` (MAIN, REVERSAL, EF) over 1 s Binance
  klines (`k1s` tables, `t0/fetch_1s.py` shape: ts,o,h,l,cl,v,n,tb) + the 1 Hz venue tape (`venues.q` poly_up/poly_dn) and
  grades on `venues.outcome`. Prints per-lane n/hit/per$1/halves, an EF block census, and the WHOLE grid over the EF real
  score (0.30..0.60), first read per candle where the price rule holds. `--out X.csv` also writes `X_grid.csv`.
  Usage: `python3 analysis/v/model/replay_lanes_1s.py --klines k_*.sqlite3 --venues venues.sqlite3 --ef --out ef.csv`
  (~1 min per 10 h of tape). No depth stream is stored, so book features read neutral - state it.

## Asks (in order; each one a short file under analysis/h1/, numbers first)
1. **Run it on every venue-quote span you hold** (the tape I have is 09-08 -> 09-16 01:xx; if you hold more, run more).
   Report the per-lane table and the EF grid. Mark every cell under 60.
2. **verify.py on the EF grid CSV**: grading (venues.outcome = Polymarket's own), sample, halves, permutation on the
   predicted SIDES (never labels), sweep over theta (non-monotone = noise), costs (+0.02/+0.05 on the ask), null (buy the
   same side blind at the same ask; and buy the cheap side blind), quote_age (the tape row is <= 5 s from the read),
   paired vs REVERSAL on shared candles (McNemar on discordant pairs only).
3. **Harness fidelity**: on 09-15 02:05 -> 09-16 01:xx the Zurich live journals hold real MAIN/REVERSAL lane decisions
   (`diagnostics` rows with lane=MAIN/REVERSAL, side, sec, ask_up/ask_dn; V's `analysis/v/model/replay_lane_cap.py` reads
   them). Compare the replay's MAIN/REVERSAL placements on the same candles: side agreement, |sec| difference, and whether
   the replay's per$1 matches the journal's on the shared candles. If the harness disagrees with the running lane, say so
   first - the EF numbers are worthless until it agrees.
4. **Improve, walk-forward only**: if (1) shows anything, fit NOTHING on the same days you read. Feature-scale calibration
   (the flow normaliser, sigma) on the first half, read the second half at the anchors. No gates, no threshold picks.
   Report the full grid both halves.
Do not touch `learner/` or `analysis/v/`. Reply by committing under `analysis/h1/` and, if a one-shot Routine to
`session_01SmMRZqqMru5UdaeAoJarkr` works from your box, one line with the file path.
