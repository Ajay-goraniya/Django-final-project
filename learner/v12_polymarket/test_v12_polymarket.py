import asyncio, pathlib, sys, tempfile, time
from argparse import Namespace
from types import SimpleNamespace
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from btc_model_v12_polymarket import ceil_tick, target_stake, ev_at_price, threshold_passes, Store, Runner

HERE = pathlib.Path(__file__).resolve().parent

def test_math():
    assert ceil_tick(0.501,0.01)==0.51
    assert ceil_tick(0.55,0.01)==0.55
    assert target_stake(0)==1 and target_stake(29.99)==1
    assert target_stake(30)==2 and target_stake(40)==3 and target_stake(50)==4 and target_stake(999)==20
    d={"p":0.8,"threshold":{"conf_floor":0.75,"ev_floor":0.02}}
    assert threshold_passes(d,0.03)
    assert not threshold_passes(d,0.01)
    assert ev_at_price(0.8,0.50) > ev_at_price(0.8,0.60)

def test_store_ladder():
    with tempfile.TemporaryDirectory() as td:
        s=Store(str(pathlib.Path(td)/"x.sqlite3"),False,29)
        assert s.stake()==1
        s.set_meta("lane_equity","30")
        assert s.stake()==1
        assert s.stake()==2
        s.set_meta("lane_equity","29")
        assert s.stake()==1

def args(db):
    return Namespace(model=str(HERE/'model_v10.json'), db=str(db), reset=False, lane_equity=0.0,
        execution='paper', confirm_live_orders=False, mode='accuracy', ev=None, fixed_stake=None,
        execution_deadline_sec=242, retry_window_ms=1800, max_attempts=3, min_retry_usdc=.10,
        max_quote_age_ms=5000, pad_ticks=1, retry_delay_ms=1, kill_slippage=.03,
        kill_pnl_per_dollar=-3.0, port=9999)

class FakeLive:
    def __init__(self, ambiguous=False): self.n=0; self.ambiguous=ambiguous
    def place(self, token, amount, cap):
        self.n += 1
        if self.ambiguous: raise TimeoutError('submit timed out')
        if self.n == 1: return SimpleNamespace(ok=False, code='fak_not_filled', message='no match')
        return SimpleNamespace(ok=True, order_id='ord2', status='matched', trade_ids=('tr2',))
    def fills(self, token, order_ids, trade_ids):
        if 'tr2' not in trade_ids: return None
        return dict(raw_notional=0.50, shares=1.0, avg_price=0.50, fee_rate_bps=700, trade_ids=['tr2'])

def test_retry_then_fill():
    async def run():
        with tempfile.TemporaryDirectory() as td:
            a=args(pathlib.Path(td)/'x.sqlite3'); r=Runner(a); r.a.execution='live'; r.live=FakeLive()
            tok='T'; r.ladders[tok]={'asks':{0.50:100},'bids':{0.49:100},'ts_ms':int(time.time()*1000)}; r.token_meta[tok]={'tick':0.01}
            d={'p':0.85,'threshold':{'conf_floor':0.8,'ev_floor':0.02}}
            q=r.best_quote(tok); assert q
            ep=int(time.time()//300)*300
            r.db.create_trade(epoch=ep,signal_ms=int(time.time()*1000),mode='accuracy',execution='live',side='UP',token_id=tok,p=.85,quote_ask=.50,quote_age_ms=0,signal_ev=.2,sec=30,rv60=1,requested_stake=1,state='SIGNALLED',feat=None)
            await r.execute_live(ep,d,tok,q,1.0)
            row=r.db.con.execute('select state,attempts from trades where candle_epoch=?',(ep,)).fetchone()
            assert row==('FILLED',2), row
    asyncio.run(run())

def test_ambiguous_kills_lane():
    async def run():
        with tempfile.TemporaryDirectory() as td:
            a=args(pathlib.Path(td)/'x.sqlite3'); r=Runner(a); r.a.execution='live'; r.live=FakeLive(ambiguous=True)
            tok='T'; r.ladders[tok]={'asks':{0.50:100},'bids':{0.49:100},'ts_ms':int(time.time()*1000)}; r.token_meta[tok]={'tick':0.01}
            d={'p':0.85,'threshold':{'conf_floor':0.8,'ev_floor':0.02}}
            q=r.best_quote(tok); assert q
            ep=int(time.time()//300)*300
            r.db.create_trade(epoch=ep,signal_ms=int(time.time()*1000),mode='accuracy',execution='live',side='UP',token_id=tok,p=.85,quote_ask=.50,quote_age_ms=0,signal_ev=.2,sec=30,rv60=1,requested_stake=1,state='SIGNALLED',feat=None)
            await r.execute_live(ep,d,tok,q,1.0)
            row=r.db.con.execute('select state from trades where candle_epoch=?',(ep,)).fetchone()
            assert row==('AMBIGUOUS',), row
            assert not r.db.enabled()
    asyncio.run(run())

def main():
    test_math(); test_store_ladder(); test_retry_then_fill(); test_ambiguous_kills_lane(); print('v12 tests: PASS')

if __name__=='__main__': main()
