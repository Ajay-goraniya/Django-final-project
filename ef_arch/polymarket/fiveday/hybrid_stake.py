#!/usr/bin/env python3
"""
hybrid_stake.py -- the user's HYBRID STAKING rule, shared by every test in this directory.

    start capital            $50 (default)
    stake                    10% of available capital
    stake is NOT recomputed after every trade; it is recomputed ONLY when
        the running WIN streak reaches 3   (3 consecutive settled wins)   or
        the running LOSS streak reaches 2  (2 consecutive settled losses)
    at a trigger: new_stake = 10% * current available capital, and BOTH streak
        counters are reset to 0 (a streak is consumed by the recalculation)
    a win resets the loss counter, a loss resets the win counter
    an unexecutable trade is NO trade: no W/L, no streak change, no capital change
    PnL is applied to capital at settlement, i.e. before the next window's trade
    stake is capped at available capital (no leverage, no injected capital)
    the day is bankrupt if capital < $1 (venue minimum order is 5 shares, so at
        price p a stake below 5p cannot be placed; those events are counted)

trades: iterable of (fill_price_for_stake: callable(stake)->(price or nan, shares_available), win: bool)
"""
import math

def run_hybrid(trades, r_fee, start=50.0, frac=0.10, win_trigger=3, loss_trigger=2, state=None, cost_fn=None, min_shares=5.0):
    cost = cost_fn or (lambda q, r: q / (1.0 - r * (1.0 - q)))   # BUY-fee semantics: win return = (1 - r(1-q))/q - 1
    st = state or dict(C=start, stake=frac * start, wins=0, losses=0)
    C, stake, wins, losses = st["C"], st["stake"], st["wins"], st["losses"]
    eq = [C]; log = []; n = nw = 0; peak = C; maxdd = 0.0; lo_cap = C
    n_recalc_w = n_recalc_l = 0; max_ws = max_ls = 0; stakes = []; below_min = 0; skipped = 0; bankrupt = False
    for fill, win in trades:
        if C < 1.0: bankrupt = True; break
        s = min(stake, C)
        q, shares_avail = fill(s)
        if q is None or not (isinstance(q, float) and math.isfinite(q)) or q <= 0 or q >= 1: skipped += 1; continue
        if s / q < min_shares: below_min += 1          # venue minimum order size (5 shares); still simulated, counted
        pnl = s * ((1.0 / cost(q, r_fee) - 1.0) if win else -1.0)
        C += pnl; n += 1; nw += int(win); stakes.append(s); eq.append(C)
        peak = max(peak, C); maxdd = max(maxdd, peak - C); lo_cap = min(lo_cap, C)
        if win: wins += 1; losses = 0; max_ws = max(max_ws, wins)
        else: losses += 1; wins = 0; max_ls = max(max_ls, losses)
        log.append(dict(stake=s, q=q, win=win, pnl=pnl, capital=C))
        if wins >= win_trigger: stake = frac * C; wins = losses = 0; n_recalc_w += 1
        elif losses >= loss_trigger: stake = frac * C; wins = losses = 0; n_recalc_l += 1
    res = dict(start=eq[0], end=C, pnl=C - eq[0], ret_pct=(100 * (C - eq[0]) / eq[0] if eq[0] > 0 else float("nan")), trades=n, wins=nw, losses=n - nw,
               acc=100 * nw / n if n else float("nan"), start_stake=stakes[0] if stakes else st["stake"], end_stake=stake,
               min_stake=min(stakes) if stakes else float("nan"), max_stake=max(stakes) if stakes else float("nan"),
               recalc_3w=n_recalc_w, recalc_2l=n_recalc_l, maxdd=maxdd, lowest_capital=lo_cap, max_win_streak=max_ws,
               max_loss_streak=max_ls, below_min_order=below_min, skipped_unexecutable=skipped, bankrupt=bankrupt)
    return res, dict(C=C, stake=stake, wins=wins, losses=losses), eq, log

def run_fixed(trades, r_fee, stake, start=50.0, cost_fn=None):
    cost = cost_fn or (lambda q, r: q / (1.0 - r * (1.0 - q)))   # BUY-fee semantics: win return = (1 - r(1-q))/q - 1
    C = start; n = nw = 0
    for fill, win in trades:
        q, _ = fill(stake)
        if q is None or not (isinstance(q, float) and math.isfinite(q)) or q <= 0 or q >= 1: continue
        C += stake * ((1.0 / cost(q, r_fee) - 1.0) if win else -1.0); n += 1; nw += int(win)
    return dict(pnl=C - start, trades=n, acc=100 * nw / n if n else float("nan"))
