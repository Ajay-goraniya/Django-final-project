"""Zurich ledger: EF (build11) as its own line beside EF (v10)'s paper record, plus MAIN and REVERSAL.

Every line is read-only from the live4 journal and graded on results.actual (Polymarket's own oracle,
which this lane's `actual` column matches). An order belongs to build11 when its EF signal's decision
JSON carries engine='build11'; everything else EF is v10. per$1 = shadow pnl / spent-including-fees.
"""
import sqlite3, json, sys, datetime as dt
DB = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
eng = {}
for s in c.execute("SELECT epoch,decision FROM signals WHERE kind='EF' AND decision IS NOT NULL"):
    try: eng[s['epoch']] = (json.loads(s['decision']) or {}).get('engine') or 'v10'
    except Exception: eng[s['epoch']] = 'v10'
V10_RESTORE = 1790115479.0   # 22:17:59 UTC 09-22, audited ef_engine build11 -> v10
rows = c.execute("""SELECT o.epoch,o.kind,o.lane,o.plan,o.ts,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe
                    FROM orders o JOIN fills f ON f.order_id=o.id
                    WHERE o.status='FILLED' GROUP BY o.id""").fetchall()
lines = {}
for r in rows:
    a = res.get(r['epoch'])
    if a is None: continue                                   # not graded yet
    side = (json.loads(r['plan']) or {}).get('side') or (c.execute(
        "SELECT side FROM signals WHERE epoch=? AND kind=? LIMIT 1", (r['epoch'], r['kind'])).fetchone() or [None])[0]
    if side is None: continue
    if r['kind'] != 'EF': name = r['kind']
    elif eng.get(r['epoch']) == 'build11': name = 'EF (build11)'
    elif r['ts'] >= V10_RESTORE: name = 'EF (v10 restored)'
    else: name = 'EF (v10)'
    L = lines.setdefault(name, dict(n=0, w=0, cost=0., payout=0., lanes=set()))
    cost = (r['sp'] or 0.) + (r['fe'] or 0.); win = (side == a)
    L['n'] += 1; L['w'] += win; L['cost'] += cost; L['payout'] += (r['sh'] or 0.) if win else 0.
    L['lanes'].add(r['lane'])
print(f"# Zurich live4 ledger  {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC   graded on results.actual")
print(f"{'line':<18} {'n':>4} {'hit':>7} {'spent':>9} {'pnl':>9} {'per$1':>8}  lane")
for k in ('EF (v10)', 'EF (v10 restored)', 'EF (build11)', 'MAIN', 'REVERSAL'):
    L = lines.get(k)
    if not L: print(f"{k:<18} {0:>4} {'-':>7} {'-':>9} {'-':>9} {'-':>8}  -"); continue
    pnl = L['payout'] - L['cost']
    print(f"{k:<18} {L['n']:>4} {L['w']/L['n']*100:>6.1f}% {L['cost']:>9.2f} {pnl:>+9.3f} "
          f"{pnl/L['cost'] if L['cost'] else 0:>+8.3f}  {'/'.join(sorted(L['lanes']))}"
          f"{'  * insufficient (n<60)' if L['n'] < 60 else ''}")
tot = c.execute('SELECT count(*),coalesce(sum(shadow_pnl),0),coalesce(sum(pnl),0) FROM results').fetchone()
try: tape = c.execute('SELECT count(*),max(ts)-min(ts) FROM tape1s').fetchone()
except Exception: tape = (0, 0)
print('* a line under 60 graded fires is not a reading. Do not quote its per$1 as a result.')
print(f"results n={tot[0]} sum(shadow_pnl)={tot[1]:+.4f} sum(pnl)={tot[2]:+.4f} | tape1s rows={tape[0]} span={tape[1] or 0:.0f}s")

# ---- 12.24.1: what the Platt calibration removed (V, 09-22 22:4x) ----------------------------
# EF decide rows carry p_raw and calibrated=true once _calibrate lowers a claim. The EF fire rule is
# EV > 0 against the padded break-even, and `ev` in the row is already computed from the CALIBRATED p,
# so ev_raw = ev + (p_raw - p). A fire "calibration removed" is one that clears on raw and not on
# calibrated. Counted only from CAL_ON, and reported with the rows that had no p_raw at all.
CAL_ON = 1790116840.0        # 22:40:40 UTC 09-22, audited calibration None -> platt a=1.0677 b=-0.3208
tot = seen = removed = added = 0
shrink = []
for (d,) in c.execute('SELECT detail FROM diagnostics WHERE ts>=? ', (CAL_ON,)):
    try: j = json.loads(d)
    except Exception: continue
    if 'breakeven' not in j or 'ev' not in j: continue          # EF decide rows only
    tot += 1
    if j.get('p_raw') is None: continue
    seen += 1; shrink.append(j['p_raw'] - j['p'])
    ev_raw = j['ev'] + (j['p_raw'] - j['p'])
    if ev_raw > 0 and j['ev'] <= 0: removed += 1
    if ev_raw <= 0 and j['ev'] > 0: added += 1
print(f"calibration since 22:40:40: EF decide rows {tot}, carrying p_raw {seen}, "
      f"fires REMOVED {removed}, fires added {added}"
      + (f", median shrink p_raw-p {sorted(shrink)[len(shrink)//2]:+.4f}" if shrink else ""))
