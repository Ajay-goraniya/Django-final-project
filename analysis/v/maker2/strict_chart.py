#!/usr/bin/env python3
"""Chart for M5: account from $100 at $10 per fill with NO ruin stop (so every day is visible), strict vs loosest, ruin line marked."""
import sys, runpy, io, contextlib, datetime as dt, numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as mdates
S = sys.argv[1]
sys.argv = ['x', '--tape', f'{S}/hist/lean*.json.gz,{S}/wallets_raw.json.gz,{S}/fresh48/fresh_tape.json.gz',
            '--bn', f'{S}/hist/bin1s_0911_0926.json,{S}/bin1s_48h.json,{S}/fresh48/bin1s_fresh.json', '--out', f'{S}/nr2']
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path('analysis/v/maker2/strict_pfav.py')
res = g['res']
fig, ax = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True, gridspec_kw={'height_ratios': [3, 1.2]})
for key, lab, col, lw in ((('tape', 'fixed0.304', 'thru', 0.01), 'STRICT: trade-through fill, +1c slippage, calm < 0.304', '#1f6feb', 1.8),
                          (('tape', 'causal', 'thru', 0.01), 'STRICT + causal calm cut (no look-ahead)', '#8250df', 1.2),
                          (('tape', 'fixed0.304', 'touch', 0.0), 'LOOSEST: touch fill, no slippage', '#9aa4b2', 1.0)):
    f = sorted((r for r in res[key][0] if r[key[2]]), key=lambda r: r['e'])
    x = [(10 / (r['b'] + key[3]) - 10) if r['win'] else -10.0 for r in f]
    t = [dt.datetime.fromtimestamp(r['e'], dt.timezone.utc) for r in f]; q = 100 + np.cumsum(x)
    ax[0].plot(t, q, color=col, lw=lw, label=f'{lab}  (end {q[-1]:+.0f})')
    if key[1] == 'fixed0.304' and key[2] == 'thru':
        pk = np.maximum.accumulate(np.r_[100, q])[1:]
        ax[0].fill_between(t, q, pk, color='#d1242f', alpha=0.18, label='drawdown from peak (strict)')
        ax[1].fill_between(t, 0, -(pk - q), color='#d1242f', alpha=0.6)
ax[0].axhline(100, color='k', lw=0.7, ls='--', label=r'\$100 start'); ax[0].axhline(10, color='#d1242f', lw=1.2, ls=':', label=r'\$10 = account can no longer place a \$10 trade')
ax[0].axvspan(dt.datetime(2026, 9, 26, 0, 0, tzinfo=dt.timezone.utc), dt.datetime(2026, 9, 28, 21, tzinfo=dt.timezone.utc), color='#f2cc60', alpha=0.25, label='09-26..28: where the idea was found')
ax[0].set_ylabel(r'account \$ (\$10 per trade, no ruin stop)'); ax[1].set_ylabel('drawdown $')
ax[0].set_title('Passive FAV, calm markets - strict backtest 09-11..09-30 (5,584 candles, public Polymarket tape, venue settlement)')
ax[0].legend(loc='lower left', fontsize=8); ax[1].xaxis.set_major_locator(mdates.DayLocator(interval=2)); ax[1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
fig.tight_layout(); fig.savefig('analysis/v/maker2/STRICT_PFAV_CALM.png', dpi=110); print('ok')
