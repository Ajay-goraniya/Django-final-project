# What we want on Polymarket, and how execution has to work

Written 09-11. Scope: this is the target we are building toward in v12, not something that exists yet.
Nothing here is deployed. The decision to go live is the user's, next week, after the weekend test.

## 1. The goal in one line

Take the version that is already making money on paper at Polymarket and run it live, with the same
execution quality we get on Predict.fun: near-100% fill rate, few retries, and no fill at a price that
kills the edge.

The paper run is the reason we care. Since 09-08 17:35 UTC the v10 model trading Polymarket's real asks
has done 216 wins / 193 losses, 52.8%, **+517.9 at $10 per fire** after the 7% taker fee. Per $1 staked
that is +0.148, positive on every UTC day so far, both halves of the run positive. Predict.fun live is
+0.04 to +0.11 per $1 on the same kind of fire. That gap is the whole case for the venue.

Two honest caveats, so nobody reads the number wrong:

- Weekday data only. Zero weekend coverage. That is what the Saturday-Sunday test is for.
- The paper run assumed it could buy at the ask it saw. Live execution is exactly the assumption being
  tested. If fills come in worse than the quoted ask, the edge shrinks by that difference.

## 2. What "live" means here

A separate lane on Polymarket, running beside Tokyo, starting at $1 a fire. Same ladder as Predict.fun:
$1 under $30 equity, $2 at $30, $3 at $40, then +$1 per +$10, capped at $20, step down immediately when
equity drops below the rung, step up only after the higher rung holds for two consecutive checks.
The engine runs it 24/7 with no human in the loop, the same as the current lanes.

## 3. How execution has to work

The five-minute market gives us one shot. We decide mid-candle, and the position has to exist within a
second or two or the price we decided on is gone. So the executor is built for speed and certainty of
fill, not for price improvement.

**Take, never make.** Every entry is a marketable limit order that crosses the spread. Polymarket charges
takers and lets makers trade free, and it is tempting to rest a passive order to save the fee. Do not.
A resting order that does not fill is a candle with no position, and a signal that only trades when the
market comes to it is a different, worse signal. We pay the taker fee and count it in the EV rule before
we fire.

**Fill-and-kill, with a price cap.** Submit FAK (take what is there at or better than my limit, cancel
the rest) rather than plain limit. The limit is the top-of-book ask plus a small pad in ticks. The pad is
what buys the fill; the EV check is what stops the pad from eating the edge. The order is only sent if
the trade is still profitable *at the padded price* after the fee. If it is not, we skip the candle.
Skipping is free. Overpaying is not.

**Size is not the problem, latency is.** Our stake is $1 to $20, which is 2 to 45 shares. The top level
of the book carries 280 to 620 shares. One level covers us many times over, so a fill failure is almost
never about depth. It is about the quote being stale by the time the order lands. That is why the quote
comes from the websocket book feed (`wss://ws-subscriptions-clob.polymarket.com/ws/market`, PING every
10 seconds) and not from polling REST. We price off a book that is milliseconds old, not seconds.

**Retries: at most three, each on a fresh quote.** This is the rule that gets Predict.fun to 269 fills
out of 271 attempts. The important half of it is *fresh quote*: a retry re-reads the book and re-runs
the EV check before resubmitting. It never re-sends the old price. If the book moved against us and the
trade no longer clears EV, the retry becomes an abandon, not a worse fill. There is also a deadline
inside the candle: past it we stop trying, because a late entry has less time to be right.

**Never double-fill.** Each order is signed with its own client order id. If a submit times out we
re-query that id and read what actually happened. We never blind-resubmit on a timeout. On Predict.fun
this is the difference between a clean ledger and a phantom position.

**Slippage is measured, not assumed.** Every fill records the quote we decided on, the price we paid,
the attempt count and the latency. Rolling averages of those are what tell us whether the paper edge
survived contact with the venue. The kill rule already used for the REVERSAL lane applies: if average
slippage runs over 3 cents across 20 fills, or PnL per $1 goes below -3.0 across 20 fills, the lane
turns itself off.

