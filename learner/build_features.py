#!/usr/bin/env python3
"""
build_features.py -- one feature row per (candle, decision offset) for EVERY
candle of every day on disk, from the raw replay data. Nothing is model-
derived, nothing is synthetic; every number is computed causally from data
with timestamp <= the decision time.

Why every candle: the existing learners only ever see the candles EF fired
on. They never learn what the skipped candles would have done, so they are
trained on a selected, biased sample of a few hundred rows. This gives them
~2,300 candles x 10 decision points.

Label: the venue's resolved outcome (Chainlink 60s TWAP), because that is what
pays; NOT the Binance candle direction (they disagree on ~11% of candles).
"""
import datetime as dt, glob, json, math, pathlib, sys
import numpy as np, pyarrow as pa, pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[1]
DAYS = ["2026-08-29", "2026-08-30", "2026-08-31", "2026-09-02",
        "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
OFFSETS = [15, 30, 45, 60, 90, 120, 150, 180, 210, 240]     # seconds into candle
OUT = ROOT / "learner" / "features.parquet"
US = 1_000_000


def day_epoch(d):
    return int(dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())


def load_settlement(d):
    S = {}
    f = ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{d}.json"
    for r in json.loads(f.read_text())["rows"]:
        m = r["market"]
        try:
            names = json.loads(m["outcomes"]); prices = json.loads(m["outcomePrices"])
        except Exception:
            continue
        w = [n for n, p in zip(names, prices) if str(p) == "1"]
        if len(w) == 1:
            S[int(r["epoch"])] = 1 if w[0].strip().upper() == "UP" else 0
    return S


def load_quotes(d):
    """(epoch, second) -> (ask_up, ask_dn, bid_up, bid_dn, is_book), every second."""
    t = pq.read_table(ROOT / f"week_data/predictfun/quotes_1s_unified/poly_1s_{d}.parquet",
                      columns=["window_epoch", "side", "offset_s", "quote_source",
                               "best_ask", "best_bid"])
    c = {n: t.column(n).to_numpy(zero_copy_only=False) for n in t.column_names}
    Q = {}
    for i in range(t.num_rows):
        if c["quote_source"][i] == "none":
            continue
        k = (int(c["window_epoch"][i]), int(c["offset_s"][i]))
        e = Q.setdefault(k, [np.nan, np.nan, np.nan, np.nan, 0])
        a, b = c["best_ask"][i], c["best_bid"][i]
        if str(c["side"][i]).upper() == "UP":
            e[0], e[2] = a, b
        else:
            e[1], e[3] = a, b
        if c["quote_source"][i] == "book":
            e[4] = 1
    return Q


def load_day_tapes(d):
    nd = ROOT / "week_replay" / d / "normalized"
    sp = pa.concat_tables([pq.read_table(f, columns=["timestamp", "price", "quantity", "is_buyer_maker"])
                           for f in sorted(glob.glob(str(nd / "spot_aggtrades_*.parquet")))])
    pp = pa.concat_tables([pq.read_table(f, columns=["timestamp", "price", "quantity", "signed_quote_notional", "quote_notional"])
                           for f in sorted(glob.glob(str(nd / "perp_trades_*.parquet")))])
    spot = {n: sp.column(n).to_numpy(zero_copy_only=False) for n in sp.column_names}
    perp = {n: pp.column(n).to_numpy(zero_copy_only=False) for n in pp.column_names}
    o = np.argsort(spot["timestamp"], kind="stable")
    spot = {k: v[o] for k, v in spot.items()}
    o = np.argsort(perp["timestamp"], kind="stable")
    perp = {k: v[o] for k, v in perp.items()}
    # cumulative sums for O(1) window aggregates
    spot["cum_buy"] = np.cumsum(np.where(~spot["is_buyer_maker"], spot["quantity"], 0.0))
    spot["cum_sell"] = np.cumsum(np.where(spot["is_buyer_maker"], spot["quantity"], 0.0))
    perp["cum_signed"] = np.cumsum(perp["signed_quote_notional"])
    perp["cum_abs"] = np.cumsum(perp["quote_notional"])
    perp["cum_n"] = np.arange(1, len(perp["timestamp"]) + 1, dtype=np.float64)
    return spot, perp


def depth_at(d, ts_list):
    """Top-of-book snapshot at each decision timestamp (last ladder <= ts).
    Reads hour files one at a time; only the rows we need are converted."""
    nd = ROOT / "week_replay" / d / "normalized"
    W0 = day_epoch(d) * US
    out = {ts: None for ts in ts_list}
    by_hour = {}
    for ts in ts_list:
        by_hour.setdefault(int((ts - W0) // (3600 * US)), []).append(ts)
    cols = ["local_timestamp", "is_crossed"] + \
           [f"bid_px_{i}" for i in range(5)] + [f"ask_px_{i}" for i in range(5)] + \
           [f"bid_qty_{i}" for i in range(20)] + [f"ask_qty_{i}" for i in range(20)]
    for h, tss in by_hour.items():
        f = nd / f"perp_depth20_{h:02d}.parquet"
        if not f.exists():
            continue
        t = pq.read_table(f, columns=cols)
        lt = t.column("local_timestamp").to_numpy()
        idx = np.searchsorted(lt, np.array(tss), side="right") - 1
        ok = idx >= 0
        if not ok.any():
            continue
        sub = t.take(pa.array(idx[ok]))
        c = {n: sub.column(n).to_numpy(zero_copy_only=False) for n in cols}
        for j, ts in enumerate(np.array(tss)[ok]):
            bq5 = sum(c[f"bid_qty_{i}"][j] for i in range(5)); aq5 = sum(c[f"ask_qty_{i}"][j] for i in range(5))
            bq20 = sum(c[f"bid_qty_{i}"][j] for i in range(20)); aq20 = sum(c[f"ask_qty_{i}"][j] for i in range(20))
            b0, a0 = c["bid_px_0"][j], c["ask_px_0"][j]
            bq0, aq0 = c["bid_qty_0"][j], c["ask_qty_0"][j]
            if not (np.isfinite(b0) and np.isfinite(a0)) or a0 <= 0 or b0 <= 0:
                continue
            mid = (a0 + b0) / 2
            micro = (a0 * bq0 + b0 * aq0) / (bq0 + aq0) if (bq0 + aq0) > 0 else mid
            out[int(ts)] = dict(
                spread_bps=(a0 - b0) / mid * 1e4,
                imb5=(bq5 - aq5) / (bq5 + aq5) if (bq5 + aq5) > 0 else 0.0,
                imb20=(bq20 - aq20) / (bq20 + aq20) if (bq20 + aq20) > 0 else 0.0,
                micro_bps=(micro - mid) / mid * 1e4,
                depth_mid=mid, crossed=float(c["is_crossed"][j]),
                age_ms=(ts - lt[idx[ok][j]]) / 1000.0,
            )
    return out


def px_at(spot, ts):
    i = np.searchsorted(spot["timestamp"], ts, side="right") - 1
    return spot["price"][i] if i >= 0 else np.nan


def build_day(d):
    S = load_settlement(d); Q = load_quotes(d)
    spot, perp = load_day_tapes(d)
    W0 = day_epoch(d)
    sts, spx = spot["timestamp"], spot["price"]
    pts = perp["timestamp"]
    rows = []
    # decision timestamps for depth lookup
    dts = [(W0 + k * 300 + off) * US for k in range(288) for off in OFFSETS]
    D = depth_at(d, dts)
    for k in range(288):
        ep = W0 + k * 300
        if ep not in S:
            continue
        o_us = ep * US
        # candle open reference = first spot trade at/after open
        i0 = np.searchsorted(sts, o_us, side="left")
        if i0 >= len(sts):
            continue
        open_px = spx[i0]
        # previous candle moves (context)
        p_prev1 = px_at(spot, o_us); p_prev2 = px_at(spot, o_us - 300 * US); p_prev3 = px_at(spot, o_us - 600 * US)
        prev1 = (p_prev1 / p_prev2 - 1) * 1e4 if np.isfinite(p_prev2) and p_prev2 > 0 else 0.0
        prev2 = (p_prev2 / p_prev3 - 1) * 1e4 if np.isfinite(p_prev3) and p_prev3 > 0 else 0.0
        for off in OFFSETS:
            t_us = o_us + off * US
            i = np.searchsorted(sts, t_us, side="right") - 1
            if i < i0:
                continue
            p = spx[i]
            seg = spx[i0:i + 1]
            hi, lo = seg.max(), seg.min()
            rng = hi - lo
            def ret(sec):
                q = px_at(spot, t_us - sec * US)
                return (p / q - 1) * 1e4 if np.isfinite(q) and q > 0 else 0.0
            # realized vol: 1s sampled log returns over last 60s
            grid = np.arange(t_us - 60 * US, t_us + 1, US)
            gi = np.searchsorted(sts, grid, side="right") - 1
            gi = gi[gi >= 0]
            gp = spx[gi]
            lr = np.diff(np.log(gp)) if len(gp) > 2 else np.array([0.0])
            rv60 = float(np.std(lr) * 1e4) if len(lr) > 1 else 0.0
            # spot flow windows
            def spot_imb(sec):
                a = np.searchsorted(sts, t_us - sec * US, side="left"); b = i
                if b < a:
                    return 0.0
                buy = spot["cum_buy"][b] - (spot["cum_buy"][a - 1] if a > 0 else 0.0)
                sell = spot["cum_sell"][b] - (spot["cum_sell"][a - 1] if a > 0 else 0.0)
                tot = buy + sell
                return (buy - sell) / tot if tot > 0 else 0.0
            # perp flow windows
            pi = np.searchsorted(pts, t_us, side="right") - 1
            def perp_ofi(sec):
                a = np.searchsorted(pts, t_us - sec * US, side="left"); b = pi
                if b < a or b < 0:
                    return 0.0, 0.0
                sg = perp["cum_signed"][b] - (perp["cum_signed"][a - 1] if a > 0 else 0.0)
                ab = perp["cum_abs"][b] - (perp["cum_abs"][a - 1] if a > 0 else 0.0)
                n = perp["cum_n"][b] - (perp["cum_n"][a - 1] if a > 0 else 0.0)
                return (sg / ab if ab > 0 else 0.0), n
            ofi5, n5 = perp_ofi(5); ofi15, n15 = perp_ofi(15); ofi60, n60 = perp_ofi(60)
            perp_px = perp["price"][pi] if pi >= 0 else np.nan
            basis = (perp_px / p - 1) * 1e4 if np.isfinite(perp_px) else 0.0
            dp = D.get(int(t_us)) or {}
            q = Q.get((ep, off))
            ask_up = q[0] if q else np.nan; ask_dn = q[1] if q else np.nan
            bid_up = q[2] if q else np.nan; bid_dn = q[3] if q else np.nan
            # venue implied probability of UP: mid of UP if both sides, else from asks
            if q and np.isfinite(ask_up) and np.isfinite(bid_up):
                p_venue = (ask_up + bid_up) / 2
            elif q and np.isfinite(ask_up) and np.isfinite(ask_dn):
                p_venue = (ask_up + (1 - ask_dn)) / 2
            else:
                p_venue = np.nan
            hod = ((ep % 86400) / 86400.0) * 2 * math.pi
            # ---- v11 additions (all causal)
            def pv_at(sec):
                qq = Q.get((ep, sec))
                if not qq: return np.nan
                if np.isfinite(qq[0]) and np.isfinite(qq[2]): return (qq[0] + qq[2]) / 2
                if np.isfinite(qq[0]) and np.isfinite(qq[1]): return (qq[0] + (1 - qq[1])) / 2
                return np.nan
            pv_now = pv_at(off)
            dpv15 = pv_now - pv_at(off - 15) if off >= 15 and np.isfinite(pv_now) and np.isfinite(pv_at(off - 15)) else 0.0
            dpv30 = pv_now - pv_at(off - 30) if off >= 30 and np.isfinite(pv_now) and np.isfinite(pv_at(off - 30)) else 0.0
            dpv60 = pv_now - pv_at(off - 60) if off >= 60 and np.isfinite(pv_now) and np.isfinite(pv_at(off - 60)) else 0.0
            venue_spread = (ask_up + ask_dn - 1.0) if (q and np.isfinite(ask_up) and np.isfinite(ask_dn)) else np.nan
            # physics fair value: P(close > open | current move, realized vol, time left), Brownian
            sec_left_ = 300 - off
            sig = rv60 * math.sqrt(max(sec_left_, 1))      # bps std of remaining move
            z = (p / open_px - 1) * 1e4 / sig if sig > 1e-9 else (50.0 if p > open_px else (-50.0 if p < open_px else 0.0))
            phys_p = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            ret120 = ret(120); ret180 = ret(180)
            vwap_seg = spot["quantity"][i0:i + 1]
            vwap = float(np.sum(seg * vwap_seg) / np.sum(vwap_seg)) if np.sum(vwap_seg) > 0 else p
            vwap_dev = (p / vwap - 1) * 1e4
            rows.append(dict(
                date=d, epoch=ep, offset=off, y=S[ep],
                move_bps=(p / open_px - 1) * 1e4,
                ret5=ret(5), ret15=ret(15), ret30=ret(30), ret60=ret(60),
                rv60=rv60,
                range_bps=rng / open_px * 1e4,
                pos_in_range=((p - lo) / rng) if rng > 0 else 0.5,
                dist_hi_bps=(hi - p) / open_px * 1e4, dist_lo_bps=(p - lo) / open_px * 1e4,
                spot_imb15=spot_imb(15), spot_imb60=spot_imb(60),
                ofi5=ofi5, ofi15=ofi15, ofi60=ofi60, perp_n15=n15,
                basis_bps=basis,
                spread_bps=dp.get("spread_bps", np.nan), imb5=dp.get("imb5", np.nan),
                imb20=dp.get("imb20", np.nan), micro_bps=dp.get("micro_bps", np.nan),
                depth_age_ms=dp.get("age_ms", np.nan), crossed=dp.get("crossed", np.nan),
                prev1_bps=prev1, prev2_bps=prev2,
                sec_left=300 - off, hod_sin=math.sin(hod), hod_cos=math.cos(hod),
                ask_up=ask_up, ask_dn=ask_dn, bid_up=bid_up, bid_dn=bid_dn,
                p_venue=p_venue, is_book=(q[4] if q else 0),
                dpv15=dpv15, dpv30=dpv30, dpv60=dpv60, venue_spread=venue_spread,
                phys_p=phys_p, ret120=ret120, ret180=ret180, vwap_dev=vwap_dev,
            ))
    return rows


if __name__ == "__main__":
    days = sys.argv[1:] or DAYS
    all_rows = []
    for d in days:
        r = build_day(d)
        all_rows += r
        print(f"{d}: {len(r):,} rows  ({len(r)//len(OFFSETS)} candles)", flush=True)
    import pandas as pd
    df = pd.DataFrame(all_rows)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {len(df):,} rows x {df.shape[1]} cols -> {OUT}")
    print("label balance UP:", round(df.drop_duplicates('epoch')['y'].mean(), 3))
