"""Live broker for official polymarket-client==0.10.0; venue is source of truth."""
import asyncio, dataclasses, importlib.metadata, json, os, time
from types import SimpleNamespace
from poly_core import fee, error_info

class LiveBroker:
    basis='VENUE_CONFIRMED_TRADE_AND_VENUE_FEE'
    def __init__(self,books): self.books=books; self.client=None; self.wallet=None
    async def open(self):
        if importlib.metadata.version('polymarket-client')!='0.10.0': raise RuntimeError('Use polymarket-client==0.10.0')
        from polymarket import AsyncSecureClient
        from polymarket.auth import RelayerApiKey
        from polymarket._internal.actions.orders.typed_data import _build_standard_typed_data
        from polymarket._internal.protocol import is_v2_position_id
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak
        class TrackedClient(AsyncSecureClient):
            async def _sign_order(self,draft,*,post_only):
                signed=await super()._sign_order(draft,post_only=post_only)
                fields=dataclasses.asdict(signed); fields.update(chain_id=draft.chain_id,exchange_address=draft.exchange_address)
                version='3' if is_v2_position_id(signed.token_id) else '2'
                msg=encode_typed_data(full_message=_build_standard_typed_data(SimpleNamespace(**fields),protocol_version=version))
                self.journal_hash='0x'+keccak(b'\x19'+msg.version+msg.header+msg.body).hex()
                return signed
        names=['POLYMARKET_PRIVATE_KEY','POLYMARKET_WALLET_ADDRESS','RELAYER_API_KEY','RELAYER_API_KEY_ADDRESS']
        missing=[n for n in names if not os.environ.get(n)]
        if missing: raise RuntimeError('Missing environment variables: '+', '.join(missing))
        self.wallet=os.environ[names[1]]
        self.client=await TrackedClient.create(private_key=os.environ[names[0]],wallet=self.wallet,api_key=RelayerApiKey(key=os.environ[names[2]],address=os.environ[names[3]]))
    async def metadata(self,t):
        c=self.client
        b,m=await asyncio.gather(c.get_order_book(token_id=t),c._ctx.order_metadata.fetch_current_market(c._ctx,token_id=t))
        return (float(b.tick_size),float(b.min_order_size),float(m.fee_info.rate),float(m.fee_info.exponent))
    async def cash(self):
        b=await self.client.get_balance_allowance(asset_type='COLLATERAL'); return b.balance/1e6
    async def prepare(self,t,plan):
        # Client and signer are created once in open(); no construction or balance REST on hot path.
        s=await self.client.create_market_order(token_id=t,side='BUY',amount=str(plan['amount']),max_price=str(plan['cap']),order_type='FAK')
        if s.maker_amount/1e6>plan['amount']+1e-8 or s.taker_amount<=0 or s.maker_amount/s.taker_amount>plan['cap']+1e-8: raise RuntimeError('Signed amount/price exceeds cap')
        return s,self.client.journal_hash
    async def post(self,signed):
        try:
            r=await self.client.post_order(signed)
        except Exception as e:
            # A 4xx venue response proves rejection; 408/5xx can arrive after the
            # server has seen the request, so those remain genuinely ambiguous.
            if type(e).__name__=='RequestRejectedError':
                status=getattr(e,'status',getattr(e,'status_code',None))
                if isinstance(status,int) and 400<=status<500 and status!=408:
                    info=error_info(e,phase='post',request_reached=True)
                    return {'rejected':info}
            raise
        if r.ok: return {'id':str(r.order_id)}
        # Some SDK versions return a non-ok response instead of throwing.
        info={'class':'RequestRejectedResponse','message':str(getattr(r,'message','') or getattr(r,'code','rejected')),
              'code':str(getattr(r,'code','rejected')),'request_reached':True}
        status=getattr(r,'status',None)
        if status is not None: info['status']=status
        if status==408 or (isinstance(status,int) and status>=500):
            info['request_reached']='UNKNOWN'
            return {'ambiguous':info}
        return {'rejected':info}
    async def _trade_fills(self,r):
        plan=json.loads(r['plan']); fills=[]; seen_qty=0.; unsettled=False
        # Account trade tape is authoritative for actual matched economics.
        async for page in self.client.list_account_trades(token_id=r['token'],after=str(max(0,int(r['ts'])-120))):
            for t in getattr(page,'items',()):
                if str(getattr(t,'taker_order_id',''))!=r['id'] or str(getattr(t,'trader_side','')).upper()!='TAKER': continue
                n,p=float(t.size),float(t.price); seen_qty+=n; st=str(getattr(t,'status','')).upper()
                if st=='CONFIRMED':
                    # Fee comes from the venue's own record for THIS trade when it
                    # reports one. The locally configured rate/exponent is only a
                    # fallback, and the basis string says which was used so the
                    # dashboard never presents an estimate as a venue figure.
                    bps=getattr(t,'fee_rate_bps',None)
                    if bps is not None and str(bps)!='':
                        f_amt=round(n*p*float(bps)/10000.0,6); f_basis='VENUE_FEE_RATE_BPS'
                    else:
                        f_amt=fee(p,n,plan['rate'],plan['exponent']); f_basis='LOCAL_FEE_ESTIMATE'
                    fills.append((str(t.id),dict(shares=n,spent=n*p,price=p,fees=f_amt,
                                                 fee_basis=f_basis,fee_rate_bps=(float(bps) if bps not in (None,'') else None))))
                elif st not in ('FAILED','CANCELLED','CANCELED'):
                    unsettled=True
        return fills,seen_qty,unsettled
    async def reconcile(self,r):
        fills,trade_qty,trade_unsettled=await self._trade_fills(r)
        order=None; order_missing=False; order_error=None
        try:
            order=await self.client.get_order(order_id=r['id'])
        except Exception as e:
            # get_order is open-order state. 404 + no trade is evidence the FAK is not live;
            # other errors keep state unresolved and never trigger a duplicate submission.
            if type(e).__name__=='RequestRejectedError' and getattr(e,'status',None)==404:
                order_missing=True
            else:
                order_error=error_info(e,phase='reconcile_get_order')
        if order is not None:
            if str(order.token_id)!=r['token'] or str(order.side).upper()!='BUY': raise RuntimeError('Order identity mismatch')
            st=str(order.status).upper(); matched=float(getattr(order,'size_matched',0) or 0)
            live=st not in ('MATCHED','CANCELED','CANCELLED','EXPIRED','REJECTED')
            terminal=(not live) and not trade_unsettled and abs(trade_qty-matched)<1e-5
            return dict(terminal=terminal,fills=fills,live=live,reason=f'order status {st}')
        if order_error is not None:
            return dict(terminal=False,fills=fills,live=False,reason=json.dumps(order_error,ensure_ascii=False))
        # FAK cannot remain resting. If it is absent from open-order state, has no trade,
        # and this absence has been observed twice after a grace period, it is proven no-fill.
        age=max(0,time.time()-float(r['ts']))
        misses=int(r.get('reconcile_count') or 0)+1
        if fills:
            # Confirmed trade itself proves fill even if open-order endpoint no longer retains the FAK.
            return dict(terminal=not trade_unsettled,fills=fills,live=False,reason='confirmed account trade; order no longer open')
        if order_missing and not trade_unsettled and age>=2.0 and misses>=2:
            return dict(terminal=True,fills=[],live=False,verified_no_fill=True,reason='not present in open orders and no matching account trade after repeated venue checks')
        return dict(terminal=False,fills=[],live=False,reason='venue reconciliation in progress')
    # A 5-minute candle's position is OPEN only while the candle is live. Once it
    # settles it becomes REDEEMABLE, and CLOSED after redemption. Querying without
    # a status filter therefore misses exactly the settled positions whose PnL we
    # need, which is why v12.2's first live run kept reporting LOCAL_FROM_FILLS
    # with rows "awaiting venue". All three statuses are queried and merged.
    POSITION_STATUSES=('OPEN','REDEEMABLE','CLOSED')
    async def positions(self,status=None,condition_ids=None):
        """Venue positions with the venue's own PnL and cost fields.

        realized_pnl / unrealized_pnl / total_pnl / entry_cost_usdc /
        entry_fees_usdc / current_value are computed by Polymarket, not here.

        condition_ids narrows the query to the markets we actually need priced,
        so attaching PnL to a settled candle does not page the whole history.
        """
        out=[]; seen=set()
        if not hasattr(self.client,'list_positions'): return out
        statuses=[status] if status else list(self.POSITION_STATUSES)
        ids=list(condition_ids) if condition_ids else None
        for st in statuses:
            kw={'status':st}
            if ids: kw['condition_id']=ids
            try:
                pages=self.client.list_positions(**kw)
            except TypeError:
                pages=self.client.list_positions()      # older client surface
            async for page in pages:
                for p in getattr(page,'items',()):
                    key=(str(getattr(p,'condition_id','')),str(getattr(p,'asset_id','')))
                    if key in seen: continue
                    seen.add(key)
                    out.append(dict(
                        condition_id=str(getattr(p,'condition_id','') or ''),
                        asset_id=str(getattr(p,'asset_id','') or ''),
                        outcome=str(getattr(p,'outcome','') or ''),
                        size=float(getattr(p,'current_size',0) or 0),
                        avg_price=float(getattr(p,'avg_price',0) or 0),
                        entry_cost=float(getattr(p,'entry_cost_usdc',0) or 0),
                        entry_fees=float(getattr(p,'entry_fees_usdc',0) or 0),
                        total_cost=float(getattr(p,'total_cost_usdc',0) or 0),
                        current_price=float(getattr(p,'current_price',0) or 0),
                        current_value=float(getattr(p,'current_value',0) or 0),
                        realized_pnl=float(getattr(p,'realized_pnl',0) or 0),
                        unrealized_pnl=float(getattr(p,'unrealized_pnl',0) or 0),
                        total_pnl=float(getattr(p,'total_pnl',0) or 0),
                        status=str(getattr(p,'status','') or ''),
                        redeemable=bool(getattr(p,'redeemable',False)),
                    ))
        return out
    async def portfolio_value(self):
        try:
            v=await self.client.get_portfolio_value()
            return float(getattr(v,'value',0) or 0)
        except Exception:
            return None
    async def account_pnl(self,interval='max'):
        """Polymarket's own account PnL series. The last point is the venue's
        realized/unrealized figure for the wallet; we never recompute it."""
        try:
            s=await self.client.get_user_pnl(interval=interval)
        except Exception:
            return None
        pts=list(getattr(s,'points',()) or ())
        if not pts: return None
        p=pts[-1]
        g=lambda n: (float(getattr(p,n)) if getattr(p,n,None) is not None else None)
        return dict(ts=getattr(p,'timestamp',None),realized_pnl=g('realized_pnl'),
                    unrealized_pnl=g('unrealized_pnl'),settled_pnl=g('settled_pnl'),
                    economic_pnl=g('economic_pnl'),trade_pnl=g('trade_pnl'),
                    fees_paid=g('fees_paid'),volume=g('volume_usdc'),
                    trade_count=getattr(p,'trade_count',None))
    async def venue_truth(self,condition_ids=None):
        """One authenticated snapshot of everything the dashboard reports as money.

        Cash, portfolio value, per-position PnL and account PnL all come from
        Polymarket. Nothing in here is derived from the local journal.
        """
        cash,value,pos,pnl,snap=await asyncio.gather(
            self.cash(),self.portfolio_value(),self.positions(condition_ids=condition_ids),
            self.account_pnl(),self.account_snapshot(),return_exceptions=True)
        err=lambda x: None if isinstance(x,BaseException) else x
        pos=err(pos) or []
        snap=err(snap) or {}
        return dict(cash=err(cash),portfolio_value=err(value),positions=pos,
                    account_pnl=err(pnl),open_order_ids=snap.get('open_order_ids'),
                    open_value=sum(p['current_value'] for p in pos if p['size']>0),
                    realized_pnl=sum(p['realized_pnl'] for p in pos) if pos else None,
                    unrealized_pnl=sum(p['unrealized_pnl'] for p in pos) if pos else None,
                    fees_paid=sum(p['entry_fees'] for p in pos) if pos else None,
                    ts=time.time(),source='polymarket-api')
    async def account_snapshot(self):
        cash=await self.cash(); open_ids=set(); positions=[]
        try:
            async for page in self.client.list_open_orders():
                for o in getattr(page,'items',()): open_ids.add(str(getattr(o,'id',getattr(o,'order_id',''))))
        except Exception:
            pass
        # Newer 0.10.x clients expose wallet positions. Keep this optional so the pinned
        # client remains usable if its exact patch surface differs.
        if hasattr(self.client,'list_positions'):
            try:
                async for page in self.client.list_positions():
                    for p in getattr(page,'items',()):
                        size=float(getattr(p,'size',getattr(p,'amount',0)) or 0)
                        if size>0: positions.append(dict(condition_id=str(getattr(p,'condition_id','')),asset_id=str(getattr(p,'asset_id',getattr(p,'token_id',''))),size=size,current_value=float(getattr(p,'current_value',0) or 0)))
            except Exception:
                pass
        return dict(cash=cash,open_order_ids=open_ids,positions=positions,ts=time.time())
    async def redeem(self,condition): return await self.client.redeem_positions(condition_id=condition)
    async def claim_state(self,claim_id):
        if not claim_id.startswith('relayer:'): return None
        from polymarket._internal.actions.relayer.poll import fetch_gasless_transaction
        tx=await fetch_gasless_transaction(self.client._ctx.relayer,transaction_id=claim_id.split(':',1)[1])
        return str(tx.state)
    async def close(self):
        if self.client: await self.client.close()
