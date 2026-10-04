"""Standalone Polymarket market-channel probe. Run BESIDE the engine, never inside it.
Subscribes to the current 5-min BTC candle's UP/DOWN tokens and prints, once per second,
the max inter-event gap per token and the now-minus-venue-timestamp lag in that second.
Usage: venv/bin/python analysis/aws/ws_gap_probe.py [seconds=300]  (run from learner/v12_2 so the runner module imports)
"""
import asyncio, json, time, collections, sys, websockets
sys.path.insert(0,'.')
from btc_model_v10_runner import http_json, GAMMA, POLY_WS
DUR=int(sys.argv[1]) if len(sys.argv)>1 else 300
def tokens(ep):
    data=http_json(GAMMA.format(ep))
    ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
    if not ms: return []
    t=ms[0]['clobTokenIds']; t=json.loads(t) if isinstance(t,str) else t
    return [str(x) for x in t]
async def main():
    t_end=time.time()+DUR
    while time.time()<t_end:
        ep=int(time.time()//300)*300; toks=tokens(ep)+tokens(ep+300)
        if not toks: await asyncio.sleep(2); continue
        last={}; sec=collections.defaultdict(lambda: dict(n=0,maxgap=0.,maxlag=0.))
        print(f'# epoch {ep} tokens {[t[:8] for t in toks]}',flush=True)
        try:
            async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
                await w.send(json.dumps({'assets_ids':toks,'type':'market'}))
                cur=int(time.time())
                while time.time()<min(t_end,ep+300):
                    try: msg=await asyncio.wait_for(w.recv(),5)
                    except asyncio.TimeoutError: await w.send('PING'); continue
                    if msg=='PONG': continue
                    now=time.time()
                    if int(now)!=cur:
                        for s in sorted(sec):
                            r=sec[s]; print(f'{s} sec_into_candle={s-ep} events={r["n"]} maxgap_ms={r["maxgap"]*1000:.0f} maxlag_ms={r["maxlag"]*1000:.0f}',flush=True)
                        sec.clear(); cur=int(now)
                    for ev in (json.loads(msg) if msg.startswith('[') else [json.loads(msg)]):
                        lag=now-float(ev['timestamp'])/1000; r=sec[cur]; r['n']+=1; r['maxlag']=max(r['maxlag'],lag)
                        for cc in ev.get('price_changes',[ev]):
                            a=str(cc.get('asset_id'))
                            if a in last: r['maxgap']=max(r['maxgap'],now-last[a])
                            last[a]=now
        except Exception as e: print('# reconnect',type(e).__name__,flush=True); await asyncio.sleep(1)
asyncio.run(main())
