18:57 UTC 09-15 | (1) results n=51 W29/L22 pnl +42.09 | cash 90.94 open 0.00 | master on, halt null, pid 72358 alive, build 12.9.0
(2) hour|n|W|pnl: 11|3|3|+13.53 ; 12|3|2|+6.29 ; 13|4|1|-8.72 ; 14|5|2|+5.52 ; 15|5|2|-2.11 ; 16|2|1|-0.70 ; 17|3|0|-14.45 ; 18|3|1|-2.97
(3) losses since 14:00 (time side paid p sec): 14:01 DOWN .46 .642 65 | 14:23 DOWN .41 .544 181 | 14:35 UP .33 .531 30 | 15:07 DOWN .47 .627 156 | 15:30 UP .49 .623 36 | 15:37 DOWN .43 .510 128
    16:01 UP .45 .678 75 | 17:01 UP .47 .623 71 | 17:11 DOWN .43 .540 85 | 17:18 DOWN .47 .664 210 | 18:08 UP .39 .569 232 | 18:27 DOWN .42 .594 158  (each -4.80..-4.83 = full $5 stake less fee)
(4) hour|fills|rejects: 14|5|10 ; 15|5|7 ; 16|2|4 ; 17|3|2 ; 18|4|8  (since 14:00: 19 fills / 31 rejects = 38%)
(5) since 17:31: halt none; KILL_CONDITION x2 at 17:31:27 = watch-only re-report of the pre-restart 20-result window (unit -5.23 vs -3.0, acted=false); RECONCILE_STUCK 6 = one per rejected order on its first reconcile pass (get_order UnexpectedResponseError, logged once each, all orders terminal); no error rows.
Verdict: 12 losses since 14:00 vs 7 wins on the same window; n<60, no reading on p or sec. Engine healthy; the run is losing.
