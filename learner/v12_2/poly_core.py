"""Polymarket order policy, book cache, durable trade journal and reconciliation."""
import asyncio, json, math, os, sqlite3, threading, time, uuid
from collections import deque
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR

D=lambda x:Decimal(str(x))


def fee(price,shares,rate=.07,exponent=1):
    return round(shares*rate*(price*(1-price))**exponent,5)


def _safe_error_value(value, depth=0):
    """Best-effort JSON-safe error payload with credential/signature redaction."""
    if depth > 4:
        return '<truncated>'
    if value is None or isinstance(value,(bool,int,float)):
        return value
    if isinstance(value,str):
        text=value[:4096]
        for env in ('POLYMARKET_PRIVATE_KEY','RELAYER_API_KEY','DASHBOARD_PASSWORD'):
            secret=os.environ.get(env)
            if secret and len(secret)>=6:
                text=text.replace(secret,'<redacted>')
        return text
    if isinstance(value,dict):
        out={}
        for k,v in list(value.items())[:80]:
            key=str(k)
            low=key.lower()
            if any(x in low for x in ('private','secret','password','authorization','signature','api_key','apikey')):
                out[key]='<redacted>'
            else:
                out[key]=_safe_error_value(v,depth+1)
        return out
    if isinstance(value,(list,tuple)):
        return [_safe_error_value(v,depth+1) for v in list(value)[:80]]
    return _safe_error_value(str(value),depth+1)


def error_info(exc, *, phase=None, request_reached=None):
    """Serialize an exception while retaining the useful venue rejection text.

    Explicit HTTP rejection => request_reached=True.  Transport ambiguity should
    pass ``'UNKNOWN'`` rather than pretending the venue definitely saw it.
    """
    out={
        'class':type(exc).__name__,
        'message':_safe_error_value(str(exc)),
        'repr':_safe_error_value(repr(exc)),
    }
    for name in ('status','status_code','code','retry_after','restriction','reason'):
        try:
            value=getattr(exc,name,None)
            if value is not None and isinstance(value,(str,int,float,bool)):
                out[name]=_safe_error_value(value)
        except Exception:
            pass
    # Some HTTP clients hang the raw response off the exception.  Capture only
    # sanitized response data; never headers/cookies/auth/signatures.
    try:
        response=getattr(exc,'response',None)
        if response is not None:
            status=getattr(response,'status_code',getattr(response,'status',None))
            if status is not None: out.setdefault('status',status)
            try:
                body=getattr(response,'text',None)
                if callable(body): body=body()
                if body: out['response_body']=_safe_error_value(body)
            except Exception:
                pass
            try:
                fn=getattr(response,'json',None)
                if callable(fn):
                    body_json=fn()
                    if body_json is not None: out['response_json']=_safe_error_value(body_json)
            except Exception:
                pass
    except Exception:
        pass
    if phase: out['phase']=phase
    if request_reached is not None:
        out['request_reached']=request_reached if isinstance(request_reached,str) else bool(request_reached)
    return out


def compact_error(info):
    if isinstance(info,str): return info
    if not isinstance(info,dict): return str(info)
    cls=info.get('class') or 'Error'; msg=info.get('message') or ''
    status=info.get('status'); code=info.get('code')
    bits=[f'{cls}: {msg}' if msg else cls]
    if status is not None: bits.append(f'HTTP {status}')
    if code: bits.append(f'code={code}')
    return ' · '.join(bits)


class BookCache:
    def __init__(self):
        self.books={}; self.terms={}; self.seq=0
        # Venue event time minus our clock, measured continuously.  v12.1 dropped
        # every book event more than 2s from local time, so a host whose clock had
        # drifted (a fresh VPS before NTP settles) discarded the entire feed and
        # reported an empty book rather than a clock problem.  We now measure the
        # offset, correct for it, and surface it instead of dropping data.
        self.clock_offset=0.0; self._offset_seeded=False
        self._delta_hist=deque(maxlen=200)   # 12.15.4: window for positive-skew evidence
        self.dropped_future=0; self.dropped_stale=0; self.applied=0
        # Last tick_size_change per token, and the running count.
        self.tick_changes={}; self.tick_change_count=0
        # Why quote() declined, counted. Distinguishes a one-sided book from a
        # stale or crossed one, which the "waiting for fresh books" message does
        # not.
        self.quote_block=dict(no_book=0,no_asks=0,no_bids=0,stale=0,crossed=0,ok=0)
        # 12.8.10: the last refusal per token, with the age quote() judged, so
        # publish() can say WHICH token blocked a decision and HOW old it was.
        self.block_detail={}
    def prune(self,keep):
        """Drop books for tokens we are no longer subscribed to, keep the rest.

        The venue loop used to clear() on every cycle and again on every
        reconnect, so a token's only full snapshot was the one the subscribe
        delivered. A fire early in a candle then priced off a book snapshotted a
        cycle earlier, patched only by deltas with no continuity check. Keeping
        the book across a resubscribe means the fresh snapshot replaces it
        rather than the cache starting empty."""
        keep=set(map(str,keep))
        for t in [t for t in self.books if t not in keep]: self.books.pop(t,None)
    def health(self):
        return dict(clock_offset_s=round(self.clock_offset,3),applied=self.applied,
                    dropped_future=self.dropped_future,dropped_stale=self.dropped_stale,
                    tokens=len(self.books),tick_changes=self.tick_change_count,
                    quote_block=dict(self.quote_block))
    def apply(self,e):
        stamp=float(e['timestamp'])/1000; now=time.time()
        if not math.isfinite(stamp): return
        delta=now-stamp
        # Seed the offset from the first event rather than converging toward it.
        # An EMA starting at zero would reject several hundred events before it
        # caught up with a badly set clock, which is the same outage this change
        # exists to prevent - just slower.
        # 12.15.4: correct the clock in BOTH directions, with asymmetric evidence.
        # A NEGATIVE delta is impossible without skew (transit >= 0), so the
        # negative side follows a new minimum at once, as it always did. A POSITIVE
        # skew (local clock ahead) looks exactly like transport lag on any single
        # packet, so it is adopted only from the floor of a full window of samples
        # - one packet, or the first packet, can never move it. Before this the
        # offset was seeded min(delta,0) and could only become more negative: a
        # clock >8 s ahead dropped every valid book event as stale, and ~3 s ahead
        # failed the freshness bar on data received milliseconds earlier.
        self._delta_hist.append(delta)
        if not self._offset_seeded:
            self.clock_offset=min(delta,0.0); self._offset_seeded=True
        elif delta<self.clock_offset:
            self.clock_offset=delta
        elif len(self._delta_hist)==self._delta_hist.maxlen:
            floor=min(self._delta_hist)
            if floor>self.clock_offset: self.clock_offset+=.05*(floor-self.clock_offset)
            elif self.clock_offset<0: self.clock_offset=.999*self.clock_offset
        elif self.clock_offset<0:
            self.clock_offset=.999*self.clock_offset
        corrected=delta-self.clock_offset
        if corrected>8: self.dropped_stale+=1; return
        if corrected<-8: self.dropped_future+=1; return
        self.applied+=1
        k=e.get('event_type')
        if k=='tick_size_change':
            # The venue moves these markets between the 0.01 and 0.001 grids
            # intra-candle - 8 times in 300 s on the active tokens, measured
            # 09-13. Popping terms makes housekeeping refetch, but that runs on a
            # 5 s loop, so the token has no terms until it does and the lane
            # skips. Record every change with its time so a reject can be tied to
            # a preceding switch instead of inferred.
            token=str(e['asset_id']); self.terms.pop(token,None)
            self.tick_changes[token]=dict(at=time.monotonic(),wall=time.time(),
                                          old=e.get('old_tick_size'),new=e.get('new_tick_size'))
            self.tick_change_count+=1; return
        if k=='book':
            token=str(e['asset_id'])
            if token in self.books and stamp<self.books[token]['event']: return
            b={s:{float(x['price']):float(x['size']) for x in e.get(s,[]) if 0<float(x['price'])<1 and math.isfinite(float(x['size'])) and float(x['size'])>0} for s in ('asks','bids')}
            self.books[token]=b; self.seq+=1; b.update(event=stamp,arrival=time.monotonic(),seq=self.seq,snapshot=time.monotonic())
        elif k=='price_change':
            for c in e.get('price_changes',[]):
                b=self.books.get(str(c.get('asset_id')))
                if not b or stamp<b['event'] or c.get('side') not in ('BUY','SELL'): continue
                p,q=float(c['price']),float(c['size'])
                if not (0<p<1 and q>=0 and math.isfinite(q)): continue
                side=b['asks' if c['side']=='SELL' else 'bids']
                if q: side[p]=q
                else: side.pop(p,None)
                # snapshot is deliberately NOT refreshed: a delta does not
                # resync the book. There is no venue sequence number per token,
                # so a dropped price_change is undetectable and leaves a phantom
                # level that survives until the next full 'book' event. Age from
                # the last snapshot is the only measure of how far our book may
                # have drifted from the venue's.
                self.seq+=1; b.update(event=stamp,arrival=time.monotonic(),seq=self.seq)
    def quote(self,t,max_age=.75):
        """Top of book, or None with the reason counted.

        A one-sided book yields no quote, which is almost certainly the source of
        the 20.9% of a session spent on "Waiting for fresh UP and DOWN books".
        Whether that is the ACTIVE token (costly) or the NEXT-candle token that
        nobody is quoting yet (benign) decides whether requiring both sides is
        wrong. Count the reasons so that is measurable; do not change the rule on
        an argument.
        """
        b=self.books.get(t)
        if not b: self.quote_block['no_book']+=1; self.block_detail[t]=('no_book',None); return None
        if not b['asks']: self.quote_block['no_asks']+=1; self.block_detail[t]=('no_asks',time.monotonic()-b['arrival']); return None
        if not b['bids']: self.quote_block['no_bids']+=1; self.block_detail[t]=('no_bids',time.monotonic()-b['arrival']); return None
        # Monotonic arrival is authoritative for age: it cannot be moved by clock
        # drift or NTP steps.  The wall-clock figure is corrected by the measured
        # offset and used only when it indicates the book is OLDER.
        mono=time.monotonic()-b['arrival']
        wall=(time.time()-b['event'])-self.clock_offset
        age=max(mono,min(wall,mono+max_age))
        if not 0<=age<=max_age: self.quote_block['stale']+=1; self.block_detail[t]=('stale',age); return None
        ask,bid=min(b['asks']),max(b['bids'])
        if bid>=ask: self.quote_block['crossed']+=1; self.block_detail[t]=('crossed',age); return None
        self.quote_block['ok']+=1; self.block_detail.pop(t,None)
        return dict(ask=ask,bid=bid,asks=sorted(b['asks'].items()),seq=b['seq'],age_ms=age*1000,
                    snapshot_age_s=time.monotonic()-b.get('snapshot',b['arrival']))


