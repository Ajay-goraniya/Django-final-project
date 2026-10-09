# M14 - a fire-time skip rule for London fixed15 that cuts >= 5% of losses without cutting profit (owner 09-30 16:4x). BEFORE running.
Owner: "if a fix can cut 5% of our loss without cutting profit or affecting much, find it". M13: losses are the candles that go
flat AFTER the fire; pre-open vol/activity do not predict it. So only information AT THE FIRE is allowed.
DATA: London's own real fixed15 EF fills (every fill, 09-23..now), graded on the venue's resolution, real stake/price/fee.
FEATURES at the fire (no look-ahead): fire second; ask paid; distance from the opening TWAP60 line at the fire (bps, signed to our
side); momentum = our-side move over the last 5 s and last 15 s before the fire (still going vs stalling); rv60; book spread and
top-of-book size on our side if logged; Chainlink-vs-Binance basis at the fire.
RULES = single-feature skips at fixed cut points only: skip the fires in the worst 10% / 20% / 30% of that feature, direction fixed
by the mechanism BEFORE looking (small distance from the line = skip; momentum against us / stalling = skip; high ask = skip).
WALK-FORWARD: choose the rule on 09-23..27, test ONCE on 09-28..now (sealed). PASS = on the sealed test the rule cuts total $ lost by
>= 5% AND total PnL is >= baseline PnL AND the skipped fires are net negative, and on train both halves agree.
Report the FULL grid (every feature x cut: train and test PnL, $ lost, fires skipped, win% of skipped), run analysis/h1/verify.py
(halves, sample, costs, paired, null). NOTHING is deployed; a pass goes to the owner as a proposal needing his confirmation.
