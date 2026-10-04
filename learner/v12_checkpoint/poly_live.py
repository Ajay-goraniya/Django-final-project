"""Live broker for official polymarket-client==0.10.0; no auto live activation."""
import asyncio, dataclasses, importlib.metadata, json, os
from types import SimpleNamespace
from poly_core import fee

class LiveBroker:
    basis='CONFIRMED_FILL_WITH_ESTIMATED_VENUE_FEE'
    def __init__(self,books): self.books=books; self.client=None
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
                fields=dataclasses.asdict(signed)
                fields.update(chain_id=draft.chain_id,exchange_address=draft.exchange_address)
                version='3' if is_v2_position_id(signed.token_id) else '2'
                msg=encode_typed_data(full_message=_build_standard_typed_data(SimpleNamespace(**fields),protocol_version=version))
                self.journal_hash='0x'+keccak(b'\x19'+msg.version+msg.header+msg.body).hex()
                return signed
        names=['POLYMARKET_PRIVATE_KEY','POLYMARKET_WALLET_ADDRESS','RELAYER_API_KEY','RELAYER_API_KEY_ADDRESS']
        missing=[n for n in names if not os.environ.get(n)]
        if missing: raise RuntimeError('Missing environment variables: '+', '.join(missing))
        self.client=await TrackedClient.create(private_key=os.environ[names[0]],wallet=os.environ[names[1]],api_key=RelayerApiKey(key=os.environ[names[2]],address=os.environ[names[3]]))
    async def metadata(self,t):
        c=self.client
        b,m=await asyncio.gather(c.get_order_book(token_id=t),c._ctx.order_metadata.fetch_current_market(c._ctx,token_id=t))
        return (float(b.tick_size),float(b.min_order_size),float(m.fee_info.rate),float(m.fee_info.exponent))
    async def cash(self):
        b=await self.client.get_balance_allowance(asset_type='COLLATERAL'); return b.balance/1e6
    async def prepare(self,t,plan):
        s=await self.client.create_market_order(token_id=t,side='BUY',amount=str(plan['amount']),max_price=str(plan['cap']),order_type='FAK')
        if s.maker_amount/1e6>plan['amount']+1e-8 or s.taker_amount<=0 or s.maker_amount/s.taker_amount>plan['cap']+1e-8: raise RuntimeError('Signed amount/price exceeds cap')
        return s,self.client.journal_hash
    async def post(self,signed):
        r=await self.client.post_order(signed)
        return {'id':str(r.order_id)} if r.ok else {'rejected':r.code}
    async def reconcile(self,r):
        o=await self.client.get_order(order_id=r['id'])
        if str(o.token_id)!=r['token'] or o.side!='BUY': raise RuntimeError('Order identity mismatch')
        plan=json.loads(r['plan']); fills=[]; quantity=0.; terminal=True
        async for page in self.client.list_account_trades(token_id=r['token'],after=str(int(r['ts'])-60)):
            for t in page.items:
                if str(t.taker_order_id)!=r['id'] or t.trader_side!='TAKER': continue
                n,p=float(t.size),float(t.price); quantity+=n
                if str(t.status).upper()=='CONFIRMED': fills.append((t.id,dict(shares=n,spent=n*p,price=p,fees=fee(p,n,plan['rate'],plan['exponent']))))
                elif str(t.status).upper()!='FAILED': terminal=False
        terminal=terminal and str(o.status).upper() in ('MATCHED','CANCELED','CANCELLED','EXPIRED') and abs(quantity-float(o.size_matched))<1e-5
        return dict(terminal=terminal,fills=fills)
    async def redeem(self,condition): return await self.client.redeem_positions(condition_id=condition)
    async def claim_state(self,claim_id):
        if not claim_id.startswith('relayer:'): return None
        from polymarket._internal.actions.relayer.poll import fetch_gasless_transaction
        tx=await fetch_gasless_transaction(self.client._ctx.relayer,transaction_id=claim_id.split(':',1)[1])
        return str(tx.state)
    async def close(self):
        if self.client: await self.client.close()
