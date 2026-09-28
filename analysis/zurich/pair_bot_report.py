#!/usr/bin/env python3
"""What V's pair_bot.py did in PAPER on Zurich, and whether my own scan sees the same windows. READ-ONLY.

pair_bot is V's code at learner/v12_2/pair_bot.py, audited before starting and not modified: the order path
sits behind `self.live = bool(a.live and a.owner_confirmed)`, neither flag was passed, so every row below is
PAPER and no order can have been sent. It runs on its own sqlite and its own log, separate from the engine,
the recorder and the ms probe.

Comparison target: arb_windows.csv, which is the recorder + tape1s scan with the 15 s snapshot-age gate from
the 09-28 correction. Three independent implementations read the same two markets here - pair_bot's own WS,
my recorder, and the ms probe - so where they disagree is as informative as where they agree.
"""
import sys, csv, sqlite3, subprocess, time, datetime as dt, collections, numpy as np

PAIR = '/home/ubuntu/pm_pair/pair_paper.sqlite3'
CSV = '/home/ubuntu/claude-work/repo/analysis/zurich/arb_windows.csv'
f = lambda x: dt.datetime.fromtimestamp(int(x), dt.timezone.utc).strftime('%m-%d %H:%M')

c = sqlite3.connect(f'file:{PAIR}?mode=ro', uri=True); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute('SELECT * FROM pairs ORDER BY ts')]
if not rows:
    print('pair_bot has detected no pair yet'); sys.exit(0)
t0, t1 = min(r['ts'] for r in rows), max(r['ts'] for r in rows)
modes = collections.Counter(r['mode'] for r in rows)
print(f'pair_bot PAPER: {len(rows)} pairs, {f(t0)} -> {f(t1)}, modes {dict(modes)}')
assert set(modes) <= {'PAPER'}, 'a non-PAPER row exists - stop and report'

cost = np.array([r['cost'] for r in rows], float)
sh = np.array([r['shares'] for r in rows], float)
print(f'\n(1) PAIRS PER WINDOW: {len(rows)} pairs across {len({r["T"] for r in rows})} distinct 15m windows '
      f'(max {max(collections.Counter(r["T"] for r in rows).values())} in any one window)')
print(f'(2) COST: p10 {np.percentile(cost,10):.4f}  p50 {np.percentile(cost,50):.4f}  '
      f'p90 {np.percentile(cost,90):.4f}  min {cost.min():.4f}  max {cost.max():.4f}')
print(f'(3) SHARES: p10 {np.percentile(sh,10):.0f}  p50 {np.percentile(sh,50):.0f}  '
      f'max {sh.max():.0f}; both legs PAPER_FILL on '
      f'{sum(1 for r in rows if r["st15"]=="PAPER_FILL" and r["st5"]=="PAPER_FILL")}/{len(rows)}')

print(f'\n(4) SETTLED PAYOFF - 0 per share-pair would mean the dominance structure is broken')
st = [r for r in rows if r['payout'] is not None and r['out15'] and r['out5']]
if not st: print('    nothing settled yet')
else:
    pp = collections.Counter(round(r['payout'] / r['shares']) for r in st)
    print(f'    settled {len(st)}/{len(rows)}; payoff per share-pair {dict(pp)}'
          + ('   <- 0 PRESENT, investigate' if 0 in pp else '   <- no zero, structure held'))
    tot_sp = sum(r['spent15'] + r['spent5'] for r in st); tot_pn = sum(r['pnl'] for r in st)
    print(f'    spent {tot_sp:.2f}, payout {sum(r["payout"] for r in st):.2f}, pnl {tot_pn:+.4f}, '
          f'per $1 {tot_pn/tot_sp if tot_sp else 0:+.4f}'
          + ('  *n<60, not a reading' if len(st) < 60 else ''))
    for r in st:
        print(f'    {f(r["T"])}  sec {r["sec"]:3d}  {r["leg15"]}+{r["leg5"]}  {r["a15"]:.3f}+{r["a5"]:.3f} '
              f'cost {r["cost"]:.4f} x{r["shares"]:.0f}  settled {r["out15"]}/{r["out5"]}  '
              f'payoff {r["payout"]/r["shares"]:.0f}  pnl {r["pnl"]:+.4f}  gap {r["L15"]-r["L5"]:+.2f}')

print(f'\n(5) THE SAME HOURS IN MY OWN SCAN (arb_windows.csv, 15 s snapshot-age gate)')
try: mine = list(csv.DictReader(open(CSV)))
except Exception as e: print(f'    cannot read {CSV}: {e}'); sys.exit(0)
def bot_start():
    """pair_bot's whole RUNNING period, not just the windows it fired on - otherwise "mine only" is vacuous.
    argv[1] overrides; otherwise take the live process's elapsed time, else fall back to the first pair."""
    if len(sys.argv) > 1: return int(sys.argv[1])
    for pid in subprocess.run(['pgrep', '-f', 'pair_bot[.]py'], capture_output=True, text=True
                              ).stdout.split():
        e = subprocess.run(['ps', '-o', 'etimes=', '-p', pid], capture_output=True, text=True).stdout.strip()
        if e.isdigit(): return int(time.time()) - int(e)
    return int(min(r['T'] for r in rows))

lo = bot_start() // 900 * 900; hi = int(time.time()) // 900 * 900 - 900
mw = {int(x['ep15']): x for x in mine if lo <= int(x['ep15']) <= hi}
pw = {int(r['T']): r for r in rows}
both = sorted(set(mw) & set(pw)); only_m = sorted(set(mw) - set(pw)); only_p = sorted(set(pw) - set(mw))
print(f'    pair_bot window span {f(lo)} -> {f(hi)}; my scan has {len(mw)} riskless windows in it')
print(f'    BOTH {len(both)}: ' + ', '.join(f(e) for e in both))
for e in both:
    print(f'      {f(e)}  pair_bot {pw[e]["leg15"]}+{pw[e]["leg5"]} cost {pw[e]["cost"]:.4f} at sec {pw[e]["sec"]}'
          f'  |  mine {mw[e]["leg15"]}+{mw[e]["leg5"]} cost {mw[e]["cost"]} best {mw[e]["best_cost"]} '
          f'at sec {mw[e]["sec"]}, {mw[e]["n_riskless_secs"]} riskless s, gap {mw[e]["gap"]}'
          + ('   LEGS DISAGREE' if (pw[e]['leg15'], pw[e]['leg5']) != (mw[e]['leg15'], mw[e]['leg5']) else ''))
print(f'    MINE ONLY {len(only_m)}: ' + ', '.join(
    f'{f(e)} (cost {mw[e]["cost"]}, {mw[e]["n_riskless_secs"]} s, gap {mw[e]["gap"]})' for e in only_m))
print(f'    PAIR_BOT ONLY {len(only_p)}: ' + ', '.join(
    f'{f(e)} (cost {pw[e]["cost"]:.4f} at sec {pw[e]["sec"]})' for e in only_p))
print('\n    A window in one list and not the other is not a contradiction by itself: these costs sit within a '
      'cent of 1.000,\n    so a single tick on either leg, or a few hundred ms of timing, moves a window across '
      'the line. What matters is\n    whether the LEGS agree where both fire, and whether any settled payoff is 0.')
