#!/usr/bin/env python3
"""The user's hybrid staking WITH the real bounds: stake is clamped to
[$1, $50]. 10% of available capital, recomputed only on a 3-win or 2-loss
streak, then clamped. Without the clamp the rule compounds to numbers the
order book could never absorb; with it the stake tops out at $50."""
import math

def run_capped(trades, r_fee, start=50.0, frac=0.10, win_trigger=3, loss_trigger=2,
               stake_min=1.0, stake_max=50.0, cost_fn=None):
    cost = cost_fn or (lambda q, r: q / (1.0 - r * (1.0 - q)))
    clamp = lambda s: min(stake_max, max(stake_min, s))
    C = start; stake = clamp(frac * start); wins = losses = 0
    eq = [C]; n = nw = 0; peak = C; maxdd = 0.0; lo = C
    stakes = []; rw = rl = 0; mws = mls = 0; skipped = 0; bankrupt = False
    for fill, win in trades:
        if C < stake_min:
            bankrupt = True; break
        s = min(stake, C)
        q, _sh = fill(s)
        if q is None or not math.isfinite(q) or not 0 < q < 1:
            skipped += 1; continue
        pnl = s * ((1.0 / cost(q, r_fee) - 1.0) if win else -1.0)
        C += pnl; n += 1; nw += int(win); stakes.append(s); eq.append(C)
        peak = max(peak, C); maxdd = max(maxdd, peak - C); lo = min(lo, C)
        if win: wins += 1; losses = 0; mws = max(mws, wins)
        else:   losses += 1; wins = 0; mls = max(mls, losses)
        if wins >= win_trigger:   stake = clamp(frac * C); wins = losses = 0; rw += 1
        elif losses >= loss_trigger: stake = clamp(frac * C); wins = losses = 0; rl += 1
    return dict(start=start, end=C, pnl=C - start,
                ret_pct=100 * (C - start) / start, trades=n, wins=nw,
                acc=100 * nw / n if n else float("nan"),
                min_stake=min(stakes) if stakes else float("nan"),
                max_stake=max(stakes) if stakes else float("nan"),
                avg_stake=sum(stakes) / len(stakes) if stakes else float("nan"),
                maxdd=maxdd, lowest=lo, peak=peak, recalc_3w=rw, recalc_2l=rl,
                max_win_streak=mws, max_loss_streak=mls,
                skipped=skipped, bankrupt=bankrupt, equity=eq)
