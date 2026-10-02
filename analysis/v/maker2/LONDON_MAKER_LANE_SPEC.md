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
- cancels: Binance >= 2 bps against our side over the last 1 s; favourite flips; bid leaves band; vol leaves calm; sec 121;
  candle end. A risen bid = cancel + fresh post next pass.
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
