"""Per-event venue-timestamp lag (now - ev.timestamp) on the ACTIVE candle's two tokens only.
Prints a histogram at the end. Question: does the venue stamp lag our wall clock by >0.75 s / >2 s
often enough to explain the census's 28.5% 'stale 2-5 s' cells via quote()'s wall-clock clamp?"""
import sys,os,json,time,asyncio,collections

sys.path.insert(0,'/home/user/Django-final-project/learner/v12_2')
import websockets
from btc_model_v10_runner import http_json, GAMMA, POLY_WS
DUR=int(sys.argv[1]) if len(sys.argv)>1 else 150
def tokens(ep):
    data=http_json(GAMMA.format(ep))
    ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
    if not ms: return []
    t=ms[0]['clobTokenIds']; t=json.loads(t) if isinstance(t,str) else t
    return [str(x) for x in t]
BUCK=[(-1e9,0),(0,0.1),(0.1,0.25),(0.25,0.75),(0.75,1),(1,2),(2,5),(5,8),(8,1e9)]
async def main():
    t_end=time.time()+DUR; lags=collections.defaultdict(list); gaps=collections.defaultdict(list)
    while time.time()<t_end:
        ep=int(time.time()//300)*300; act=tokens(ep)
        if not act: await asyncio.sleep(2); continue
        last={}
        try:
            async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
                await w.send(json.dumps({'assets_ids':act,'type':'market'}))
                while time.time()<min(t_end,ep+300):
                    try: msg=await asyncio.wait_for(w.recv(),5)
                    except asyncio.TimeoutError: await w.send('PING'); continue
                    if msg=='PONG': continue
                    now=time.time()
                    for ev in (json.loads(msg) if msg.startswith('[') else [json.loads(msg)]):
                        k=ev.get('event_type'); lag=now-float(ev['timestamp'])/1000
                        lags[k].append(lag)
                        for cc in ev.get('price_changes',[ev]):
                            a=str(cc.get('asset_id'))
                            if a in last: gaps[a].append(now-last[a])
                            last[a]=now
        except Exception as e: print('# reconnect',type(e).__name__,flush=True); await asyncio.sleep(1)
    def q(v,p): v=sorted(v); return v[min(len(v)-1,int(p*len(v)))] if v else float('nan')
    for k,v in lags.items():
        print(f'{k}: n={len(v)} p50={q(v,.5)*1000:.0f}ms p90={q(v,.9)*1000:.0f}ms p99={q(v,.99)*1000:.0f}ms max={max(v)*1000:.0f}ms  share>0.75s={sum(x>0.75 for x in v)/len(v):.3%} share>2s={sum(x>2 for x in v)/len(v):.3%}')
        print('   hist',{f'{lo}-{hi}':sum(lo<=x<hi for x in v) for lo,hi in BUCK})
    for a,v in gaps.items():
        print(f'gap {a[:8]}: n={len(v)} p50={q(v,.5)*1000:.0f}ms p99={q(v,.99)*1000:.0f}ms max={max(v)*1000:.0f}ms share>2s={sum(x>2 for x in v)/len(v):.3%}')
asyncio.run(main())
