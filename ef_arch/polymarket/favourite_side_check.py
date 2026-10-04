#!/usr/bin/env python3
"""The mirror of the reversal overpricing: is the CONTINUATION (favourite) side underpriced at real asks?
No search. Fixed rule: buy the continuation side once per window at a FIXED offset, at its real $10 VWAP,
settle on Chainlink. Report win rate vs price bucket and PnL/100 at fee 0 and 7% for a few fixed offsets."""
import numpy as np, pandas as pd, pyarrow.parquet as pq, pathlib
L = pq.read_table(pathlib.Path(__file__).resolve().parent / "polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book & L.fill_ok_s10]
def cost(q, r): return q * (1 + r * (1 - q))
# continuation side = the side whose ask is > 0.5 (the market favourite); tie -> skip
L["fav"] = np.where(L.best_ask > 0.5, True, np.where(L.best_ask < 0.5, False, np.nan))
F = L[L.fav == True].copy(); F["win"] = (F.outcome == F.side)
print(f"favourite-side rows (ask>0.5): {len(F):,}  windows {F.window_epoch.nunique()}  win rate {100*F.win.mean():.1f}%  mean ask {F.vwap_s10.mean():.3f}")
print("\nFAVOURITE calibration by real $10 VWAP bucket (diff>0 => underpriced => +EV at fee 0):")
print(f"{'vwap bucket':<12}{'n':>7}{'mean vwap':>11}{'realized':>10}{'diff':>8}{'EV/$ fee0':>11}{'EV/$ fee7':>11}")
for lo, hi in ((.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0)):
    m = (F.vwap_s10 >= lo) & (F.vwap_s10 < hi)
    if m.sum():
        q = F.vwap_s10[m].mean(); w = F.win[m].mean()
        print(f"[{lo:.1f},{hi:.1f})   {int(m.sum()):>7}{q:>11.3f}{w:>10.3f}{w-q:>+8.3f}{w/cost(q,0)-1:>+11.3f}{w/cost(q,.07)-1:>+11.3f}")
print("\nFIXED-OFFSET RULE: buy continuation side at offset X (once per window), $10, settle Chainlink")
print(f"{'offset':>7}{'trades':>8}{'win%':>7}{'avg vwap':>10}{'PnL/100 fee0':>14}{'PnL/100 fee7':>14}{'maxDD fee0':>12}")
for X in (30, 60, 90, 120, 180, 240):
    T = F[F.offset_s == X].sort_values("window_epoch")
    if T.empty: continue
    p0 = np.where(T.win, 1/cost(T.vwap_s10,0)-1, -1.0); p7 = np.where(T.win, 1/cost(T.vwap_s10,.07)-1, -1.0)
    eq = np.cumsum(p0); dd = float((np.maximum.accumulate(eq)-eq).max())
    print(f"{X:>7}{len(T):>8}{100*T.win.mean():>7.1f}{T.vwap_s10.mean():>10.3f}{100*p0.sum()/288:>+14.2f}{100*p7.sum()/288:>+14.2f}{dd:>12.2f}")
print("\nNOTE: this is a bias harvest with no BTC signal, one day, fee 0 as reported by the venue, ladder walk at the instant, no latency.")
