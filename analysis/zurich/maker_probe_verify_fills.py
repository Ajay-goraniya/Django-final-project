#!/usr/bin/env python3
"""READ-ONLY venue check for the 10-01 maker-fill blindness. Posts nothing, cancels nothing.

Needs the four venue env vars in the environment (POLYMARKET_PRIVATE_KEY, POLYMARKET_WALLET_ADDRESS,
RELAYER_API_KEY, RELAYER_API_KEY_ADDRESS) - the session that found the bug does not have them, so
this is the half of the confirmation that has to be run by V or the owner:

    cd /home/ubuntu/pm_paper_zurich && .venv/bin/python /home/ubuntu/maker_probe/verify_fills.py

It prints, for every live order this probe ever posted: whether the venue still has it OPEN, and
every account trade whose maker_orders[] names it - the nesting the old check_fill could not see.
"""
import asyncio, sqlite3, sys, time
sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
DB = '/home/ubuntu/maker_probe/maker_probe.sqlite3'


async def main():
    from poly_live import LiveBroker
    b = LiveBroker(None); await b.open()
    d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); d.row_factory = sqlite3.Row
    rows = d.execute("select id, epoch, side, token, price, shares, venue_order_id, post_ts_ms, "
                     "status, cancel_reason from orders where dry=0 and venue_order_id is not null "
                     "order by id").fetchall()
    ours = {r['venue_order_id']: r for r in rows}
    print(f'{len(ours)} live order ids in the probe db\n')

    print('--- OPEN ORDERS ON THE WALLET (ours flagged; anything else is 8787/London, leave alone) ---')
    n = 0
    async for page in b.client.list_open_orders():
        for o in page.items:
            n += 1
            mine = 'OURS' if str(o.id) in ours else 'not ours'
            print(f'  [{mine}] {o.id[:18]} {o.side} {o.price} size {o.original_size} '
                  f'matched {o.size_matched} status {o.status}')
    print(f'  total open on wallet: {n}\n')

    print('--- ACCOUNT TRADES NAMING ONE OF OUR ORDERS ---')
    for tok in sorted({r['token'] for r in rows if r['token']}):
        async for page in b.client.list_account_trades(token_id=tok):
            for t in page.items:
                hits = [m for m in t.maker_orders if str(m.order_id) in ours]
                taker = str(t.taker_order_id) in ours
                if not hits and not taker: continue
                ts = t.matched_at.strftime('%F %T')
                st = getattr(t.status, 'value', t.status)
                if taker:
                    r = ours[str(t.taker_order_id)]
                    print(f'  {ts} TAKER  row {r["id"]:3} {t.size} @ {t.price} status {st}')
                for m in hits:
                    r = ours[str(m.order_id)]
                    print(f'  {ts} MAKER  row {r["id"]:3} {m.matched_amount} @ {m.price} '
                          f'status {st} (db said {r["status"]}: {r["cancel_reason"]})')
            if not page.has_more: break
    print('\ndone', time.strftime('%F %T', time.gmtime()), 'UTC')

asyncio.run(main())
