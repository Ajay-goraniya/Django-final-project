# M36 (V, 10-03 11:3x) - owner: "work with that strategy and find the perfect match that makes profit". History only.
Family = owner's ratchet stop (M35), parameters swept. Grid FROZEN here before any run; full grid reported, never the best cell.

FACT THAT FIXES THE FILL MODEL: Polymarket has no stop orders. A resting sell priced below the bid executes at once as a
taker. So every stop exit = TAKER SELL AT THE BID THAT TRIGGERED IT, paying 0.07p(1-p). Re-buys = taker at the ask, fee.
"Fill exactly at the stop" is not achievable; it is printed only as a reference column, never read.
The only truly RESTING exit is a take-profit limit ABOVE the market (zero fee, fills only when bid >= T + 1 tick).

ENTRIES (same entries for every cell and for HOLD):
  E1 Zurich fixed15 fires with a 1 Hz bid book (n125 taker-at-ask, n63 ask-touch resting).
  E2 Zurich M32-BIG entry set (3,693 entries, real 1 Hz bid+ask) - the scale test, per arm and pooled.
  E3 London's own real fixed-EF fills (n252) on its own 1 Hz book.
GRID (P = entry price, peak = highest bid since entry/re-entry):
  a   arm level: stop first switches on when bid >= (1+a)P,     a in {0 (bid>=P), 5, 10, 15, 20, 30}%
  g   trailing give-back: stop = max(P, peak*(1-g)),             g in {5, 10, 15, 20}%   (owner's steps ~ a10/g5..10)
  O   owner's literal steps (a10 -> stop 1.05P, a20 -> stop 1.10P fixed) as one extra row
  R   re-buy after a stop: {off, on: new mark S, re-buy at ask >= 1.10S}
  T   resting take-profit: {none, +20, +30, +50}%
  => 6 x 4 x 2 x 4 = 192 cells + O rows. Exits after sec 270 -> hold to settlement (venue resolution label).
REPORT per cell: n, $@10, per $1 (fees ON, triggering bid = PRIMARY), t, maxDD, worst trade, green days, halves,
paired vs HOLD on the same entries (verify.py paired()), and a RANDOM-ENTRY control: same exit cell on random side at a
random fire second on the same candles (tests whether the exit rule alone "makes money").
PASS (all required): primary per $1 > 0 with t >= 2 on n >= 60; both halves > 0; >= 60% green days; beats HOLD paired;
AND every grid neighbour (a +-1 step, g +-1 step) also > 0 (a plateau, not a peak); AND holds on E2 pooled.
Anything else = FAIL, reported as such.
