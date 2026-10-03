# M35 (V, 10-03 11:2x) - owner's ratchet stop on fixed EF, exits as RESTING orders. History only.
Owner: "buy fixed ef, book moves 10% up set stop loss at 5% below, if price moves 20% above set stop loss to 10%, and then keep
that stop loss to 10% above from marked price ... if price drops we sell at marked point ... All this resting orders".
RULE (frozen; V's reading - owner may correct): mark P = our entry price.
  start: stop = P (sell at the mark if the price drops back to it).
  once bid >= 1.10*P: stop = 1.05*P.   once bid >= 1.20*P: stop = 1.10*P, and it stays there (no further trailing).
  stop hit (bid <= stop) -> sell at the stop price; never re-buy. No hit before sec 270 -> hold to settlement.
FEES: owner says all resting -> PRIMARY column zero fee on entry and exit; second column taker fee 0.07p(1-p) on exit.
  (Caveat to state: a resting sell at the stop fills only if someone takes it; selling exactly at the stop is a best case.)
DATA: (1) Zurich: M29 fixed15 15 days, entry = ask-touch resting fill (primary) and taker-at-ask (second), exits on 1 Hz bid.
      (2) London: its own REAL fixed-EF fills (all fixed-EF lanes since 09-23 incl. 13.2.x resting), exits on its 1 Hz book.
REPORT vs HOLD on identical entries: n, W/L/stopped-out, $, per $1, maxDD, worst trade, green days, halves.

## AMENDMENT 10-03 11:2x (owner corrected step 5): "if stop is hit, then it's our new marked price and rebuy if book comes back
## to that price and cross 10% above"
On a stop at price S: SELL at S, and S becomes the NEW MARK. RE-BUY (at the ask) when the price rises back through S to >= 1.10*S.
After the re-buy the same ratchet runs on mark S: price is already >= 1.10*S so stop = 1.05*S; once bid >= 1.20*S stop = 1.10*S.
Next stop hit -> that stop price is the new mark, and so on until sec 270; held position at 270 -> settlement.
Realistic arming (London's fix): the first stop at P arms only once the bid has reached P (taker fills start ~1c under).
Report this corrected rule (fee and zero-fee) next to the first version.
