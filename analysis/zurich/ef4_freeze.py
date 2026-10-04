#!/usr/bin/env python3
"""Freeze the EF-4 stump model as shadow arm D. Run ONCE. READ-ONLY on all engine data.

V pre-authorised this: "If it beats C on $ AND DD, pre-register it as arm D in the running shadow."
It does - EF-4gb t=0.00 S0=0 is +$164.0 / DD $75.5 / P/DD 2.17 / 4-of-4 days against C at +$16.3 / $85.3.

TWO THINGS V MUST BE ABLE TO REVERSE, so they are stated here and in the poke rather than buried:
  1. This is the STUMP model. The ridge linear was the primary and it FAILED - once the six absolute
     BTC-price columns were removed it fell from +$417 to +$116 and no longer beat C's drawdown. I ran
     two fits and am proposing the one that worked, which is itself a selection, and V should weigh it
     as such.
  2. Trained on 09-24..09-27 only, and 84% of the profit is two of the four test days (though unlike
     every other arm today the remaining days still sum POSITIVE, +$26.0).

Same freeze discipline as arm A: one fit on days < 09-28, exported with a sha256, and ef3_shadow refuses
to run if the file ever changes. No level features - they are excluded by CONSTRUCTION here, not by a
follow-up check, because that is the defect that killed the linear model.
"""
import sys, os, json, hashlib, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1
from ef3 import FITS
from ef4 import gb_reg, gb_reg_pred

OUT = '/home/ubuntu/pm_ef3/ef4_model_D.json'
LEVEL = ['_price', 'ref_open', 'ref_now', 'ref_inst', 'bn_line_open', 'bn_line_now']

if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, yw, q, day = (z[k][keep] for k in ('X', 'y', 'q', 'day'))
    names = [str(s) for s in z['names']]
    drop = {names.index(k) for k in LEVEL if k in names}
    cols = [i for i in range(len(names)) if i not in drop]
    X = X[:, cols].astype(np.float64); names = [names[i] for i in cols]
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(yw.astype(float), np.where(filled, q, 0.5)), 0.0)
    days = sorted(set(day.tolist()))
    tr = np.isin(day, days[:-1])          # 09-24..09-27, the same training span as arm A's fit #3
    print(f'training rows {tr.sum():,} on days {days[:-1]}, {len(names)} features (levels excluded)')
    mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd > 0, sd, 1.0)
    g = gb_reg((X[tr] - mu) / sd, tgt[tr])
    body = dict(trees=[[int(j), float(t), float(vl), float(vr)] for j, t, vl, vr in g['trees']],
                base=float(g['base']), mean=mu.tolist(), sd=sd.tolist(), names=names,
                rule='fire at the first pass with p_side >= 0.5 and predicted after-fill $ >= 0.00',
                threshold=0.0, sec_floor=0,
                trained_on=days[:-1], n_train=int(tr.sum()),
                note='EF-4 squared-loss stump model. Target = realised $ per $1 as executed by the '
                     '+250 ms FAK sim: 0 if no fill, per1(win, fill_price) if filled. Absolute BTC '
                     'price columns excluded by construction.')
    blob = json.dumps(body, sort_keys=True)
    body['sha256'] = hashlib.sha256(blob.encode()).hexdigest()
    body['frozen_at'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    if os.path.exists(OUT):
        raise SystemExit(f'{OUT} already exists - REFUSING to refreeze. Delete it deliberately if you '
                         f'really mean to re-register arm D.')
    json.dump(body, open(OUT, 'w'))
    print(f'froze arm D -> {OUT}  sha256 {body["sha256"][:16]}  {len(body["trees"])} stumps')
