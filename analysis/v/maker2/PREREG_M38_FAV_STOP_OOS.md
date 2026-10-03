# M38 (V, 10-03 12:0x) - walk-forward of the ONLY positive M36 pairing, frozen BEFORE looking. History only, nothing live.
Candidate (frozen from M36 E2 arm FAV, n791): FAV calm entries + ratchet a15 g10 R-off T-none. In-sample +0.0061/$1 vs HOLD +0.0281.
DATA: FAV calm fires on Zurich NOT in the M32-BIG/M36 entry set (forward paper days since that set was cut), real 1 Hz bid+ask.
PRIMARY: stop exit = taker at triggering bid + 0.07p(1-p); entry as the FAV lane prices it. Label = venues.outcome.
REPORT: HOLD vs a15g10 (and the owner's literal rows a10 O-steps R-off for reference): n, per $1, t, halves, green days,
maxDD, worst, paired vs HOLD (verify.py paired()). No other cell is run.
PASS = a15g10 per $1 > 0 with t >= 2 on n >= 60, both halves > 0, >= 60% green days. Else FAIL. n < 60 = INSUFFICIENT.