# Build 36's execution-survivability policy, ported as percentages.
#
# Build 36 (Predict.fun) set no price ceiling at all: it sent a value-denominated
# market buy with an isMinAmountOut floor, and the tolerance scaled INVERSELY
# with price - about 100% headroom on a 6c share, about 10% on a 45c one. v12
# instead used a flat 0-5 tick pad, which collapses in relative terms exactly
# where build 36 was most generous: at ask 0.28 one tick is 3.6% against build
# 36's ~50%.
#
# The bands below are build 36's stated PRICE-EXPANSION intent, not its bps
# figures - those were Predict's isMinAmountOut encoding of this same intent and
# do not port to a venue where the equivalent encoding is a price cap.
#
# Deliberately NOT an eligibility gate. Build 36's own comment: "execution
# survivability only: no EF eligibility/share-price gate is added here". EV is
# decided once, on the signal, at the price we expect to pay - see
# _gate_on_padded_ev in the runner. This only governs how far a fill may walk.
# Ticks above the ask at which EV is judged, fixed and independent of both
# pad_ticks and slippage_mode. 1 reproduces 12.3.4's bar exactly, so widening
# the execution cap can never loosen or tighten which trades qualify.
EV_REFERENCE_PAD=1
SLIPPAGE_BANDS=((0.10,1.00),(0.20,0.70),(0.30,0.50),(0.40,0.20))
SLIPPAGE_FALLBACK=0.10


def slippage_band(ask):
    """Fraction of price a fill may expand by, from build 36's bands."""
    if not (isinstance(ask,(int,float)) and math.isfinite(ask)) or ask<=0: return SLIPPAGE_BANDS[0][1]
    for upper,frac in SLIPPAGE_BANDS:
        if ask<upper: return frac
    return SLIPPAGE_FALLBACK


def order_plan(q,terms,stake,d,pad=1,band=False,require_depth=True):
    tick,minimum,rate,exp=map(float,terms)
    if not all(map(math.isfinite,(tick,minimum,rate,exp,stake,d['p'],d['threshold']))) or not (0<tick<1 and minimum>0 and 0<=rate<1 and exp>=1 and stake>0 and 0<d['p']<1 and pad>=0):
        raise ValueError('invalid order inputs')
    # D is Decimal(str(x)) - see the top of this module - so the venue's decimal
    # is what gets divided and the cap lands exactly on the tick grid:
    # cap == ask + pad*tick at every price. Do NOT "fix" this by reaching for
    # Decimal directly: Decimal(0.28)/Decimal(0.01) is 28.000...2 and
    # ROUND_CEILING turns that into 29. I shipped exactly that non-fix as 12.3.1
    # after reproducing the "bug" in a scratch script that defined its own D and
    # never imported this one. TickGridRounding guards both mistakes.
    # The narrowest cap that is still marketable: the ask itself on the grid.
    floor_cap=float((D(q['ask'])/D(tick)).to_integral_value(rounding=ROUND_CEILING)*D(tick))
    if band:
        # Proportional headroom, snapped up to the tick grid.
        # Stay in Decimal for the multiply. 0.28*1.5 is 0.42000000000000004 as a
        # float, which ceils to 0.43 and quietly hands out a free tick - the same
        # trap that produced a phantom off-by-one bug earlier in this build.
        raw=D(q['ask'])*(D(1)+D(slippage_band(q['ask'])))
        cap=float((raw/D(tick)).to_integral_value(rounding=ROUND_CEILING)*D(tick))
    else:
        cap=float(((D(q['ask'])/D(tick)).to_integral_value(rounding=ROUND_CEILING)+pad)*D(tick))
    # Clamp, do not refuse. A band cap above the top tick must not reject a trade
    # the EV test would have taken - that would make the survivability parameter
    # a second opinion again, which is the whole bug. The highest valid price is
    # still marketable and still fills.
    cap=min(cap,float((D(1)-D(tick))))
    if not 0<cap<1: raise ValueError('price cap outside market')
    # THE EV PRICE IS INDEPENDENT OF THE EXECUTION CAP. They are two different
    # questions and tying them together was a real error.
    #
    # "Once the order is in execution it should be filled... why are you removing
    # slippage once the order is placed?" - the operator, and they are right. The
    # cap is not a second opinion on the trade; the trade was already decided.
    # Its only job is to survive the flight to the venue, and a taker pays the
    # resting maker's price regardless (20 of 20 fills at or better than the
    # quoted ask, cap never reached), so a wide cap is free.
    #
    # But `_px = ask if band else cap` made the EV bar move with the slippage
    # dial: switching to band mode judged EV at the ask instead of ask+1 tick and
    # silently loosened the test by +0.019 to +0.028, admitting marginal trades
    # 12.3.4 refused. Widening a survivability parameter must not change which
    # trades qualify - in EITHER direction.
    #
    # So EV is always judged at the same reference, ask + EV_REFERENCE_PAD ticks,
    # which is exactly what 12.3.4 used. The cap is then free to be as wide as
    # the band wants without touching the decision.
    _px=float(((D(q['ask'])/D(tick)).to_integral_value(rounding=ROUND_CEILING)+EV_REFERENCE_PAD)*D(tick))
    _px=min(_px,float(D(1)-D(tick)))
    f=rate*(_px*(1-_px))**exp
    cost=max(_px+f,_px/(1-f/_px))
    if d.get('price_rule')=='lane_cap':
        # 12.18.0: MAIN/REVERSAL carry no model-EV test (build11 parity, see
        # poly_lanes.LANE_MAX_ASK). Their one price control is a maximum entry.
        _mx=float(d.get('max_ask',1.0))
        if float(q['ask'])>_mx+1e-9: raise ValueError(f"ask {float(q['ask']):.2f} above lane cap {_mx:.2f}")
    elif d['p']/cost-1<d['threshold']: raise ValueError('price fails model EV')
    levels=[rate*(p*(1-p))**exp/p for p,size in q['asks'] if p<=cap]
    if not levels: raise ValueError('no executable ask at cap')
    # Can the ladder absorb the whole stake at or under the cap?
    #
    # ONLY meaningful for a genuinely all-or-nothing broker. It is off for both
    # live (FAK) and paper.
    #
    # 12.4.1 turned this on for live on the theory that the rejects were thin
    # books. That was wrong, and is retracted in 12.4.5. Polymarket's own error
    # table says a FAK needs at least ONE match and partially fills otherwise -
    # so a thin book is a partial fill, never the "no orders found to match"
    # reject we actually get. And the book is not thin: the live BTC 5m ladder
    # carries ~$98 at the touch and ~$254 within a cent against a $3 stake.
    # The check could never bind, and could only convert a partial fill into a
    # local skip. Kept for a real FOK broker, which we do not run.
    if require_depth:
        _depth=0.
        for _p,_n in q['asks']:
            if _p>cap: break
            _depth+=_p*_n
            if _depth>=stake: break
        if _depth+1e-9<stake:
            raise ValueError(f'book too thin at cap: {_depth:.2f} of {stake:.2f} available')
    ratio=max(levels)
    amount=float((D(stake)/(1+D(ratio))).quantize(D('.01'),rounding=ROUND_DOWN))
    if band and amount/cap+1e-8<minimum:
        # The venue minimum is 5 SHARES, not dollars, and the size we sign is
        # amount/cap - so a WIDER cap signs FEWER shares and a generous band can
        # trip the floor the tight pad cleared. At the live $3 stake that pulls
        # the tradable ask from 0.57 down to 0.52, i.e. band mode would trade a
        # reject problem for a skip problem across the expensive half of the
        # book. Clamp the cushion to the widest cap that still clears the floor
        # instead of dropping the trade: some cushion beats none, and this is
        # never worse than tick mode, which is the whole point of the parameter.
        #
        # One pass is enough. Narrowing the cap can only drop ask levels, which
        # can only lower max(levels), which can only RAISE amount - so the
        # recomputed plan clears the floor whenever any marketable cap does.
        clamped=float((D(amount)/D(minimum)/D(tick)).to_integral_value(rounding=ROUND_FLOOR)*D(tick))
        if clamped>=floor_cap:
            cap=clamped
            levels=[rate*(p*(1-p))**exp/p for p,size in q['asks'] if p<=cap]
            if not levels: raise ValueError('no executable ask at cap')
            ratio=max(levels)
            amount=float((D(stake)/(1+D(ratio))).quantize(D('.01'),rounding=ROUND_DOWN))
    if amount/cap+1e-8<minimum:
        # 12.18.0: a $3 stake cannot buy Polymarket's 5-share minimum above ask
        # 0.60, which is where MAIN buys (15 of 101 Zurich refusals). With
        # d['min_topup'] (set by the engine on PAPER lanes only) the plan is
        # raised to the minimum; the live stake stays the owner's.
        if d.get('min_topup'):
            amount=float((D(minimum)*D(cap)).quantize(D('.01'),rounding=ROUND_CEILING))
            stake=max(float(stake),float((D(amount)*(1+D(ratio))).quantize(D('.01'),rounding=ROUND_CEILING)))
        else: raise ValueError('below venue minimum; stake not increased')
    return dict(cap=cap,amount=amount,max_shares=amount/cap,budget=stake,quote=q['ask'],pre_submit_quote=q['ask'],age_ms=q['age_ms'],rate=rate,exponent=exp,seq=q['seq'])


