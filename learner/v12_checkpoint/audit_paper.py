"""Audit supplied logged trades. This is not an execution backtest."""
import collections,datetime as dt,hashlib,json,pathlib,sqlite3,sys
from btc_model_v10 import Model,FEATURES

def audit(path):
    # Read-only serialized copy also works where the host fsync API is unavailable.
    b=pathlib.Path(path).read_bytes(); b=bytearray(b); b[18]=b[19]=1
    c=sqlite3.connect(':memory:');c.deserialize(bytes(b));c.row_factory=sqlite3.Row
    rows=c.execute('SELECT * FROM trades ORDER BY candle_epoch').fetchall()
    model=Model(pathlib.Path(__file__).with_name('model_v10.json')); daily=collections.defaultdict(lambda:dict(settled=0,wins=0,pnl=0,pending=0))
    valid=[];invalid=[];mismatch=[];checked=0;errors=[]
    for r in rows:
        if r['ask'] is None or not .02<r['ask']<1: invalid.append(r['candle_epoch']);continue
        day=dt.datetime.fromtimestamp(r['ts_ms']/1000,dt.timezone.utc).date().isoformat()
        if r['win'] is None:daily[day]['pending']+=1;continue
        valid.append(r);daily[day]['settled']+=1;daily[day]['wins']+=r['win'];daily[day]['pnl']+=r['pnl']
        expected=r['stake']*((1-.07*(1-r['ask']))/r['ask']-1) if r['win'] else -r['stake']
        if abs(expected-r['pnl'])>1e-6:errors.append(r['candle_epoch'])
        try:
            f=json.loads(r['feat']);p=model.p_up(f);ps=p if r['side']=='UP' else 1-p;checked+=1
            if abs(ps-r['p'])>.0006:mismatch.append(dict(epoch=r['candle_epoch'],stored_p=r['p'],recomputed_p=ps))
        except (TypeError,KeyError,ValueError):pass
    sensitivity=[]
    for slip in [0,.005,.01,.02,.03]:
        pnls=[]
        for r in valid:
            price=min(.999,r['ask']+slip)
            pnls.append(r['stake']*((1-.07*(1-price))/price-1) if r['win'] else -r['stake'])
        sensitivity.append(dict(extra_price=slip,pnl=sum(pnls)))
    n=len(valid);wins=sum(r['win'] for r in valid);pnl=sum(r['pnl'] for r in valid)
    begin=min(r['ts_ms'] for r in valid)/1000;end=max(r['ts_ms'] for r in valid)/1000
    return dict(source_sha256=hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest(),integrity=c.execute('pragma integrity_check').fetchone()[0],settled=n,wins=wins,losses=n-wins,accuracy_pct=100*wins/n,pnl=pnl,staked=sum(r['stake'] for r in valid),pnl_per_dollar=pnl/sum(r['stake'] for r in valid),pending=sum(x['pending'] for x in daily.values()),invalid_quote_rows=invalid,first_fire_utc=dt.datetime.fromtimestamp(begin,dt.timezone.utc).isoformat(),last_settled_fire_utc=dt.datetime.fromtimestamp(end,dt.timezone.utc).isoformat(),observed_span_hours=(end-begin)/3600,settled_fires_per_24h_of_observed_span=n/((end-begin)/86400),daily=dict(daily),fee_formula_mismatch_epochs=errors,model_probability_comparisons=checked,model_probability_mismatches=mismatch,price_sensitivity=sensitivity,limitations=['Logged paper outcomes were not independently re-fetched.','Dust ask <= .02 explicitly excluded; all excluded epochs listed.','Sensitivity assumes every original fill and outcome unchanged; does not model actual liquidity, fresh quote gates or cancellations.','No weekend coverage and no live fill-rate validation.'])
if __name__=='__main__': print(json.dumps(audit(sys.argv[1]),indent=2))
