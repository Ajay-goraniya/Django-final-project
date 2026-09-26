# Read-only diagnostic: same socket/subscription as ws_gap_probe, but records gaps PER TOKEN
# and labels each token ACTIVE (current candle) vs NEXT (next candle). No engine, no orders.
import asyncio, json, time, collections, sys, websockets
sys.path.insert(0,'.')
from btc_model_v10_runner import http_json, GAMMA, POLY_WS
DUR=int(sys.argv[1]) if len(sys.argv)>1 else 180
def tokens(ep):
    data=http_json(GAMMA.format(ep))
    ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
    if not ms: return []
    t=ms[0]['clobTokenIds']; t=json.loads(t) if isinstance(t,str) else t
    return [str(x) for x in t]
async def main():
    t_end=time.time()+DUR; gaps=collections.defaultdict(list); role={}; cnt=collections.Counter()
    while time.time()<t_end:
        ep=int(time.time()//300)*300
        a=tokens(ep); n=tokens(ep+300)
        for t in a: role[t]='ACTIVE'
        for t in n: role.setdefault(t,'NEXT')
        toks=a+n
        if not toks: await asyncio.sleep(2); continue
        last={}
        async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
            await w.send(json.dumps({'assets_ids':toks,'type':'market'}))
            while time.time()<min(t_end,ep+300):
                try: msg=await asyncio.wait_for(w.recv(),5)
                except asyncio.TimeoutError: await w.send('PING'); continue
                if msg=='PONG': continue
                now=time.time()
                for ev in (json.loads(msg) if msg.startswith('[') else [json.loads(msg)]):
                    for cc in ev.get('price_changes',[ev]):
                        k=str(cc.get('asset_id'))
                        if k not in role: continue
                        cnt[k]+=1
                        if k in last: gaps[k].append((now-last[k])*1000)
                        last[k]=now
    print(f"{'token':10} {'role':7} {'n':>7} {'p50':>7} {'p90':>7} {'p99':>7} {'max':>8} {'%>750ms':>8}")
    agg=collections.defaultdict(list)
    for k,v in gaps.items():
        s=sorted(v); p=lambda q:s[int(round((len(s)-1)*q))]
        agg[role[k]].extend(v)
        print(f"{k[:8]:10} {role[k]:7} {len(s):7d} {p(.5):7.0f} {p(.9):7.0f} {p(.99):7.0f} {s[-1]:8.0f} {100*sum(1 for x in s if x>750)/len(s):7.1f}%")
    for r,v in agg.items():
        s=sorted(v); p=lambda q:s[int(round((len(s)-1)*q))]
        print(f"ALL-{r:6} {'':7} {len(s):7d} {p(.5):7.0f} {p(.9):7.0f} {p(.99):7.0f} {s[-1]:8.0f} {100*sum(1 for x in s if x>750)/len(s):7.1f}%")
asyncio.run(main())
