# Read-only: reproduce ws_gap_probe's EXACT maxgap logic, but record which asset_id produced each
# gap and whether it was subscribed. No engine, no orders.
import asyncio, json, time, collections, sys, websockets
sys.path.insert(0,'.')
from btc_model_v10_runner import http_json, GAMMA, POLY_WS
def tokens(ep):
    d=http_json(GAMMA.format(ep))
    ms=[m for e in d for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
    if not ms: return []
    t=ms[0]['clobTokenIds']; t=json.loads(t) if isinstance(t,str) else t
    return [str(x) for x in t]
async def main():
    ep=int(time.time()//300)*300; subs=set(tokens(ep)+tokens(ep+300))
    print(f"subscribed={len(subs)} tokens")
    t_end=time.time()+60; last={}; seen=collections.Counter(); big=collections.Counter(); bigsub=collections.Counter()
    async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
        await w.send(json.dumps({'assets_ids':sorted(subs),'type':'market'}))
        while time.time()<t_end:
            try: msg=await asyncio.wait_for(w.recv(),5)
            except asyncio.TimeoutError: await w.send('PING'); continue
            if msg=='PONG': continue
            now=time.time()
            for ev in (json.loads(msg) if msg.startswith('[') else [json.loads(msg)]):
                for cc in ev.get('price_changes',[ev]):
                    a=str(cc.get('asset_id')); seen[a]+=1
                    if a in last and (now-last[a])*1000>750:
                        big[a]+=1; bigsub['SUBSCRIBED' if a in subs else 'FOREIGN']+=1
                    last[a]=now
    print(f"distinct asset_ids seen = {len(seen)}  (subscribed {len([a for a in seen if a in subs])}, foreign {len([a for a in seen if a not in subs])})")
    print(f"events on subscribed = {sum(v for a,v in seen.items() if a in subs)}, on foreign = {sum(v for a,v in seen.items() if a not in subs)}")
    print(f">750ms gap occurrences: {dict(bigsub)}")
    print("top gap-producing assets:", [(a[:8], 'SUB' if a in subs else 'FOR', c) for a,c in big.most_common(5)])
asyncio.run(main())
