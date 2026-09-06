#!/usr/bin/env python3
"""Per-day calibration, stake executability, first-fill lag, pooled real-ladder numbers, hybrid path sanity."""
import pathlib, sys, numpy as np, pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
DATES = ["2026-08-22", "2026-08-24", "2026-08-27", "2026-08-31", "2026-09-05"]
def cost(q, r): return q / (1.0 - r * (1.0 - q))   # BUY-fee semantics: win return = (1 - r(1-q))/q - 1
P = {d: pd.read_parquet(HERE / "data" / f"tape_proxy_{d}.parquet") for d in DATES}
print("PER-DAY FAVOURITE CALIBRATION, TRADE-TAPE PROXY, $5 fill bucket, 120 s offset only (n | mean fill | realized | diff | EV/$ fee7)")
for d in DATES:
    F = P[d]; F = F[(F.offset_s == 120) & F.fav.notna() & F.ok_d0_s5]
    cells = []
    for lo, hi in ((.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0)):
        m = (F.vwap_d0_s5 >= lo) & (F.vwap_d0_s5 < hi)
        if m.sum(): q = F.vwap_d0_s5[m].mean(); w = F.win_fav[m].mean(); cells.append(f"[{lo:.1f},{hi:.1f}) {int(m.sum()):>3} {q:.3f} {w:.3f} {w-q:+.3f} {w*(1-.07*(1-q))/q-1:+.3f}")
        else: cells.append(f"[{lo:.1f},{hi:.1f})   0")
    print(f"  {d}: " + " | ".join(cells))
print("\nPER-DAY CALIBRATION, all offsets pooled (n | diff realized-price | EV/$ fee7):")
for d in DATES:
    F = P[d]; F = F[F.fav.notna() & F.ok_d0_s5]; cells = []
    for lo, hi in ((.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0)):
        m = (F.vwap_d0_s5 >= lo) & (F.vwap_d0_s5 < hi); q = F.vwap_d0_s5[m].mean(); w = F.win_fav[m].mean()
        cells.append(f"[{lo:.1f},{hi:.1f}) {int(m.sum()):>4} {w-q:+.3f} {w*(1-.07*(1-q))/q-1:+.3f}")
    print(f"  {d}: " + " | ".join(cells))
print("\nSTAKE EXECUTABILITY on the tape within 15 s of T (120 s offset): fill-ok %, mean fill, mean slippage vs the first print after T, median first-fill lag s")
print(f"{'date':<12}" + "".join(f"{'$'+str(s)+' ok%':>9}{'fill':>7}{'slip':>7}{'lag':>5}" for s in (2, 5, 10, 100)))
for d in DATES:
    F = P[d]; F = F[(F.offset_s == 120) & F.fav.notna()]; line = f"{d:<12}"
    for s in (2, 5, 10, 100):
        ok = F[f"ok_d0_s{s}"]; v = F[f"vwap_d0_s{s}"]; lag = F.get(f"first_fill_lag_d0_s{s}")
        line += f"{100*ok.mean():>9.1f}{v[ok].mean():>7.3f}{(v[ok]-F.vwap_d0_s2[ok]).mean():>+7.3f}{(lag[ok].median() if lag is not None else float('nan')):>5.0f}"
    print(line)
print("\nTRADES PER WINDOW (tape density): " + ", ".join(f"{d}: median {int(P[d].drop_duplicates('window_epoch').n_trades.median())}" for d in DATES))

L = pd.read_parquet(HERE / "data" / "polyorderbooks_btc5m_ladders.parquet"); L = L[L.has_book & L.fav.notna()]
print("\nREAL LADDERS (PolyOrderbooks, partial days) POOLED, by offset: markets | win% | avg $5 VWAP | PnL/100 fee7 | PnL/100 fee0 | +1s fee7 | +5s fee7 | $2 ok% | $100 ok%")
for X in (30, 60, 90, 120, 180, 240):
    T = L[L.offset_s == X]; ok = T.ok_d0_s5; v = T.vwap_d0_s5[ok]; w = T.win_fav[ok]
    p7 = 100 * np.where(w, (1 - .07 * (1 - v)) / v - 1, -1.0).mean(); p0 = 100 * np.where(w, 1 / v - 1, -1.0).mean()
    def lat(dly):
        o = T[f"ok_d{dly}_s5"]; vv = T[f"vwap_d{dly}_s5"][o]; ww = T.win_fav[o]; return 100 * np.where(ww, (1 - .07 * (1 - vv)) / vv - 1, -1.0).mean()
    print(f"  {X:>4}s  {int(ok.sum()):>4}  {100*w.mean():>5.1f}  {v.mean():.3f}  {p7:>+7.2f}  {p0:>+7.2f}  {lat(1):>+7.2f}  {lat(5):>+7.2f}  {100*T.ok_d0_s2.mean():>5.1f}  {100*T.ok_d0_s100.mean():>5.1f}")
R = L[L.day.isin(["2026-08-22", "2026-08-24"]) & (L.offset_s == 120)]; ok = R.ok_d0_s5; v = R.vwap_d0_s5[ok]; w = R.win_fav[ok]
print(f"  requested dates only (08-22 + 08-24), 120 s: markets {int(ok.sum())}  win {100*w.mean():.1f}%  PnL/100 fee7 {100*np.where(w,(1-.07*(1-v))/v-1,-1.0).mean():+.2f}")

H = pd.read_csv(HERE / "hybrid_staking_5day_paths.csv")
print("\nHYBRID PATH SANITY (independent, 120 s, fee 0.07): date | trades | max capital | min capital | end")
for d, g in H[H["mode"] == "independent"].groupby("date"): print(f"  {d}: {len(g):>4}  max {g.capital.max():7.2f}  min {g.capital.min():6.2f}  end {g.capital.iloc[-1]:6.2f}  max stake {g.stake.max():6.2f}")
