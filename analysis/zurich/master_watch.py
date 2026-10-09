#!/usr/bin/env python3
"""Read-only watch on master / stake / the LIVE order count.

WHY THIS EXISTS. On 09-28 master was armed by someone other than me at ~19:40 and disarmed by ~20:12,
and 11 real orders went out. Nothing noticed. It surfaced only because a lane-breakdown query happened
to run for an unrelated health check, hours later. V's standing instruction is "no poke needed unless
master changes again" - which is only a workable instruction if something is actually watching.

So this records, once a minute, the three facts that would have caught it, and appends a line ONLY when
one of them changes. Steady state writes nothing, so the log is a pure change history.

STRICTLY READ-ONLY on the engine database: opened mode=ro, and it must stay that way. It never writes
master, never writes stake, never places or cancels anything. Arming or disarming master is the owner's
or V's call in writing - and that cuts both ways, so this does not "helpfully" turn anything off either.
It observes and it tells the truth about what it saw.
"""
import json, os, sqlite3, sys, time

DB    = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
STATE = '/home/ubuntu/pm_ef3/master_watch.json'
LOG   = '/home/ubuntu/pm_ef3/master_watch.log'


def snapshot():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        meta = dict(c.execute("SELECT k, v FROM meta WHERE k IN ('master','next_stake')").fetchall())
        n_live, first, last = c.execute(
            "SELECT count(*), min(ts), max(ts) FROM orders WHERE lane='LIVE'").fetchone()
        return dict(master=meta.get('master'), next_stake=meta.get('next_stake'),
                    n_live=int(n_live or 0), live_first=first, live_last=last)
    finally:
        c.close()


def main():
    now = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    try:
        cur = snapshot()
    except Exception as e:
        # A read failure is itself worth one line - a silent watcher is the thing we are fixing.
        with open(LOG, 'a') as f:
            f.write(f'{now}Z  READ-FAILED  {type(e).__name__}: {e}\n')
        return 1

    prev = None
    if os.path.exists(STATE):
        try:
            prev = json.load(open(STATE))
        except Exception:
            prev = None

    if prev is None:
        with open(LOG, 'a') as f:
            f.write(f'{now}Z  BASELINE  {json.dumps(cur, sort_keys=True)}\n')
    else:
        changed = [k for k in ('master', 'next_stake', 'n_live') if prev.get(k) != cur.get(k)]
        if changed:
            bits = '  '.join(f'{k}: {prev.get(k)!r} -> {cur.get(k)!r}' for k in changed)
            tag = 'MASTER-CHANGED' if 'master' in changed else \
                  'LIVE-ORDERS' if 'n_live' in changed else 'STAKE-CHANGED'
            with open(LOG, 'a') as f:
                f.write(f'{now}Z  {tag}  {bits}\n')

    tmp = STATE + '.tmp'
    json.dump(cur, open(tmp, 'w'), sort_keys=True)
    os.replace(tmp, STATE)   # atomic, so a kill mid-write cannot corrupt the baseline
    return 0


if __name__ == '__main__':
    sys.exit(main())
