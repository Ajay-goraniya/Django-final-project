# London change approved by the owner 10-01 ~15:1x UTC: "Yesssssss" to BOTH, after V listed exactly these two changes.
1. EF-MAKER execution (M18): EF keeps its decisions. Instead of crossing the ask, post a post-only BUY at (ask at fire - 0.01) for
   30 s (never past sec 270), then cancel the rest. Partial fills kept. One order per candle, no re-post, no chase. Stake unchanged ($5).
2. SESSION TRIAL: EF live only 13:00-24:00 UTC. 00:00-13:00 UTC EF keeps deciding and LOGS what it would have fired (shadow, with the
   M18 maker sim). Review 10-04 ~13:00 UTC: if 00-13 shadow is positive over the 3 days, it goes back on.
Build -> tests -> V reviews the tests -> go live. Stops and alerts unchanged.
Known trap (Zurich probe, 09-30): maker fills appear ONLY in trade.maker_orders[] - fill detection must read it.
