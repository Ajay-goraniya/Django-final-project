#!/usr/bin/env python3
"""Owner's PnL chart (V, 10-02): cumulative real PnL of the Zurich maker probe by fill time, peak and low marked, UTC sessions
shaded. usage: probe_pnl_chart.py <fills.csv> <out.html> [tab title] [title] [subtitle] [band label]"""
import sys, csv, json, datetime
rows = list(csv.DictReader(open(sys.argv[1])))
pts, cum = [], 0.0
for r in rows:
    cum += float(r['pnl_usd'])
    pts.append(dict(t=r['fill_ts_utc'], v=round(cum, 2), p=round(float(r['pnl_usd']), 2), side=r.get('side', ''),
                    price=r.get('price', ''), won=r.get('won', ''), s=r.get('session', '')))
hi = max(range(len(pts)), key=lambda i: pts[i]['v']); lo = min(range(len(pts)), key=lambda i: pts[i]['v'])
day = {}
for r in rows:
    d = r['fill_ts_utc'][:10]; day.setdefault(d, [0, 0.0]); day[d][0] += 1; day[d][1] += float(r['pnl_usd'])
ses = {}
for r in rows:
    s = r.get('session', '?'); ses.setdefault(s, [0, 0, 0.0]); ses[s][0] += 1; ses[s][1] += int(r.get('won') or 0); ses[s][2] += float(r['pnl_usd'])
html = open(__file__.replace('.py', '_template.html')).read()
html = html.replace('__DATA__', json.dumps(pts)).replace('__HI__', str(hi)).replace('__LO__', str(lo))
A = sys.argv + [None] * 6
html = (html.replace('__TAB__', A[3] or 'Maker PnL Curve').replace('__TITLE__', A[4] or 'Maker test — real PnL, fill by fill')
        .replace('__SUB__', A[5] or 'Zurich maker probe, real money, cumulative $ after each graded fill (UTC). Shaded = 00:00–13:00 UTC (Asia + Europe).')
        .replace('__BAND__', A[6] or '00–13 UTC'))
html = html.replace('__DAYS__', json.dumps(day)).replace('__SES__', json.dumps(ses))
open(sys.argv[2], 'w').write(html)
print(f'{len(pts)} fills; final {pts[-1]["v"]:+.2f}; peak {pts[hi]["v"]:+.2f} at {pts[hi]["t"]}; low {pts[lo]["v"]:+.2f} at {pts[lo]["t"]}')