def walk_book(q,plan):
    left=plan['amount']; sh=spent=fees=0.
    for p,n in q['asks']:
        if p>plan['cap']: break
        size=min(n,left/p); sh+=size; spent+=size*p
        fees+=fee(p,size,plan['rate'],plan['exponent']); left-=size*p
        if left<1e-9: break
    return dict(shares=sh,spent=spent,fees=fees,price=spent/sh if sh else None)


class Journal:
    def __init__(self,path,lane,model_hash):
        self.c=sqlite3.connect(path,check_same_thread=False); self.c.row_factory=sqlite3.Row; self.lock=threading.RLock()
        self._kill_reported=set()   # 12.8.8: KILL_CONDITION rules already written this episode
        self._halt_checked_at=None  # 12.9.0: monotonic stamp of the last halt_check that ran (see every_s)
        self._meta_cache={}         # 12.19.0: k -> (monotonic, value); see get()
        self.c.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS signals(epoch INTEGER PRIMARY KEY,ts REAL,side TEXT,token TEXT,condition_id TEXT,decision TEXT,status TEXT,kind TEXT DEFAULT 'EF');
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,epoch INTEGER,attempt INTEGER,status TEXT,plan TEXT,ts REAL,latency REAL,reason TEXT);
        CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY,order_id TEXT,epoch INTEGER,shares REAL,spent REAL,fees REAL,price REAL,basis TEXT);
        CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY AUTOINCREMENT,epoch INTEGER UNIQUE,actual TEXT,payout REAL,pnl REAL,ts REAL,claim_status TEXT DEFAULT 'PENDING',claim_id TEXT);
        CREATE TABLE IF NOT EXISTS diagnostics(ts REAL,epoch INTEGER,detail TEXT);
        CREATE TABLE IF NOT EXISTS candle_attempts(epoch INTEGER,kind TEXT,n INTEGER,PRIMARY KEY(epoch,kind));
        CREATE TABLE IF NOT EXISTS candles(epoch INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,volume REAL);
        CREATE TABLE IF NOT EXISTS tape1s(ts INTEGER PRIMARY KEY,spot_px REAL,spot_buy REAL,spot_sell REAL,perp_px REAL,perp_buy REAL,perp_sell REAL,
            bid5 REAL,ask5 REAL,bid20 REAL,ask20 REAL,ref_px REAL,up_ask REAL,dn_ask REAL);
        ''')
        self._add_columns('orders',{
            'error_json':'TEXT','timing_json':'TEXT','request_reached':'INTEGER DEFAULT 0',
            'reconcile_count':'INTEGER DEFAULT 0','last_reconcile':'REAL','venue_live':'INTEGER DEFAULT 0',
            'venue_absent':'INTEGER DEFAULT 0','venue_checked':'REAL'
        })
        # Money as Polymarket reports it, kept beside the local figure rather than
        # replacing it, so the two can be compared and any divergence surfaced.
        self._add_columns('results',{'claim_tries':'INTEGER DEFAULT 0',
            'venue_pnl':'REAL','venue_realized_pnl':'REAL','venue_fees':'REAL',
            'venue_value':'REAL','venue_ts':'REAL','pnl_basis':"TEXT DEFAULT 'LOCAL_FROM_FILLS'"
        })
        self._add_columns('fills',{'fee_basis':'TEXT','fee_rate_bps':'REAL'})
        self._add_columns('signals',{'kind':"TEXT DEFAULT 'EF'"})
        self._add_columns('orders',{'kind':"TEXT DEFAULT 'EF'"})
        # 12.21.0: every order names the lane it went to. On a process with live credentials,
        # master OFF sends orders to the paper broker ('PAPER', shadow) and master ON to the
        # venue ('LIVE'); results carry the venue pnl in pnl/payout and the shadow pnl beside it.
        self._add_columns('orders',{'lane':'TEXT'}); self._add_columns('results',{'shadow_payout':'REAL','shadow_pnl':'REAL'})
        self.lane=lane
        self._migrate_signals_multilane()
        # After the multilane rebuild, not before: that rebuild recreates the
        # table from an explicit column list and would drop anything added
        # ahead of it.
        self._add_columns('signals',{'attempts':'INTEGER DEFAULT 0'})
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS venue_state(ts REAL PRIMARY KEY,cash REAL,portfolio_value REAL,
            open_value REAL,realized_pnl REAL,unrealized_pnl REAL,fees_paid REAL,detail TEXT);
        ''')
        # 12.9.0: housekeeping's retention DELETE and _main_oneshot_check's
        # control_write scan both walk diagnostics by ts; ~30k rows/day, 7-day
        # keep, and until now no index - a full scan every 5 s on the loop thread.
        self.c.executescript('CREATE INDEX IF NOT EXISTS diagnostics_ts ON diagnostics(ts);')
        if 'id' not in [r[1] for r in self.c.execute('PRAGMA table_info(results)')]:
            self.c.close(); raise ValueError('Pre-release database schema: preserve it and choose a new DB')
        for k,v in [('lane',lane),('model_hash',model_hash),('build','12.24.1')]:
            old=self.get(k)
            # v12.0 -> v12.1 is an additive execution/accounting migration.
            if k=='build' and old in ('12.0','12.1','12.2','12.2.1','12.2.2','12.2.3','12.2.4','12.3.0','12.3.1','12.3.2','12.3.3','12.3.4','12.3.5','12.3.6','12.3.7','12.3.8','12.4.0','12.4.1','12.4.2','12.4.3','12.4.4','12.4.5','12.4.6','12.4.7','12.4.8','12.4.9','12.4.10','12.4.11','12.5.0','12.5.1','12.5.2','12.6.0','12.6.1','12.6.2','12.7.0','12.7.1','12.8.0','12.8.1','12.8.2','12.8.3','12.8.4','12.8.5','12.8.6','12.8.7','12.8.8','12.8.9','12.8.10','12.8.11','12.9.0','12.10.0','12.11.0','12.11.1','12.11.2','12.11.3','12.12.0','12.12.1','12.12.2','12.13.0','12.13.1','12.14.0','12.14.1','12.15.0','12.15.1','12.15.2','12.15.3','12.15.4','12.15.5','12.16.0','12.16.1','12.17.0','12.18.0','12.19.0','12.19.1','12.20.0','12.21.0','12.21.1','12.21.2','12.21.3','12.21.4','12.22.0','12.23.0','12.23.1','12.23.2','12.24.0','12.24.1'): pass
            elif old is not None and old!=v: raise ValueError('Database identity mismatch; choose a new DB')
            self.set(k,v)
    def _migrate_signals_multilane(self):
        """Widen signals from one row per candle to one row per (candle, lane).

        Until this build EF was the only lane that could fire, so epoch alone was
        a sufficient key. MAIN and REVERSAL both trade the same candle - REVERSAL
        is a hedge placed beside an open MAIN, not a replacement for it - so the
        key has to carry the lane. SQLite cannot alter a primary key in place, so
        the table is rebuilt; every existing row is stamped EF, which is what it
        was, and no history is dropped."""
        cols=[r[1] for r in self.c.execute('PRAGMA table_info(signals)')]
        if not cols: return
        pk=[r[1] for r in self.c.execute('PRAGMA table_info(signals)') if r[5]]
        if pk==['epoch','kind']: return
        with self.lock,self.c:
            self.c.execute('''CREATE TABLE IF NOT EXISTS signals_ml(
                epoch INTEGER,ts REAL,side TEXT,token TEXT,condition_id TEXT,
                decision TEXT,status TEXT,kind TEXT NOT NULL DEFAULT 'EF',
                PRIMARY KEY(epoch,kind))''')
            self.c.execute('''INSERT OR IGNORE INTO signals_ml(epoch,ts,side,token,condition_id,decision,status,kind)
                              SELECT epoch,ts,side,token,condition_id,decision,status,
                                     coalesce(kind,'EF') FROM signals''')
            self.c.execute('DROP TABLE signals')
            self.c.execute('ALTER TABLE signals_ml RENAME TO signals')
    def _add_columns(self,table,cols):
        existing={r[1] for r in self.c.execute(f'PRAGMA table_info({table})')}
        with self.c:
            for name,decl in cols.items():
                if name not in existing: self.c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
    def sql(self,q,args=()):
        with self.lock,self.c: return self.c.execute(q,args).fetchall()
    # 12.19.0: every control read on the fire path (ui.allowed() is six of them, twice per
    # attempt) was a SELECT under the journal lock. Writes go through set()/set_many(), which
    # refresh the cache, so a read is served from memory for META_TTL_S and re-read after.
    META_TTL_S=2.0
    def get(self,k,default=None):
        c=self._meta_cache.get(k)
        if c is not None and time.monotonic()-c[0]<self.META_TTL_S: return c[1] if c[1] is not self._MISSING else default
        r=self.sql('SELECT v FROM meta WHERE k=?',(k,)); v=json.loads(r[0][0]) if r else self._MISSING
        self._meta_cache[k]=(time.monotonic(),v); return default if v is self._MISSING else v
    _MISSING=object()
    # Controls whose value decides whether, and how, real money moves. Every
    # write to one is audited below.
    AUDITED={'master','main_enabled','reversal_enabled','ef_enabled','ev_settings','halt_cleared_at','calibration',
             'stake_settings','next_stake','halt','sx_enabled','tp','sl','rules','ef_cash_floor','ef_engine'}
    def set(self,k,v):
        """Set a meta key, recording who changed a control and from what.

        The lane flags have silently reverted twice on the Tokyo engine with no
        restart and no known cause, and on 09-13 pad_ticks moved from 2 to 1 with
        nobody admitting to it. A bare INSERT OR REPLACE leaves no trace, so
        those events are unreconstructable after the fact. Control writes now
        record old value, new value and the calling frame, which turns "something
        changed it" into a name.
        """
        self._audit(k,v)
        self.sql('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v)))
        self._meta_cache[k]=(time.monotonic(),json.loads(json.dumps(v)))
    def _audit(self,k,v):
        """Record old value, new value and the calling frame for a control.

        [:-2] drops this frame AND its caller (`set` or `set_many`), so the last
        entry is the code that actually asked for the change - the same frame the
        single-key path recorded before this was factored out.
        """
        if k not in self.AUDITED: return
        try:
            old=self.get(k)
            if old!=v:
                import traceback
                where=[f'{f.filename.rsplit("/",1)[-1]}:{f.lineno} {f.name}'
                       for f in traceback.extract_stack()[:-2][-4:]]
                self.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),0,json.dumps(dict(
                    reason='control_write',key=k,old=old,new=v,stack=where))))
        except Exception: pass
    def set_many(self,updates):
        """Several controls in ONE transaction, each one audited.

        `/api/controls/apply` wrote its updates with a bare INSERT OR REPLACE so
        that master and the stake bundle land together. That kept them atomic and
        also bypassed `set()`, which is where the audit lives.

        Found 09-13: every `master` row in the journal is True -> False - twelve
        safe-startup writes and one wipeout - and there has never been a single
        False -> True, not the operator's arming and not any re-arm after a
        deploy. An audit built to answer "who turned this on", after the lane
        flags reverted twice with no known cause, had never once recorded
        anything being turned ON. This keeps the atomicity and closes that.
        """
        for k,v in updates.items(): self._audit(k,v)
        with self.lock,self.c:
            for k,v in updates.items():
                self.c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v)))
        for k,v in updates.items(): self._meta_cache[k]=(time.monotonic(),json.loads(json.dumps(v)))
    def reserve(self,ep,d,token,condition,kind='EF'):
        with self.lock,self.c:
            return self.c.execute('''INSERT OR IGNORE INTO signals(epoch,ts,side,token,condition_id,decision,status,kind)
                                     VALUES(?,?,?,?,?,?,?,?)''',
                (ep,time.time(),d['side'],token,condition,json.dumps(d),'RESERVED',kind)).rowcount==1
    def status(self,ep,status,kind='EF'): self.sql('UPDATE signals SET status=? WHERE epoch=? AND kind=?',(status,ep,kind))
    # Outcomes where nothing was ever sent to the venue. A candle that ends in
    # one of these has NOT been traded, so holding the reservation until the
    # candle closes throws away every later chance in it.
    # BUDGET (12.9.0): the post would have had under Executor.POST_FLOOR_S to
    # live, so it was not sent. Same shape as DEADLINE.
    NO_ORDER_SENT={'SKIPPED','DEADLINE','SIGNAL_CHANGED','EV_CHANGED','PREPARE_FAILED','BUDGET'}
    MAX_ATTEMPTS_PER_CANDLE=4
    def release(self,ep,status,kind='EF'):
        """Mark the attempt and free the candle if nothing was sent.

        The reservation is a PRIMARY KEY(epoch,kind) row, so one refused attempt
        used to consume the whole candle: the signal showed as fired, no trade
        happened, and a later realignment inside the same five minutes could not
        fire again. Bounded at MAX_ATTEMPTS_PER_CANDLE so a repeatedly refused
        candle cannot spin.
        """
        self.status(ep,status,kind)
        if status not in self.NO_ORDER_SENT: return False
        with self.lock,self.c:
            # The count cannot live on the signals row: re-arming deletes it, so
            # the counter would reset every time and the candle would spin.
            row=self.c.execute('SELECT n FROM candle_attempts WHERE epoch=? AND kind=?',(ep,kind)).fetchone()
            n=(row[0] if row else 0)+1
            self.c.execute('INSERT OR REPLACE INTO candle_attempts VALUES(?,?,?)',(ep,kind,n))
            if n>=self.MAX_ATTEMPTS_PER_CANDLE:
                self.c.execute('UPDATE signals SET attempts=? WHERE epoch=? AND kind=?',(n,ep,kind))
                return False
            # 12.15.3: never delete a signals row while an order on that candle can
            # still be alive at the venue.
            #
            # reconcile() and grade() both INNER JOIN orders to signals, so an order
            # orphaned by this DELETE can never be reconciled and its epoch can never
            # be graded - it would hold its reserve until it aged into `phantom` and
            # block grading forever. Today that cannot happen: every one of the 41
            # orphaned epochs in the live journal is REJECTED, because the only path
            # that reaches here after a post is the retryable-rejection branch. But
            # nothing in the code enforced that - one new `continue` after a
            # non-terminal post and this becomes a permanently stranded live order.
            # So make the invariant explicit rather than incidental.
            alive=self.c.execute("SELECT count(*) FROM orders WHERE epoch=? AND coalesce(kind,'EF')=?"
                                 " AND status IN ('SUBMITTING','UNKNOWN','PENDING','FILLED')",
                                 (ep,kind)).fetchone()[0]
            self.c.execute('UPDATE signals SET attempts=? WHERE epoch=? AND kind=?',(n,ep,kind))
            if alive:
                self.c.execute('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(
                    reason='rearm_refused_order_alive',kind=kind,after=status,attempt=n,orders=alive))))
                return False
            self.c.execute('DELETE FROM signals WHERE epoch=? AND kind=?',(ep,kind))
            self.c.execute('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(
                reason='candle_rearmed',kind=kind,after=status,attempt=n))))
        return True
    def order(self,oid,ep,n,plan,timing=None,kind='EF',lane=None):
        self.sql('''INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,timing_json,request_reached,reconcile_count,venue_live,kind,lane)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(oid,ep,n,'SUBMITTING',json.dumps(plan),time.time(),None,None,json.dumps(timing or {}),0,0,0,kind,lane or self.lane))
    def order_status(self,oid,status,reason=None,latency=None,*,error=None,timing=None,request_reached=None,venue_live=None):
        fields=['status=?','reason=?','latency=coalesce(?,latency)']; vals=[status,reason,latency]
        if error is not None: fields.append('error_json=?'); vals.append(json.dumps(error,ensure_ascii=False))
        if timing is not None: fields.append('timing_json=?'); vals.append(json.dumps(timing))
        if request_reached is not None: fields.append('request_reached=?'); vals.append(1 if request_reached else 0)
        if venue_live is not None: fields.append('venue_live=?'); vals.append(1 if venue_live else 0)
        vals.append(oid); self.sql('UPDATE orders SET '+','.join(fields)+' WHERE id=?',tuple(vals))
    def reconcile_touch(self,oid,venue_live=False):
        self.sql('UPDATE orders SET reconcile_count=reconcile_count+1,last_reconcile=?,venue_live=? WHERE id=?',(time.time(),1 if venue_live else 0,oid))
    def fill(self,oid,ep,tid,f,basis):
        self.sql('''INSERT OR IGNORE INTO fills(id,order_id,epoch,shares,spent,fees,price,basis,fee_basis,fee_rate_bps)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',
                 (tid,oid,ep,f['shares'],f['spent'],f['fees'],f['price'],basis,
                  f.get('fee_basis'),f.get('fee_rate_bps')))
    def grade(self,ep,actual):
        if actual not in ('UP','DOWN'): return
        with self.lock,self.c:
            if self.c.execute("SELECT 1 FROM orders WHERE epoch=? AND status IN ('SUBMITTING','UNKNOWN','PENDING')",(ep,)).fetchone(): return
            # Each lane is graded on its own fills: MAIN and REVERSAL can hold
            # opposite sides of the same candle, so summing them together would
            # net a hedge into a single meaningless number.
            rows=self.c.execute('''SELECT s.kind,s.side,sum(f.shares),sum(f.spent+f.fees),coalesce(o.lane,?) lane
                                   FROM signals s JOIN orders o ON o.epoch=s.epoch AND coalesce(o.kind,'EF')=s.kind
                                   JOIN fills f ON f.order_id=o.id
                                   WHERE s.epoch=? GROUP BY s.kind,s.side,coalesce(o.lane,?)''',(self.lane,ep,self.lane)).fetchall()
            if not rows: return
            # 12.21.0: pnl/payout are this journal's own lane (LIVE on a live process); shadow_* are
            # the paper broker's fills on the same candle. On a paper process both are the same fills.
            def tot(lane):
                R=[r for r in rows if r[4]==lane]
                return sum((r[2] if r[1]==actual else 0) for r in R),sum(r[3] for r in R)
            payout,staked=tot(self.lane); sp,ss=tot('PAPER')
            self.c.execute('INSERT OR IGNORE INTO results(epoch,actual,payout,pnl,ts,shadow_payout,shadow_pnl) VALUES(?,?,?,?,?,?,?)',
                           (ep,actual,payout,payout-staked,time.time(),sp,sp-ss))
    def venue_snapshot(self,truth):
        if not isinstance(truth,dict): return
        self.sql('INSERT OR REPLACE INTO venue_state VALUES(?,?,?,?,?,?,?,?)',(
            float(truth.get('ts') or time.time()),truth.get('cash'),truth.get('portfolio_value'),
            truth.get('open_value'),truth.get('realized_pnl'),truth.get('unrealized_pnl'),
            truth.get('fees_paid'),
            # default=str so an unserialisable SDK value cannot abort the write.
            # When this raised, the whole venue snapshot was lost inside the
            # loop's exception handler and the reported PnL silently stayed on
            # the local basis.
            json.dumps(truth.get('account_pnl') or {},ensure_ascii=False,default=str)))
    def apply_venue_pnl(self,positions):
        """Write Polymarket's own per-position PnL onto the settled rows.

        Matched by condition_id through the signal that opened the epoch, so the
        number attributed to a candle is the venue's, not ours."""
        by_condition={}
        for p in positions or []:
            c=p.get('condition_id')
            if not c: continue
            a=by_condition.setdefault(c,dict(realized=0.,total=0.,fees=0.,value=0.))
            a['realized']+=p.get('realized_pnl') or 0.; a['total']+=p.get('total_pnl') or 0.
            a['fees']+=p.get('entry_fees') or 0.; a['value']+=p.get('current_value') or 0.
        if not by_condition: return 0
        rows=self.sql('''SELECT DISTINCT r.epoch,s.condition_id FROM results r JOIN signals s USING(epoch)
                         WHERE s.condition_id IS NOT NULL''')
        n=0
        for row in rows:
            a=by_condition.get(row['condition_id'])
            if not a: continue
            self.sql('''UPDATE results SET venue_pnl=?,venue_realized_pnl=?,venue_fees=?,venue_value=?,
                        venue_ts=?,pnl_basis='VENUE_POSITION_PNL' WHERE epoch=?''',
                     (a['total'],a['realized'],a['fees'],a['value'],time.time(),row['epoch']))
            n+=1
        return n
    def conditions_awaiting_venue(self,limit=60):
        """Markets with a settled row the venue has not yet priced.

        Passed to the positions query so attaching PnL to a settled candle costs
        one narrow lookup instead of paging the whole position history.
        """
        rows=self.sql('''SELECT DISTINCT s.condition_id FROM results r JOIN signals s USING(epoch)
                         WHERE r.venue_pnl IS NULL AND s.condition_id IS NOT NULL
                         ORDER BY r.epoch DESC LIMIT ?''',(int(limit),))
        return [r['condition_id'] for r in rows if r['condition_id']]
    def venue_metrics(self):
        """Wins, losses and PnL from the venue's numbers only. Rows the venue has
        not priced yet are excluded rather than back-filled from local math."""
        r=self.sql('''SELECT count(*) n,coalesce(sum(venue_pnl>0),0) w,coalesce(sum(venue_pnl<0),0) l,
                      coalesce(sum(venue_pnl),0) pnl FROM results WHERE venue_pnl IS NOT NULL''')[0]
        n=r['n'] or 0
        return dict(n=n,wins=r['w'],losses=r['l'],pnl=r['pnl'],
                    accuracy=(r['w']/n if n else None),basis='VENUE_POSITION_PNL')
    def pnl_divergence(self):
        """Largest gap between the venue figure and our local one, if any."""
        r=self.sql('''SELECT count(*) n,coalesce(max(abs(venue_pnl-pnl)),0) worst,
                      coalesce(sum(venue_pnl-pnl),0) total FROM results WHERE venue_pnl IS NOT NULL''')[0]
        return dict(compared=r['n'] or 0,worst_abs=r['worst'],total_delta=r['total'])
    def lane_metrics(self):
        """12.20.0: settled wins / losses / pnl PER LANE, from that lane's own fills. `results` is one
        row per epoch (the net across lanes), so the dashboard's MAIN and REVERSAL cards, which were
        handed empty dicts, showed 0 W / 0 L forever while the lane traded (owner, 09-22 12:53 BST:
        "Why no shadow grading here??"). A lane's candle is a win when its side is the venue's actual."""
        rows=self.sql('''SELECT s.kind kind,s.epoch epoch,s.side side,r.actual actual,sum(f.shares) sh,sum(f.spent+f.fees) cost,coalesce(o.lane,?) lane
                         FROM results r JOIN signals s USING(epoch)
                         JOIN orders o ON o.epoch=s.epoch AND coalesce(o.kind,'EF')=s.kind
                         JOIN fills f ON f.order_id=o.id
                         WHERE r.actual IN ('UP','DOWN') GROUP BY s.kind,s.epoch,coalesce(o.lane,?)''',(self.lane,self.lane))
        out={}
        for r in rows:
            # 12.21.0: real = fills the venue took (LIVE), shadow = the paper broker's (PAPER)
            m=out.setdefault(r['kind'] or 'EF',dict(real=dict(n=0,wins=0,losses=0,pnl=0.),shadow=dict(n=0,wins=0,losses=0,pnl=0.)))
            b=m['real'] if r['lane']=='LIVE' else m['shadow']
            pnl=((r['sh'] or 0.) if r['side']==r['actual'] else 0.)-(r['cost'] or 0.)
            b['n']+=1; b['wins']+=int(pnl>0); b['losses']+=int(pnl<=0); b['pnl']+=pnl
        for m in out.values():
            for b in (m['real'],m['shadow']): b['accuracy']=(b['wins']/b['n'] if b['n'] else None)
        return out
    def metrics_for(self,lane):
        """12.21.4: settled candles that carry fills of ONE lane ('LIVE' or 'PAPER'), with that lane's
        pnl column: results.pnl is this journal's own lane, results.shadow_pnl is the paper broker's."""
        col='pnl' if lane==self.lane else 'shadow_pnl'
        n,w,l,pnl=self.sql(f'''SELECT count(*),coalesce(sum({col}>0),0),coalesce(sum({col}<0),0),coalesce(sum({col}),0) FROM results
                               WHERE epoch IN (SELECT o.epoch FROM orders o JOIN fills f ON f.order_id=o.id WHERE coalesce(o.lane,?)=?)''',(self.lane,lane))[0]
        return dict(n=n,wins=w,losses=l,pnl=pnl,accuracy=w/n if n else None)
    def metrics(self):
        n,w,l,pnl=self.sql('SELECT count(*),coalesce(sum(pnl>0),0),coalesce(sum(pnl<0),0),coalesce(sum(pnl),0) FROM results')[0]
        return dict(n=n,wins=w,losses=l,pnl=pnl,accuracy=w/n if n else None)
    def rolling(self,windows=(20,40)):
        """Rolling health over the most recent settled results. Observes only.

        Everything the engine reported was cumulative - total PnL, PnL by kind,
        the day - and a cumulative total hides a turn: a run that made money for
        two days and is losing now still reads as "up" until the whole gain is
        gone. The operator asked why that was not being observed. It was not.

        Changes no behaviour: gates nothing, sizes nothing, refuses nothing.

        Lane attribution is deliberately conditional. `results` has no `kind` -
        it is one row per epoch - so when two lanes trade the same candle their
        shared PnL cannot be split, and a naive join would count it twice. The
        per-lane block is therefore emitted only for windows with no mixed
        epoch, and `mixed_epochs` says how many were dropped.
        """
        rows=self.kill_window()
        def cut(rs):
            if not rs: return None
            staked=sum(r['staked'] or 0 for r in rs)
            px=sorted(r['px'] for r in rs if r['px'] is not None)
            wins=sum(1 for r in rs if (r['pnl'] or 0)>0)
            return dict(n=len(rs),wins=wins,accuracy=wins/len(rs),
                        pnl=sum(r['pnl'] or 0 for r in rs),
                        per_dollar=(sum(r['pnl'] or 0 for r in rs)/staked) if staked else None,
                        median_price=(px[len(px)//2] if px else None),
                        # Under the bar is marked, never silently read as a rate.
                        sufficient=len(rs)>=60)
        out={'all':{},'by_kind':{},'mixed_epochs':sum(1 for r in rows if (r['kinds'] or 1)>1)}
        for w in windows:
            win=rows[:w]
            out['all'][w]=cut(win)
            if any((r['kinds'] or 1)>1 for r in win):
                out['by_kind'][w]=None      # unattributable, not zero
                continue
            out['by_kind'][w]={k:cut([r for r in win if r['kind']==k])
                               for k in sorted({r['kind'] for r in win})}
        # Distance to each kill rule, so the safety net is visible before it trips.
        unit=[(r['pnl'] or 0)/r['staked'] for r in rows[:20] if r['staked']]
        out['kill']=dict(unit_return_sum=(sum(unit) if len(unit)==20 else None),
                         unit_return_limit=-3.0,
                         results_until_armed=max(0,20-len(rows)),
                         armed=len(rows)>=20)
        # PER LANE TOO. halt_check enforces per lane as of 12.5.1, and reporting
        # only the blended figure would leave the engine acting on one number
        # while the operator reads another - the same shape as the hardcoded
        # dashboard build string that said 12.4.4 while 12.4.6 was running.
        # Whatever the rule enforces is what the screen must show.
        out['kill']['by_kind']={}
        for k in sorted({r['kind'] for r in rows if (r['kinds'] or 1)==1}):
            own=[(r['pnl'] or 0)/r['staked'] for r in rows
                 if (r['kinds'] or 1)==1 and r['kind']==k and r['staked']][:20]
            out['kill']['by_kind'][k]=dict(
                n=len(own), unit_return_sum=(sum(own) if len(own)==20 else None),
                results_until_armed=max(0,20-len(own)), armed=len(own)>=20)
        return out
    ABSENT_GRACE_S=5.0
    ABSENT_CONFIRMATIONS=2
    def mark_venue_open(self,open_ids,now=None):
        """Cross-check every unresolved local order against the venue's open orders.

        The local reserve is the only number on the dashboard that the venue does
        not publish, so it is the one that can drift. An order we recorded as
        PENDING that the venue does not list, and that produced no trade, is not
        holding venue funds - it is a local row outliving the thing it described.

        A single absence proves nothing: there is a real race between our submit
        and the order appearing in the listing. Release requires the order to be
        older than the grace period AND absent on consecutive checks, the same
        standard the reconciler applies before declaring a no-fill.
        """
        if open_ids is None: return 0
        now=time.time() if now is None else now
        ids=set(str(x) for x in open_ids)
        rows=self.sql("SELECT id,ts FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")
        touched=0
        for r in rows:
            if str(r['id']) in ids:
                self.sql('UPDATE orders SET venue_absent=0,venue_live=1,venue_checked=? WHERE id=?',(now,r['id']))
            elif (now-float(r['ts'] or 0))>=self.ABSENT_GRACE_S:
                self.sql('UPDATE orders SET venue_absent=venue_absent+1,venue_live=0,venue_checked=? WHERE id=?',(now,r['id']))
            touched+=1
        return touched
    def reserve_detail(self):
        """The reserve split by what the venue can actually confirm.

        confirmed  the venue lists this order as open
        unverified we have not yet proved it either way (inside the grace period)
        phantom    repeatedly absent from the venue with no fill; not real money
        """
        rows=self.sql('''SELECT id,status,venue_live,coalesce(venue_absent,0) absent,venue_checked,ts,
                         coalesce(json_extract(plan,'$.budget'),0) budget,
                         (SELECT count(*) FROM fills f WHERE f.order_id=orders.id) fills
                         FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING') AND coalesce(lane,?)=?''',(self.lane,self.lane))
        out=dict(confirmed=0.0,unverified=0.0,phantom=0.0,rows=len(rows),phantom_ids=[])
        for r in rows:
            b=float(r['budget'] or 0)
            if r['venue_checked'] is None: out['unverified']+=b
            elif r['venue_live']: out['confirmed']+=b
            elif r['absent']>=self.ABSENT_CONFIRMATIONS and not r['fills']:
                out['phantom']+=b; out['phantom_ids'].append(r['id'])
            else: out['unverified']+=b
        out['total']=out['confirmed']+out['unverified']+out['phantom']
        out['effective']=out['confirmed']+out['unverified']
        return out
    def live_reserve(self,venue_verified=True):
        """Funds to hold back before sizing the next order.

        With venue_verified, an order the venue has repeatedly denied holding is
        excluded, so a dead local row cannot shrink what you are able to trade.
        """
        if not venue_verified:
            return float(self.sql("SELECT coalesce(sum(json_extract(plan,'$.budget')),0) FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")[0][0] or 0)
        return self.reserve_detail()['effective']
    def kill_window(self):
        """The settled rows the kill rule acts on. ONE query, shared.

        Three times on 09-13 the thing that ACTS and the thing that is DISPLAYED
        were changed separately and drifted apart: the hardcoded 12.4.4 header
        against a meta reading 12.4.6; halt_check enforcing per-lane while
        rolling() still showed the blend; and halt_check honouring the fresh
        window after a clear while rolling() showed the stale one - which made
        the dashboard say EF was armed at -4.46 minutes after the clear had in
        fact reset enforcement. An operator reading that would have concluded the
        clear failed, which is the wrong direction for a safety display to lie in.

        So there is no second query to drift. Both callers take these rows, and
        a test asserts they report the same thing.
        """
        since=float(self.get('halt_cleared_at') or -1.0)
        return [dict(x) for x in self.sql("""
            SELECT r.epoch, r.pnl,
                   sum(f.spent+f.fees) staked,
                   sum(f.spent)/nullif(sum(f.shares),0) px,
                   r.pnl/sum(f.spent+f.fees) unit,
                   count(DISTINCT coalesce(o.kind,'EF')) kinds,
                   min(coalesce(o.kind,'EF')) kind
            FROM results r
            JOIN fills f ON f.epoch=r.epoch
            JOIN orders o ON o.id=f.order_id
            WHERE r.pnl IS NOT NULL AND r.ts>?
            GROUP BY r.epoch ORDER BY r.epoch DESC""",(since,))]
    # 12.9.0: halt_check is watch-only (12.8.8) yet ran ~4 SELECTs incl. the
    # 3-table kill_window join once a second from Executor.reconcile. Callers on
    # a loop pass every_s; a bare call (tests, operator tooling) always runs.
    HALT_CHECK_EVERY_S=60.0
    def halt_check(self,every_s=0.0):
        now=time.monotonic()
        if every_s and self._halt_checked_at is not None and now-self._halt_checked_at<every_s: return False
        self._halt_checked_at=now
        # Only what has happened SINCE the operator last cleared a kill.
        #
        # Without this the reset does not reset. The window is the last 20
        # settled results, clearing `halt` does not change those results, and no
        # new result can arrive while every lane is blocked - so halt_check
        # re-fires on the very next reconcile pass, about a second later. Proved
        # on 09-13: clear -> None -> 'EF: 20 settled unit returns sum below -3'.
        # 12.4.1 added clear-halt because "a kill switch with no reset is an
        # outage"; the reset itself was still an outage.
        #
        # So a clear starts a FRESH window and the rule cannot fire again until
        # 20 results have settled after it. That is deliberately weaker: the lane
        # gets up to 20 more trades before it can stop itself. It is the price of
        # having a reset at all, and the operator takes it knowingly when they
        # clear.
        # Measured against the ask that was on the book immediately before submit,
        # which is the price the fill can fairly be judged against. The signal
        # quote can be hundreds of milliseconds older and flatters the number.
        # -1 rather than 0: a row with ts=0 must still count toward a KILL rule.
        # Silently dropping any settled result from a safety check is the wrong
        # failure direction, and `> 0` would have excluded exactly those rows.
        since=float(self.get('halt_cleared_at') or -1.0)
        r=self.sql('''SELECT sum(f.spent)/sum(f.shares)-min(coalesce(json_extract(o.plan,'$.pre_submit_quote'),
                      json_extract(o.plan,'$.quote'))) FROM fills f JOIN orders o ON o.id=f.order_id
                      WHERE o.ts>? GROUP BY f.epoch ORDER BY f.epoch DESC LIMIT 20''',(since,))
        # A NULL group makes sum() raise TypeError, which is unguarded all the
        # way up through reconcile_loop and gather() and would exit the process
        # holding open positions. Currently armed and unfired: the live DB has 13
        # results, and this needs 20.
        vals=[x[0] for x in r if x[0] is not None]
        # 12.8.8: WATCHED, never acted on. User, 09-13 23:5x, on seeing the
        # kill rule described: "kill ?? bro we don't need that, what i said was
        # you will turn off master when it will run out of money, it doesn't
        # mean you write a code block for that in model". Same correction as
        # 12.8.3 (LOW_BALANCE): the rule was for the operator to watch, and it
        # had been written into the engine. So the three conditions are still
        # computed - slippage over the last 20 fills, the blended 20-result unit
        # sum, and each lane's own 20-result unit sum - and each writes ONE
        # KILL_CONDITION diagnostics row per episode with the number in it,
        # `acted:false`. `halt` is never written here. The only engine-set halt
        # left is the order-identity mismatch in Executor.fire, an integrity
        # stop, not a PnL rule. rolling()['kill'] still shows every condition,
        # from the same kill_window() rows, so the screen and this method
        # cannot drift (12.5.x lesson) - it just no longer stops anything.
        #
        # Per-lane, not blended, is still the right arithmetic (see 12.5.1): an
        # epoch traded by two lanes cannot be attributed to either and is left
        # out of the per-lane windows rather than counted twice.
        conds={}
        if len(vals)==20: conds['SLIPPAGE']=(sum(vals)/20>.03, dict(avg_slippage=sum(vals)/20,n=20,limit=.03))
        rows=self.kill_window()
        blended=[x['unit'] for x in rows[:20] if x['unit'] is not None]
        if len(blended)==20: conds['ALL']=(sum(blended)<-3, dict(unit_sum=sum(blended),n=20,limit=-3.0))
        for k in sorted({x['kind'] for x in rows if (x['kinds'] or 1)==1}):
            own=[x['unit'] for x in rows
                 if (x['kinds'] or 1)==1 and x['kind']==k and x['unit'] is not None][:20]
            if len(own)==20: conds[k]=(sum(own)<-3, dict(unit_sum=sum(own),n=20,limit=-3.0))
        # One row per episode: a condition that clears (or whose window empties,
        # e.g. after the operator clears halt_cleared_at) re-arms its report.
        for rule in list(self._kill_reported):
            if not conds.get(rule,(False,))[0]: self._kill_reported.discard(rule)
        for rule,(hit,info) in conds.items():
            if hit and rule not in self._kill_reported:
                self._kill_reported.add(rule)
                self.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),0,json.dumps(dict(
                    kind='KILL_CONDITION',rule=rule,acted=False,**info))))
        return True

