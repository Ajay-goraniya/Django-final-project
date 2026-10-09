# M43 (V, 10-03 12:3x) owner: "what price limit orders should I put on BOTH sides at candle open to get filled?"
# Rule: at sec 0 rest a BUY limit at price b on UP and on DOWN (maker, 1 share each). A leg fills when that side's best ask <= b
# (a seller reached our price; queue ignored = optimistic). Orders rest until sec 295. Both filled -> +1-2b. One filled -> that side's
# result (1-b or -b). None -> 0. b grid 0.30..0.49 reported in full, all-day + 4 fixed sessions (UTC open): ASIA 00-07 EU 07-13 US 13-20 LATE 20-24.
# POLY = Polymarket 08-01 5 s (maker fee 0, labels = market outcome). PRED = Predict.fun book1s 09-11..16 (2% share skim, Binance close>=open).
import sqlite3, numpy as np, pandas as pd
SESS=[('ASIA',0,7),('EU',7,13),('US',13,20),('LATE',20,24)]
def evaluate(tag,rows,skim):
    df=pd.DataFrame(rows,columns=['e','mu','md','upw'])
    df['h']=pd.to_datetime(df.e,unit='s').dt.hour; df['day']=pd.to_datetime(df.e,unit='s').dt.strftime('%m-%d')
    print(f'\n== {tag}: {len(df)} candles  (per candle $ on 1 share/leg; both% = both legs filled)')
    print('   b    | ALL: both% one% pnl/candle green | '+' | '.join(f'{s}: both% pnl' for s,_,_ in SESS))
    for b in np.round(np.arange(0.30,0.50,0.02),2):
        fu=df.mu<=b; fd=df.md<=b
        pnl=np.where(fu&fd, (1-skim)-2*b, np.where(fu, np.where(df.upw,(1-skim)-b,-b), np.where(fd, np.where(~df.upw,(1-skim)-b,-b),0.0)))
        df['p']=pnl; g=df.groupby('day').p.sum()
        s=[]
        for name,a,z in SESS:
            m=(df.h>=a)&(df.h<z); s.append(f'{name}: {(fu&fd)[m].mean():4.0%} {df.p[m].mean():+.3f}')
        print(f'  {b:.2f}  | ALL: {(fu&fd).mean():4.0%} {(fu^fd).mean():4.0%} {pnl.mean():+.4f} {(g>0).sum()}/{len(g)} | '+' | '.join(s))
# POLYMARKET
p=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet'); p=p[p.has_book&(p.offset_s<=295)]
rows=[]
for e,g in p.groupby('window_epoch'):
    u=g[g.side=='UP'].best_ask.min(); d=g[g.side=='DOWN'].best_ask.min()
    if np.isnan(u) or np.isnan(d): continue
    rows.append((e,u,d,g.outcome.iloc[0]=='UP'))
evaluate('POLYMARKET 08-01',rows,0.0)
# PREDICT
c=sqlite3.connect('/tmp/book1s.sqlite3')
d=pd.read_sql('select epoch,sec,price,open,ask_up,ask_dn,book_candle from b1',c).dropna(subset=['sec'])
lab=d.sort_values(['epoch','sec']).groupby('epoch').agg(price=('price','last'),open=('open','first'),mx=('sec','max'))
lab=lab[lab.mx>=290]; upw=(lab.price>=lab.open)
d=d[(d.book_candle==d.epoch)&(d.sec<=295)]
rows=[(e,g.ask_up.min(),g.ask_dn.min(),bool(upw[e])) for e,g in d.groupby('epoch') if e in upw.index and len(g)>200]
evaluate('PREDICT 09-11..16',rows,0.02)
