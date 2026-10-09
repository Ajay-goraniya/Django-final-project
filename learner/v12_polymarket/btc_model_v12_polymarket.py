#!/usr/bin/env python3
"""
btc_model_v12_polymarket.py

Polymarket execution wrapper around the profitable v10 paper signal.

Default is PAPER. Live orders require ALL of:
  --execution live
  --confirm-live-orders
  POLYMARKET_PRIVATE_KEY
  POLYMARKET_DEPOSIT_WALLET
  POLYMARKET_ELIGIBILITY_CONFIRMED=YES

The model/feature logic remains in btc_model_v10.py + model_v10.json.
This file changes venue execution and accounting, not the direction model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import pathlib
import sqlite3
import threading
import time
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import numpy as np
from btc_model_v10 import FEATURES, Model, FeatureState

US = 1_000_000
UA = {"User-Agent": "learner-v12-polymarket/1.0"}
GAMMA = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
MODEL_FEE = 0.07
BUILD = "v12-polymarket-live-guarded"


def model_cost(q: float) -> float:
    return q / (1.0 - MODEL_FEE * (1.0 - q))


def ev_at_price(p_side: float, price: float) -> float:
    c = model_cost(price)
    return p_side * (1.0 / c - 1.0) - (1.0 - p_side)


def http_json(url: str, timeout: int = 8):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def ceil_tick(price: float, tick: float) -> float:
    tick = tick if tick > 0 else 0.01
    p = Decimal(str(price)); t = Decimal(str(tick))
    return float((p / t).to_integral_value(rounding=ROUND_CEILING) * t)


def target_stake(equity: float) -> float:
    if equity < 30:
        return 1.0
    if equity < 40:
        return 2.0
    return float(min(20, 3 + int((equity - 40) // 10)))


def threshold_passes(decision: dict, ev: float) -> bool:
    thr = decision.get("threshold")
    if isinstance(thr, dict):
        return decision.get("p", 0.0) >= float(thr.get("conf_floor", 0.0)) and ev >= float(thr.get("ev_floor", -999.0))
    try:
        return ev >= float(thr)
    except Exception:
        return False


@dataclass
class Quote:
    price: float
    size: float
    age_ms: int
    tick: float


class Store:
    def __init__(self, path: str, reset: bool, initial_equity: float):
        p = pathlib.Path(path)
        if reset and p.exists():
            p.unlink()
        self.con = sqlite3.connect(str(p), check_same_thread=False)
        self.con.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS trades(
          candle_epoch INTEGER PRIMARY KEY,
          signal_ms INTEGER, mode TEXT, execution TEXT, side TEXT, token_id TEXT,
          p REAL, quote_ask REAL, quote_age_ms INTEGER, signal_ev REAL, sec INTEGER, rv60 REAL,
          requested_stake REAL, state TEXT, attempts INTEGER DEFAULT 0,
          order_ids TEXT, trade_ids TEXT,
          raw_notional REAL, filled_shares REAL, avg_fill_price REAL, slippage REAL, fee_rate_bps REAL,
          actual TEXT, win INTEGER, pnl REAL, pnl_per_dollar REAL, graded_ms INTEGER,
          reason TEXT, feat TEXT
        );
        CREATE TABLE IF NOT EXISTS attempts(
          candle_epoch INTEGER, attempt INTEGER, ts_ms INTEGER, quote_ask REAL, quote_age_ms INTEGER,
          tick REAL, cap_price REAL, ev_at_cap REAL, requested_usdc REAL,
          result TEXT, order_id TEXT, latency_ms INTEGER, detail TEXT,
          PRIMARY KEY(candle_epoch, attempt)
        );
        CREATE TABLE IF NOT EXISTS decisions(
          ts_ms INTEGER, candle_epoch INTEGER, sec INTEGER, side TEXT, p REAL, ask REAL, ev REAL, fire INTEGER, feat TEXT
        );
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        self.lock = threading.RLock()
        self.set_meta("build", BUILD)
        if self.get_meta("lane_equity") is None:
            self.set_meta("lane_equity", str(initial_equity))
        if self.get_meta("ladder_stake") is None:
            self.set_meta("ladder_stake", str(target_stake(initial_equity)))
        if self.get_meta("up_target") is None:
            self.set_meta("up_target", "")
        if self.get_meta("up_checks") is None:
            self.set_meta("up_checks", "0")
        if self.get_meta("lane_enabled") is None:
            self.set_meta("lane_enabled", "1")
        if self.get_meta("kill_reason") is None:
            self.set_meta("kill_reason", "")

    def get_meta(self, k: str):
        with self.lock:
            r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return r[0] if r else None

    def set_meta(self, k: str, v: str):
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v)))
            self.con.commit()

    def enabled(self) -> bool:
        return self.get_meta("lane_enabled") == "1"

    def disable(self, reason: str):
        self.set_meta("lane_enabled", "0")
        self.set_meta("kill_reason", reason)

    def stake(self, fixed: float | None = None) -> float:
        if fixed is not None:
            return float(fixed)
        with self.lock:
            eq = float(self.get_meta("lane_equity") or 0)
            cur = float(self.get_meta("ladder_stake") or 1)
            tgt = target_stake(eq)
            if tgt < cur:
                cur = tgt
                self.set_meta("ladder_stake", cur)
                self.set_meta("up_target", "")
                self.set_meta("up_checks", "0")
            elif tgt > cur:
                prev = self.get_meta("up_target") or ""
                n = int(self.get_meta("up_checks") or 0)
                if prev == str(tgt):
                    n += 1
                else:
                    prev, n = str(tgt), 1
                self.set_meta("up_target", prev)
                self.set_meta("up_checks", str(n))
                if n >= 2:
                    cur = tgt
                    self.set_meta("ladder_stake", cur)
                    self.set_meta("up_target", "")
                    self.set_meta("up_checks", "0")
            return float(cur)

    def create_trade(self, **r):
        with self.lock:
            self.con.execute("""
              INSERT OR IGNORE INTO trades(
                candle_epoch,signal_ms,mode,execution,side,token_id,p,quote_ask,quote_age_ms,signal_ev,sec,rv60,
                requested_stake,state,reason,feat)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (r["epoch"], r["signal_ms"], r["mode"], r["execution"], r["side"], r.get("token_id"),
                  r["p"], r["quote_ask"], r.get("quote_age_ms"), r["signal_ev"], r["sec"], r["rv60"],
                  r["requested_stake"], r.get("state", "SIGNALLED"), r.get("reason", ""), r.get("feat")))
            self.con.commit()

    def attempt(self, epoch: int, attempt: int, **r):
        with self.lock:
            self.con.execute("""
              INSERT OR REPLACE INTO attempts(candle_epoch,attempt,ts_ms,quote_ask,quote_age_ms,tick,cap_price,ev_at_cap,
                requested_usdc,result,order_id,latency_ms,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (epoch, attempt, r.get("ts_ms"), r.get("quote_ask"), r.get("quote_age_ms"), r.get("tick"),
                  r.get("cap_price"), r.get("ev_at_cap"), r.get("requested_usdc"), r.get("result"),
                  r.get("order_id"), r.get("latency_ms"), r.get("detail")))
            self.con.commit()

    def mark_execution(self, epoch: int, *, state: str, attempts: int, order_ids=None, trade_ids=None,
                       raw_notional=None, shares=None, avg_fill_price=None, slippage=None, fee_rate_bps=None,
                       reason: str = ""):
        with self.lock:
            self.con.execute("""UPDATE trades SET state=?,attempts=?,order_ids=?,trade_ids=?,raw_notional=?,filled_shares=?,
              avg_fill_price=?,slippage=?,fee_rate_bps=?,reason=? WHERE candle_epoch=?""",
              (state, attempts, json.dumps(order_ids or []), json.dumps(trade_ids or []), raw_notional, shares,
               avg_fill_price, slippage, fee_rate_bps, reason, epoch))
            self.con.commit()

    def decision(self, ts_ms: int, epoch: int, d: dict):
        with self.lock:
            self.con.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)",
              (ts_ms, epoch, d.get("sec"), d.get("side"), d.get("p"), d.get("ask"), d.get("ev"), int(bool(d.get("fire"))), d.get("feat")))
            self.con.commit()

    def ungraded(self, before_epoch: int):
        with self.lock:
            return self.con.execute("""SELECT candle_epoch,side,execution,quote_ask,requested_stake,raw_notional,filled_shares,state
              FROM trades WHERE actual IS NULL AND candle_epoch < ? AND state IN ('PAPER_FILLED','FILLED')""", (before_epoch,)).fetchall()

    def pending_reconcile(self):
        with self.lock:
            return self.con.execute("""SELECT candle_epoch,token_id,quote_ask,requested_stake,order_ids,trade_ids,attempts
              FROM trades WHERE execution='live' AND state IN ('FILL_PENDING','DELAYED')""").fetchall()

    def grade(self, epoch: int, actual: str, win: bool, pnl: float, stake_used: float):
        ppd = pnl / stake_used if stake_used > 0 else None
        with self.lock:
            self.con.execute("UPDATE trades SET actual=?,win=?,pnl=?,pnl_per_dollar=?,graded_ms=? WHERE candle_epoch=?",
                             (actual, int(win), pnl, ppd, int(time.time()*1000), epoch))
            eq = float(self.get_meta("lane_equity") or 0) + pnl
            self.set_meta("lane_equity", str(eq))
            self.con.commit()

    def recent_quality(self, n: int = 20):
        with self.lock:
            slips = [r[0] for r in self.con.execute("SELECT slippage FROM trades WHERE state='FILLED' AND slippage IS NOT NULL ORDER BY candle_epoch DESC LIMIT ?", (n,)).fetchall()]
            ppd = [r[0] for r in self.con.execute("SELECT pnl_per_dollar FROM trades WHERE actual IS NOT NULL AND pnl_per_dollar IS NOT NULL ORDER BY candle_epoch DESC LIMIT ?", (n,)).fetchall()]
        return slips, ppd

    def stats(self):
        with self.lock:
            n,w,pnl,stk = self.con.execute("""SELECT COUNT(*),COALESCE(SUM(win),0),COALESCE(SUM(pnl),0),
              COALESCE(SUM(CASE WHEN raw_notional>0 THEN raw_notional ELSE requested_stake END),0)
              FROM trades WHERE actual IS NOT NULL""").fetchone()
            pend = self.con.execute("SELECT COUNT(*) FROM trades WHERE actual IS NULL AND state IN ('PAPER_FILLED','FILLED','FILL_PENDING','DELAYED')").fetchone()[0]
            fills = self.con.execute("SELECT COUNT(*) FROM trades WHERE state IN ('FILLED','PAPER_FILLED')").fetchone()[0]
            sigs = self.con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            last = self.con.execute("""SELECT candle_epoch,side,quote_ask,p,execution,state,attempts,avg_fill_price,actual,win,pnl
              FROM trades ORDER BY candle_epoch DESC LIMIT 5""").fetchall()
            lat = self.con.execute("SELECT AVG(latency_ms) FROM attempts WHERE result='filled'").fetchone()[0]
        eq = float(self.get_meta("lane_equity") or 0)
        return dict(graded=n,wins=w,accuracy=round(100*w/n,1) if n else None,pnl=round(pnl,2),staked=round(stk,2),
                    roi_pct=round(100*pnl/stk,2) if stk else None,pending=pend,signals=sigs,fills=fills,
                    fill_rate_pct=round(100*fills/sigs,2) if sigs else None,avg_fill_latency_ms=round(lat,1) if lat is not None else None,
                    lane_equity=round(eq,2),lane_enabled=self.enabled(),kill_reason=self.get_meta("kill_reason") or "",
                    ladder_stake=float(self.get_meta("ladder_stake") or 1),
                    last=[dict(epoch=e,side=s,ask=a,p=p,execution=x,state=st,attempts=at,fill=fp,actual=ac,win=wn,pnl=pl)
                          for e,s,a,p,x,st,at,fp,ac,wn,pl in last])


class PolyLiveClient:
    """Thin sync-SDK adapter. It is called through asyncio.to_thread()."""
    def __init__(self):
        try:
            from polymarket import SecureClient
        except Exception as e:
            raise RuntimeError("Live mode needs: pip install 'polymarket-client>=0.9.0,<1'") from e
        pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
        wallet = os.environ.get("POLYMARKET_DEPOSIT_WALLET", "").strip()
        if not pk or not wallet:
            raise RuntimeError("Live mode requires POLYMARKET_PRIVATE_KEY and POLYMARKET_DEPOSIT_WALLET")
        self.client = SecureClient.create(private_key=pk, wallet=wallet)
        if self.client.get_closed_only_mode():
            raise RuntimeError("Polymarket account is in closed-only mode; refusing to arm live entry")

    def close(self):
        try: self.client.close()
        except Exception: pass

    def place(self, token: str, amount: float, cap: float):
        return self.client.place_market_order(token_id=token, side="BUY", amount=str(round(amount,6)),
                                              max_spend=str(round(amount,6)), max_price=str(cap), order_type="FAK")

    def fills(self, token: str, order_ids: list[str], trade_ids: list[str]):
        items = []
        seen = set()
        for tid in trade_ids:
            try:
                page = self.client.list_account_trades(token_id=token, id=tid).first_page()
                for t in page.items:
                    if str(getattr(t,"id", "")) not in seen:
                        seen.add(str(getattr(t,"id", ""))); items.append(t)
            except Exception:
                pass
        if not items and order_ids:
            try:
                page = self.client.list_account_trades(token_id=token).first_page()
                for t in page.items:
                    if str(getattr(t,"taker_order_id", "")) in order_ids and str(getattr(t,"id", "")) not in seen:
                        seen.add(str(getattr(t,"id", ""))); items.append(t)
            except Exception:
                pass
        good = [t for t in items if str(getattr(t,"status", "")) != "FAILED" and as_float(getattr(t,"size",0)) > 0]
        if not good:
            return None
        shares = sum(as_float(getattr(t,"size",0)) for t in good)
        notion = sum(as_float(getattr(t,"size",0))*as_float(getattr(t,"price",0)) for t in good)
        avg = notion/shares if shares > 0 else None
        fee = sum(as_float(getattr(t,"fee_rate_bps",0))*as_float(getattr(t,"size",0)) for t in good)/shares if shares else None
        tids = [str(getattr(t,"id","")) for t in good]
        return dict(raw_notional=notion, shares=shares, avg_price=avg, fee_rate_bps=fee, trade_ids=tids)


class Runner:
    def __init__(self, a):
        self.a = a
        self.m = Model(a.model)
        self.st = FeatureState()
        self.db = Store(a.db, a.reset, a.lane_equity)
        self.age = {"spot":0.0,"perp":0.0,"depth":0.0,"venue":0.0}
        self.msgs = {}
        self._agg = None
        self.market: dict[int, dict|None] = {}
        self.ladders: dict[str,dict] = {}
        self.token_meta: dict[str,dict] = {}
        self.fired = set()
        self.last_decision = {}
        self.started = time.time()
        self.live: PolyLiveClient|None = None
        if a.execution == "live":
            if not a.confirm_live_orders:
                raise RuntimeError("Live mode requires --confirm-live-orders")
            if os.environ.get("POLYMARKET_ELIGIBILITY_CONFIRMED", "").strip().upper() != "YES":
                raise RuntimeError("Live mode requires POLYMARKET_ELIGIBILITY_CONFIRMED=YES")
            self.live = PolyLiveClient()

    async def ws(self,url,handler,name):
        import websockets
        while True:
            try:
                async with websockets.connect(url,ping_interval=20,max_size=2**22) as w:
                    async for msg in w:
                        handler(json.loads(msg)); self.age[name]=time.time(); self.msgs[name]=self.msgs.get(name,0)+1
            except Exception as e:
                print(f"[{name}] reconnect: {type(e).__name__}",flush=True); await asyncio.sleep(2)

    def on_spot(self,j): self.st.on_spot_trade(int(j["T"])*1000,float(j["p"]),float(j["q"]),bool(j["m"]))

    def on_perp(self,j):
        p,q,m,T=float(j["p"]),float(j["q"]),bool(j["m"]),int(j["T"]); k=(T,m,p)
        if self._agg and self._agg[0]==k: self._agg[1]+=q; return
        if self._agg:
            (T0,m0,p0),q0=self._agg; self.st.on_perp_trade(T0*1000,p0,q0,p0*q0*(-1.0 if m0 else 1.0),p0*q0)
        self._agg=[k,q]

    def on_depth(self,j):
        b=[(float(x[0]),float(x[1])) for x in j.get("b",[])][:20]; a=[(float(x[0]),float(x[1])) for x in j.get("a",[])][:20]
        if not b or not a:return
        self.st.on_depth(int(j.get("E",time.time()*1000))*1000,b[0][0],b[0][1],a[0][0],a[0][1],sum(q for _,q in b[:5]),sum(q for _,q in a[:5]),sum(q for _,q in b),sum(q for _,q in a))

    async def resolve_market(self,ep):
        if ep in self.market:return self.market[ep]
        j=await asyncio.to_thread(http_json,GAMMA.format(ep)); info=None
        if j:
            mk=(j[0].get("markets") or [{}])[0]
            try:
                toks=json.loads(mk.get("clobTokenIds") or "[]"); outs=json.loads(mk.get("outcomes") or "[]")
                if outs and str(outs[0]).strip().upper()!="UP": toks=toks[::-1]
                if len(toks)==2:
                    tick=as_float(mk.get("orderPriceMinTickSize") or mk.get("minimumTickSize"),0.01) or 0.01
                    mins=as_float(mk.get("orderMinSize") or mk.get("minimumOrderSize"),0.0)
                    info={"tokens":(str(toks[0]),str(toks[1])),"tick":tick,"min_size":mins,"condition_id":mk.get("conditionId")}
                    for t in info["tokens"]: self.token_meta.setdefault(t,{"tick":tick,"min_size":mins})
            except Exception: info=None
        self.market[ep]=info
        for old in [k for k in self.market if k<ep-1800]: self.market.pop(old,None)
        return info

    def best_quote(self, token: str) -> Quote|None:
        lad=self.ladders.get(token)
        if not lad:return None
        asks=[(p,q) for p,q in lad["asks"].items() if q>0 and 0<p<1]
        if not asks:return None
        p,q=min(asks,key=lambda x:x[0]); age=max(0,int(time.time()*1000-lad.get("ts_ms",0)))
        tick=as_float(self.token_meta.get(token,{}).get("tick"),0.01) or 0.01
        return Quote(p,q,age,tick)

    def _publish_venue(self):
        ep=int(time.time()//300)*300; info=self.market.get(ep)
        if not info:return
        up,dn=info["tokens"]
        def best(tok):
            lad=self.ladders.get(tok)
            if not lad:return (None,None)
            aa=[p for p,q in lad["asks"].items() if q>0 and 0<p<1]; bb=[p for p,q in lad["bids"].items() if q>0 and 0<p<1]
            return (min(aa) if aa else None,max(bb) if bb else None)
        au,bu=best(up); ad,bd=best(dn); self.st.on_venue_quote(au,bu,ad,bd)
        if au is not None or ad is not None:self.age["venue"]=time.time()

    def _apply_ws(self,ev):
        k=ev.get("event_type"); nowms=int(time.time()*1000)
        if k=="book":
            tok=str(ev.get("asset_id")); self.ladders[tok]={"asks":{float(x["price"]):float(x["size"]) for x in ev.get("asks",[])},"bids":{float(x["price"]):float(x["size"]) for x in ev.get("bids",[])},"ts_ms":nowms}
            if ev.get("tick_size"): self.token_meta.setdefault(tok,{})["tick"]=as_float(ev.get("tick_size"),0.01)
            if ev.get("min_order_size"): self.token_meta.setdefault(tok,{})["min_size"]=as_float(ev.get("min_order_size"),0.0)
        elif k=="price_change":
            touched=set()
            for ch in ev.get("price_changes",[]):
                tok=str(ch.get("asset_id")); lad=self.ladders.get(tok)
                if lad is None:continue
                side="asks" if str(ch.get("side","")).upper()=="SELL" else "bids"
                try: price,size=float(ch["price"]),float(ch["size"])
                except Exception:continue
                if size<=0:lad[side].pop(price,None)
                else:lad[side][price]=size
                lad["ts_ms"]=nowms; touched.add(tok)
        else:return
        self.msgs["venue_ws"]=self.msgs.get("venue_ws",0)+1; self._publish_venue()

    async def venue(self):
        import websockets
        while True:
            now=time.time(); ep=int(now//300)*300; cur=await self.resolve_market(ep); nxt=await self.resolve_market(ep+300)
            toks=[t for info in (cur,nxt) if info for t in info["tokens"]]
            if not toks: await asyncio.sleep(5); continue
            try:
                async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
                    await w.send(json.dumps({"assets_ids":toks,"type":"market"}))
                    async def pinger():
                        while True: await asyncio.sleep(5); await w.send("PING")
                    pt=asyncio.create_task(pinger())
                    try:
                        while True:
                            ep_now=int(time.time()//300)*300
                            if ep_now>ep and time.time()-ep_now>=30:break
                            try:m=await asyncio.wait_for(w.recv(),timeout=15)
                            except asyncio.TimeoutError:break
                            if m=="PONG":continue
                            try:d=json.loads(m)
                            except Exception:continue
                            for ev in (d if isinstance(d,list) else [d]):
                                if isinstance(ev,dict):self._apply_ws(ev)
                    finally:pt.cancel()
            except Exception as e:
                print(f"[venue] reconnect: {type(e).__name__}",flush=True); await asyncio.sleep(2)

    def diagnostics(self,ep,now,d):
        try:
            f=self.st.features(ep*US,int(now*US)) or {}; x=np.nan_to_num(np.array([f.get(k,0.0) for k in FEATURES],dtype=float)); zc=(x-self.m.mean)/self.m.scale*self.m.coef
            d["feat"]=json.dumps({k:(None if not np.isfinite(v) else round(float(v),6)) for k,v in f.items()}|{"_contrib":{k:round(float(c),4) for k,c in zip(FEATURES,zc)}})
            top=sorted(zip(FEATURES,zc,x),key=lambda t:-abs(t[1]))[:4]; d["top"]=" ".join(f"{k}={v:.3g}({c:+.2f})" for k,c,v in top)
        except Exception as e:d["feat"]=None;d["top"]=f"diag error {e!r}"

    async def _refresh_fill(self, epoch:int, token:str, quote_ask:float, order_ids:list[str], trade_ids:list[str], attempts:int):
        if not self.live:return False
        f=await asyncio.to_thread(self.live.fills,token,order_ids,trade_ids)
        if not f:return False
        slippage=f["avg_price"]-quote_ask if f["avg_price"] is not None else None
        self.db.mark_execution(epoch,state="FILLED",attempts=attempts,order_ids=order_ids,trade_ids=f["trade_ids"],raw_notional=f["raw_notional"],shares=f["shares"],avg_fill_price=f["avg_price"],slippage=slippage,fee_rate_bps=f["fee_rate_bps"],reason="matched")
        return True

    async def execute_live(self, ep:int, d:dict, token:str, signal_quote:Quote, stake:float):
        assert self.live is not None
        deadline=min(ep+self.a.execution_deadline_sec,time.time()+self.a.retry_window_ms/1000.0)
        order_ids=[]; trade_ids=[]; attempts=0; remaining=stake
        while attempts < self.a.max_attempts and remaining >= self.a.min_retry_usdc and time.time() < deadline:
            q=self.best_quote(token)
            if not q or q.age_ms>self.a.max_quote_age_ms:
                self.db.mark_execution(ep,state="SKIPPED",attempts=attempts,order_ids=order_ids,trade_ids=trade_ids,reason="stale_or_missing_quote"); return
            cap=ceil_tick(q.price+self.a.pad_ticks*q.tick,q.tick); cap=min(cap,1.0-q.tick)
            ev=ev_at_price(float(d["p"]),cap)
            if not threshold_passes(d,ev):
                self.db.mark_execution(ep,state="SKIPPED",attempts=attempts,order_ids=order_ids,trade_ids=trade_ids,reason=f"ev_failed_at_cap:{ev:.4f}"); return
            attempts+=1; t0=time.perf_counter()
            try:
                resp=await asyncio.to_thread(self.live.place,token,remaining,cap)
                lat=int((time.perf_counter()-t0)*1000); ok=bool(getattr(resp,"ok",False))
                if not ok:
                    code=str(getattr(resp,"code","unknown")); msg=str(getattr(resp,"message",""))
                    self.db.attempt(ep,attempts,ts_ms=int(time.time()*1000),quote_ask=q.price,quote_age_ms=q.age_ms,tick=q.tick,cap_price=cap,ev_at_cap=ev,requested_usdc=remaining,result="rejected",latency_ms=lat,detail=f"{code}:{msg}")
                    if code in {"fak_not_filled","unmatched","market_not_ready"} and attempts<self.a.max_attempts:
                        await asyncio.sleep(self.a.retry_delay_ms/1000.0); continue
                    self.db.mark_execution(ep,state="REJECTED",attempts=attempts,order_ids=order_ids,trade_ids=trade_ids,reason=f"{code}:{msg}"); return
                oid=str(getattr(resp,"order_id","")); status=str(getattr(resp,"status","")); tids=[str(x) for x in getattr(resp,"trade_ids",())]
                if oid:order_ids.append(oid)
                trade_ids.extend(t for t in tids if t not in trade_ids)
                result="filled" if tids or status=="matched" else "accepted_pending"
                self.db.attempt(ep,attempts,ts_ms=int(time.time()*1000),quote_ask=q.price,quote_age_ms=q.age_ms,tick=q.tick,cap_price=cap,ev_at_cap=ev,requested_usdc=remaining,result=result,order_id=oid,latency_ms=lat,detail=status)
                self.db.mark_execution(ep,state="FILL_PENDING" if status!="delayed" else "DELAYED",attempts=attempts,order_ids=order_ids,trade_ids=trade_ids,reason=status)
                # Accepted means do NOT submit another order until the fill is reconciled.
                for _ in range(5):
                    if await self._refresh_fill(ep,token,signal_quote.price,order_ids,trade_ids,attempts): return
                    await asyncio.sleep(0.20)
                return
            except Exception as e:
                lat=int((time.perf_counter()-t0)*1000); detail=f"{type(e).__name__}:{e}"
                self.db.attempt(ep,attempts,ts_ms=int(time.time()*1000),quote_ask=q.price,quote_age_ms=q.age_ms,tick=q.tick,cap_price=cap,ev_at_cap=ev,requested_usdc=remaining,result="AMBIGUOUS",latency_ms=lat,detail=detail)
                # Submission may have reached the venue. Never blind-resubmit.
                self.db.mark_execution(ep,state="AMBIGUOUS",attempts=attempts,order_ids=order_ids,trade_ids=trade_ids,reason=detail)
                self.db.disable("ambiguous live order submission; manual reconciliation required")
                print(f"[KILL] ambiguous live submit on {ep}; lane disabled: {detail}",flush=True); return

    async def fire(self,ep,now,d):
        info=self.market.get(ep) or await self.resolve_market(ep)
        if not info:return
        token=info["tokens"][0 if d["side"]=="UP" else 1]; q=self.best_quote(token)
        if not q:return
        stake=self.db.stake(self.a.fixed_stake)
        self.db.create_trade(epoch=ep,signal_ms=int(now*1000),mode=self.a.mode,execution=self.a.execution,side=d["side"],token_id=token,p=d["p"],quote_ask=q.price,quote_age_ms=q.age_ms,signal_ev=d["ev"],sec=d["sec"],rv60=d["rv60"],requested_stake=stake,state="SIGNALLED",feat=d.get("feat"))
        if self.a.execution=="paper":
            self.db.mark_execution(ep,state="PAPER_FILLED",attempts=1,order_ids=[],trade_ids=[],raw_notional=stake,shares=stake/model_cost(q.price),avg_fill_price=q.price,slippage=0.0,fee_rate_bps=700.0,reason="paper_at_ws_ask")
        elif not self.db.enabled():
            self.db.mark_execution(ep,state="DISABLED",attempts=0,reason=self.db.get_meta("kill_reason") or "lane_disabled")
        else:
            await self.execute_live(ep,d,token,q,stake)

    async def decide_loop(self):
        while True:
            now=time.time(); ep=int(now//300)*300
            fresh=all(now-self.age[k]<10 for k in ("spot","perp","venue"))
            warm=(len(self.st.s_ts)>50 and (self.st.s_ts[-1]-self.st.s_ts[0])>=600*US and len(self.st.p_ts)>20 and (self.st.p_ts[-1]-self.st.p_ts[0])>=60*US)
            fresh=fresh and warm
            if fresh and ep not in self.fired and 5<=now-ep<=285:
                d=self.m.decide(self.st,ep*US,int(now*US),mode=self.a.mode,ev_threshold=(self.a.ev if self.a.mode=="pnl" and self.a.ev is not None else None)); self.diagnostics(ep,now,d); self.last_decision=dict(d,epoch=ep,ts=int(now))
                if d.get("fire"):
                    self.fired.add(ep); await self.fire(ep,now,d)
                    print(f"[{time.strftime('%H:%M:%S')}] FIRE {d['side']} p={d['p']} ask={d['ask']} ev={d['ev']} sec={d['sec']} exec={self.a.execution}",flush=True)
                elif now-getattr(self,"_last_dec_log",0)>=15:
                    self._last_dec_log=now; self.db.decision(int(now*1000),ep,d)
            await asyncio.sleep(0.25)

    async def reconcile_loop(self):
        while True:
            if self.live:
                for ep,token,qask,stake,oids,tids,attempts in self.db.pending_reconcile():
                    try: order_ids=json.loads(oids or "[]"); trade_ids=json.loads(tids or "[]")
                    except Exception: order_ids=[];trade_ids=[]
                    await self._refresh_fill(ep,token,qask,order_ids,trade_ids,attempts)
            await asyncio.sleep(3)

    async def grade_loop(self):
        while True:
            now=time.time()
            for ep,side,execution,qask,requested,raw_notional,shares,state in self.db.ungraded(int(now)-390):
                j=await asyncio.to_thread(http_json,GAMMA.format(ep))
                if not j:continue
                mk=(j[0].get("markets") or [{}])[0]
                try:
                    names=json.loads(mk.get("outcomes"));prices=json.loads(mk.get("outcomePrices"));w=[n for n,p in zip(names,prices) if str(p)=="1"]
                except Exception:w=[]
                if len(w)!=1:continue
                actual=w[0].strip().upper();win=(actual==side)
                stake_used=float(raw_notional or requested or 0)
                # Same fee/economic convention as the v10 paper model, but using actual live avg fill when available.
                price=qask
                if execution=="live":
                    with self.db.lock:
                        rr=self.db.con.execute("SELECT avg_fill_price FROM trades WHERE candle_epoch=?",(ep,)).fetchone(); price=(rr[0] if rr and rr[0] else qask)
                pnl=stake_used*((1/model_cost(price)-1) if win else -1.0)
                self.db.grade(ep,actual,win,pnl,stake_used)
                s=self.db.stats();print(f"[{time.strftime('%H:%M:%S')}] SETTLED {ep} {side}->{actual} {'WIN' if win else 'LOSS'} {pnl:+.2f} | acc {s['accuracy']}% pnl {s['pnl']:+.2f}",flush=True)
            self.apply_kills()
            await asyncio.sleep(20)

    def apply_kills(self):
        if self.a.execution!="live" or not self.db.enabled():return
        slips,ppd=self.db.recent_quality(20)
        if len(slips)>=20 and sum(slips)/len(slips)>self.a.kill_slippage:
            self.db.disable(f"20-fill mean slippage {sum(slips)/len(slips):.4f} > {self.a.kill_slippage:.4f}")
        elif len(ppd)>=20 and sum(ppd)/len(ppd)<self.a.kill_pnl_per_dollar:
            self.db.disable(f"20-fill pnl/$ {sum(ppd)/len(ppd):.4f} < {self.a.kill_pnl_per_dollar:.4f}")

    def serve(self):
        r=self
        class H(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_GET(self):
                now=time.time();body=json.dumps(dict(build=BUILD,execution=r.a.execution,mode=r.a.mode,model=str(r.a.model),db=str(r.a.db),uptime_s=int(now-r.started),feed_age_s={k:(round(now-v,3) if v else None) for k,v in r.age.items()},feed_msgs=r.msgs,last_decision=r.last_decision,**r.db.stats()),indent=1).encode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        HTTPServer(("0.0.0.0",self.a.port),H).serve_forever()

    async def main(self):
        threading.Thread(target=self.serve,daemon=True).start();print(f"{BUILD} execution={self.a.execution} mode={self.a.mode} db={self.a.db} status=http://127.0.0.1:{self.a.port}/",flush=True)
        try:
            await asyncio.gather(self.ws("wss://data-stream.binance.vision/ws/btcusdt@aggTrade",self.on_spot,"spot"),self.ws("wss://fstream.binance.com/ws/btcusdt@trade",self.on_perp,"perp"),self.ws("wss://fstream.binance.com/ws/btcusdt@depth20@100ms",self.on_depth,"depth"),self.venue(),self.decide_loop(),self.reconcile_loop(),self.grade_loop())
        finally:
            if self.live: await asyncio.to_thread(self.live.close)


def parse_args():
    ap=argparse.ArgumentParser()
    ap.add_argument("--port",type=int,default=8788);ap.add_argument("--db",default="v12_polymarket.sqlite3");ap.add_argument("--reset",action="store_true")
    ap.add_argument("--mode",default="accuracy",choices=["accuracy","pnl"]);ap.add_argument("--ev",type=float,default=None)
    ap.add_argument("--model",default=str(pathlib.Path(__file__).resolve().parent/"model_v10.json"))
    ap.add_argument("--execution",default="paper",choices=["paper","live"]);ap.add_argument("--confirm-live-orders",action="store_true")
    ap.add_argument("--lane-equity",type=float,default=0.0,help="starting strategy equity; default 0 => $1 ladder stake")
    ap.add_argument("--fixed-stake",type=float,default=None,help="testing override; bypasses ladder")
    ap.add_argument("--pad-ticks",type=int,default=1);ap.add_argument("--max-attempts",type=int,default=3);ap.add_argument("--retry-delay-ms",type=int,default=75)
    ap.add_argument("--retry-window-ms",type=int,default=1800);ap.add_argument("--execution-deadline-sec",type=int,default=242);ap.add_argument("--max-quote-age-ms",type=int,default=5000)
    ap.add_argument("--min-retry-usdc",type=float,default=0.10);ap.add_argument("--kill-slippage",type=float,default=0.03);ap.add_argument("--kill-pnl-per-dollar",type=float,default=-3.0)
    return ap.parse_args()


if __name__=="__main__":
    a=parse_args()
    try:asyncio.run(Runner(a).main())
    except KeyboardInterrupt:print("stopped")