class PaperBroker:
    # Fills whatever the ladder holds, so the pre-send depth check does not apply.
    all_or_nothing=False
    basis='PAPER_DEPTH_FEE_ESTIMATE'
    def __init__(self,books,db=None): self.books=books; self.db=db; self.pending={}
    async def prepare(self,token,plan):
        oid='paper-'+uuid.uuid4().hex; return (oid,token,plan),oid
    async def post(self,signed):
        oid,token,plan=signed; q=self.books.quote(token)
        f=walk_book(q,plan) if q else None
        if not f or not f['shares']: return {'rejected':{'class':'PaperReject','message':'fak_not_filled','code':'fak_not_filled','request_reached':True}}
        if self.db:
            ep=self.db.sql('SELECT epoch FROM orders WHERE id=?',(oid,))[0][0]; self.db.fill(oid,ep,oid,f,self.basis)
        else: self.pending[oid]=f
        return {'id':oid}
    async def reconcile(self,r):
        f=self.pending.pop(r['id'],None)
        return dict(terminal=True,fills=[(r['id'],f)] if f else [],live=False,verified_no_fill=not bool(f))
    async def keepalive(self): return None   # 12.19.0: no connection to keep warm


class Executor:
    # 12.19.0: after a retryable reject, re-price on a book that has CHANGED since
    # the rejected attempt was priced (the reject says the touch moved) - but wait
    # at most this long for the tick, then fire at whatever the book is. Replaces
    # the flat 75 ms sleep (paper's retry_delay_ms): a tick usually arrives well
    # inside 100 ms, and a quiet book no longer costs 75 ms per attempt. 12.8.7's
    # objection to waiting for a tick was an UNBOUNDED wait inside a 2 s budget.
    RETRY_TICK_WAIT_S=0.1
    # 12.9.0, audit_hotpath defect (i): wait_for(post, max(.001, deadline-start))
    # could send a real order with a few-ms timeout - the deadline check runs
    # BEFORE the second reassess (~30 ms) and order_plan - then cancel it in
    # flight and leave UNKNOWN with the reserve held until reconcile proved
    # absence. Under this much budget left the attempt is not posted; the
    # candle is released as BUDGET (re-arms like DEADLINE) and the timing kept.
    POST_FLOOR_S=0.4
    def __init__(self,db,books,broker,age=.75,pad=1,budget_s=2.0,post_timeout_s=1.2,attempts=4,shadow=None):
        self.db=db; self.books=books; self.broker=broker; self.age=age; self.pad=pad; self.band=False
        # 12.21.0: with a shadow (paper) broker beside a live one, `master` picks the broker per
        # fire: OFF -> shadow, lane 'PAPER'; ON -> broker, lane = the journal's ('LIVE'). Owner,
        # 09-22: "if master off it's paper and if master on it's live it's that simple". Without a
        # shadow (paper process, tests) the single broker is used whatever master says.
        self.shadow=shadow
        # A venue that fills partially does not need the pre-send depth check.
        self.require_depth=getattr(broker,'all_or_nothing',True)
        self._stuck_reported=set()   # 12.8.11: (order id, reason head) already written as RECONCILE_STUCK
        # v12.1 hardcoded a 2.0s total budget and a 1.2s post timeout. Both are
        # fine beside the venue and too tight from a distant region: three
        # attempts of sign + round trip do not fit in 2s when one round trip is
        # 300ms. They are settings now, so a deployment can be given a budget
        # that matches its measured latency instead of silently running out of
        # time and recording DEADLINE.
        self.budget_s=float(budget_s); self.post_timeout_s=float(post_timeout_s)
        self.max_attempts=max(1,int(attempts))
        self.latency_samples=[]
        # 12.19.0: the pre-post check calls this (the dashboard's allowed(kind)) instead of a
        # second full decide. None = no control check before the post (tests, paper harness).
        self.allowed=None
    def _sample(self,timing,outcome):
        """Record one attempt's stage timings.

        v12.1 sampled only accepted submissions, so the published p95 excluded
        every rejection and timeout - exactly the attempts that are slow. Latency
        is recorded for all of them and the outcome is kept alongside so the
        percentiles can be read overall or per outcome."""
        t=dict(timing); t['outcome']=outcome
        self.latency_samples.append(t); self.latency_samples=self.latency_samples[-500:]
    @staticmethod
    def _ambiguous(exc):
        # Transport failures and HTTP 408/5xx can occur after the venue saw the
        # request.  4xx RequestRejectedError (except 408) is explicit rejection.
        if type(exc).__name__=='RequestRejectedError':
            status=getattr(exc,'status',getattr(exc,'status_code',None))
            return status in (None,408) or (isinstance(status,int) and status>=500)
        return type(exc).__name__ in {'TransportError','TimeoutError','ConnectionLostError','UnexpectedResponseError'} or isinstance(exc,(asyncio.TimeoutError,TimeoutError,ConnectionError,OSError))
    async def fire(self,ep,d,token,condition,stake,reassess,kind='EF'):
        if self.db.get('halt') or not self.db.reserve(ep,d,token,condition,kind): return
        fire_start=time.monotonic(); deadline=min(fire_start+self.budget_s,fire_start+ep+240-time.time()); seq=-1; ticked=None
        broker,lane=self.route()
        for n in range(1,self.max_attempts+1):
            timing={'attempt':n,'signal_ts_ms':d.get('features',{}).get('ts_ms')}
            if ticked is not None: timing['retry_ticked']=ticked   # 12.19.0: did the book change before this re-price
            t=time.monotonic()
            # Take the CURRENT fresh book. Until 12.8.7 attempts >= 2 waited here
            # for q['seq'] to change - for the book to TICK since the last
            # attempt - inside a 2 s budget. On a quiet book that wait ran the
            # budget out: 82 live orders produced 4 second attempts and 10
            # DEADLINEs, while the paper engine (which takes whatever the book
            # is, sleeps 75 ms and fires again) got three shots inside a second.
            # Task 76 priced the difference at 31 venue rejects worth +0.25/$1.
            # `self.age` still applies: a stale book still waits.
            while time.monotonic()<deadline:
                q=self.books.quote(token,self.age)
                if q: break
                await asyncio.sleep(.005)
            else: self.db.release(ep,'DEADLINE',kind); return
            timing['quote_wait_ms']=1000*(time.monotonic()-t); timing['quote_read_ms']=timing['quote_wait_ms']; timing['book_age_ms']=q['age_ms']; seq=q['seq']
            # Recorded, never gated on. 12.3.2 refused orders above a snapshot-age
            # limit; the AWS session showed that is a seconds-into-candle
            # threshold in disguise - venue() subscribes once per cycle and
            # clears the cache, so snapshot age is ~sec-30 after the rollover and
            # ~300+sec before it. On 28 live orders it refused a HIGHER share of
            # fills than rejects at every limit from 30 s to 300 s (at 90 s: 73%
            # of fills, 53% of rejects), because fills cluster at both ends of
            # the candle. Instrument, do not gate.
            timing['snapshot_age_s']=q.get('snapshot_age_s')
            t=time.monotonic(); new=reassess(); timing['decision_ms']=1000*(time.monotonic()-t)
            if not new.get('fire') or new['side']!=d['side']: self.db.release(ep,'SIGNAL_CHANGED',kind); return
            # What tick we believed, and how long since a tick_size_change on
            # this token. If the engine prices on a grid the venue has just moved
            # off, "no orders found to match" follows - this makes that decidable
            # from the journal rather than inferred.
            _terms=self.books.terms[token]
            timing['believed_tick']=float(_terms[0])
            _tc=getattr(self.books,'tick_changes',{}).get(token)
            timing['since_tick_change_s']=(round(time.monotonic()-_tc['at'],2) if _tc else None)
            timing['last_tick_change']=(_tc.get('new') if _tc else None)
            new=dict(new,min_topup=(lane!='LIVE'))   # 12.21.0: paper/shadow may top up to the venue minimum; live never
            try: plan=order_plan(q,_terms,stake,new,self.pad,band=self.band,require_depth=self.require_depth)
            except (ValueError,KeyError) as e:
                # This one exit is 97% of everything EF loses before the network,
                # and it used to record a bare sentence with no lane and no
                # prices - so the largest loss in the system could not be split
                # by kind at all (diagnostics has ts and epoch only, and one
                # epoch can hold an EF and a MAIN signal at once). Record what
                # makes it decidable: which lane, which side, and the three
                # numbers the EV comparison is made of.
                self.db.release(ep,'SKIPPED',kind)
                self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(
                    reason='order_plan_refused',kind=kind,side=new.get('side'),error=str(e),
                    ask=q.get('ask'),p=new.get('p'),threshold=new.get('threshold'),
                    band=self.band,pad=self.pad,stake=stake)))); return
            timing['signal_quote']=float(d.get('ask',plan['quote'])) if d.get('ask') is not None else plan['quote']
            t=time.monotonic()
            try: signed,oid=await asyncio.wait_for(broker.prepare(token,plan),max(.001,deadline-time.monotonic()))
            except Exception as e:
                info=error_info(e,phase='prepare',request_reached=False)
                self.db.release(ep,'PREPARE_FAILED',kind); self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(info,reason='prepare_failed',kind=kind))))
                print('[order prepare failed]',compact_error(info),flush=True); return
            timing['sign_ms']=1000*(time.monotonic()-t)
            if time.monotonic()>=deadline: self.db.release(ep,'DEADLINE',kind); return
            # A tick during the ~10 ms sign no longer abandons the signed order.
            # The guard that matters is the order_plan(latest, ...) re-check a
            # few lines down: it re-judges EV and depth on the moved book and
            # releases EV_CHANGED if they fail. The signed cap is from q; if the
            # ask moved above it the FAK rejects cheaply, if below it fills
            # better - which is exactly what paper does, and what the old
            # `latest['seq']!=seq: continue` denied: it sent the attempt back to
            # wait for yet another tick.
            latest=self.books.quote(token,self.age)
            if not latest: continue
            plan['pre_submit_quote']=latest['ask']; plan['signal_quote']=timing['signal_quote']
            # 12.19.0: ONE decision per attempt. This was a second full reassess() - for EF a
            # whole decide_now(): model, features, and ui.allowed()'s SELECTs - 1.5-17 ms p50
            # on the live box, run ~10 ms after the first one said fire. What the moved book
            # can change is caught by order_plan(latest) below (EV_CHANGED); what a control
            # can change is caught by allowed(kind). Neither needs the model run again.
            t=time.monotonic(); final=new
            if self.allowed is not None and not self.allowed(kind):
                timing['final_recheck_ms']=1000*(time.monotonic()-t); self.db.release(ep,'SIGNAL_CHANGED',kind); return
            timing['final_recheck_ms']=1000*(time.monotonic()-t)
            try: order_plan(latest,self.books.terms[token],stake,final,self.pad,band=self.band,require_depth=self.require_depth)
            except (KeyError,ValueError): self.db.release(ep,'EV_CHANGED',kind); return
            timing['pre_submit_book_age_ms']=latest['age_ms']; timing['fire_to_submit_ms']=1000*(time.monotonic()-fire_start)
            left=deadline-time.monotonic(); timing['post_budget_left_ms']=1000*left
            if left<self.POST_FLOOR_S:
                timing['total_attempt_ms']=1000*(time.monotonic()-fire_start)
                self.db.release(ep,'BUDGET',kind); self._sample(timing,'BUDGET')
                print(f'[order not sent] BUDGET: {1000*left:.0f} ms left of budget, floor {1000*self.POST_FLOOR_S:.0f} ms; attempt={n} kind={kind}',flush=True); return
            # 12.12.1 (H1's R-18a blocker): one INDEPENDENT book read stamped at submit, so a
            # counterfactual "would price X have filled" is an observation instead of an
            # inference. `quote` and `pre_submit_quote` are set from reads taken milliseconds
            # apart and are identical on 182 of 191 live orders - the same-read trap CLAUDE.md
            # warns about - and neither carries the displayed size, which is what a fill needs.
            # This is a local cache read: no network, no added latency before the post.
            sb=self.books.quote(token,self.age)
            if sb:
                timing['submit_book']=dict(ask=sb.get('ask'),bid=sb.get('bid'),
                    size=(sb['asks'][0][1] if sb.get('asks') else None),
                    age_ms=sb.get('age_ms'),seq=sb.get('seq'),ts_ms=int(time.time()*1000))
            t=time.monotonic(); self.db.order(oid,ep,n,plan,timing,kind,lane); start=time.monotonic()
            # 12.19.0: the honest pre-wire number. fire_to_submit_ms above stops BEFORE the
            # submit_book read and this INSERT; fire_to_wire_ms is stamped as the POST leaves.
            timing['db_order_ms']=1000*(start-t); timing['fire_to_wire_ms']=1000*(start-fire_start)
            try:
                r=await asyncio.wait_for(broker.post(signed),min(self.post_timeout_s,max(.001,deadline-start)))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                elapsed=1000*(time.monotonic()-start); timing['submit_ms']=elapsed; timing['response_ms']=elapsed; timing['network_roundtrip_ms']=elapsed; timing['total_attempt_ms']=1000*(time.monotonic()-fire_start)
                ambiguous=self._ambiguous(e); info=error_info(e,phase='post',request_reached=('UNKNOWN' if ambiguous else False))
                status='UNKNOWN' if ambiguous else 'REJECTED'
                self.db.order_status(oid,status,compact_error(info),elapsed,error=info,timing=timing,request_reached=(None if ambiguous else False))
                self.db.status(ep,'PENDING' if ambiguous else 'REJECTED',kind)
                self._sample(timing,status)
                print(f'[order {status.lower()}] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={elapsed:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                return
            latency=1000*(time.monotonic()-start); timing['submit_ms']=latency; timing['response_ms']=latency; timing['network_roundtrip_ms']=latency; timing['total_attempt_ms']=1000*(time.monotonic()-fire_start)
            ambiguous_response=r.get('ambiguous')
            if ambiguous_response:
                info=ambiguous_response if isinstance(ambiguous_response,dict) else {'class':'AmbiguousResponse','message':str(ambiguous_response),'request_reached':'UNKNOWN'}
                self.db.order_status(oid,'UNKNOWN',compact_error(info),latency,error=info,timing=timing,request_reached=None)
                self.db.status(ep,'PENDING',kind)
                self._sample(timing,'UNKNOWN')
                print(f'[order unknown] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={latency:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                return
            rejected=r.get('rejected')
            if rejected:
                info=rejected if isinstance(rejected,dict) else {'class':'RequestRejected','message':str(rejected),'code':str(rejected),'request_reached':True}
                self.db.order_status(oid,'REJECTED',compact_error(info),latency,error=info,timing=timing,request_reached=True)
                self._sample(timing,'REJECTED')
                print(f'[order rejected] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={latency:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                # error_info() never populates 'code' for this exception - the
                # stored keys are class/message/phase/repr/request_reached/status -
                # so this matched the venue's full sentence against the whitelist,
                # missed, and every unfilled FAK returned instead of retrying. The
                # attempt histogram across 34 live orders was {1: 34}: the entire
                # retry apparatus had never once executed.
                code=' '.join(str(info.get(k) or '') for k in ('code','message','class')).lower()
                # Substring, not equality: the venue sends a whole sentence -
                # "no orders found to match with FAK order. FAK orders are
                # partially filled or killed if no match is found." - which
                # never equalled any whitelist entry, so every one of 20 live
                # rejections took the return branch.
                RETRYABLE=('fak_not_filled','unmatched','market_not_ready',
                           'no orders found to match','partially filled or killed')
                if not any(x in code for x in RETRYABLE):
                    self.db.status(ep,'REJECTED',kind); return
                ticked=await self._await_tick(token,seq,deadline)
                continue
            if r.get('id')!=oid:
                info={'class':'OrderIdentityMismatch','message':f'signed={oid} response={r.get("id")}', 'request_reached':True}
                self.db.set('halt','Order hash mismatch; reconcile before resuming'); self.db.order_status(oid,'UNKNOWN',compact_error(info),latency,error=info,timing=timing,request_reached=True); return
            self.db.order_status(oid,'PENDING',latency=latency,timing=timing,request_reached=True,venue_live=True); self.db.status(ep,'PENDING',kind)
            self._sample(timing,'ACCEPTED')
            return
        self.db.status(ep,'EXHAUSTED',kind)
    def route(self):
        """(broker, lane) for the next order - see __init__ (12.21.0)."""
        if self.shadow is not None and not self.db.get('master',False): return self.shadow,'PAPER'
        return self.broker,getattr(self.db,'lane','PAPER')
    def broker_for(self,lane):
        return self.shadow if (self.shadow is not None and lane=='PAPER' and getattr(self.db,'lane','PAPER')!='PAPER') else self.broker
    async def _await_tick(self,token,seq,deadline):
        """12.19.0: True when the local book changed (seq) since the rejected attempt was
        priced, False when RETRY_TICK_WAIT_S (or the deadline) passed first. Local reads only."""
        end=min(deadline,time.monotonic()+self.RETRY_TICK_WAIT_S)
        while time.monotonic()<end:
            q=self.books.quote(token,self.age)
            if q and q.get('seq')!=seq: return True
            await asyncio.sleep(.002)
        return False
    async def reconcile(self):
        rows=self.db.sql('''SELECT o.*,s.token FROM orders o
                            JOIN signals s ON s.epoch=o.epoch AND s.kind=coalesce(o.kind,'EF')
                            WHERE o.status IN ('SUBMITTING','UNKNOWN','PENDING')''')
        for row in rows:
            r=dict(row)
            try: out=await asyncio.wait_for(self.broker_for(r.get('lane')).reconcile(r),8)
            except Exception as e:
                info=error_info(e,phase='reconcile')
                self.db.reconcile_touch(r['id'],venue_live=False)
                # Do not overwrite the original submission error; leave UNKNOWN until venue truth is established.
                self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),r['epoch'],json.dumps(info)))
                continue
            if out is None: continue
            self.db.reconcile_touch(r['id'],venue_live=bool(out.get('live')))
            if not out.get('terminal') and str(out.get('reason','')).startswith('{'):
                # 12.8.11: a reconcile that RETURNS an error (rather than raising)
                # left no trace for 4,292 attempts. One row per order per reason.
                try:
                    err=json.loads(out['reason']); key=(r['id'],err.get('class'),str(err.get('message'))[:40])
                    if key not in self._stuck_reported:
                        self._stuck_reported.add(key)
                        self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),r['epoch'],json.dumps(dict(kind='RECONCILE_STUCK',order=str(r['id'])[-8:],
                            **{k:err.get(k) for k in ('class','message','phase','status')},reconcile_count=r.get('reconcile_count'),venue_absent=r.get('venue_absent')))))
                except Exception: pass
            for tid,f in out.get('fills',[]): self.db.fill(r['id'],r['epoch'],tid,f,self.broker_for(r.get('lane')).basis)
            if out.get('terminal'):
                has_fill=bool(self.db.sql('SELECT 1 FROM fills WHERE order_id=?',(r['id'],)))
                state='FILLED' if has_fill else 'NO_FILL'
                reason=out.get('reason') or ('venue-confirmed fill' if has_fill else 'venue-confirmed no fill')
                self.db.order_status(r['id'],state,reason,venue_live=False); self.db.status(r['epoch'],state,r['kind'] if 'kind' in r.keys() and r['kind'] else 'EF')
                print(f'[reconcile] id={r["id"]} -> {state}: {reason}',flush=True)
        self.db.halt_check(every_s=self.db.HALT_CHECK_EVERY_S)
    def latency_stats(self):
        def pcts(vals):
            if not vals: return None
            vals=sorted(vals)
            def pct(p): return round(vals[min(len(vals)-1,max(0,round((len(vals)-1)*p)))],1)
            return {'n':len(vals),'p50_ms':pct(.50),'p95_ms':pct(.95),'p99_ms':pct(.99),'max_ms':round(vals[-1],1)}
        S=self.latency_samples
        # 12.19.1: the transport/sign facts do not depend on having fired yet (Zurich: the
        # early return hid them on a fresh paper process). Paper's broker has neither -> None.
        b=getattr(self,'broker',None)
        base={'keepalive_ms':getattr(b,'keepalive_ms',None),'keepalive_age_s':(round(time.monotonic()-b.keepalive_at,1) if getattr(b,'keepalive_at',None) else None),'sign_mode':getattr(b,'sign_mode',None)}
        if not S: return base
        out=dict(base,total=pcts([float(x['total_attempt_ms']) for x in S if x.get('total_attempt_ms') is not None]))
        for stage in ('quote_wait_ms','decision_ms','sign_ms','final_recheck_ms','fire_to_submit_ms','db_order_ms','fire_to_wire_ms','network_roundtrip_ms','book_age_ms'):
            v=[float(x[stage]) for x in S if x.get(stage) is not None]
            if v: out[stage]=pcts(v)
        by={}
        for x in S:
            o=x.get('outcome') or 'UNKNOWN'
            if x.get('total_attempt_ms') is not None: by.setdefault(o,[]).append(float(x['total_attempt_ms']))
        out['by_outcome']={k:pcts(v) for k,v in by.items()}
        t=out.get('total') or {}
        out.update({k:t.get(k) for k in ('n','p50_ms','p95_ms','p99_ms','max_ms')})
        return out
