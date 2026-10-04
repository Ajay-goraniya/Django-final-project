"""Split RAW's London-execution loss into missed fills on winners vs slippage, per $1. READ-ONLY.

The two components of analysis/v/rawfixed/LONDON_EXEC_MODEL.md are turned on one at a time on the
SAME fires, so the pieces are marginals of one model rather than three separate models:

  (a) Bernoulli fill, P(fill|win) 54.1% vs P(fill|lose) 65.0%
  (b) slippage, cents p10/p50/p90 = -1/+2/+11 on the ask actually paid

(a) is really two different costs and they are separated here, because only the second is a real edge
loss. Random subsampling deploys less capital but does not change per$1 in expectation; it is the
ASYMMETRY (winners filling less often than losers) that is adverse selection. So (a) is run twice:
once symmetric at the blended rate 155/263 = 58.9%, once at London's two real rates. The gap between
those two is the missed-fills-on-winners cost. The components do not add exactly - slippage is paid
only on filled trades - so the interaction term is printed rather than hidden.
"""
import random, statistics as st, sys
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from raw_vs_fixed_london_exec import load, draw_slip, bucket, SLIP, STAKE, RUNS

P_WIN, P_LOSE = 79/146, 76/117
P_SYM = (79 + 76) / (146 + 117)

def run(fires, rng, fill, slip):
    """fill in {None,'sym','asym'}; slip bool. Returns (pnl, cost, n_filled)."""
    pnl = cost_tot = 0.; k = 0
    for fr in fires:
        q = fr['ask']
        if fill == 'sym' and rng.random() > P_SYM: continue
        if fill == 'asym' and rng.random() > (P_WIN if fr['win'] else P_LOSE): continue
        price = min(0.99, max(0.01, q + draw_slip(rng, SLIP))) if slip else q
        sh = STAKE / price; cost = STAKE + 0.07 * sh * price * (1 - price)
        pnl += (sh if fr['win'] else 0.) - cost; cost_tot += cost; k += 1
    return pnl, cost_tot, k

def summarise(fires, fill, slip, runs):
    o = [run(fires, random.Random(2000 + i), fill, slip) for i in range(runs)]
    pnl = st.mean([x[0] for x in o]); cost = st.mean([x[1] for x in o])
    return pnl, (pnl / cost if cost else 0.), st.mean([x[2] for x in o]), cost

if __name__ == '__main__':
    cands = load()
    for arm in ('RAW', 'FIXED'):
        fires = [c['fire'][arm] for c in sorted((c for c in cands.values() if arm in c['fire']),
                                                key=lambda c: c['fire'][arm]['ts'])]
        print(f'\n=== {arm}: {len(fires)} fires, stake ${STAKE:.0f} ===')
        print(f"{'arm':<40}{'fills':>7}{'deployed':>10}{'totPnL':>10}{'per$1':>9}")
        rows = {}
        for lbl, fill, slip, runs in (
                ('0 paper: fill all, no slippage', None, False, 1),
                ('1 + symmetric fill 58.9% only', 'sym', False, RUNS),
                ("2 + London's asymmetric fill only", 'asym', False, RUNS),
                ('3 + slippage only, fill all', None, True, RUNS),
                ('4 full London execution (2+3)', 'asym', True, RUNS)):
            pnl, per1, k, cost = summarise(fires, fill, slip, runs)
            rows[lbl[0]] = (pnl, per1, k)
            print(f'{lbl:<40}{k:>7.0f}{cost:>10.0f}{pnl:>+10.2f}{per1:>+9.4f}')
        p0, p1, p2, p3, p4 = (rows[k][1] for k in '01234')
        print(f'  per$1 attribution, from paper {p0:+.4f} to full execution {p4:+.4f} '
              f'({p4-p0:+.4f} total):')
        print(f'    fewer trades at random (symmetric fill)   {p1-p0:+.4f}   <- capital, not edge')
        print(f'    MISSED FILLS ON WINNERS (the asymmetry)   {p2-p1:+.4f}')
        print(f'    SLIPPAGE alone, on every fire             {p3-p0:+.4f}')
        print(f'    interaction (slippage only on fills)      {(p4-p0)-(p2-p0)-(p3-p0):+.4f}')
