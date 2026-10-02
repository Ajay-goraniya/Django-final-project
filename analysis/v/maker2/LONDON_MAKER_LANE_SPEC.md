# London 13.3.0 - EF lane becomes the MAKER brain (Zurich maker probe, rule as live). Spec (V, 10-02 ~14:0x UTC)

Owner, 10-02 14:0x: "rebuild that maker trade model on london now, keep the same design and instead of ef you replace maker
trades, everything stays same so in trade control i can change stake, turn off turn on, pnl curves, and everything".
CLAUDE.md: no change goes on London without the owner's confirmation of THAT change. This build is that change; it is BUILT and
TESTED, then the restart waits for his explicit "go" (master is OFF anyway - nothing trades until he turns it on).

## What changes
The EF lane's BRAIN and EXECUTION are replaced by the maker probe's, exactly as running on Zurich (pid 475268, commit f7b5f9d,
backups/zurich_maker_probe_20261002.zip):
- calm: Binance 1 s log-return std over [open-300, open) x1e4 < 0.304 (poly_fav.FavBrain.vol_before_open, frozen; >=240 pts)
- window: post only in sec 60-120; hard cancel at 121
- favourite: the side whose BEST BID is in [0.60, 0.80]
- order: post-only BUY at that best bid (never crosses; refuse on bid>=ask / crossed / no ask), size from trade control (below)
- cancels of a RESTING order (code as live, owner 'option A' 09-30): ONLY Binance >= 2 bps against our side over the last 1 s,
  sec outside 60-120, candle end, already filled. Favourite flip / bid leaving band / vol gate only a NEW post (CORRECTED 14:1x,
  London caught V's spec error against maker_probe.py Quoter.decide and its tests).
- limits: one open order at a time, at most one FILL per candle, max 3 posts per candle, remainder < 1 share = dust (cancel)
- hold to settlement, graded on the venue's own resolution. Fills read from trade.maker_orders[] and queried by MARKET
  (a fill can be booked on the complement token) - the 13.2.1 fix.
- NEVER cancel_all / cancel_market_orders (shared wallet with Zurich) - every cancel by order_id.

## What stays exactly as it is
Dashboard and trade control: EF on/off, master, stake setting, PnL curves, ledgers, last-fill card, health/alerts, journal.
MAIN and REVERSAL lanes untouched (both OFF). The v10 path stays blocked behind the lane EF engine (LANE_EF_ENGINES gate -
add the new engine name to it, or v10 silently trades).
Stake: trade control's stake in $ -> shares = floor(stake / bid, 2 dp), minimum 5 shares (venue minimum). Default $5 (~7 shares).
The 13.2.x 13-24 session trial is REMOVED for this lane (the probe trades all hours).

## Decisions for the owner (not assumed)
1. STOPS: the probe has -$10/day and -$20 lifetime stops. London's standing rule (owner 09-23) is NO coded PnL stop. Default in
   this build: OFF on London (rule respected); available as a trade-control setting if he wants it.
2. SHARED WALLET: London and Zurich trade from ONE wallet. Running the probe on Zurich AND this lane on London = the same bet twice,
   competing for the same bids. Recommendation: when London goes live, stop the Zurich probe (one switch: remove its ENABLED file).
3. CASH: wallet ~$17. One $5 order + Zurich probe fits; two overlapping candles do not.

## Acceptance before "go"
Full test suite green; the probe's 55+ property tests ported (never crosses, 2 bps cancel both sides, 60/121 edges, one fill per
candle, dust, by-id cancel only, maker_orders[] fill parse incl. complement token); a dry run (master OFF) logging >= 20 decision
rows with the same reasons as Zurich's probe on the same candles (parity check). V reviews the tests, then asks the owner for "go".

## OWNER ADDENDUM 10-02 ~14:1x (his words): "make sure that maker test replace ef but all the things that i can control in ef should
## be same, like stake, on, off and specifically master, recording trades in csv and data csv page and file, accounting and accuracy and all"
The maker brain must plug into the EF lane's EXISTING plumbing, not run beside it. Acceptance checklist (each item tested):
 1. MASTER: the maker lane sends a live order ONLY when master is ON; master OFF = paper/shadow exactly like EF today.
 2. EF on/off toggle in trade control turns the maker lane on/off (no new switch needed).
 3. STAKE: trade control's EF stake drives the order size ($ -> shares at the bid, min 5).
 4. RECORDING: every maker order/fill/cancel/settlement lands in the same journal tables EF uses, so the CSV export, the data/CSV
    page and the CSV file include them with the same columns (lane = EF, plus engine = maker, order type post-only, price paid = bid).
 5. ACCOUNTING: fills and settlements flow into the same PnL, cash, realized/unrealized, ledgers and PnL curves; partial fills
    counted at the filled shares; maker fee 0.
 6. ACCURACY / metrics: metrics.ef (accuracy, wins, losses, real vs shadow, local_pnl) computed from maker fills the same way.
 7. Dashboard last-fill card, health, alerts unchanged.
Show each of 1-7 passing in the test report before V asks the owner for "go".

## OWNER ADDENDUM 10-02 ~14:2x - STOP LIMITS (answers decision 1): "for the limit set the textbox, I'll set by myself what limit I want"
 8. Trade control gets TEXT BOXES for the maker lane's loss limits: "daily loss limit $" and "lifetime loss limit $". The owner types
    the value. EMPTY = no limit (default; London's no-coded-stop rule holds until he types one). When hit: the maker lane stops
    posting (EF lane off for the day / for good), never master, never a halt of other lanes; the stop is visible on the dashboard.
    Validated input (positive number or empty), persisted across restarts, logged in the audit table like other trade-control changes.
