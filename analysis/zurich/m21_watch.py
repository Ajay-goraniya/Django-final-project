#!/usr/bin/env python3
"""Cron twin of the watcher's M21 mark: writes .candles200.alerted the first time the probe reaches
200 DISTINCT graded candles, and logs it. READ-ONLY on the probe db. Exists so the mark survives
my session ending - the in-session watcher alone would miss it."""
import os, sqlite3, time
DB = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
FLAG = '/home/ubuntu/maker_probe/.candles200.alerted'
LOG = '/home/ubuntu/maker_probe/m21.log'
BAR = 200
d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
n = d.execute('select count(distinct epoch) from fills where pnl is not null').fetchone()[0]
if n >= BAR and not os.path.exists(FLAG):
    open(FLAG, 'w').write(str(n))
    with open(LOG, 'a') as f:
        f.write(f'[{time.strftime("%F %T", time.gmtime())}] M21 MARK REACHED: {n} distinct graded '
                f'candles. Run the OOS evaluation on fills after 10-02 10:27 UTC.\n')