## 4. What is different from Predict.fun, concretely

| | Predict.fun | Polymarket |
|---|---|---|
| Order | REST submit, signed | EIP-712 typed data, signed, Polygon chain 137 |
| Types | market-style take | GTC / GTD / FAK / FOK. GTD expires one minute *before* its stated time |
| Fee | flat 2% | takers pay shares x 0.07 x p x (1-p); makers free |
| Tick / min size | fixed | per token, read from the book endpoint per market |
| Settles on | Binance candle close >= open | Chainlink BTC/USD 60-second TWAP |
| Book depth | thin | 280-620 shares a level, 1c spread, ~$16k a market |
| Funding | venue balance | USDC on Polygon, with allowances approved up front |

The settlement row is the dangerous one. The two venues disagree on about 10% of candles, all of them
near-flat. A model trained on Binance closes is *negative* on Polymarket for exactly this reason: it
fires hardest where the two disagree. Anything we trade on Polymarket is graded on Polymarket's own
outcome, and any direction model for it has to be trained on that outcome. This has already produced one
completely fake result, so it is not a detail.

## 5. What has to be true before a single live order

1. **Account verification.** Polymarket's relayer allows 100 transactions a day unverified, 10,000
   verified. We fire around 150 times a day. An unverified account cannot run this lane at all. This is
   on Polymarket's side, not ours, so it has to be started early.
2. **Jurisdiction check.** Markets carry a `restricted` flag and the geoblock is tiered. The severe tier
   blocks new orders *and* prevents closing open positions, which on a 5-minute market is a settlement
   risk, not just an access annoyance. The user confirms eligibility against the terms before we fund.
3. **Funding.** USDC on Polygon in the trading wallet, allowances approved.
4. **The fee number nailed down.** The docs say 0.07, the help centre implies 0.0625, and the market data
   field matches neither. Our numbers use 0.07, which is the conservative choice. One real fill settles it.
5. **Weekend evidence.** The paper run has never seen a weekend. The Saturday-Sunday test fills that gap.

## 6. How we will know it worked

The same three numbers we judge everything by, on the live lane, not on paper:

- **Fill rate and attempts.** Target is the Predict.fun standard: over 99% filled, first attempt
  accepted almost always.
- **Slippage in cents** between the quote we decided on and the price we paid. If this is near zero, the
  paper PnL transfers. If it is a cent or more, it does not, and we say so.
- **PnL per $1 staked**, graded on Polymarket's outcome, both halves of the run positive, and positive
  every day rather than on average. A number that only works some days is a number we have to explain
  before we trust it.

## 7. Correction, 09-11 14:05 - what crossing actually costs

An earlier version of my reasoning used a 1.5 cent crossing cost. H1 decomposed it and that number was wrong:
the genuine crossing part (fill minus the quote the engine itself saw at the order, median quote age 151 ms)
is only **+0.26c +/- 0.18c**, and across all 380 live EF fills it is **+0.46c +/- 0.09c, both halves identical**.
The rest of the 1.5c was a timing difference between two price feeds, not a cost anyone pays. Proof it was not
an execution cost: the same decomposition run on REVERSAL returns +15.4c, which is obviously not crossing.

**The defensible crossing prior is +0.5c +/- 0.1c**, valid at $1-$4 stakes where the top of book covers the
order. Polymarket's fee is separate and must not be double-counted with it. On that prior the Polymarket paper
+0.187 per $1 lands near **+0.18, not +0.10** - crossing is close to a rounding error at our size.

That makes the crossing question settled and NOT the blocker. The blocker is quote age: only 23 of 427 paper
asks matched the 5-second collector at the same second, and the paper had no record of how old its quote was.
This is the same exposure that took the 11.2 replay from +0.27 per fire to about zero. Fixed at 13:28 - the
paper runner now records book_age_ms on every fire - so the number can be certified from here forward, but
+0.187 is not an honest figure until that re-run happens on fires that carry the column.
