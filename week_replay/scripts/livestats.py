import sqlite3, datetime, sys, json
import pathlib
RUNS = pathlib.Path(__file__).resolve().parents[1] / 'runs'
sys.path.insert(0,'/home/user/Django-final-project/ef_arch/polymarket/fiveday')
def stats(tag):
    con=sqlite3.connect(f"file:{RUNS}/week_{tag}.sqlite3?mode=ro",uri=True,timeout=15)
    q=con.execute("select count(*) from candles where actual is not null and actual!=''").fetchone()[0]
    lastc=con.execute("select max(candle_id) from candles").fetchone()[0]
    rows=con.execute("select candle_id,direction,actual,correct,pnl,stake,financial_pnl,financial_result,"
                     "financial_is_shadow,seconds_into_candle from trades where kind='EF' order by ts_ms").fetchall()
    tot=len(rows)
    graded=[r for r in rows if r[2]]
    acc=sum(1 for r in graded if r[1]==r[2])/len(graded)*100 if graded else None
    fin=[r for r in rows if r[6] is not None]
    finw=sum(1 for r in fin if (r[6] or 0)>0)
    pnl=sum(r[6] or 0 for r in fin)
    stk=sum(r[5] or 0 for r in fin)
    return dict(tag=tag,
      upto=datetime.datetime.utcfromtimestamp(lastc/1000).strftime('%m-%d %H:%M') if lastc else '-',
      settled_candles=q, ef_trades=tot,
      freq_per_100=round(tot/q*100,1) if q else None,
      fires_per_day=round(tot/q*288,1) if q else None,
      dir_acc=round(acc,2) if acc is not None else None, dir_n=len(graded),
      pnl_n=len(fin), pnl_winrate=round(finw/len(fin)*100,2) if fin else None,
      pnl_sum=round(pnl,4), stake_sum=round(stk,2),
      ret_on_stake=round(pnl/stk*100,2) if stk else None,
      avg_fire_sec=round(sum(r[9] or 0 for r in rows)/tot,1) if tot else None)
for t in ('v9_4','v9_5','b36'):
    try: print(json.dumps(stats(t)))
    except Exception as e: print(t,'ERR',e)
