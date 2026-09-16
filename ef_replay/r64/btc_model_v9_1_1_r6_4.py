#!/usr/bin/env python3
"""BTC Model v9.1.1 — trusted v8.1 GPT core + BTC-only EF Runway v2 + PnL-truth accounting.

The single-file Termux service consumes Binance BTCUSDT ``aggTrade``,
``depth5@100ms`` and ``kline_5m`` streams, preserves the v6.4 signal model,
and submits production Predict.fun orders through the official Python SDK.

v7 execution guarantees:

* Predict.fun order books and authenticated wallet events use WebSockets.
* REST is limited to market discovery, initial book bootstrap, order submission,
  and paced exact-hash recovery after an ambiguous response or reconnect.
* MAIN, REVERSAL and EF use one stake configuration and one win/loss streak.
* The master switch is forced OFF on every launch; MAIN / REVERSAL / EF also
  have persistent individual toggles, and all gates are rechecked before POST.
* Only explicit terminal rejection can cause up to three replacements. A timeout stays
  UNKNOWN and is reconciled by the immutable signed order hash.
* v7.7: settled winnings the venue has not yet auto-claimed still count as
  bankroll for stake sizing, so compounding no longer lags the redemption. They
  never count as funding: an order is still paid for from spendable USDT only.
* v7.7: ``delay_ms`` is the total latency of an order across every replacement,
  with the final attempt reported separately as ``last_attempt_ms``.
* Forbidden signals remain measurable, display as blue ``F`` rows in Data, and
  never add an ``F`` label to the existing candlestick chart.
* No auxiliary learner, external ML package, or separate EF capture store exists.
* v9.1.1 State X is a per-trade execution veto only. OFF has zero execution
  authority while shadow diagnostics continue; there is no blanket timer pause.

Install: ``pip install --upgrade websocket-client 'predict-sdk>=0.0.22'``
Credentials: ``PREDICT_API_KEY``, ``PREDICT_PRIVATE_KEY`` (the exported Privy
wallet key), and ``PREDICT_ACCOUNT_ADDRESS`` (the Predict deposit address).
``PREDICT_JWT`` is optional because v7 obtains and renews it automatically.
Run: ``python btc_model_v9_1_1.py --port 8787``
Test: ``python btc_model_v9_1_1.py --self-test``
Dashboard: ``http://127.0.0.1:8787``
"""

from __future__ import annotations

import argparse
import ast
import base64
import hmac
import csv
import hashlib
import http.client
import io
import json
import math
import random
import os
import queue
import re
import signal
import socket
import ssl
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock
from collections import deque
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

VERSION = "9.1.1"
BUILD_REVISION = "9.1.1-r6.4-true-hot-ef"
BUILD_NUMBER = 11
def _build_stamp() -> Tuple[str, str]:
    """A fingerprint of the file that is actually running.

    Two builds with the same version string are indistinguishable on a phone,
    so an edited file that never reached the device looks exactly like one that
    did. This hashes the source on disk and reports its mtime, which makes a
    stale download or a cached page obvious at a glance.
    """
    try:
        source = Path(__file__).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
        return digest, ""
    except Exception:
        return "unknown", "unknown"


BUILD_SHA, BUILT_AT = _build_stamp()

# --- London wall clock ----------------------------------------------------
# Every human-facing time in this file is Europe/London, never the host's
# clock. A VPS almost always runs UTC, so relying on device time silently
# shifted ban windows and every displayed timestamp by an hour for half the
# year. Europe/London is used rather than a fixed offset because it is GMT in
# winter and BST in summer; a hardcoded +0 or +1 is wrong six months a year.
#
# Internal arithmetic still uses epoch milliseconds and is unaffected: only
# formatting and the ban-rule wall clock are converted.
DISPLAY_TIMEZONE = os.getenv("BTC_MODEL_TZ", "Europe/London").strip()

# --- dashboard exposure ---------------------------------------------------
# Default stays loopback. Binding anywhere else requires a password, enforced
# at startup rather than trusted to the operator, because the controls page has
# no other protection and the signing key sits on the same machine.
DASHBOARD_PASSWORD = os.getenv("BTC_MODEL_PASSWORD", "").strip()
DASHBOARD_MIN_PASSWORD_LEN = 12


def is_loopback_host(host: str) -> bool:
    return str(host).strip() in ("127.0.0.1", "localhost", "::1", "")


class _UKClock(tzinfo):
    """Europe/London without the IANA database.

    Termux and slim server images frequently ship no tzdata, and zoneinfo then
    behaves like UTC. Falling back to UTC would put every displayed time and
    every ban window an hour out for seven months of the year, so this
    implements the rule directly: British Summer Time runs from 01:00 UTC on
    the last Sunday in March to 01:00 UTC on the last Sunday in October.

    Nothing here converts between zones. Calling astimezone() inside utcoffset()
    re-enters this class through the same path and recurses until the stack
    dies, so both branches compare naive fields only, and fromutc is overridden
    so the UTC-side decision never routes through the local-side one.

    zoneinfo is still preferred when present, because it tracks the real
    database if the UK ever changes the rule. This is the safety net.
    """

    _BASE = timedelta(0)
    _SUMMER = timedelta(hours=1)

    @staticmethod
    def _last_sunday(year: int, month: int, hour: int) -> datetime:
        day = 31                      # March and October both have 31 days
        while True:
            candidate = datetime(year, month, day, hour)
            if candidate.weekday() == 6:      # Sunday
                return candidate
            day -= 1

    def _bst_from_utc(self, naive_utc: datetime) -> bool:
        """Decide from a UTC wall time. Both boundaries are 01:00 UTC."""
        year = naive_utc.year
        start = self._last_sunday(year, 3, 1)
        end = self._last_sunday(year, 10, 1)
        return start <= naive_utc < end

    def _bst_from_local(self, naive_local: datetime, fold: int = 0) -> bool:
        """Decide from a London wall time.

        The clocks go forward at 01:00 GMT (local 01:00) and back at 02:00 BST
        (local 02:00), so the local-side boundaries are not the same numbers as
        the UTC-side ones. On fall-back day 01:00-02:00 local happens twice;
        `fold` distinguishes them, 0 being the first (still BST) pass.
        """
        year = naive_local.year
        start = self._last_sunday(year, 3, 1)
        end = self._last_sunday(year, 10, 2)
        if end - self._SUMMER <= naive_local < end:
            return fold == 0
        return start <= naive_local < end

    def fromutc(self, dt: datetime) -> datetime:
        naive = dt.replace(tzinfo=None)
        summer = self._bst_from_utc(naive)
        local = dt + (self._SUMMER if summer else self._BASE)
        if not summer:
            end_utc = self._last_sunday(naive.year, 10, 1)
            if end_utc <= naive < end_utc + self._SUMMER:
                # Second pass through the repeated hour.
                return local.replace(fold=1)
        return local

    def utcoffset(self, dt: Optional[datetime]) -> timedelta:
        if dt is None:
            return self._BASE
        naive = dt.replace(tzinfo=None)
        return (self._SUMMER if self._bst_from_local(naive, dt.fold)
                else self._BASE)

    def dst(self, dt: Optional[datetime]) -> timedelta:
        if dt is None:
            return self._BASE
        naive = dt.replace(tzinfo=None)
        return (self._SUMMER if self._bst_from_local(naive, dt.fold)
                else self._BASE)

    def tzname(self, dt: Optional[datetime]) -> str:
        if dt is None:
            return "GMT"
        naive = dt.replace(tzinfo=None)
        return "BST" if self._bst_from_local(naive, dt.fold) else "GMT"


def _resolve_zone(name: str) -> Tuple[Any, str]:
    """Return a tzinfo for `name`; never silently degrade to UTC."""
    try:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(name)
        # Prove the database is really present: a tzdata-less install can
        # still construct a key and then behave like UTC.
        probe = datetime(2026, 8, 15, 12, tzinfo=timezone.utc).astimezone(zone)
        if name in ("Europe/London",) and probe.utcoffset() == timedelta(0):
            raise RuntimeError("tzdata present but inert")
        return zone, name
    except Exception:
        if name in ("Europe/London", "", "London"):
            return _UKClock(), "Europe/London (built-in DST rule)"
        return timezone.utc, "UTC (tzdata missing)"


DISPLAY_TZ, DISPLAY_TZ_NAME = _resolve_zone(DISPLAY_TIMEZONE)


def london_dt(ts_ms: Optional[int] = None) -> datetime:
    """Epoch milliseconds as a London-local datetime."""
    stamp = now_ms() if ts_ms is None else int(ts_ms)
    return datetime.fromtimestamp(stamp / 1000.0, tz=DISPLAY_TZ)


def london_label(ts_ms: Optional[int] = None) -> str:
    """'BST' or 'GMT' for the instant given, so the UI never says UTC wrongly."""
    try:
        return london_dt(ts_ms).strftime("%Z") or "GMT"
    except Exception:
        return "GMT"


def london_runtime(ts_ms: Optional[int] = None) -> str:
    """Header stamp in mm/dd/hh/mm/ss, London time."""
    return london_dt(ts_ms).strftime("%m/%d/%H/%M/%S")
SYMBOL = "BTCUSDT"
STREAM_SYMBOL = "btcusdt"
CANDLE_MS = 300_000
PORT_DEFAULT = int(os.getenv("BTC_MODEL_PORT", "8787"))
OPEN_WINDOW_MS = 5_000

# ---- Refined State X: execution-only protection -------------------------
# These values are frozen for the forward test. State X is evaluated only
# after a genuine MAIN / REVERSAL / EF signal has fired and may only prevent a
# new order submission. It never participates in any signal calculation.
STATE_X_WINDOW_MS = 15 * 60_000
STATE_X_BASELINE_MS = 6 * 60 * 60_000
STATE_X_PERCENTILE = 0.80
STATE_X_CONFIRM_CANDLES = 2
STATE_X_DELTA30_MIN = 0.95
STATE_X_DURATION_MS = 35 * 60_000
REVERSAL_MIN_SECOND = 30.0
REVERSAL_LAST_SECOND = 285.0
# v4.6: every reversal gate tightened. $3 of body on a $100k coin was noise,
# 2.5 s of persistence was one burst of tape, and 0.10 path efficiency accepted
# pure chop. An eighth check now requires the fair odds to already favour the
# reversal side, which is the v5/v7 idea applied to the mid-candle turn.
REVERSAL_PERSIST_MS = 4_000
REVERSAL_MIN_SAMPLES = 6
REVERSAL_BODY_CROSS_USD = 25.0
REVERSAL_MAX_OPEN_CROSSES = 3
REVERSAL_MIN_PATH_EFFICIENCY = 0.25
REVERSAL_MAX_OPPOSITE_WICK = 0.35
REVERSAL_MIN_PROBABILITY = 0.80
REVERSAL_MIN_ODDS = 0.58
# The v5/v7 reversal has a single condition, so there is no check quorum.
# The dashboard still reports a monitor block; these keep it well formed.
REVERSAL_CHECK_COUNT = 1
# v4.5: the OFI votes below are in the new quote units ($ thousands), not the
# old depth-normalised scale. They sit at the same fraction of full scale as
# the v4.0.3 values did, so the reversal gate is no easier to pass than before.
REVERSAL_OFI_5S_MIN = 4.0
REVERSAL_OFI_1S_MIN = 2.0
OPEN_CROSS_DEADBAND_USD = 0.50
SSE_INTERVAL_SEC = 0.25
CHART_CANDLES = 360

# ---- v4.5: aggressive depth clusters ----
CLUSTER_WINDOW = 300          # depth samples kept for the mean/sigma estimate
CLUSTER_MIN_SAMPLES = 30      # below this the z-score is reported as zero
CLUSTER_SIGMA = 2.0           # a spike must exceed mean + 2 sigma
# A very calm book can have a near-zero sigma, which would turn ordinary noise
# into a 50-sigma reading. Sigma is floored at 1% of the mean resting size.
CLUSTER_SIGMA_FLOOR = 0.01
OFI_QUOTE_SCALE = 1_000.0     # OFI is reported in thousands of USD

# ---- v4.5: model ----
MODEL_TEMPERATURE = 1.55
MODEL_LEARNING_RATE = 0.05
MODEL_WEIGHT_CLAMP = 0.35     # |weight - anchor| may never exceed this
MODEL_MIN_SAMPLES = 12        # settled MAIN rows required before adapting

# ---- Predict.fun order book --------------------------------------------
# Accuracy is settled; execution price is the open question. A candle called
# correctly is worthless if the share already costs 0.92, so v7 signs against
# the freshest websocket ladder and stores the actual confirmed fills. The
# production mainnet API requires a key; testnet is an independent sandbox and
# LiveExecutor deliberately refuses to arm there.
PREDICT_BASE_TESTNET = "https://api-testnet.predict.fun"
PREDICT_BASE_MAINNET = "https://api.predict.fun"
PREDICT_WS_URL = "wss://ws.predict.fun/ws"
PREDICT_DISCOVERY_POLL_SEC = 2.0
PREDICT_MARKET_REFRESH_SEC = 60.0
# A transient miss exactly at the five-minute boundary must not make an early
# EF untradeable. This path runs only while no exact market is available; the
# healthy websocket path still performs just one REST discovery per minute.
PREDICT_REDISCOVER_SEC = 5.0
PREDICT_TIMEOUT = 6.0
PREDICT_FEE_RATE = 0.02
# Predict sends heartbeats every 15 seconds. An unchanged order book is still
# current, so connection liveness—not the age of its last price change—is the
# safe freshness signal.
PREDICT_WS_STALE_MS = 20_000
# A half-open mobile connection must not leave trading permanently blocked.
# Two missed 15-second application heartbeats force a clean reconnect.
PREDICT_WS_RECONNECT_MS = 30_000
PREDICT_SEARCH_LIMIT = 100
PREDICT_MARKET_MAX_PAGES = 3
PREDICT_TESTNET_LIMIT_RPM = 240
PREDICT_MAINNET_LIMIT_RPM = 240
# Leave 25% headroom below either documented allowance. WebSocket books and
# wallet events keep normal REST use far below this ceiling.
PREDICT_LOCAL_LIMIT_RPM = 180
# /v1/search documents its own 50 RPM default; stay below that too. The working
# /v1/markets path is preferred and search is only a fallback.
PREDICT_LOCAL_SEARCH_LIMIT_RPM = 40

# ---- real execution -----------------------------------------------------
# MARKET BUY by value is calculated by the official SDK against the live
# websocket ladder. A bounded 1% tolerance aims for a high fill rate without
# silently accepting any price. Only an explicit terminal rejection may cause
# up to three replacements; a timeout is an UNKNOWN state and is reconciled by hash.
PREDICT_ORDER_SLIPPAGE_BPS = max(
    0, min(500, int(os.getenv("PREDICT_SLIPPAGE_BPS", "100"))))
# R6.3.1: EF-only dynamic MARKET BUY tolerance. MAIN/REVERSAL keep the
# legacy PREDICT_ORDER_SLIPPAGE_BPS unchanged. These values are the exact
# Predict isMinAmountOut translations of the operator's desired maximum PRICE
# expansion bands:
#   VWAP < 0.10        -> allow ~100% price rise -> 50.00% min-out = 5000 bps
#   0.10 <= VWAP < .20 -> allow ~ 70% price rise -> 41.18% min-out = 4118 bps
#   0.20 <= VWAP < .30 -> allow ~ 50% price rise -> 33.33% min-out = 3333 bps
#   0.30 <= VWAP < .40 -> allow ~ 20% price rise -> 16.67% min-out = 1667 bps
#   VWAP >= 0.40       -> allow ~ 10% price rise ->  9.09% min-out =  909 bps
#
# Predict's BUY helper uses isMinAmountOut=True, so this changes only the
# minimum accepted shares for an already-qualified EF. It is execution
# survivability only: no EF eligibility/share-price gate is added here and the
# signed tolerance is never capped against EF_MAX_SHARE_PRICE.
EF_SLIPPAGE_BANDS: Tuple[Tuple[float, int], ...] = (
    (0.10, 5000),
    (0.20, 4118),
    (0.30, 3333),
    (0.40, 1667),
)
EF_SLIPPAGE_FALLBACK_BPS = 909
EF_SLIPPAGE_INVALID_BPS = 5000

def ef_slippage_bps(executable_vwap: Optional[float]) -> int:
    """Return EF-only Predict isMinAmountOut bps from the same-book VWAP.

    Bands are half-open at their upper edge, so exactly 0.10 enters the
    0.10-0.20 band, exactly 0.20 enters 0.20-0.30, etc. A missing/invalid VWAP
    receives the widest signing tolerance, but it still cannot execute because
    the surrounding execution path requires a valid executable full-stake
    quote. This helper never consults EF_MAX_SHARE_PRICE and is not a signal or
    execution eligibility gate.
    """
    price = finite_float(executable_vwap)
    if price is None or price <= 0.0:
        return EF_SLIPPAGE_INVALID_BPS
    for upper, bps in EF_SLIPPAGE_BANDS:
        if price < upper:
            return bps
    return EF_SLIPPAGE_FALLBACK_BPS
PREDICT_ORDER_MAX_RETRIES = 3
PREDICT_ORDER_STATUS_TIMEOUT_SEC = 2.0
PREDICT_ORDER_RECONCILE_SEC = 0.50
PREDICT_ORDER_MIN_REMAINING_MS = 3_000
# Shared stakes are cent-precision. Permit only half-cent SDK/integer
# quantization at the final full-stake boundary; larger shortages block.
PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD = 0.005000001
PREDICT_ORDER_TERMINAL_FAILURES = {
    "ORDERNOTACCEPTED", "ORDEREXPIRED", "ORDERCANCELLED",
    "ORDERTRANSACTIONFAILED", "REJECTED", "CANCELLED", "CANCELED",
    "EXPIRED", "FAILED",
}
PREDICT_ORDER_POSITIVE_STATES = {
    "ORDERACCEPTED", "ORDERTRANSACTIONSUBMITTED", "ORDERTRANSACTIONSUCCESS",
    "OPEN", "PENDING", "MATCHED", "PARTIALLYFILLED", "FILLED", "SUCCESS",
}
# Financial accounting must not treat an order lifecycle as final while more
# fills/reconciliation can still change the economics. This single set is used
# defensively by settlement, accuracy, streak and dashboard accounting.
FINANCIAL_UNRESOLVED_ORDER_STATUSES = frozenset({
    "QUEUED", "SIGNING", "SUBMITTING", "UNKNOWN", "ACCEPTED", "MATCHING",
    "OPEN", "PENDING", "PARTIALLYFILLED", "FILLED_DETAILS_PENDING",
})


def financial_order_is_final(order_status: Any, is_shadow: bool = False,
                             filled: bool = False) -> bool:
    """Whether current economics are stable enough for financial accounting.

    Predict.fun BUYs are submitted fill-or-kill. A wallet-confirmed complete
    fill can therefore outrank a stale local QUEUED/OPEN label after reconnect.
    The two statuses that explicitly mean the fill economics are still mutable
    remain excluded. Unfilled rows still require a terminal lifecycle.
    """
    if is_shadow:
        return True
    status = str(order_status or "").upper()
    if filled:
        return status not in frozenset({"PARTIALLYFILLED", "FILLED_DETAILS_PENDING"})
    return status not in FINANCIAL_UNRESOLVED_ORDER_STATUSES
# A POST transport failure can happen after the venue received the bytes. These
# errors are therefore UNKNOWN, never proof that creating a replacement is safe.
PREDICT_AMBIGUOUS_TRANSPORT_ERRORS = (
    TimeoutError,
    urllib.error.URLError,
    socket.timeout,
    OSError,
    http.client.HTTPException,
)


def _full_shared_stake_available(
    requested_stake: float, executable_stake: float
) -> bool:
    # Shared stakes are cent-precision; Predict SDK calculations are integer
    # token/share arithmetic. Permit only half-cent quantization, never a real
    # partial stake.
    try:
        requested = float(requested_stake)
        executable = float(executable_stake)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(requested) or not math.isfinite(executable):
        return False
    if requested <= 0.0 or executable < 0.0:
        return False
    return executable + PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD >= requested


class PredictRequestNotSent(RuntimeError):
    """A local gate failed before any HTTP bytes could reach the venue."""


# Authentication is renewed off the order hot path. JWT claims are decoded
# only to schedule renewal; the venue remains the authority that verifies the
# signature and token. Approval and wallet-balance reads use the SDK's on-chain
# read methods and are cached so a signal never waits for an RPC round trip.
PREDICT_AUTH_MIN_REFRESH_SKEW_SEC = 30.0
PREDICT_AUTH_MAX_REFRESH_SKEW_SEC = 300.0
PREDICT_AUTH_RETRY_MAX_SEC = 60.0
PREDICT_APPROVAL_RECHECK_SEC = 15 * 60.0
PREDICT_APPROVAL_STALE_SEC = 20 * 60.0
PREDICT_BALANCE_RECHECK_SEC = 10.0
PREDICT_BALANCE_STALE_SEC = 30.0
PREDICT_PREFLIGHT_RETRY_SEC = 3.0

# --- v7.7: winning shares that are settled but not yet redeemed -----------
# A won position pays one dollar per share, but the venue's auto-claim needs a
# few seconds to turn those shares into smart-account USDT. During that window
# balance_of("USDT") under-reports the true bankroll, which made streak/percent
# sizing compound from an artificially small number right at the moment a win
# should have grown the stake. v7.7 keeps an explicit claim ledger: a settled
# win is registered as an outstanding payout and is retired as soon as a later
# wallet read actually shows the money arrive.
#
# Sizing uses wallet + outstanding payouts. FUNDING still uses wallet only:
# unredeemed shares cannot pay for an order, so the hard pre-submit gate is
# unchanged and an order can never be sent against money that is not there yet.
PREDICT_CLAIM_TTL_SEC = 900.0        # after 15 min an uncredited claim is dropped
PREDICT_CLAIM_EPSILON_USD = 0.005    # ignore sub-half-cent wallet noise

# --- v7.8: venue-truth positions -----------------------------------------
# GET /v1/positions/{address} reports, per position, the shares actually held
# (`amount`), the price actually paid (`averageBuyPriceUsd`), the live mark
# (`valueUsd`), the venue's own P&L (`pnlUsd`), and WON/LOST once resolved.
# v7.7 inferred all of this locally; v7.8 reads it. A WON position still
# carrying shares is money won and not yet redeemed - no inference needed.
PREDICT_POSITIONS_PATH = "/v1/positions"
PREDICT_POSITIONS_POLL_SEC = 15.0    # positions only move on fill and settle
PREDICT_POSITIONS_FAST_SEC = 2.0     # after a fill, look again promptly
PREDICT_POSITIONS_STALE_SEC = 90.0   # past this the venue view is not trusted
PREDICT_POSITIONS_PAGE = 100

# One-time fresh start for visible signals and live results. Historical
# prediction/feature rows and the core online model weights are retained.
SIGNAL_EPOCH_KEY = "signal_epoch_v7"

# ---- regime classification ----------------------------------------------
# Markets behave differently trending and ranging. The label is recorded from
# the first candle so the question "does accuracy differ by regime" can be
# answered from data rather than assumed.
REGIME_TREND_ADX = 25.0
REGIME_RANGE_WICK = 0.50
REGIME_RANGE_CROSSES = 3

# ---- v4.9 confidence factors -------------------------------------------
# These do not gate the signal. Each returns a multiplier applied to the
# distance between the blended probability and 0.5, so a hostile condition
# pulls the prediction toward a coin flip rather than suppressing it. Every
# candle still receives exactly one MAIN prediction.
VOL_REFERENCE = 1.00          # volume_ratio considered normal
VOL_FLOOR_FACTOR = 0.55       # confidence multiplier in a dead market
VOL_CEILING_FACTOR = 0.80     # violent volume is also unreliable
VOLATILITY_WINDOW = 120       # price samples for the realised-move estimate
REJECTION_MIN_ACTIVITY = 0.5  # below this there is nothing to read
REJECTION_CAP = 6.0           # a retreat beyond six sigma tells us nothing more
REJECTION_HALF_LIFE_SEC = 8.0  # absorption is a moment, not a mood
REJECTION_ZONE_SIGMA = 1.5    # how close to the extreme counts as at it
REJECTION_MIN_SCALE_USD = 1.5  # floor on sigma, so a quiet tape is not noise
RUNWAY_MIN_FACTOR = 0.55      # a call with no time left is close to a guess
FEASIBILITY_SIGMAS = 2.5      # a move beyond this many sigma is implausible

# ---- v5/v7 pressure gauge (ported verbatim) ----
# score = 0.45*clamp(imb/0.3) + 0.35*clamp(delta/0.25) + 0.20*mom
# It fires a direction at |score| >= 0.15 and calls it "strong" above 0.45.
# These four constants are the tested v5/v7 values and must not be tuned.
IMBALANCE_STRONG = 0.12
DELTA_STRONG = 0.10
MIN_SCORE = 2
PRESSURE_FIRE = 0.15
PRESSURE_STRONG = 0.45
PRESSURE_HISTORY = 300        # one price sample per second, as in v5/v7

# ---- v4.6: fair odds and the gated track (the v5/v7 entry rule) ----
# p_up = Phi(lead / (sigma * sqrt(seconds_left))). This is not a forecast: it
# says how far the candle has already travelled relative to what it can still
# do. GATED only fires when flow and odds agree, exactly as v5/v7 did.
EDGE_CONTRADICTION_KEEP = 0.25  # conviction kept when the blend disagrees
# MAIN's evidence bar. Calls fired inside ten seconds scored 44 percent
# against 77 percent after forty, because nothing had yet held.
MAIN_HOLD_MS = 12_000         # the alignment must survive this long
MAIN_HOLD_READS = 60          # and this many independent feature rebuilds
# v8.1 note: this counter is event-rate dependent -- a rebuild is not an
# independent observation, so on a fast tape it is satisfied by traffic and
# on a slow one it binds. Replacing it with a count of distinct wall-clock
# seconds changes when MAIN fires, and that cannot be validated without
# intra-candle history. Deliberately left untouched. See the release notes.
MAIN_LAST_SECOND = 295.0      # a call is welcome right up to the close
GATED_MIN_SECOND = 20.0
GATED_LAST_SECOND = 270.0
GATED_ODDS_UP = 0.60
GATED_ODDS_DOWN = 0.40
GATED_MAX_ODDS = 0.85        # above this the payout cannot cover the risk
GATED_FLOW_EDGE = 0.05       # model must lean the same way by this much
GATED_VOL_MIN = 0.70         # v5/v7 volume floor, in medians

# ---- v9.1.1 r3 MAIN settlement-quality guard ---------------------------
# The trusted legacy MAIN pressure/fair-odds persistence still creates the
# candidate. MAIN is no longer obliged to fire merely because that legacy
# alignment survived: immediately before fire this BTC-only guard asks whether
# the same side is plausibly the FINAL 5-minute settlement side. There is no
# hard "wait until N seconds" rule. Early candidates can pass when exceptional,
# but a marginal first-minute 60/40 reading carries a large remaining-horizon
# uncertainty and normally keeps watching instead of becoming a bet.
MAIN_SETTLEMENT_SCORE_FLOOR = 0.605
MAIN_SETTLEMENT_MARGINAL_EXTRA = 0.065
MAIN_SETTLEMENT_FAIR_STRONG = 0.84
MAIN_SETTLEMENT_MAX_HOSTILE_FAMILIES = 2
MAIN_SETTLEMENT_EF_OPPOSITION_VETO = 0.64
MAIN_SETTLEMENT_EARLY_PENALTY = 0.085
MAIN_SETTLEMENT_HOLD_BASE = 0.50
MAIN_SETTLEMENT_HOLD_UNCERTAINTY = 0.12
MAIN_SETTLEMENT_CONSENSUS_BASE = 0.64
MAIN_SETTLEMENT_CONSENSUS_UNCERTAINTY = 0.12

# ---- v8.1 GPT: regime adaptation ---------------------------------------
# The adaptive multiplier is deliberately connected only to fair odds, the
# signal surface whose volatility scale is otherwise a lagging 24-candle
# median body. It is NOT multiplied into the legacy tick sigma: doing both
# would count the same volatility expansion twice and would silently rescale
# EF, rejection tracking and State X inputs.
#
# Prices are sampled as completed one-second closes. The fast/slow RMS ratio
# is refreshed once per completed bucket and cached, so websocket traffic
# cannot change the measurement or add a multi-millisecond scan to every
# feature rebuild. A neutral band returns exactly 1.0 during ordinary
# variation; outside it the multiplier engages smoothly and remains bounded.
ADAPT_ENABLED = True          # master switch; False restores v8 fair odds
ADAPT_BUCKET_MS = 1_000       # wall-clock sampling grid, one second
ADAPT_FAST_SEC = 180          # responsive scale, three minutes
ADAPT_SLOW_SEC = 3_600        # baseline scale, one hour
ADAPT_MIN_FAST = 60           # completed returns before fast is trusted
ADAPT_MIN_SLOW = 600          # completed returns before slow is trusted
ADAPT_RATIO_LO = 0.30         # hard lower safety bound
ADAPT_RATIO_HI = 6.00         # hard upper safety bound
ADAPT_IDENTITY_LO = 0.85      # exact legacy behaviour inside this band
ADAPT_IDENTITY_HI = 1.15
ADAPT_FULL_LO = 0.67          # fully apply raw contraction by this point
ADAPT_FULL_HI = 1.50          # fully apply raw expansion by this point
ADAPT_WINSOR_SIGMAS = 5.0     # one bad print cannot dominate the estimate
ADAPT_MIN_ACTIVE_SHARE = 0.10 # sparse isolated jumps do not define a regime
ADAPT_STALE_BUCKETS = 5       # a longer gap breaks the return chain

# ---- economics ----------------------------------------------------------
PNL_STAKE_USD = 10.0          # legacy/offline fallback only; never live sizing
PNL_REVERSAL_STAKE_USD = 10.0  # legacy/offline fallback only; never live sizing

# --- capital model (v5.12) -----------------------------------------------
# Every filled or live-pending leg reserves wallet capital. MAIN, REVERSAL and
# EF use exactly one shared stake and one shared win/loss streak.
STARTING_CAPITAL_USD = 100.0  # offline self-test / legacy fallback only
CAPITAL_RISK_FRACTION = 0.10
MAX_STAKE_USD = 50.0
MIN_STAKE_USD = 1.00
# Every leg spends the same wallet, reserves capital while unresolved, and
# advances the same staking streak after a settled fill.
CAPITAL_KINDS = ("MAIN", "REVERSAL", "EF")
COMPOUNDING_KINDS = CAPITAL_KINDS

# --- execution-control clock --------------------------------------------
# Ban rules are stored as explicit per-signal windows. Predictions continue
# recording while a ban blocks execution, so each window stays measurable.
# Default is the London wall clock, not the host's. "utc" or a fixed offset
# such as "+05:30" still override it.
BAN_TIMEZONE = os.getenv("BTC_MODEL_BAN_TZ", "london").strip().lower()

# --- v6.2 execution control -----------------------------------------------
# Bans, manual toggles and staking are execution concerns only. Signals keep
# generating, settling and counting toward accuracy whatever the controls say,
# so a disabled leg stays measurable and the ban itself stays testable.
TRADE_KINDS = ("MAIN", "REVERSAL", "EF")
SYSTEM_CONTROL_KIND = "SYSTEM"
STATE_X_CONTROL_KIND = "STATE_X"

# v6.2 default: MAIN only. The v6.1 ban covered REVERSAL as well; that is now
# removed, as requested, and REVERSAL trades through the window.
DEFAULT_BAN_RULES = (
    {
        "id": "default-main-afternoon",
        "kinds": ["MAIN"],
        "days": [0, 1, 2, 3],
        "start_minute": 15 * 60,        # 15:00
        "end_minute": 19 * 60,          # exclusive, so 18:59:59 is the last
        "label": "MAIN Mon-Thu 3:00PM-6:59PM",
    },
)

STAKE_MODE_FIXED = "fixed"
STAKE_MODE_PERCENT = "percent"
STAKE_MODE_STREAK = "streak"
STAKE_MODES = (STAKE_MODE_FIXED, STAKE_MODE_PERCENT, STAKE_MODE_STREAK)

# Planned default: $10 flat, held between resets, recalculated to 10% of free
# capital after 3 consecutive wins or 2 consecutive losses, capped at $50.
DEFAULT_STAKE_CONFIG = {
    "mode": STAKE_MODE_STREAK,
    "fixed_stake": 10.0,
    "percent": 10.0,
    "current_stake": 10.0,
    "win_trigger": 3,
    "loss_trigger": 2,
    "min_stake": 1.0,
    "max_stake": 50.0,
}
PNL_MIN_PRICE = 0.00          # no minimum EF share-price gate; 0.01 is valid
PNL_MAX_PRICE = 0.95          # binary share price ceiling
PNL_TRADE_BLOCK = 100.0       # "P&L per 100 trades" block size

# ---- v5.5: independent contrarian exhaustion-flow (EF) ----------------
# EF is deliberately selective. It looks for a move that is still visibly on
# one side of the candle open while real-time flow/book/wick evidence has turned
# against that move. The prediction is the opposite final candle direction, so
# the corresponding Predict.fun share should still be cheap. These constants
# belong only to EF; none participates in MAIN or REVERSAL. There is no fixed
# phase window: exhaustion is often most valuable in the final minute. Live
# input readiness and the closed-candle flag define when EF can be evaluated.
# --- v6.1: the side-odds inversion -------------------------------------
# side_odds was the strongest single predictor in 47,385 recorded ticks, and
# EF had it backwards. Requiring HIGH odds selected the cases where the market
# most agreed with the move in progress, which is exactly when betting against
# it fails. Accuracy by odds band:
#     <=0.55  54.7%      0.60-0.70  42.9%      0.80+  13.3%
# Inverted AUC 0.779, the best in the dataset. This is now a CEILING.
EF_MAX_SIDE_ODDS = 0.60
EF_MIN_EXTENSION_SIGMA = 0.35
EF_MIN_VOLUME_RATIO = 0.00   # was 0.70, EF only. MAIN keeps VOL_FLOOR and
                            # GATED keeps GATED_VOL_MIN, both untouched.
                            # Replay: 0.70 was the worst setting in its own
                            # column (0.50, 0.85 and 1.00 all beat it), which
                            # reads as noise rather than a real edge at 0.70.
                            # Thin-volume entries are genuinely cheaper
                            # (0.256 vs 0.274) but less accurate (40% vs 50%),
                            # so they are marginal trades, not hidden value.
# --- v6 thresholds, fitted on 58 recorded candles (51,884 ticks) ----------
# Chosen from the recorded replay dataset, judged on edge per dollar rather
# than accuracy: EF buys around 0.27 where break-even is 27%, so 44% is a
# +0.18 edge. A 720-way search found a 66.7% variant on 6 fires, but that is
# the maximum of a search on a tiny sample; this config has 9 fires behind it
# and the same P&L. Treat the magnitude as unproven until live data lands.
EF_MAX_SHARE_PRICE = 0.50   # v6.1: low-odds entries price near 0.46
# score contains an `extension` term built FROM side_odds, so inverting the
# odds gate mechanically crushes the score: only 177 of 3,928 low-odds ticks
# reached 0.74, and with the other gates the config fired ZERO times. score is
# also negatively correlated with success (higher score -> worse outcomes), so
# it is retained for display and the edge test but no longer vetoes a trade.
EF_SCORE_THRESHOLD = 0.74
EF_SCORE_GATES_ENTRY = False
EF_PERSIST_MS = 1_500
EF_MIN_SAMPLES = 3          # was 10: EF evaluates ~3/s under load, not
                            # ~12/s, so 10 reads silently overrode the 1.5s
                            # hold. Runs held 2.2s and died at 7 reads.
EF_COMPUTE_INTERVAL_MS = 10
EF_MIN_TRADE_EVENTS = 3      # minimum aggTrades in trailing 5s
EF_MAX_TRADE_AGE_MS = 1_500 # newest aggTrade must still be fresh
EF_MIN_CROSSING_FEASIBILITY = 0.80   # v6.1: back to 0.80. With the odds
                            # inversion the two gates now agree instead of
                            # fighting; 0.80 was the best validated setting.
EF_SPEED_PERSISTENCE = 0.40
EF_MAX_SPEED_REACH_SIGMAS = 1.50
EF_MAX_OPEN_CROSSES = 3
EF_MAX_FLOW_FLIPS_5S = 4
EF_MIN_OPPOSITE_FLOW = 0.0   # v6.1: must not oppose, need not be strong
EF_MIN_OPPOSITE_BOOK = 0.0   # v6.1: sign matters, magnitude did not
EF_MIN_REJECTION = 0.0       # v6.1: added ~2pts, inside noise
EF_DEPTH_HISTORY_MS = 7_000
# R6 EF hot execution has no PRICE_LIMIT cooldown/re-arm cycle.
# Legacy value is kept at zero only so old database/audit helpers remain loadable.
EF_PRICE_LIMIT_COOLDOWN_MS = 0
EF_PURPLE = "#9b59ff"

# ---- r6.3 production Early-EF prep gate ---------------------------------
# Promoted verbatim from the r6.2 Early-EF A/B arm tested on 2026-08-30.
# These thresholds use only causal BTC EF prep evidence already in memory.
# Predict.fun remains downstream execution-only and cannot alter qualification.
EF_EARLY_SCORE_MIN = 0.535
EF_EARLY_REACH_MIN = 0.38
EF_EARLY_CONTROL_MIN = 0.44
EF_EARLY_SETTLEMENT_MIN = 0.48
EF_EARLY_QUALITY_MIN = 0.51
EF_EARLY_CHOP_MAX = 0.88

# ---- v9.1.1 r5 EF adaptive settlement gate -----------------------------
# Arithmetic reference only; no historical fitting. At the maximum permitted EF
# share price P=0.50 and fee f=0.02, break-even belief is P*(1+f)=0.51.
# IMPORTANT: this is a MAX-PRICE reference, not a universal probability gate.
# Actual trade economics are evaluated against the current executable VWAP.
EF_P_BASE = EF_MAX_SHARE_PRICE * (1.0 + PREDICT_FEE_RATE)
EF_EDGE_BASE = 0.0
# Consensus is an incoherence veto, not a second price/economic gate. Its base
# therefore must not inherit EF_P_BASE. A 10% untilted physics probability is
# treated as the structural "very weak" boundary and paired with the existing
# unchanged control-transfer minimum 0.54. This is a design bound, not a fit.
EF_CONS_PHYSICS_MIN = 0.10
EF_CONS_CONTROL_MIN = 0.54
EF_CONS_BASE = math.sqrt(EF_CONS_PHYSICS_MIN * EF_CONS_CONTROL_MIN)
EF_P_UNCERTAINTY = 0.12
EF_CONS_UNCERTAINTY = 0.12
EF_EDGE_UNCERTAINTY = 0.12
# A full uncertainty reading can raise each bar by at most its fixed 0.12 term.
# EF_P_CAP remains the conservative max-price diagnostic cap only.
EF_P_CAP = min(0.99, EF_P_BASE + EF_P_UNCERTAINTY)
EF_CONS_CAP = min(0.99, EF_CONS_BASE + EF_CONS_UNCERTAINTY)
EF_EDGE_CAP = EF_EDGE_BASE + EF_EDGE_UNCERTAINTY
# Structural half-sigma cap on the microstructure tilt. Deliberately unchanged
# in this correction: do not mix a second parameter change into the gate fix.
EF_SETTLEMENT_EVIDENCE_Z = 0.50

EF_EXPORT_FIELDS = (
    # Legacy columns stay first for backwards-compatible CSV consumers.
    "ef_score", "ef_extension", "ef_opposite_flow", "ef_opposite_book",
    "ef_rejection", "ef_path_quality", "ef_chop", "ef_flow_flips_5s",
    "ef_book5", "ef_book_trend_1s", "ef_book_replenishment", "ef_event_ofi",
    "ef_microprice", "ef_buy_absorption", "ef_sell_absorption",
    "ef_crossing_feasibility", "ef_crossing_distance",
    "ef_opposite_speed", "ef_seconds_available", "ef_input_ready",
    "ef_quote_price", "ef_evidence_direction",
    # v9.1.1 BTC-only EF / Runway-v2 causal diagnostics.
    "ef_direction", "ef_phase_second", "ef_seconds_left",
    "ef_distance_to_open", "ef_distance_from_extreme_to_open",
    "ef_recovery_fraction", "ef_reversal_quality", "ef_reachability",
    "ef_control_transfer", "ef_settlement_feasibility",
    "ef_runway_v2_score", "ef_new_side_effectiveness",
    "ef_old_side_effectiveness", "ef_effectiveness_transfer",
    "ef_delta_250ms", "ef_delta_1s", "ef_delta_2s", "ef_delta_5s",
    "ef_delta_30s", "ef_ofi_1s", "ef_ofi_5s",
    "ef_main_direction", "ef_main_probability_up", "ef_rev_proximity",
    "ef_execution_vwap", "ef_execution_max_price", "ef_execution_shares",
    "ef_execution_eligible", "ef_execution_reason",
    # Adaptive settlement/price-vs-belief diagnostics.
    "ef_settlement_probability", "ef_settlement_probability_base",
    "ef_consensus", "ef_expected_edge", "ef_probability_floor",
    "ef_consensus_floor", "ef_edge_floor", "ef_uncertainty",
    "ef_reference_vwap_10", "ef_abstain_reason", "ef_attempt_seq",
)

REST_BASES = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
)
# Public Binance market streams required by the strict flowchart.
SUBSCRIBE_STREAMS = (
    f"{STREAM_SYMBOL}@aggTrade",
    f"{STREAM_SYMBOL}@depth5@100ms",
    f"{STREAM_SYMBOL}@kline_5m",
)
# Prefer the main Binance host. data-stream.binance.vision is last because some
# mobile networks open the socket but do not deliver the first event reliably.
WS_ENDPOINTS = (
    "wss://stream.binance.com:443/ws",
    "wss://stream.binance.com:9443/ws",
    "wss://data-stream.binance.vision/ws",
)
WS_CONNECT_TIMEOUT_SEC = 8.0
WS_FIRST_EVENT_TIMEOUT_SEC = 25.0
WS_STALE_TIMEOUT_SEC = 15.0


def avg_move(hist, secs: float = 10.0) -> float:
    """Median absolute move over `secs` seconds, exactly matching v5/v7.

    The legacy implementation restarted a forward scan for every sample, which
    is O(n^2) on every websocket event. Timestamps are monotonic in this ring,
    so one non-decreasing right pointer produces the identical first qualifying
    partner for every left sample in O(n). This is a latency-only optimization:
    the returned sample set and median are unchanged.
    """
    rows = list(hist)
    moves = []
    right = 1
    for left in range(len(rows)):
        if right <= left:
            right = left + 1
        while right < len(rows) and rows[right][0] - rows[left][0] < secs:
            right += 1
        if right < len(rows):
            moves.append(abs(rows[right][1] - rows[left][1]))
    moves.sort()
    return moves[len(moves) // 2] if moves else 0.0


def pressure_score(imb: float, delta: float, mom: float) -> float:
    """The v5/v7 pressure gauge. Weights and divisors are fixed."""
    return (0.45 * max(-1.0, min(1.0, imb / 0.3))
            + 0.35 * max(-1.0, min(1.0, delta / 0.25))
            + 0.20 * mom)


def pressure_text(score: float, magnitude: float) -> str:
    """v5/v7 wording: direction, strength, and the expected move."""
    if abs(score) < PRESSURE_FIRE:
        return "BALANCED"
    direction = "UP" if score > 0 else "DOWN"
    strength = "strong" if abs(score) > PRESSURE_STRONG else "weak"
    estimate = magnitude * (1.0 + abs(score)) if magnitude else 0.0
    return f"{direction} {strength} ~${estimate:.0f}"


def make_call(imb: float, delta: float) -> str:
    """v5/v7 open-of-candle call: two independent votes must agree."""
    votes = 0
    votes += 1 if imb > IMBALANCE_STRONG else (-1 if imb < -IMBALANCE_STRONG else 0)
    votes += 1 if delta > DELTA_STRONG else (-1 if delta < -DELTA_STRONG else 0)
    if votes >= MIN_SCORE:
        return "UP"
    if votes <= -MIN_SCORE:
        return "DOWN"
    return "NO-CALL"


def classify_regime(adx: float, wick_ratio: float, open_crosses: float,
                    volume_ratio: float) -> str:
    """Label the market so accuracy can later be compared across regimes.

    Recorded from the first candle and never used to gate anything. Whether
    trending candles genuinely predict better than ranging ones is a question
    for the data, and it cannot be answered unless the label exists first.
    """
    if volume_ratio >= 2.5:
        return "HIGH_VOL"
    if adx >= REGIME_TREND_ADX and wick_ratio < 0.30:
        return "TRENDING"
    if wick_ratio > REGIME_RANGE_WICK or open_crosses > REGIME_RANGE_CROSSES:
        return "RANGING"
    return "NEUTRAL"


def vol_normalise(value: float, sigma: float, floor: float = 0.25) -> float:
    """Express a reading in units of current volatility.

    A delta of 0.4 means something quite different on a calm tape and a
    violent one. Dividing by realised volatility makes the same number carry
    the same meaning in both, which is the cleanest available fix for the
    model performing worst exactly where it is blindest.
    """
    scale = max(sigma, floor)
    return clamp(value / scale, -8.0, 8.0)


def volume_factor(volume_ratio: float) -> float:
    """Confidence weight from participation.

    A dead market has too few prints to trust, and a violent one is usually
    reacting to something the order book cannot yet price. Both are damped.
    """
    if volume_ratio <= 0.0:
        return VOL_FLOOR_FACTOR
    if volume_ratio < VOL_REFERENCE:
        span = max(volume_ratio / VOL_REFERENCE, 0.0)
        return VOL_FLOOR_FACTOR + (1.0 - VOL_FLOOR_FACTOR) * span
    if volume_ratio <= 2.0:
        return 1.0
    excess = min((volume_ratio - 2.0) / 3.0, 1.0)
    return 1.0 - (1.0 - VOL_CEILING_FACTOR) * excess


def rejection_factor(direction_sign: float, reject_up: float,
                     reject_down: float) -> float:
    """Confidence weight from absorption standing against the call.

    Reads the balance between the two sides rather than either magnitude.
    Magnitude cannot work: a pure random walk retreats fifty-eight sigma from
    its running high over five minutes, so any absolute threshold is crossed
    on every candle. What distinguishes a real rejection is that absorption is
    one-sided, and a ratio is bounded by construction, so it cannot saturate.

    0.5 means both sides absorbed equally, which is chop and carries no
    information. 1.0 means every absorption seen this candle stood against the
    direction being called.
    """
    total = reject_up + reject_down
    if total <= REJECTION_MIN_ACTIVITY:
        return 1.0
    opposing = reject_up if direction_sign > 0 else reject_down
    share = opposing / total
    if share <= 0.5:
        return 1.0
    severity = min((share - 0.5) * 2.0, 1.0)
    return 1.0 - 0.5 * severity


def runway_factor(seconds_left: float) -> float:
    """Confidence weight from how much time the move still has to happen.

    Deliberately the opposite of rewarding patience. A call with four minutes
    left has room to be right; the same call with fifteen seconds left needs
    the market to cooperate immediately. Waiting for certainty is worthless
    here, because by the time a move is obvious there is no lead left to trade
    on.
    """
    if seconds_left <= 0.0:
        return 0.5
    fraction = clamp(seconds_left / 240.0, 0.0, 1.0)
    return RUNWAY_MIN_FACTOR + (1.0 - RUNWAY_MIN_FACTOR) * fraction


def feasibility_factor(required_move: float, sigma_per_root_second: float,
                       seconds_left: float) -> float:
    """Confidence weight from whether the move being predicted is possible.

    Asking price to travel thirty dollars in ten seconds is a different
    proposition from asking it in four minutes. The expected dispersion over
    the remaining time answers that directly.
    """
    if seconds_left <= 0.0 or sigma_per_root_second <= 0.0:
        return 0.5
    expected = sigma_per_root_second * math.sqrt(seconds_left)
    if expected <= 0.0:
        return 0.5
    sigmas = abs(required_move) / expected
    if sigmas <= 1.0:
        return 1.0
    if sigmas >= FEASIBILITY_SIGMAS:
        return 0.5
    span = (sigmas - 1.0) / (FEASIBILITY_SIGMAS - 1.0)
    return 1.0 - 0.5 * span


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def mono_ns() -> int:
    """Process-local monotonic clock for latency and age measurements."""
    return time.monotonic_ns()


def mono_ms() -> int:
    return mono_ns() // 1_000_000


class LatencyTelemetry:
    """Bounded in-memory latency telemetry; no database writes on hot paths."""
    def __init__(self, maxlen: int = 4096) -> None:
        self.maxlen = max(128, int(maxlen))
        self._series: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self.counters: Dict[str, int] = {}

    def observe_ms(self, name: str, value_ms: float) -> None:
        try:
            value = float(value_ms)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value) or value < 0.0:
            return
        with self._lock:
            self._series.setdefault(str(name), deque(maxlen=self.maxlen)).append(value)

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            key = str(name)
            self.counters[key] = int(self.counters.get(key, 0)) + int(amount)

    @staticmethod
    def _pct(values: List[float], p: float) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * p
        lo, hi = int(math.floor(pos)), int(math.ceil(pos))
        if lo == hi:
            return ordered[lo]
        frac = pos - lo
        return ordered[lo] + (ordered[hi] - ordered[lo]) * frac

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            raw = {key: list(values) for key, values in self._series.items()}
            counters = dict(self.counters)
        stages: Dict[str, Any] = {}
        for name, values in raw.items():
            stages[name] = {
                "n": len(values),
                "p50": self._pct(values, 0.50),
                "p95": self._pct(values, 0.95),
                "p99": self._pct(values, 0.99),
                "max": max(values) if values else None,
            }
        return {"stages": stages, "counters": counters}


def candle_id_from_ms(ts_ms: int) -> int:
    return (int(ts_ms) // CANDLE_MS) * CANDLE_MS


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def logistic(value: float) -> float:
    value = clamp(value, -20.0, 20.0)
    return 1.0 / (1.0 + math.exp(-value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def finite_float(value: Any) -> Optional[float]:
    """Return a finite observed value, never a fabricated State X substitute."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


FINANCIAL_FLAT_EPS = 1e-7

def financial_result_from_pnl(value: Optional[float]) -> Optional[str]:
    """Single accounting truth used by settlement, metrics and audits."""
    if value is None:
        return None
    pnl = finite_float(value)
    if pnl is None:
        return None
    if pnl > FINANCIAL_FLAT_EPS:
        return "WIN"
    if pnl < -FINANCIAL_FLAT_EPS:
        return "LOSS"
    return "FLAT"


def first_attempt_http_status(raw_attempt_log: Any) -> Optional[str]:
    """Exact first POST result from the durable attempt journal.

    ``attempts==1`` plus a final fill is a no-retry fill metric, not HTTP
    acceptance.  This parser deliberately reads the attempt-1 journal entry so
    ``first_attempt_acceptance_rate`` means the venue returned an accepted HTTP
    response for the first signed POST.  Missing legacy journals stay unknown
    rather than being misclassified as failures.
    """
    rows: Any = raw_attempt_log
    if isinstance(rows, str):
        try:
            rows = json.loads(rows or "[]")
        except (TypeError, ValueError):
            return None
    if not isinstance(rows, list):
        return None
    attempt_one = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        try:
            attempt = int(item.get("attempt") or 0)
        except (TypeError, ValueError):
            continue
        if attempt == 1:
            attempt_one.append(str(item.get("status") or "").upper())
    if not attempt_one:
        return None
    if "ACCEPTED" in attempt_one:
        return "ACCEPTED"
    return attempt_one[-1] or None


def percentile_linear(values: Iterable[float], percentile: float) -> Optional[float]:
    """Linear (R-7 / NumPy default) percentile for the causal SX baseline."""
    observed: List[float] = []
    for value in values:
        number = finite_float(value)
        if number is not None:
            observed.append(number)
    ordered = sorted(observed)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * clamp(float(percentile), 0.0, 1.0)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def iso_utc(ts_ms: int) -> str:
    """Genuine UTC. This is a WIRE format, not a display format.

    Predict.fun sends `startsAt`/`endsAt` as UTC ISO strings and the market
    matcher parses them back as UTC, so converting this to London silently
    shifted every market window by an hour through British Summer Time and
    stopped the 5-minute market from matching its candle at all. Human-facing
    stamps use london_stamp() instead; the two must not be merged.
    """
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


def london_stamp(ts_ms: int) -> str:
    """Human-facing timestamp: same layout as iso_utc, London wall clock."""
    return london_dt(ts_ms).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def ef_trade_window(
    trades: Iterable[Tuple[int, float, float, float]],
    ts_ms: int,
    window_ms: int,
) -> Dict[str, float]:
    """Executed-flow summary for EF; positive delta means aggressive buying."""
    cutoff = int(ts_ms) - int(window_ms)
    rows: List[Tuple[int, float, float, float]] = []
    for row in reversed(trades):
        if int(row[0]) < cutoff:
            break
        rows.append(row)
    rows.reverse()
    if not rows:
        return {"delta": 0.0, "count_delta": 0.0, "quote": 0.0,
                "count": 0.0, "move": 0.0}
    buy_quote = sum(max(float(row[3]), 0.0) for row in rows)
    sell_quote = sum(max(-float(row[3]), 0.0) for row in rows)
    buys = sum(1 for row in rows if float(row[3]) > 0.0)
    sells = sum(1 for row in rows if float(row[3]) < 0.0)
    total_quote = buy_quote + sell_quote
    total_count = buys + sells
    return {
        "delta": ((buy_quote - sell_quote) / total_quote
                  if total_quote > 0.0 else 0.0),
        "count_delta": ((buys - sells) / total_count if total_count else 0.0),
        "quote": total_quote,
        "count": float(total_count),
        "move": float(rows[-1][1]) - float(rows[0][1]),
    }


def ef_path_stats(
    trades: Iterable[Tuple[int, float, float, float]],
    ts_ms: int,
    window_ms: int,
) -> Dict[str, float]:
    cutoff = int(ts_ms) - int(window_ms)
    rows: List[Tuple[int, float, float, float]] = []
    for row in reversed(trades):
        if int(row[0]) < cutoff:
            break
        rows.append(row)
    rows.reverse()
    if len(rows) < 2:
        return {"move": 0.0, "path": 0.0, "efficiency": 0.0,
                "jump_ratio": 0.0}
    prices = [float(row[1]) for row in rows]
    steps = [prices[index] - prices[index - 1]
             for index in range(1, len(prices))]
    path = sum(abs(step) for step in steps)
    move = prices[-1] - prices[0]
    nonzero = sorted(abs(step) for step in steps if abs(step) > 1e-9)
    median = nonzero[len(nonzero) // 2] if nonzero else 0.0
    recent_jump = max([abs(step) for step in steps[-8:]] or [0.0])
    return {
        "move": move,
        "path": path,
        "efficiency": abs(move) / path if path > 0.0 else 0.0,
        "jump_ratio": recent_jump / median if median > 0.0 else 0.0,
    }



def local_moment(ts_ms: Optional[int] = None) -> Tuple[Any, str]:
    """The wall clock the ban rules are written against, plus its label.

    London, never the host clock. `BTC_MODEL_BAN_TZ` can still force `utc` or
    a fixed offset, but the default no longer depends on how the VPS happens
    to be configured: a ban written for 15:00-18:59 must mean 15:00-18:59 in
    London whether the machine is set to UTC, New York, or anything else.
    """
    stamp = now_ms() if ts_ms is None else int(ts_ms)
    if BAN_TIMEZONE in ("", "local", "london", "europe/london"):
        return london_dt(stamp), london_label(stamp)
    moment = datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc)
    label = "UTC"
    if BAN_TIMEZONE not in ("utc", "z"):
        try:
            sign = -1 if BAN_TIMEZONE.startswith("-") else 1
            body = BAN_TIMEZONE.lstrip("+-")
            hours, _, minutes = body.partition(":")
            moment = moment + sign * timedelta(
                hours=int(hours or 0), minutes=int(minutes or 0))
            label = f"UTC{'+' if sign > 0 else '-'}{body}"
        except (TypeError, ValueError):
            label = "UTC"
    return moment, label


def minute_to_clock(minute: int) -> str:
    """Minutes past midnight as a 12-hour label, matching the UI selectors."""
    minute = int(minute) % (24 * 60)
    hour, mins = divmod(minute, 60)
    suffix = "AM" if hour < 12 else "PM"
    display = hour % 12 or 12
    return f"{display}:{mins:02d}{suffix}"


def describe_rule(rule: Dict[str, Any]) -> str:
    days = rule.get("days") or []
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if len(days) == 7:
        span = "Every day"
    elif days == [0, 1, 2, 3, 4]:
        span = "Mon-Fri"
    elif days and days == list(range(min(days), max(days) + 1)):
        span = f"{names[min(days)]}-{names[max(days)]}"
    else:
        span = ", ".join(names[d] for d in sorted(days)) or "no days"
    start = minute_to_clock(rule.get("start_minute", 0))
    end_minute = int(rule.get("end_minute", 0))
    last = minute_to_clock((end_minute - 1) % (24 * 60))
    kinds = "/".join(rule.get("kinds") or [])
    return f"{kinds} {span} {start}-{last}"


def rule_covers(rule: Dict[str, Any], weekday: int, minute: int) -> bool:
    """Is this instant inside the rule? End is exclusive, so 15:00-19:00
    bans up to and including 18:59:59. Windows may wrap past midnight."""
    start = int(rule.get("start_minute", 0))
    end = int(rule.get("end_minute", 0))
    days = [int(d) for d in (rule.get("days") or [])]
    if start == end:
        return False
    if start < end:
        return weekday in days and start <= minute < end
    # Wrapped window: the tail after midnight belongs to the previous day.
    if weekday in days and minute >= start:
        return True
    return ((weekday - 1) % 7) in days and minute < end


def rules_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Do two rules cover the same kind at the same instant? Checked minute
    by minute across the week, which is cheap and leaves no edge cases."""
    shared = set(a.get("kinds") or []) & set(b.get("kinds") or [])
    if not shared:
        return False
    for weekday in range(7):
        for minute in range(24 * 60):
            if rule_covers(a, weekday, minute) and rule_covers(b, weekday, minute):
                return True
    return False


def validate_ban_rule(
    rule: Dict[str, Any], others: Iterable[Dict[str, Any]]
) -> Optional[str]:
    """Return an error string, or None when the rule is safe to store."""
    kinds = [str(k).upper() for k in (rule.get("kinds") or [])]
    if not kinds:
        return "Select at least one signal type."
    for kind in kinds:
        if kind not in TRADE_KINDS:
            return f"Unknown signal type: {kind}"
    if len(set(kinds)) != len(kinds):
        return "Duplicate signal types in the same rule."
    days = rule.get("days") or []
    if not days:
        return "Select at least one day."
    for day in days:
        if not isinstance(day, int) or not 0 <= day <= 6:
            return "Days must be Monday(0) through Sunday(6)."
    start_value = rule.get("start_minute")
    end_value = rule.get("end_minute")
    if (not isinstance(start_value, int)
            or not 0 <= start_value < 24 * 60):
        return "Start time must be between 00:00 and 23:59."
    if (not isinstance(end_value, int)
            or not 0 <= end_value <= 24 * 60):
        return "End time must be between 00:00 and 24:00."
    if int(rule["start_minute"]) == int(rule["end_minute"]):
        return "Start and end time cannot be the same."
    for other in others:
        if other.get("id") == rule.get("id"):
            continue
        if rules_overlap(rule, other):
            return (
                "This overlaps an existing rule "
                f"({describe_rule(other)}); the banned state would be ambiguous."
            )
    return None


def validate_stake_config(config: Dict[str, Any]) -> Optional[str]:
    """Reject anything that could size a trade wrongly."""
    mode = str(config.get("mode", "")).lower()
    if mode not in STAKE_MODES:
        return f"Unknown staking mode: {mode or '(empty)'}"

    def number(field: str) -> Optional[float]:
        raw = config.get(field)
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value

    minimum = number("min_stake")
    maximum = number("max_stake")
    if minimum is None or minimum <= 0:
        return "Minimum stake must be greater than zero."
    if maximum is None or maximum < minimum:
        return "Maximum stake must be at least the minimum stake."
    if mode == STAKE_MODE_FIXED:
        fixed = number("fixed_stake")
        if fixed is None or fixed <= 0:
            return "Fixed stake must be greater than zero."
        if fixed < minimum or fixed > maximum:
            return "Fixed stake must sit between the minimum and maximum."
    if mode in (STAKE_MODE_PERCENT, STAKE_MODE_STREAK):
        percent = number("percent")
        if percent is None or percent <= 0 or percent > 100:
            return "Percentage must be above 0 and no more than 100."
    if mode == STAKE_MODE_STREAK:
        for field, label in (("win_trigger", "Win"), ("loss_trigger", "Loss")):
            raw = config.get(field)
            if isinstance(raw, bool) or not isinstance(raw, int):
                try:
                    raw = int(str(raw))
                except (TypeError, ValueError):
                    return f"{label} streak trigger must be a whole number."
            if raw < 1:
                return f"{label} streak trigger must be 1 or more."
        current = number("current_stake")
        if current is None or current <= 0:
            return "Current stake must be greater than zero."
        if current < minimum or current > maximum:
            return "Current stake must sit between the minimum and maximum."
    return None


def configured_stake(config: Dict[str, Any], balance: float) -> float:
    """Return the exact shared stake represented by a validated config."""
    minimum = float(config.get("min_stake", MIN_STAKE_USD))
    maximum = float(config.get("max_stake", MAX_STAKE_USD))
    mode = str(config.get("mode", STAKE_MODE_STREAK))
    if mode == STAKE_MODE_FIXED:
        stake = float(config.get("fixed_stake", MIN_STAKE_USD))
    elif mode == STAKE_MODE_PERCENT:
        stake = float(balance) * float(config.get("percent", 10.0)) / 100.0
    else:
        stake = float(config.get("current_stake", MIN_STAKE_USD))
    return round(max(minimum, min(maximum, stake)), 2)


def capital_stake(free_capital: float) -> float:
    """10% of free capital, capped at $50. Compounds as the balance grows."""
    stake = float(free_capital) * CAPITAL_RISK_FRACTION
    return round(min(stake, MAX_STAKE_USD), 2)



# --- v6 edge test ---------------------------------------------------------
# EF_SCORE is not a probability, so it cannot be compared with a price
# directly. The replay of 58 recorded candles put EF's realised hit rate near
# 0.44 at a mean entry of 0.267. This maps score onto that observed range and
# requires the result to clear price + fee + a margin. The mapping is a
# straight line fitted to a small sample: it is a floor against overpaying,
# not a calibrated probability, and it should be refitted once live EF trades
# accumulate.
EF_EDGE_MARGIN = 0.03        # required cushion over price + fee

# v6.1 recalibration. The v6 edge test priced off `score`, which the 47,385
# recorded ticks showed to be NEGATIVELY correlated with success and, once the
# odds gate was inverted, uniformly low: it rejected every trade and EF fired
# zero times. Probability is now anchored on side_odds, the strongest single
# predictor in the data (inverted AUC 0.779):
#     odds <=0.55  54.7%      0.60-0.70  42.9%      0.80+  13.3%
# and on crossing, which within the low-odds pool holds ~50-56%. Realised
# accuracy for the shipped gate combination was 77.8% over 9 fires, so these
# numbers are deliberately CONSERVATIVE relative to that: the edge test should
# stop EF overpaying, not manufacture confidence it has not earned.
EF_PROB_FLOOR = 0.45         # low-odds pool, weakest crossing
EF_PROB_CEILING = 0.62       # low-odds pool, strongest crossing


def ef_implied_probability(evidence: Dict[str, Any]) -> float:
    """Probability EF's contrarian call resolves, from the two features that
    actually discriminate: side_odds (inverted) and crossing feasibility."""
    odds = clamp(safe_float(evidence.get("side_odds"), 1.0), 0.0, 1.0)
    cross = max(0.0, safe_float(evidence.get("crossing_feasibility")))
    # Lower odds is better: full weight at 0.40, none at EF_MAX_SIDE_ODDS.
    span = max(1e-9, EF_MAX_SIDE_ODDS - 0.40)
    odds_term = clamp((EF_MAX_SIDE_ODDS - odds) / span, 0.0, 1.0)
    # Crossing saturates around 1.2 in the recorded data.
    cross_term = clamp(cross / 1.20, 0.0, 1.0)
    blend = 0.65 * odds_term + 0.35 * cross_term
    return EF_PROB_FLOOR + blend * (EF_PROB_CEILING - EF_PROB_FLOOR)


def ef_expected_edge(evidence: Dict[str, Any], price: float) -> float:
    """Implied probability minus the all-in cost of the share."""
    cost = float(price) * (1.0 + PREDICT_FEE_RATE)
    return ef_implied_probability(evidence) - cost


def ef_has_edge(evidence: Dict[str, Any], price: Optional[float]) -> bool:
    if price is None or price <= 0.0:
        return False
    return ef_expected_edge(evidence, price) >= EF_EDGE_MARGIN


def ef_crossing_runway(
    distance_usd: float,
    seconds_left: float,
    sigma_per_root_second: float,
    opposite_move_1s: float,
    opposite_move_5s: float,
) -> Dict[str, float]:
    """Estimate whether an exhausted move can still cross the candle open.

    This is deliberately a dynamic runway check, not a clock window. A setup
    can pass in the final minute when price is close enough to the open or the
    opposing move is already fast enough. An implausibly distant cross is
    rejected even if its cheap opposite share looks tempting.
    """
    distance = max(float(distance_usd), 0.0)
    available = max(
        float(seconds_left) - (EF_PERSIST_MS / 1_000.0), 0.0
    )
    sigma_root = max(float(sigma_per_root_second), 0.0)
    volatility_reach = sigma_root * math.sqrt(available)
    speed_1s = max(float(opposite_move_1s), 0.0)
    speed_5s = max(float(opposite_move_5s), 0.0) / 5.0
    opposite_speed = 0.65 * speed_1s + 0.35 * speed_5s
    speed_reach = opposite_speed * available * EF_SPEED_PERSISTENCE
    speed_reach = min(
        speed_reach, EF_MAX_SPEED_REACH_SIGMAS * volatility_reach
    )
    reachable = 0.75 * volatility_reach + speed_reach
    feasibility = (
        clamp(reachable / distance, 0.0, 2.0) if distance > 1e-9 else 0.0
    )
    return {
        "feasibility": feasibility,
        "distance": distance,
        "seconds_available": available,
        "opposite_speed": opposite_speed,
        "volatility_reach": volatility_reach,
        "speed_reach": speed_reach,
        "reachable": reachable,
    }


def ef_adaptive_settlement(
    distance_to_open: float,
    recovery_from_extreme: float,
    seconds_left: float,
    sigma_per_root_second: float,
    control_transfer: float,
    phase_second: float,
) -> Dict[str, float]:
    """Absolute EF close belief + independent consensus + ratchet-up floors.

    Predict.fun price is intentionally absent. This is BTC settlement belief only.
    Venue price is consulted later for execution and the hard $0.50 ceiling only.
    """
    distance = max(0.0, float(distance_to_open))
    recovery = max(0.0, float(recovery_from_extreme))
    left = max(0.0, float(seconds_left))
    sigma = max(1e-9, float(sigma_per_root_second))
    horizon = max(sigma * math.sqrt(max(left, 1e-9)), 1e-9)
    residual = max(0.0, distance - recovery)
    base_z = -residual / horizon
    settlement_probability_base = clamp(
        0.5 * (1.0 + math.erf(base_z / math.sqrt(2.0))), 0.01, 0.99
    )
    control = clamp(float(control_transfer), 0.0, 1.0)
    tilt = (
        clamp((control - 0.5) * 2.0, -1.0, 1.0)
        * EF_SETTLEMENT_EVIDENCE_Z
    )
    settlement_probability = clamp(
        0.5 * (1.0 + math.erf((base_z + tilt) / math.sqrt(2.0))),
        0.01, 0.99,
    )
    # Independence is deliberate: consensus pairs UNTILTED physics with control.
    ef_consensus = math.sqrt(max(0.0, settlement_probability_base * control))
    maturity = clamp(float(phase_second) / 75.0, 0.0, 1.0)
    ef_uncertainty = clamp((1.0 - maturity) * (1.0 - control), 0.0, 1.0)
    # Legacy probability/edge floors remain diagnostic only. They do not gate EF.
    # The adaptive decision is BTC-only; Predict.fun is execution-only.
    probability_floor = clamp(
        EF_P_BASE + EF_P_UNCERTAINTY * ef_uncertainty, EF_P_BASE, EF_P_CAP
    )
    consensus_floor = clamp(
        EF_CONS_BASE + EF_CONS_UNCERTAINTY * ef_uncertainty,
        EF_CONS_BASE, EF_CONS_CAP,
    )
    edge_floor = clamp(
        EF_EDGE_BASE + EF_EDGE_UNCERTAINTY * ef_uncertainty,
        EF_EDGE_BASE, EF_EDGE_CAP,
    )
    # Reachability is intentionally absent from quality. Its old 0.30 weight is
    # split evenly across control (0.38+0.15) and absolute settlement belief
    # (0.32+0.15). Uncertainty can only subtract, never add.
    quality = clamp(
        0.53 * control + 0.47 * settlement_probability
        - 0.12 * ef_uncertainty,
        0.0, 1.0,
    )
    return {
        "horizon": horizon,
        "residual_distance": residual,
        "base_z": base_z,
        "settlement_probability_base": settlement_probability_base,
        "settlement_probability": settlement_probability,
        "ef_consensus": ef_consensus,
        "ef_uncertainty": ef_uncertainty,
        "probability_floor": probability_floor,
        "consensus_floor": consensus_floor,
        "edge_floor": edge_floor,
        "quality": quality,
        "tilt_z": tilt,
    }


def ef_adaptive_btc_gate(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """BTC-only adaptive EF gate. Predict.fun data is forbidden here.

    This layer exists only to suppress weak BTC-side setups (quiet/choppy
    conditions, weak control transfer, poor settlement structure). Venue price
    and order-book state are execution inputs and can never change whether the
    BTC EF itself qualifies.
    """
    consensus = clamp(safe_float(evidence.get("ef_consensus"), 0.0), 0.0, 1.0)
    consensus_floor = clamp(
        safe_float(evidence.get("consensus_floor"), EF_CONS_BASE),
        EF_CONS_BASE, EF_CONS_CAP,
    )
    edge_floor = clamp(
        safe_float(evidence.get("edge_floor"), EF_EDGE_BASE),
        EF_EDGE_BASE, EF_EDGE_CAP,
    )
    quality = clamp(
        safe_float(
            evidence.get("runway_v2_score"),
            safe_float(evidence.get("quality"), 0.0),
        ),
        0.0, 1.0,
    )
    reasons: List[str] = []
    if quality < 0.59:
        reasons.append(f"adaptive quality {quality:.3f}/0.590")
    if consensus < consensus_floor:
        reasons.append(f"consensus {consensus:.3f}/{consensus_floor:.3f}")
    return {
        "eligible": not reasons,
        "abstain_reason": "; ".join(reasons),
        "consensus_floor": consensus_floor,
        # Retained only as a legacy diagnostic field. It is NOT an EF gate.
        "edge_floor": edge_floor,
    }


def ef_execution_price_diagnostics(
    evidence: Dict[str, Any], executable_vwap: Optional[float]
) -> Dict[str, Any]:
    """Post-qualification execution diagnostics; never signal eligibility.

    Predict.fun price may be recorded for later analysis, but the only live EF
    execution price rule is the separate hard ``EF_MAX_SHARE_PRICE`` check.
    """
    btc_gate = ef_adaptive_btc_gate(evidence)
    probability = clamp(
        safe_float(evidence.get("settlement_probability"), 0.0), 0.0, 1.0
    )
    price = finite_float(executable_vwap)
    expected_edge: Optional[float] = None
    probability_floor: Optional[float] = None
    if price is not None and price > 0.0:
        cost = price * (1.0 + PREDICT_FEE_RATE)
        expected_edge = probability - cost
        probability_floor = clamp(
            cost + EF_P_UNCERTAINTY * safe_float(evidence.get("ef_uncertainty"), 0.0),
            0.01, 0.99,
        )
    return {
        # Critical invariant: venue price can NEVER change BTC eligibility.
        "eligible": bool(btc_gate["eligible"]),
        "expected_edge": expected_edge,
        "reference_vwap_10": None,
        "abstain_reason": str(btc_gate.get("abstain_reason") or ""),
        "probability_floor": probability_floor,
        "consensus_floor": btc_gate["consensus_floor"],
        "edge_floor": btc_gate["edge_floor"],
    }


def ef_adaptive_price_gate(
    evidence: Dict[str, Any], vwap_10: Optional[float]
) -> Dict[str, Any]:
    """Compatibility wrapper: price is diagnostic-only, never an EF gate."""
    return ef_execution_price_diagnostics(evidence, vwap_10)


def ef_runway_v2(
    distance_to_open: float,
    recovery_from_extreme: float,
    seconds_left: float,
    sigma_per_root_second: float,
    short_reversal_move: float,
    medium_reversal_move: float,
    opposite_flow: float,
    opposite_book: float,
    rejection: float,
    path_quality: float,
    chop: float,
    new_side_effectiveness: float,
    old_side_effectiveness: float,
    phase_second: float,
) -> Dict[str, float]:
    """BTC-only EF Runway v2: Reachability + Control Transfer + Settlement Feasibility.

    Short bursts are capped by causal volatility capacity rather than extrapolated
    linearly across the whole candle. Early-candle uncertainty is continuous, not
    a hard time gate, so exceptional evidence can still qualify immediately.
    """
    distance = max(0.0, float(distance_to_open))
    recovery = max(0.0, float(recovery_from_extreme))
    left = max(0.0, float(seconds_left))
    sigma = max(1e-6, float(sigma_per_root_second))
    vol_capacity = sigma * math.sqrt(max(left, 1e-6))
    short = max(0.0, float(short_reversal_move))
    medium = max(0.0, float(medium_reversal_move))
    # Only a small fraction of observed short/medium speed may persist; then cap
    # the contribution to avoid turning one 1-second impulse into a 4-minute line.
    speed_capacity = (0.55 * short + 0.45 * medium) * math.sqrt(max(left, 1.0))
    speed_capacity = min(speed_capacity, 0.90 * vol_capacity)
    residual = max(0.0, distance - recovery)
    reachable_capacity = 0.90 * vol_capacity + speed_capacity
    reachability = clamp(reachable_capacity / max(residual, 0.35 * sigma, 1e-9), 0.0, 1.0)

    flow = clamp(float(opposite_flow) / 0.65, 0.0, 1.0)
    book = clamp(float(opposite_book) / 0.47, 0.0, 1.0)
    reject = clamp(float(rejection), 0.0, 1.0)
    path = clamp(float(path_quality), 0.0, 1.0)
    new_eff = clamp(float(new_side_effectiveness), 0.0, 1.0)
    old_eff = clamp(float(old_side_effectiveness), 0.0, 1.0)
    effectiveness_transfer = clamp(new_eff - old_eff, 0.0, 1.0)
    control_transfer = clamp(
        0.25 * flow + 0.20 * book + 0.18 * reject + 0.12 * path
        + 0.25 * effectiveness_transfer, 0.0, 1.0
    )

    chop_penalty = 0.28 * clamp(float(chop), 0.0, 1.0)
    adaptive = ef_adaptive_settlement(
        distance, recovery, left, sigma, control_transfer, phase_second
    )
    # Keep the existing settlement-feasibility gate unchanged. Its uncertainty
    # term remains a penalty; the new quality score also subtracts uncertainty.
    early_uncertainty = adaptive["ef_uncertainty"] * 0.22
    stay_margin = clamp((recovery + reachable_capacity - distance) / max(vol_capacity, sigma), -1.0, 1.0)
    stay_score = clamp(0.5 + 0.5 * stay_margin, 0.0, 1.0)
    settlement_feasibility = clamp(
        0.46 * reachability + 0.36 * control_transfer + 0.18 * stay_score
        - chop_penalty - early_uncertainty, 0.0, 1.0
    )
    return {
        "reachability": reachability,
        "control_transfer": control_transfer,
        "settlement_feasibility": settlement_feasibility,
        "quality": adaptive["quality"],
        "volatility_capacity": vol_capacity,
        "speed_capacity": speed_capacity,
        "reachable_capacity": reachable_capacity,
        "residual_distance": residual,
        "stay_score": stay_score,
        "effectiveness_transfer": effectiveness_transfer,
        "early_uncertainty": early_uncertainty,
        "ef_uncertainty": adaptive["ef_uncertainty"],
        "settlement_probability_base": adaptive["settlement_probability_base"],
        "settlement_probability": adaptive["settlement_probability"],
        "ef_consensus": adaptive["ef_consensus"],
        "probability_floor": adaptive["probability_floor"],
        "consensus_floor": adaptive["consensus_floor"],
        "edge_floor": adaptive["edge_floor"],
        "settlement_base_z": adaptive["base_z"],
        "settlement_tilt_z": adaptive["tilt_z"],
    }


def main_settlement_quality(
    feature: Dict[str, Any],
    direction: str,
    open_price: float,
    current_price: float,
    sigma_per_root_second: float,
    *,
    microprice_bias: float = 0.0,
    ef_direction: Optional[str] = None,
    ef_settlement_score: float = 0.0,
    ef_fired: bool = False,
    gated_direction: Optional[str] = None,
) -> Dict[str, Any]:
    """BTC-only settlement assessment for a legacy MAIN candidate.

    This is deliberately a *final-candle* question, not another flow trigger.
    Legacy MAIN still creates the candidate; this O(1) guard can only allow it
    or keep watching. It never flips MAIN on its own, never reads Predict.fun,
    and never sleeps. Remaining-time uncertainty, price location versus the
    candle open, side stability, path/chop, flow effectiveness, book/OFI,
    rejection and already-fired BTC signal context are evaluated from the
    current in-memory snapshot.
    """
    side = str(direction).upper()
    sign = 1.0 if side == "UP" else -1.0 if side == "DOWN" else 0.0
    if not sign:
        return {"score": 0.0, "required": 1.0, "pass": False,
                "hostile_families": 99, "reason": "invalid direction"}

    fair_up = clamp(safe_float(feature.get("fair_p_up"), 0.5), 0.01, 0.99)
    fair_side = fair_up if sign > 0.0 else 1.0 - fair_up
    seconds_left = clamp(safe_float(feature.get("seconds_left"), 300.0), 1.0, 300.0)
    phase = clamp(safe_float(feature.get("phase_second"), 300.0 - seconds_left), 0.0, 300.0)
    sigma = max(1e-6, safe_float(sigma_per_root_second, 0.0))
    expected = max(sigma * math.sqrt(seconds_left), abs(current_price) * 1e-6, 1e-6)
    signed_lead = sign * (float(current_price) - float(open_price))
    lead_z = signed_lead / expected

    location = clamp(0.5 + 0.5 * math.tanh(lead_z / 0.82), 0.0, 1.0)
    # Independent remaining-horizon close probability under the causal realised
    # volatility scale. This stops fast flow from carrying MAIN by itself.
    settlement_hold = clamp(
        0.5 * (1.0 + math.erf(lead_z / math.sqrt(2.0))), 0.01, 0.99
    )
    above_balance = clamp(safe_float(feature.get("above_open_balance_30s"), 0.5), 0.0, 1.0)
    side_balance = above_balance if sign > 0.0 else 1.0 - above_balance
    progress = phase / 300.0
    lead_certainty = clamp(max(0.0, lead_z) / 1.20, 0.0, 1.0)
    horizon_uncertainty = clamp((1.0 - progress) * (1.0 - lead_certainty), 0.0, 1.0)
    hold_floor = clamp(
        MAIN_SETTLEMENT_HOLD_BASE
        + MAIN_SETTLEMENT_HOLD_UNCERTAINTY * horizon_uncertainty,
        0.50, 0.62,
    )
    settlement_consensus = math.sqrt(max(0.0, fair_side * settlement_hold))
    consensus_floor = clamp(
        MAIN_SETTLEMENT_CONSENSUS_BASE
        + MAIN_SETTLEMENT_CONSENSUS_UNCERTAINTY * horizon_uncertainty,
        MAIN_SETTLEMENT_CONSENSUS_BASE, 0.76,
    )

    d1 = clamp(sign * safe_float(feature.get("delta_1s")), -1.0, 1.0)
    d5 = clamp(sign * safe_float(feature.get("delta_5s")), -1.0, 1.0)
    d30 = clamp(sign * safe_float(feature.get("delta_30s")), -1.0, 1.0)
    imbalance = clamp(sign * safe_float(feature.get("spot_imbalance5")), -1.0, 1.0)
    ofi1 = math.tanh(sign * safe_float(feature.get("ofi_1s")) / 250.0)
    ofi5 = math.tanh(sign * safe_float(feature.get("ofi_5s")) / 250.0)
    micro = clamp(sign * safe_float(microprice_bias), -1.0, 1.0)
    flow_raw = clamp(0.18*d1 + 0.30*d5 + 0.22*d30 + 0.10*imbalance
                     + 0.08*ofi1 + 0.09*ofi5 + 0.03*micro, -1.0, 1.0)
    flow = 0.5 + 0.5 * flow_raw
    book = 0.5 + 0.5 * clamp(0.42*imbalance + 0.23*ofi1 + 0.27*ofi5 + 0.08*micro, -1.0, 1.0)

    r1 = clamp(sign * safe_float(feature.get("return_1s_bps")) / 1.30, -4.0, 4.0)
    r5 = clamp(sign * safe_float(feature.get("return_5s_bps")) / 2.50, -4.0, 4.0)
    response_raw = math.tanh(0.30*r1 + 0.70*r5)
    price_response = 0.5 + 0.5 * response_raw
    support_aggr = max(0.0, 0.30*d1 + 0.70*d5)
    hostile_aggr = max(0.0, -(0.30*d1 + 0.70*d5))
    support_move = max(0.0, response_raw)
    hostile_move = max(0.0, -response_raw)
    support_eff = support_move / (0.20 + support_aggr)
    hostile_eff = hostile_move / (0.20 + hostile_aggr)
    effectiveness = clamp(0.5 + 0.5*math.tanh(support_eff - hostile_eff), 0.0, 1.0)

    reject_up = max(0.0, safe_float(feature.get("reject_up")))
    reject_down = max(0.0, safe_float(feature.get("reject_down")))
    reject_total = reject_up + reject_down
    if reject_total > REJECTION_MIN_ACTIVITY:
        aligned_reject = ((reject_down - reject_up) if sign > 0.0
                          else (reject_up - reject_down)) / reject_total
        rejection = clamp(0.5 + 0.5*aligned_reject, 0.0, 1.0)
    else:
        rejection = 0.5

    body_ratio = clamp(sign * safe_float(feature.get("body_range_ratio")), -1.0, 1.0)
    close_location = clamp(safe_float(feature.get("close_location"), 0.5), 0.0, 1.0)
    range_location = close_location if sign > 0.0 else 1.0 - close_location
    efficiency = clamp(safe_float(feature.get("path_efficiency")), 0.0, 1.0)
    crosses = max(0.0, safe_float(feature.get("open_cross_count")))
    cross_penalty = min(1.0, crosses / 4.0)
    path_hold = clamp(0.30 + 0.20*(0.5 + 0.5*body_ratio)
                      + 0.20*range_location + 0.18*efficiency
                      + 0.12*side_balance - 0.22*cross_penalty, 0.0, 1.0)

    ef_strength = clamp(safe_float(ef_settlement_score), 0.0, 1.0)
    ef_side = str(ef_direction or "").upper()
    ef_conflict = bool(ef_side in ("UP", "DOWN") and ef_side != side and ef_strength >= 0.56)
    ef_opposition_veto = bool(ef_fired and ef_conflict and ef_strength >= MAIN_SETTLEMENT_EF_OPPOSITION_VETO)
    context_adjust = 0.0
    if ef_side in ("UP", "DOWN"):
        context_adjust += (0.035 if ef_side == side else -0.085) * ef_strength
    gated_side = str(gated_direction or "").upper()
    if gated_side in ("UP", "DOWN"):
        context_adjust += 0.018 if gated_side == side else -0.035

    hostile = [
        flow < 0.44, book < 0.42, price_response < 0.43, effectiveness < 0.40,
        rejection < 0.36, path_hold < 0.42, side_balance < 0.42, ef_conflict,
    ]
    hostile_families = sum(1 for item in hostile if item)
    hostility_penalty = 0.020 * max(0, hostile_families - 1)

    score = clamp(
        0.24*fair_side + 0.18*settlement_hold + 0.12*location
        + 0.10*side_balance + 0.09*path_hold + 0.06*range_location
        + 0.06*flow + 0.04*book + 0.04*price_response + 0.03*effectiveness
        + 0.04*rejection + context_adjust
        - MAIN_SETTLEMENT_EARLY_PENALTY*horizon_uncertainty - hostility_penalty,
        0.0, 1.0,
    )
    fair_progress = clamp(
        (fair_side - GATED_ODDS_UP) / max(MAIN_SETTLEMENT_FAIR_STRONG - GATED_ODDS_UP, 1e-9),
        0.0, 1.0,
    )
    required = (MAIN_SETTLEMENT_SCORE_FLOOR
                + MAIN_SETTLEMENT_MARGINAL_EXTRA*(1.0-fair_progress)
                + 0.045*horizon_uncertainty)
    hold_ok = settlement_hold >= hold_floor
    consensus_ok = settlement_consensus >= consensus_floor
    passed = bool(
        score >= required and hold_ok and consensus_ok
        and hostile_families <= MAIN_SETTLEMENT_MAX_HOSTILE_FAMILIES
        and not ef_opposition_veto
    )
    if ef_opposition_veto:
        reason = "opposite fired EF has stronger settlement evidence"
    elif not hold_ok:
        reason = f"final-close hold {settlement_hold:.3f} below {hold_floor:.3f} for remaining horizon"
    elif not consensus_ok:
        reason = f"settlement consensus {settlement_consensus:.3f} below {consensus_floor:.3f} for remaining horizon"
    elif hostile_families > MAIN_SETTLEMENT_MAX_HOSTILE_FAMILIES:
        reason = f"{hostile_families} hostile BTC evidence families"
    elif score < required:
        reason = f"settlement quality {score:.3f} below {required:.3f}"
    else:
        reason = "settlement quality passed"
    return {
        "score": score, "required": required, "pass": passed, "reason": reason,
        "fair_side": fair_side, "settlement_hold": settlement_hold,
        "hold_floor": hold_floor, "hold_ok": hold_ok,
        "settlement_consensus": settlement_consensus,
        "consensus_floor": consensus_floor, "consensus_ok": consensus_ok,
        "location": location, "side_balance": side_balance,
        "flow": flow, "book": book, "price_response": price_response,
        "effectiveness": effectiveness, "rejection": rejection,
        "path_hold": path_hold, "range_location": range_location,
        "hostile_families": hostile_families, "ef_conflict": ef_conflict,
        "ef_opposition_veto": ef_opposition_veto, "ef_context_strength": ef_strength,
        "gated_direction": gated_side or None, "context_adjust": context_adjust,
        "expected_move": expected, "signed_lead": signed_lead, "lead_z": lead_z,
        "phase_second": phase, "seconds_left": seconds_left,
        "horizon_uncertainty": horizon_uncertainty,
    }


def classify_ef_post_progress(
    progress_fraction: float, crossed_open: bool, actual: str, direction: str
) -> str:
    """Classify what happened after an EF fire, without using pre-fire extremes."""
    fraction = clamp(safe_float(progress_fraction), 0.0, 1.0)
    crossed = bool(crossed_open)
    if crossed and str(actual).upper() == str(direction).upper():
        return "CROSSED_AND_SETTLED_EF_SIDE"
    if crossed:
        return "CROSSED_OPEN_THEN_REVERTED"
    if fraction >= 0.75:
        return "APPROACHED_OPEN_STALLED"
    if fraction >= 0.25:
        return "REVERSAL_REAL_TOO_WEAK"
    return "REVERSAL_FAKE"


def ef_depth_totals(depth: Dict[str, Any], levels: int = 5) -> Tuple[float, float]:
    bids = list((depth or {}).get("bids") or [])[:levels]
    asks = list((depth or {}).get("asks") or [])[:levels]
    return (sum(float(qty) for _, qty in bids),
            sum(float(qty) for _, qty in asks))


def ef_depth_at_age(
    history: Iterable[Dict[str, Any]], ts_ms: int, minimum_ms: int, maximum_ms: int
) -> Optional[Dict[str, Any]]:
    for snapshot in reversed(list(history)):
        stamp = snapshot.get("recv_ms")
        if stamp is None:
            stamp = snapshot.get("ts_ms") or 0
        age = int(ts_ms) - int(stamp)
        if minimum_ms <= age <= maximum_ms:
            return snapshot
    return None


def ef_depth_change(
    previous: Optional[Dict[str, Any]], current: Dict[str, Any]
) -> Dict[str, float]:
    if not previous:
        return {"bid_change": 0.0, "ask_change": 0.0,
                "replenishment": 0.0}
    old_bid, old_ask = ef_depth_totals(previous)
    new_bid, new_ask = ef_depth_totals(current)
    bid_change = clamp(
        (new_bid - old_bid) / max(0.5 * (new_bid + old_bid), 1e-9), -1.0, 1.0)
    ask_change = clamp(
        (new_ask - old_ask) / max(0.5 * (new_ask + old_ask), 1e-9), -1.0, 1.0)
    return {
        "bid_change": bid_change,
        "ask_change": ask_change,
        "replenishment": clamp(0.5 * (bid_change - ask_change), -1.0, 1.0),
    }


def ef_depth_event_ofi(
    previous: Optional[Dict[str, Any]], current: Dict[str, Any]
) -> float:
    if not previous:
        return 0.0
    old_bids = {round(float(price), 8): float(qty)
                for price, qty in list(previous.get("bids") or [])[:5]}
    old_asks = {round(float(price), 8): float(qty)
                for price, qty in list(previous.get("asks") or [])[:5]}
    new_bids = {round(float(price), 8): float(qty)
                for price, qty in list(current.get("bids") or [])[:5]}
    new_asks = {round(float(price), 8): float(qty)
                for price, qty in list(current.get("asks") or [])[:5]}
    bid_change = sum(new_bids.get(price, 0.0) - old_bids.get(price, 0.0)
                     for price in set(old_bids) | set(new_bids))
    ask_change = sum(new_asks.get(price, 0.0) - old_asks.get(price, 0.0)
                     for price in set(old_asks) | set(new_asks))
    visible = 0.5 * (sum(old_bids.values()) + sum(old_asks.values())
                     + sum(new_bids.values()) + sum(new_asks.values()))
    return clamp((bid_change - ask_change) / max(visible, 1e-9), -1.0, 1.0)


class RollingDelta:
    """Rolling aggressive-buy versus aggressive-sell quote-volume delta."""

    def __init__(self, window_ms: int) -> None:
        self.window_ms = int(window_ms)
        self.items: Deque[Tuple[int, float, float]] = deque()
        self.buy = 0.0
        self.sell = 0.0

    def add(self, ts_ms: int, signed_quote: float) -> None:
        buy = signed_quote if signed_quote > 0.0 else 0.0
        sell = -signed_quote if signed_quote < 0.0 else 0.0
        self.items.append((ts_ms, buy, sell))
        self.buy += buy
        self.sell += sell
        self.prune(ts_ms)

    def prune(self, ts_ms: int) -> None:
        cutoff = ts_ms - self.window_ms
        while self.items and self.items[0][0] < cutoff:
            _, buy, sell = self.items.popleft()
            self.buy -= buy
            self.sell -= sell

    def value(self, ts_ms: int) -> float:
        self.prune(ts_ms)
        total = self.buy + self.sell
        return (self.buy - self.sell) / total if total > 0.0 else 0.0


class RollingSignedMean:
    """Rolling mean of already normalised signed values, used for OFI."""

    def __init__(self, window_ms: int) -> None:
        self.window_ms = int(window_ms)
        self.items: Deque[Tuple[int, float]] = deque()
        self.total = 0.0

    def add(self, ts_ms: int, value: float) -> None:
        self.items.append((ts_ms, value))
        self.total += value
        self.prune(ts_ms)

    def prune(self, ts_ms: int) -> None:
        cutoff = ts_ms - self.window_ms
        while self.items and self.items[0][0] < cutoff:
            _, value = self.items.popleft()
            self.total -= value

    def value(self, ts_ms: int) -> float:
        self.prune(ts_ms)
        return self.total / len(self.items) if self.items else 0.0


class RollingPricePath:
    """Keeps a short price path and O(1) total travelled distance."""

    def __init__(self, window_ms: int = 30_000) -> None:
        self.window_ms = int(window_ms)
        self.items: Deque[Tuple[int, float]] = deque()
        self.path = 0.0

    def add(self, ts_ms: int, price: float) -> None:
        if self.items:
            self.path += abs(price - self.items[-1][1])
        self.items.append((ts_ms, price))
        self.prune(ts_ms)

    def prune(self, ts_ms: int) -> None:
        cutoff = ts_ms - self.window_ms
        while len(self.items) > 1 and self.items[1][0] < cutoff:
            first = self.items.popleft()
            self.path -= abs(self.items[0][1] - first[1])
        while len(self.items) == 1 and self.items[0][0] < cutoff:
            self.items.popleft()
            self.path = 0.0
        if self.path < 0.0:
            self.path = 0.0

    def efficiency(self, ts_ms: int) -> float:
        self.prune(ts_ms)
        if len(self.items) < 2 or self.path <= 1e-12:
            return 0.0
        return clamp(abs(self.items[-1][1] - self.items[0][1]) / self.path, 0.0, 1.0)


class RollingOpenSides:
    """Thirty-second balance of observations above and below candle open."""

    def __init__(self, window_ms: int = 30_000) -> None:
        self.window_ms = int(window_ms)
        self.items: Deque[Tuple[int, int]] = deque()
        self.above = 0
        self.below = 0

    def add(self, ts_ms: int, side: int) -> None:
        self.items.append((ts_ms, side))
        if side > 0:
            self.above += 1
        elif side < 0:
            self.below += 1
        self.prune(ts_ms)

    def prune(self, ts_ms: int) -> None:
        cutoff = ts_ms - self.window_ms
        while self.items and self.items[0][0] < cutoff:
            _, side = self.items.popleft()
            if side > 0:
                self.above -= 1
            elif side < 0:
                self.below -= 1

    def up_balance(self, ts_ms: int) -> float:
        self.prune(ts_ms)
        total = self.above + self.below
        return self.above / total if total else 0.5



# ---------------------------------------------------------------------------
# v4.5 model: one linear-in-tanh scorer whose weights are persisted and
# adapted by online SGD after every settled candle.
# ---------------------------------------------------------------------------
# (name, anchor weight, tanh threshold)
MODEL_FEATURE_SPEC: Tuple[Tuple[str, float, float], ...] = (
    ("delta_1s", 1.10, 0.10),
    ("delta_5s", 0.95, 0.10),
    ("delta_30s", 0.55, 0.12),
    ("ofi_1s", 0.85, 250.0),
    ("ofi_5s", 0.60, 250.0),
    ("spot_imbalance5", 0.90, 0.12),
    ("return_250ms_bps", 0.25, 0.80),
    ("return_1s_bps", 0.40, 1.30),
    ("return_5s_bps", 0.35, 2.50),
    # --- new in v4.5 ---
    ("body_range_ratio", 0.30, 0.50),
    ("close_location_centred", 0.30, 0.60),
    ("aggressive_cluster_bias", 0.25, 1.50),
    ("volume_profile_delta", 0.35, 0.15),
)
MODEL_FEATURE_NAMES: Tuple[str, ...] = tuple(name for name, _, _ in MODEL_FEATURE_SPEC)

class Model:
    """score = sum(w_i * tanh(x_i / thresh_i));  prob_up = sigmoid(score / T).

    Weights start at the hand-set anchors, are loaded from the database at
    start-up, and may drift by at most MODEL_WEIGHT_CLAMP from their anchor.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        version: int = 0,
        samples: int = 0,
        temperature: float = MODEL_TEMPERATURE,
        last_candle_id: int = 0,
    ) -> None:
        self.anchors: Dict[str, float] = {n: w for n, w, _ in MODEL_FEATURE_SPEC}
        self.thresholds: Dict[str, float] = {n: t for n, _, t in MODEL_FEATURE_SPEC}
        self.temperature = float(temperature) or MODEL_TEMPERATURE
        self.version = int(version)
        self.samples = int(samples)
        self.last_candle_id = int(last_candle_id)
        self.weights: Dict[str, float] = dict(self.anchors)
        if weights:
            for name, value in weights.items():
                if name in self.weights:
                    self.weights[name] = self._clamp_to_anchor(name, safe_float(value))

    def _clamp_to_anchor(self, name: str, value: float) -> float:
        anchor = self.anchors[name]
        return clamp(value, anchor - MODEL_WEIGHT_CLAMP, anchor + MODEL_WEIGHT_CLAMP)

    @classmethod
    def load(cls, store: "Store") -> "Model":
        stored = store.load_weights()
        if not stored:
            return cls()
        return cls(
            weights=stored.get("weights") or {},
            version=int(stored.get("version") or 0),
            samples=int(stored.get("samples") or 0),
            temperature=safe_float(stored.get("temperature"), MODEL_TEMPERATURE),
            last_candle_id=int(stored.get("last_candle_id") or 0),
        )

    def inputs(self, feature: Dict[str, Any]) -> Dict[str, float]:
        """tanh-squashed model inputs; unknown or missing features become 0."""
        out: Dict[str, float] = {}
        for name in MODEL_FEATURE_NAMES:
            threshold = self.thresholds[name] or 1.0
            out[name] = math.tanh(safe_float(feature.get(name)) / threshold)
        return out

    def score_inputs(
        self, inputs: Dict[str, float]
    ) -> Tuple[float, float, Dict[str, float]]:
        components = {
            name: self.weights[name] * safe_float(inputs.get(name))
            for name in MODEL_FEATURE_NAMES
        }
        score = sum(components.values())
        return score, logistic(score / self.temperature), components

    def score(self, feature: Dict[str, Any]) -> Tuple[float, float, Dict[str, float]]:
        return self.score_inputs(self.inputs(feature))

    def sgd_step(
        self,
        feature: Dict[str, Any],
        actual_up: bool,
        learning_rate: float = MODEL_LEARNING_RATE,
    ) -> Dict[str, Any]:
        """One anchored, clamped online gradient step on the log-loss.

        d/dw_i  of the log-loss is (y - p) * tanh(x_i / thresh_i) / T, which is
        the "gradient = (actual - prob) x tanh(feat)" step from the flowchart.
        """
        inputs = self.inputs(feature)
        _, probability_up, _ = self.score_inputs(inputs)
        target = 1.0 if actual_up else 0.0
        error = target - probability_up
        deltas: Dict[str, float] = {}
        for name in MODEL_FEATURE_NAMES:
            gradient = error * inputs[name] / self.temperature
            proposed = self.weights[name] + learning_rate * gradient
            clamped = self._clamp_to_anchor(name, proposed)
            deltas[name] = clamped - self.weights[name]
            self.weights[name] = clamped
        self.samples += 1
        self.version += 1
        return {
            "version": self.version,
            "samples": self.samples,
            "probability_up": probability_up,
            "error": error,
            "deltas": deltas,
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "samples": self.samples,
            "temperature": self.temperature,
            "last_candle_id": self.last_candle_id,
            "weights": dict(self.weights),
            "anchors": dict(self.anchors),
            "thresholds": dict(self.thresholds),
        }

    def weight_table(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "weight": self.weights[name],
                "anchor": self.anchors[name],
                "drift": self.weights[name] - self.anchors[name],
                "max_drift": MODEL_WEIGHT_CLAMP,
                "threshold": self.thresholds[name],
            }
            for name in MODEL_FEATURE_NAMES
        ]


@dataclass
class Prediction:
    candle_id: int
    kind: str
    direction: str
    ts_ms: int
    price: float
    probability_up: float
    reason: str
    actual: Optional[str] = None
    correct: Optional[bool] = None
    features: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candle_id": self.candle_id,
            "kind": self.kind,
            "direction": self.direction,
            "ts_ms": self.ts_ms,
            "time": london_stamp(self.ts_ms),
            "price": self.price,
            "probability_up": self.probability_up,
            "confidence": abs(self.probability_up - 0.5) * 2.0,
            "reason": self.reason,
            "actual": self.actual,
            "correct": self.correct,
        }


class StateXProtection:
    """Causal, persisted execution protection evaluated after signal fire.

    State X deliberately knows nothing about how MAIN, REVERSAL or EF reached
    a decision. It receives one already-fired signal observation, records the
    frozen research measurements, and exposes a separate pre-submit block.
    """

    def __init__(self, store: "Store") -> None:
        self.store = store
        self.lock = threading.RLock()
        self._notification_sink: Any = lambda message: print(message, flush=True)

    @staticmethod
    def _blank_state() -> Dict[str, Any]:
        return {
            "active": False,
            "trigger_time_ms": 0,
            "end_time_ms": 0,
            "trigger_reason": "",
            "rejection_balance": None,
            "aligned_delta30_median_15m": None,
            "late_metric_15m": None,
            "late_p80_6h": None,
            "aligned_1s_metric_15m": None,
            "aligned_1s_p80_6h": None,
            "activation_notified": False,
            "clear_notified": False,
            "last_notification": "",
        }

    def set_notification_sink(self, sink: Any) -> None:
        self._notification_sink = sink if callable(sink) else (lambda _message: None)

    def _read_locked(self) -> Tuple[bool, Dict[str, Any]]:
        row = self.store.control_row(STATE_X_CONTROL_KIND)
        state = self._blank_state()
        if isinstance(row.get("pending"), dict):
            state.update(row["pending"])
        return bool(row.get("manual_enabled")), state

    def _write_locked(self, enabled: bool, state: Dict[str, Any]) -> None:
        self.store.write_control(
            STATE_X_CONTROL_KIND,
            manual_enabled=bool(enabled),
            pending=dict(state),
        )

    def _send_notification(self, message: str) -> None:
        try:
            self._notification_sink(str(message))
        except Exception:
            # A terminal/dashboard notice must never alter execution state.
            pass

    @staticmethod
    def _number_text(value: Any, digits: int = 4) -> str:
        number = finite_float(value)
        return "--" if number is None else f"{number:.{digits}f}"

    def _refresh_expiry_locked(self, current_ms: int) -> Tuple[bool, Dict[str, Any]]:
        enabled, state = self._read_locked()
        end_ms = int(state.get("end_time_ms") or 0)
        if bool(state.get("active")) and end_ms and int(current_ms) >= end_ms:
            should_notify = not bool(state.get("clear_notified"))
            message = (
                "STATE X CLEARED — Trading protection period ended | "
                f"resume {london_stamp(end_ms)}"
            )
            state["active"] = False
            state["clear_notified"] = True
            state["last_notification"] = message
            self._write_locked(enabled, state)
            if should_notify:
                self._send_notification(message)
        return enabled, state

    def apply_toggle(self, enabled: bool, ts_ms: Optional[int] = None) -> Dict[str, Any]:
        if not isinstance(enabled, bool):
            return {"ok": False, "error": "State X switch must be true or false."}
        with self.lock:
            state = self._blank_state()
            self._write_locked(bool(enabled), state)
        return {"ok": True, "enabled": bool(enabled), "state": self.snapshot(ts_ms)}

    def snapshot(self, ts_ms: Optional[int] = None) -> Dict[str, Any]:
        current = now_ms() if ts_ms is None else int(ts_ms)
        with self.lock:
            enabled, _state = self._read_locked()
        return {
            "enabled": enabled, "active": False,
            "status": "PER-TRADE" if enabled else "SHADOW DIAGNOSTIC",
            "trigger_time_ms": None, "trigger_time": None, "end_time_ms": None,
            "resume_time": None, "remaining_ms": 0, "remaining_seconds": 0.0,
            "trigger_reason": "", "last_notification": "",
        }

    @staticmethod
    def _execution_fields(state: Dict[str, Any], blocked: bool) -> Dict[str, Any]:
        return {
            "state_x": "SX" if blocked else "",
            "state_x_active": bool(blocked),
            "state_x_trigger_time": (
                (int(state.get("trigger_time_ms") or 0) or None) if blocked else None
            ),
            "state_x_end_time": (
                (int(state.get("end_time_ms") or 0) or None) if blocked else None
            ),
            "sx_trigger_reason": (
                str(state.get("trigger_reason") or "") if blocked else ""
            ),
        }

    def execution_block(
        self,
        ts_ms: Optional[int] = None,
        existing_submit_ms: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """No blanket authority in v9.1.1; SX decisions are signal-specific."""
        return False, self._execution_fields({}, False)

    def observe_signal(
        self, prediction: Prediction, feature: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Single-trade hostile-state veto; OFF remains shadow-only diagnostics."""
        ts_ms = int(prediction.ts_ms)
        direction = str(prediction.direction).upper()
        sign = 1.0 if direction == "UP" else -1.0
        r1 = sign * safe_float(feature.get("return_1s_bps"))
        r250 = sign * safe_float(feature.get("return_250ms_bps"))
        d1 = sign * safe_float(feature.get("delta_1s"))
        d5 = sign * safe_float(feature.get("delta_5s"))
        ofi1 = sign * safe_float(feature.get("ofi_1s"))
        imb = sign * safe_float(feature.get("spot_imbalance5"))
        reject_up = max(0.0, safe_float(feature.get("reject_up")))
        reject_down = max(0.0, safe_float(feature.get("reject_down")))
        rejection_against = (reject_up - reject_down) if sign > 0 else (reject_down - reject_up)
        adverse_price = (r1 <= -0.10) or (r250 <= -0.07)
        hostile = [d1 <= -0.15 or d5 <= -0.12, ofi1 <= -0.15, imb <= -0.12, rejection_against >= 0.30]
        confirmations = sum(1 for flag in hostile if flag)
        would_veto = bool(adverse_price and confirmations >= 2)
        with self.lock:
            enabled, _ = self._read_locked()
        blocked = bool(enabled and would_veto)
        reason = f"adverse BTC response + {confirmations} hostile families" if would_veto else ""
        fields = {
            "state_x": "SX" if blocked else "",
            "state_x_active": blocked,
            "state_x_trigger_time": ts_ms if blocked else None,
            "state_x_end_time": None,
            "sx_trigger_reason": reason,
            "sx_rejection_balance": rejection_against,
            "sx_aligned_delta30_median_15m": sign * safe_float(feature.get("delta_30s")),
        }
        return {
            "blocked": blocked, "would_block": would_veto, "fields": fields,
            "observation": {"ts_ms": ts_ms, "direction": direction,
                            "adverse_price": adverse_price,
                            "hostile_confirmations": confirmations,
                            "would_block": would_veto, "enabled": enabled},
        }


class TradeControls:
    """Execution controls and shared staking; State X is per-trade only in v9.1.1."""

    def __init__(self, store: "Store") -> None:
        self.store = store
        # Linearize a live POST against master-toggle and ban-rule changes.
        # If an order is already crossing the network, an OFF request waits
        # for that one submission to finish; once OFF is acknowledged, no
        # later submission can have passed the old control state.
        self.submit_gate = threading.RLock()
        # Every explicit master-toggle request advances this in-process intent
        # generation, even when it repeats the current value. A slow ON
        # preflight can therefore never overtake a later acknowledged OFF.
        self._manual_version = 0
        self.state_x = StateXProtection(store)

    def manual_version(self) -> int:
        with self.submit_gate:
            return self._manual_version

    def apply_signal_toggle(
        self, kind: str, manual_enabled: bool
    ) -> Dict[str, Any]:
        """Immediately change one stream's NEW-order permission.

        This mutation shares submit_gate with the final live POST. Therefore an
        OFF response cannot be acknowledged while an older submission is still
        crossing the venue boundary, and no later submission can pass the old
        state. Existing accepted/signed orders are never cancelled.
        """
        kind = str(kind).upper()
        if kind not in TRADE_KINDS:
            return {"ok": False, "error": f"Unknown signal: {kind}"}
        if not isinstance(manual_enabled, bool):
            return {"ok": False, "error": "Signal switch must be true or false."}
        with self.submit_gate:
            self.store.write_control(
                kind, manual_enabled=manual_enabled, pending=None
            )
        return {
            "ok": True,
            "applied": True,
            "kind": kind,
            "manual_enabled": manual_enabled,
        }

    def apply_state_x_toggle(
        self, manual_enabled: bool, ts_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """Persist and linearize the independent State X protection switch."""
        if not isinstance(manual_enabled, bool):
            return {"ok": False, "error": "State X switch must be true or false."}
        with self.submit_gate:
            return self.state_x.apply_toggle(manual_enabled, ts_ms)

    # ---- bans ---------------------------------------------------------
    def active_ban(
        self, kind: str, ts_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        moment, label = local_moment(ts_ms)
        minute = moment.hour * 60 + moment.minute
        for rule in self.store.ban_rules():
            if kind not in (rule.get("kinds") or []):
                continue
            if rule_covers(rule, moment.weekday(), minute):
                return {
                    "rule": rule,
                    "label": describe_rule(rule),
                    "until": minute_to_clock(int(rule.get("end_minute", 0))),
                    "zone": label,
                    "clock": moment.strftime("%H:%M"),
                    "weekday": moment.strftime("%a"),
                }
        return None

    # ---- effective state ----------------------------------------------
    def state(self, kind: str, ts_ms: Optional[int] = None) -> Dict[str, Any]:
        """Effective live-order state for one stream.

        Shared stake/streak stays on SYSTEM. The individual row contributes
        only its persistent manual execution preference.
        """
        if kind not in TRADE_KINDS:
            raise ValueError(f"unknown signal: {kind}")
        shared = self.store.control_row(SYSTEM_CONTROL_KIND)
        if shared.get("pending") and not self.store.open_position_kinds(ts_ms):
            self.flush_pending(SYSTEM_CONTROL_KIND, ts_ms)
            shared = self.store.control_row(SYSTEM_CONTROL_KIND)
        signal_row = self.store.control_row(kind)
        ban = self.active_ban(kind, ts_ms)
        master = bool(shared["manual_enabled"])
        individual = bool(signal_row["manual_enabled"])
        effective = master and individual and ban is None
        if not master:
            status = "MASTER OFF" + (" · SIGNAL OFF" if not individual else "")
        elif not individual:
            status = "MANUALLY OFF"
        elif ban is not None:
            status = f"AUTO-BANNED until {ban['until']}"
        else:
            status = "ACTIVE"
        pending = shared.get("pending")
        return {
            "kind": kind,
            "manual_enabled": individual,
            "master_enabled": master,
            "auto_banned": ban is not None,
            "ban": ban,
            "effective_enabled": effective,
            "status": status,
            "stake": shared["stake"],
            "win_streak": shared["win_streak"],
            "loss_streak": shared["loss_streak"],
            "pending": pending,
            "pending_status": (
                "PENDING SHARED STAKE CHANGE - applies after current position settles"
                if pending else None
            ),
            "next_stake": self.next_stake(kind),
        }

    def may_execute(
        self, kind: str, ts_ms: Optional[int] = None
    ) -> Tuple[bool, str]:
        state = self.state(kind, ts_ms)
        if not state["master_enabled"]:
            return False, "master trading switch is manually OFF"
        if not state["manual_enabled"]:
            # Keep the exact `manually OFF` phrase: existing Data/history logic
            # uses it to classify forbidden rows as signals-off (blue F).
            return False, f"{kind} trading is manually OFF"
        ban = state["ban"]
        if ban is not None:
            return False, (
                f"banned window {ban['label']} "
                f"({ban['weekday']} {ban['clock']} {ban['zone']})"
            )
        return True, ""

    # ---- staking ------------------------------------------------------
    def next_stake(self, kind: str, free_capital: Optional[float] = None) -> float:
        """One shared stake, identically returned for all three signals."""
        if kind not in TRADE_KINDS:
            raise ValueError(f"unknown signal: {kind}")
        row = self.store.control_row(SYSTEM_CONTROL_KIND)
        config = row["stake"]
        capital = self.store.capital_state()
        if free_capital is None:
            free_capital = float(capital["free"])
        # Percentage mode sizes from shared balance, not sequentially shrinking
        # free cash; simultaneous MAIN/REVERSAL/EF signals therefore request
        # the same dollar stake. Streak mode holds steady between resets.
        stake = configured_stake(config, float(capital["balance"]))
        # A funded order always uses the one configured shared stake. Do not
        # silently shrink a later MAIN/REVERSAL/EF leg when capital is short;
        # return zero so the caller records NO_CAPITAL instead.
        return stake if max(0.0, free_capital) + 1e-9 >= stake else 0.0

    def record_result(self, kind: str, won: bool) -> Dict[str, Any]:
        """Advance the shared streak using only fresh Predict.fun capital."""
        if kind not in ("MAIN_REV", "EF", *TRADE_KINDS):
            raise ValueError(f"unknown streak source: {kind}")
        with self.store.lock:
            row = self.store.control_row(SYSTEM_CONTROL_KIND)
            config = dict(row["stake"])
            win_streak = row["win_streak"] + 1 if won else 0
            loss_streak = 0 if won else row["loss_streak"] + 1
            recalculated = False
            if str(config.get("mode")) == STAKE_MODE_STREAK:
                win_trigger = max(1, int(config.get("win_trigger", 3)))
                loss_trigger = max(1, int(config.get("loss_trigger", 2)))
                if win_streak >= win_trigger or loss_streak >= loss_trigger:
                    capital = self.store.capital_state()
                    if bool(capital.get("fresh")):
                        free = float(capital["free"])
                        fresh = free * float(config.get("percent", 10.0)) / 100.0
                        fresh = max(
                            float(config.get("min_stake", MIN_STAKE_USD)),
                            min(
                                float(config.get("max_stake", MAX_STAKE_USD)),
                                fresh,
                            ),
                        )
                        config["current_stake"] = round(fresh, 2)
                        win_streak = 0
                        loss_streak = 0
                        recalculated = True
                    # No live balance proof => keep the reached streak intact.
                    # The next settled result can recalculate once the wallet
                    # worker has a fresh Predict.fun USDT balance again.
            self.store.write_control(
                SYSTEM_CONTROL_KIND,
                stake=config,
                win_streak=win_streak,
                loss_streak=loss_streak,
            )
        return {
            "kind": kind,
            "won": won,
            "win_streak": win_streak,
            "loss_streak": loss_streak,
            "recalculated": recalculated,
            "current_stake": config.get("current_stake"),
        }

    # ---- staged changes ------------------------------------------------
    def apply_change(
        self,
        kind: str = SYSTEM_CONTROL_KIND,
        manual_enabled: Optional[bool] = None,
        stake: Optional[Dict[str, Any]] = None,
        ts_ms: Optional[int] = None,
        expected_manual_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply the master toggle and shared stake configuration.

        OFF is immediate and never cancels an already accepted order. A stake
        edit is parked until all current positions settle so an open order is
        never reinterpreted with a different capital rule.
        """
        if manual_enabled is not None and not isinstance(manual_enabled, bool):
            return {"ok": False, "error": "Master switch must be true or false."}
        if stake is not None and not isinstance(stake, dict):
            return {"ok": False, "error": "Stake configuration must be an object."}
        if stake is not None:
            error = validate_stake_config(stake)
            if error:
                return {"ok": False, "error": error}
        change: Dict[str, Any] = {}
        if manual_enabled is not None:
            change["manual_enabled"] = bool(manual_enabled)
        if stake is not None:
            change["stake"] = stake
        if not change:
            return {"ok": True, "applied": False, "pending": False}
        # The whole mutation is ordered against order submission. The master
        # toggle is immediate; only stake edits wait for open positions.
        with self.submit_gate:
            if (
                expected_manual_version is not None
                and int(expected_manual_version) != self._manual_version
            ):
                return {
                    "ok": False,
                    "error": (
                        "Master state changed during live preflight; "
                        "review it and turn ON again."
                    ),
                    "stale": True,
                }
            stake_pending = (
                stake is not None
                and bool(self.store.open_position_kinds(ts_ms))
            )
            pending_value: Any = "keep"
            applied_stake = stake
            if stake is not None:
                pending_value = {"stake": stake} if stake_pending else None
                if stake_pending:
                    applied_stake = None
            # One SQLite replacement exposes master, stake and pending state
            # together to signal threads; there is no observable half-change.
            self.store.write_control(
                SYSTEM_CONTROL_KIND,
                manual_enabled=manual_enabled,
                stake=applied_stake,
                pending=pending_value,
            )
            if manual_enabled is not None:
                self._manual_version += 1
            if stake_pending:
                return {
                    "ok": True, "applied": manual_enabled is not None,
                    "pending": True, "manual_version": self._manual_version,
                }
            if stake is not None:
                self.store.write_control(
                    SYSTEM_CONTROL_KIND, stake=stake, pending=None)
            return {
                "ok": True, "applied": True, "pending": False,
                "manual_version": self._manual_version,
            }

    def flush_pending(self, kind: str, ts_ms: Optional[int] = None) -> bool:
        """Apply a parked shared stake once no live position remains."""
        with self.submit_gate:
            row = self.store.control_row(SYSTEM_CONTROL_KIND)
            pending = row.get("pending")
            if not pending:
                return False
            if self.store.open_position_kinds(ts_ms):
                return False
            self.store.write_control(
                SYSTEM_CONTROL_KIND,
                manual_enabled=pending.get("manual_enabled"),
                stake=pending.get("stake"),
                pending=None)
            return True

    def snapshot(self, ts_ms: Optional[int] = None) -> Dict[str, Any]:
        moment, label = local_moment(ts_ms)
        shared = self.store.control_row(SYSTEM_CONTROL_KIND)
        return {
            "timezone": label,
            "clock": moment.strftime("%a %H:%M"),
            "master_enabled": bool(shared["manual_enabled"]),
            "master_status": (
                "ON" if bool(shared["manual_enabled"]) else "OFF - safe startup"
            ),
            "shared_stake": shared["stake"],
            "shared_next_stake": self.next_stake("MAIN"),
            "win_streak": shared["win_streak"],
            "loss_streak": shared["loss_streak"],
            "pending": shared.get("pending"),
            "state_x": self.state_x.snapshot(ts_ms),
            "kinds": {k: self.state(k, ts_ms) for k in TRADE_KINDS},
            "rules": [
                {**rule, "describe": describe_rule(rule)}
                for rule in self.store.ban_rules()
            ],
            "open_positions": self.store.open_position_kinds(),
            "modes": list(STAKE_MODES),
        }


class Store:
    """Persistent signals, learned weights, and live execution journal."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    candle_id INTEGER PRIMARY KEY,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    closed_ts_ms INTEGER NOT NULL,
                    actual TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candle_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('MAIN','REVERSAL')),
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    ts_ms INTEGER NOT NULL,
                    price REAL NOT NULL,
                    probability_up REAL NOT NULL,
                    reason TEXT NOT NULL,
                    actual TEXT,
                    correct INTEGER,
                    UNIQUE(candle_id, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_predictions_candle
                    ON predictions(candle_id);
                CREATE TABLE IF NOT EXISTS ef_predictions (
                    candle_id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL DEFAULT 'EF' CHECK(kind='EF'),
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    ts_ms INTEGER NOT NULL,
                    price REAL NOT NULL,
                    probability_up REAL NOT NULL,
                    reason TEXT NOT NULL,
                    actual TEXT,
                    correct INTEGER,
                    features TEXT
                );
                CREATE TABLE IF NOT EXISTS ef_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candle_id INTEGER NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    ts_ms INTEGER NOT NULL,
                    decision_ts_ms INTEGER NOT NULL,
                    price REAL NOT NULL,
                    probability_up REAL NOT NULL,
                    fired INTEGER NOT NULL DEFAULT 0,
                    abstain_reason TEXT,
                    reference_vwap_10 REAL,
                    settlement_probability REAL,
                    settlement_probability_base REAL,
                    ef_consensus REAL,
                    expected_edge REAL,
                    probability_floor REAL,
                    consensus_floor REAL,
                    edge_floor REAL,
                    actual TEXT,
                    features TEXT,
                    UNIQUE(candle_id, ts_ms, direction)
                );
                CREATE INDEX IF NOT EXISTS idx_ef_candidates_candle
                    ON ef_candidates(candle_id, ts_ms);
                CREATE TABLE IF NOT EXISTS ef_progress (
                    candle_id INTEGER PRIMARY KEY,
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    fire_ts_ms INTEGER NOT NULL,
                    fire_price REAL NOT NULL,
                    candle_open REAL NOT NULL,
                    initial_distance REAL NOT NULL,
                    closest_distance REAL,
                    progress_fraction REAL,
                    crossed_open INTEGER NOT NULL DEFAULT 0,
                    first_cross_ms INTEGER,
                    best_side_distance REAL,
                    outcome_class TEXT,
                    final_actual TEXT,
                    final_financial_pnl REAL,
                    final_financial_result TEXT,
                    fire_features TEXT,
                    updated_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gated_predictions (
                    candle_id INTEGER PRIMARY KEY,
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    ts_ms INTEGER NOT NULL,
                    phase_second REAL NOT NULL,
                    price REAL NOT NULL,
                    entry_odds REAL NOT NULL,
                    reason TEXT NOT NULL,
                    actual TEXT,
                    correct INTEGER
                );
                CREATE TABLE IF NOT EXISTS model_weights (
                    version INTEGER PRIMARY KEY,
                    ts_ms INTEGER NOT NULL,
                    samples INTEGER NOT NULL,
                    temperature REAL NOT NULL,
                    last_candle_id INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta(
                    key TEXT PRIMARY KEY, value TEXT NOT NULL)
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS trades(
                    candle_id INTEGER NOT NULL, kind TEXT NOT NULL,
                    direction TEXT NOT NULL, ts_ms INTEGER NOT NULL,
                    seconds_into_candle REAL, quoted_price REAL,
                    fill_price REAL, slippage REAL, delay_ms INTEGER,
                    attempts INTEGER, filled INTEGER, break_even REAL,
                    spread REAL, book_size REAL, actual TEXT,
                    correct INTEGER, pnl REAL, stake REAL, shares REAL,
                    fee_rate REAL, market_id TEXT, market_title TEXT,
                    book_age_ms INTEGER, failure_reason TEXT,
                    attempt_log TEXT,
                    PRIMARY KEY (candle_id, kind))
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_controls(
                    kind TEXT PRIMARY KEY,
                    manual_enabled INTEGER NOT NULL DEFAULT 1,
                    stake_config TEXT NOT NULL,
                    win_streak INTEGER NOT NULL DEFAULT 0,
                    loss_streak INTEGER NOT NULL DEFAULT 0,
                    pending TEXT,
                    updated_ms INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS state_x_observations(
                    candle_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('MAIN','REVERSAL','EF')),
                    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
                    ts_ms INTEGER NOT NULL,
                    seconds_into_candle REAL,
                    aligned_return_1s_bps REAL,
                    aligned_delta_30s REAL,
                    late_metric_15m REAL,
                    aligned_1s_metric_15m REAL,
                    aligned_delta30_median_15m REAL,
                    late_p80_6h REAL,
                    aligned_1s_p80_6h REAL,
                    original_candidate INTEGER NOT NULL DEFAULT 0,
                    original_confirmed INTEGER NOT NULL DEFAULT 0,
                    rejection_balance REAL,
                    refined_trigger INTEGER NOT NULL DEFAULT 0,
                    trigger_reason TEXT,
                    inputs_ready INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(candle_id, kind)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_x_observations_ts "
                "ON state_x_observations(ts_ms)"
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS ban_rules(
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_ms INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # v7 does not create a separate EF improvement-capture table. Old
            # tables, if present in an existing database, remain untouched as
            # historical user data.
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS streak_events(
                    candle_id INTEGER NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('MAIN_REV','EF')),
                    won INTEGER NOT NULL,
                    created_ms INTEGER NOT NULL,
                    PRIMARY KEY(candle_id, source)
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS order_fills(
                    order_hash TEXT NOT NULL,
                    settlement_id TEXT NOT NULL,
                    candle_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('MAIN','REVERSAL','EF')),
                    executed_price REAL NOT NULL,
                    executed_shares REAL NOT NULL,
                    executed_value REAL NOT NULL,
                    fee_amount REAL NOT NULL DEFAULT 0,
                    fee_type TEXT,
                    confirmed_ms INTEGER NOT NULL,
                    PRIMARY KEY(order_hash, settlement_id)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_fills_trade "
                "ON order_fills(candle_id,kind)"
            )
            # v7.7: settled winnings that the venue has not yet turned back
            # into spendable smart-account USDT.
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS payout_claims(
                    candle_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('MAIN','REVERSAL','EF')),
                    payout_usd REAL NOT NULL,
                    settled_ms INTEGER NOT NULL,
                    credited_usd REAL NOT NULL DEFAULT 0,
                    credited_ms INTEGER,
                    PRIMARY KEY(candle_id, kind)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_payout_claims_open "
                "ON payout_claims(settled_ms)"
            )
            # v7.8: the venue's own view of what we hold. This table is a
            # mirror of GET /v1/positions and is never written from local
            # estimates, so anything read from it is what Predict.fun says.
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS venue_positions(
                    position_id TEXT PRIMARY KEY,
                    market_id TEXT,
                    market_title TEXT,
                    outcome_name TEXT,
                    index_set INTEGER,
                    condition_id TEXT,
                    shares REAL NOT NULL,
                    value_usd REAL,
                    avg_buy_price REAL,
                    pnl_usd REAL,
                    best_bid REAL,
                    best_ask REAL,
                    outcome_status TEXT,
                    market_status TEXT,
                    candle_id INTEGER,
                    kind TEXT,
                    direction TEXT,
                    updated_ms INTEGER NOT NULL
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_venue_positions_market "
                "ON venue_positions(market_id)"
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS outcome_events(
                    candle_id INTEGER PRIMARY KEY,
                    ts_ms INTEGER NOT NULL,
                    actual TEXT NOT NULL,
                    main_direction TEXT NOT NULL,
                    main_correct INTEGER NOT NULL,
                    main_confidence REAL NOT NULL,
                    reversal_direction TEXT,
                    reversal_correct INTEGER,
                    net_direction TEXT NOT NULL,
                    net_correct INTEGER NOT NULL
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_events (
                    candle_id INTEGER PRIMARY KEY,
                    ts_ms INTEGER NOT NULL,
                    actual TEXT NOT NULL,
                    main_direction TEXT NOT NULL,
                    main_entry_price REAL NOT NULL,
                    main_stake REAL NOT NULL,
                    main_shares REAL NOT NULL,
                    main_pnl REAL NOT NULL,
                    reversal_direction TEXT,
                    reversal_entry_price REAL,
                    reversal_stake REAL,
                    reversal_shares REAL,
                    reversal_pnl REAL,
                    net_pnl REAL NOT NULL
                );
                """
            )
            # v4.0.x databases have no feature snapshot column.
            columns = {
                row["name"]
                for row in self.db.execute("PRAGMA table_info(predictions)").fetchall()
            }
            if "features" not in columns:
                self.db.execute("ALTER TABLE predictions ADD COLUMN features TEXT")
            trade_columns = {
                row["name"]
                for row in self.db.execute("PRAGMA table_info(trades)").fetchall()
            }
            trade_additions = {
                "stake": "REAL",
                "shares": "REAL",
                "fee_rate": "REAL",
                "market_id": "TEXT",
                "market_title": "TEXT",
                "book_age_ms": "INTEGER",
                "failure_reason": "TEXT",
                "attempt_log": "TEXT",
                # v6.3: a blocked signal still records the candle and the
                # share price it would have paid, marked FORBIDDEN, so the
                # data is kept for future models without touching P&L,
                # capital, accuracy, streaks or fill statistics.
                "forbidden": "INTEGER",
                "execution_mode": "TEXT",
                "order_id": "TEXT",
                "order_hash": "TEXT",
                "order_status": "TEXT",
                "submitted_ms": "INTEGER",
                "confirmed_ms": "INTEGER",
                "filled_value": "REAL",
                "retry_count": "INTEGER",
                "fee_collateral": "REAL",
                "fee_shares": "REAL",
                # v7.7: delay_ms became the LAST attempt's latency because
                # every retry reset its own start clock. first_submit_ms pins
                # the origin so delay_ms is the true end-to-end cost of the
                # order, and last_attempt_ms keeps the per-attempt figure.
                "first_submit_ms": "INTEGER",
                "last_attempt_ms": "INTEGER",
                # v8 State X is additive research metadata. The human-readable
                # marker stays separate from the existing forbidden/F flag.
                "state_x": "TEXT",
                "state_x_active": "INTEGER",
                "state_x_trigger_time": "INTEGER",
                "state_x_end_time": "INTEGER",
                "sx_late_metric_15m": "REAL",
                "sx_late_p80_6h": "REAL",
                "sx_aligned_1s_metric_15m": "REAL",
                "sx_aligned_1s_p80_6h": "REAL",
                "sx_rejection_balance": "REAL",
                "sx_aligned_delta30_median_15m": "REAL",
                "sx_trigger_reason": "TEXT",
                # v9.1.1 financial truth / shadow-forward-test metadata.
                "financial_result": "TEXT",
                "financial_pnl": "REAL",
                "financial_source": "TEXT",
                "financial_is_shadow": "INTEGER",
                "execution_eligibility": "TEXT",
                "execution_vwap": "REAL",
                "ef_attempt_seq": "INTEGER",
            }
            for name, sql_type in trade_additions.items():
                if name not in trade_columns:
                    self.db.execute(
                        f"ALTER TABLE trades ADD COLUMN {name} {sql_type}"
                    )
            self.db.commit()
        self._seed_controls()
        # R5.1 failed-EF audit/re-arm infrastructure. Re-arm notices live in a
        # dedicated in-memory acknowledgement map, not a destructive queue. A
        # notice therefore cannot disappear merely because Engine.current_ef was
        # temporarily None or not yet restored when the executor finished.
        self._r5_ef_rearm_lock = threading.Lock()
        self._r5_ef_rearm_pending: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
        # Optional in-process lifecycle sink. Store remains the durable source of
        # truth, but a live Engine can clear its in-memory EF immediately after
        # the archive commits instead of waiting for a later market event.
        self._r5_ef_rearm_sink: Optional[Any] = None
        with self.lock:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS ef_failed_attempts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candle_id INTEGER NOT NULL,
                    direction TEXT,
                    signal_ts_ms INTEGER,
                    attempt_seq INTEGER,
                    order_status TEXT,
                    reason TEXT,
                    cooldown_until_ms INTEGER,
                    prediction_json TEXT NOT NULL,
                    trade_json TEXT NOT NULL,
                    archived_ms INTEGER NOT NULL
                )
                """
            )
            failed_columns = {
                row["name"] for row in self.db.execute(
                    "PRAGMA table_info(ef_failed_attempts)"
                ).fetchall()
            }
            if "attempt_seq" not in failed_columns:
                self.db.execute(
                    "ALTER TABLE ef_failed_attempts ADD COLUMN attempt_seq INTEGER"
                )
            if "cooldown_until_ms" not in failed_columns:
                self.db.execute(
                    "ALTER TABLE ef_failed_attempts ADD COLUMN cooldown_until_ms INTEGER"
                )
            # Backfill old audit rows deterministically by archive order so even
            # databases created by the first R5 can answer attempt 1/2/3.
            sequence_by_candle: Dict[int, int] = {}
            old_attempts = self.db.execute(
                "SELECT id,candle_id,attempt_seq FROM ef_failed_attempts "
                "ORDER BY candle_id,id"
            ).fetchall()
            for old in old_attempts:
                cid = int(old["candle_id"])
                seq = sequence_by_candle.get(cid, 0) + 1
                sequence_by_candle[cid] = seq
                if old["attempt_seq"] is None or int(old["attempt_seq"] or 0) != seq:
                    self.db.execute(
                        "UPDATE ef_failed_attempts SET attempt_seq=? WHERE id=?",
                        (seq, int(old["id"])),
                    )
            self.db.commit()

    def close(self) -> None:
        with self.lock:
            self.db.commit()
            self.db.close()

    def add_prediction(self, prediction: Prediction) -> bool:
        with self.lock:
            try:
                payload = json.dumps(prediction.features or {}, allow_nan=False)
            except (TypeError, ValueError):
                payload = "{}"
            cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO predictions
                (candle_id, kind, direction, ts_ms, price, probability_up, reason,
                 features)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction.candle_id,
                    prediction.kind,
                    prediction.direction,
                    prediction.ts_ms,
                    prediction.price,
                    prediction.probability_up,
                    prediction.reason,
                    payload,
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def get_prediction(self, candle_id: int, kind: str) -> Optional[Prediction]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM predictions WHERE candle_id=? AND kind=?",
                (candle_id, kind),
            ).fetchone()
        return self._prediction_from_row(row) if row else None

    def r5_order_hash_has_fill(self, order_hash: str) -> bool:
        # Venue-hash fill fence used by late-terminal reconciliation.
        key = str(order_hash or "").strip().lower()
        if not key:
            return False
        with self.lock:
            row = self.db.execute(
                "SELECT 1 FROM order_fills WHERE lower(order_hash)=? LIMIT 1",
                (key,),
            ).fetchone()
        return row is not None

    def _r5_next_ef_attempt_seq_locked(self, candle_id: int) -> int:
        row = self.db.execute(
            "SELECT COALESCE(MAX(attempt_seq),0) FROM ef_failed_attempts "
            "WHERE candle_id=?",
            (int(candle_id),),
        ).fetchone()
        return int((row[0] if row else 0) or 0) + 1

    def next_ef_attempt_seq(self, candle_id: int) -> int:
        with self.lock:
            return self._r5_next_ef_attempt_seq_locked(int(candle_id))

    def r5_set_ef_rearm_sink(self, sink: Optional[Any]) -> None:
        """Register the live Engine lifecycle sink; persistence stays in Store."""
        with self._r5_ef_rearm_lock:
            self._r5_ef_rearm_sink = sink if callable(sink) else None

    def r5_pending_ef_rearm_notices(self) -> List[Dict[str, Any]]:
        """Snapshot unacknowledged executor->engine lifecycle events."""
        with self._r5_ef_rearm_lock:
            return [dict(event) for event in self._r5_ef_rearm_pending.values()]

    def r5_ack_ef_rearm_notice(
        self, candle_id: int, signal_ts_ms: int, direction: str
    ) -> None:
        key = (int(candle_id), int(signal_ts_ms), str(direction or "").upper())
        with self._r5_ef_rearm_lock:
            self._r5_ef_rearm_pending.pop(key, None)

    def latest_ef_failed_attempt(self, candle_id: int) -> Optional[Dict[str, Any]]:
        """Latest archived EF attempt for restart-safe cooldown restoration."""
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM ef_failed_attempts WHERE candle_id=? "
                "ORDER BY id DESC LIMIT 1",
                (int(candle_id),),
            ).fetchone()
        return dict(row) if row is not None else None

    def r5_hashless_price_limit_rows(self) -> List[Dict[str, Any]]:
        """Active EF rows that are provably non-live and must be re-armed.

        This is an executor-side safety sweep, not signal logic. A PRICE_LIMIT
        row with no signed hash and no fill cannot possibly become a live order,
        so leaving it in the active slot can only strand Engine.current_ef.
        """
        with self.lock:
            rows = self.db.execute(
                "SELECT candle_id,ts_ms,direction,failure_reason FROM trades "
                "WHERE kind='EF' AND COALESCE(filled,0)=0 "
                "AND (order_hash IS NULL OR TRIM(order_hash)='') "
                "AND UPPER(COALESCE(order_status,''))='PRICE_LIMIT' "
                "ORDER BY ts_ms"
            ).fetchall()
        return [dict(row) for row in rows]

    def r5_hashless_queue_full_rows(self) -> List[Dict[str, Any]]:
        """EF intents that never entered the executor because its queue was full.

        No signed hash exists and no POST was possible. They are safe to archive,
        but only after executor capacity returns so the same opportunity cannot
        hot-loop against a still-full queue.
        """
        with self.lock:
            rows = self.db.execute(
                "SELECT candle_id,ts_ms,direction,failure_reason FROM trades "
                "WHERE kind='EF' AND COALESCE(filled,0)=0 "
                "AND (order_hash IS NULL OR TRIM(order_hash)='') "
                "AND UPPER(COALESCE(order_status,''))='QUEUE_FULL' "
                "ORDER BY ts_ms"
            ).fetchall()
        return [dict(row) for row in rows]

    def r5_release_failed_ef(
        self, candle_id: int, signal_ts_ms: int, direction: str,
        reason: str = "", proven_terminal_hash: str = "",
        proven_terminal_state: str = "",
    ) -> bool:
        # Archive/delete only an exact EF proven to have no live/fill risk.
        cid = int(candle_id)
        sig_ts = int(signal_ts_ms)
        sig_dir = str(direction or "").upper()
        terminal_hash = str(proven_terminal_hash or "").strip().lower()
        terminal_state = str(proven_terminal_state or "").upper()
        notice: Optional[Dict[str, Any]] = None
        with self.lock:
            pred_row = self.db.execute(
                "SELECT * FROM ef_predictions WHERE candle_id=?", (cid,)
            ).fetchone()
            trade_row = self.db.execute(
                "SELECT * FROM trades WHERE candle_id=? AND kind='EF'", (cid,)
            ).fetchone()
            if pred_row is None and trade_row is None:
                return False
            pred = dict(pred_row) if pred_row is not None else {}
            trade = dict(trade_row) if trade_row is not None else {}
            for row in (pred, trade):
                if not row:
                    continue
                if int(row.get("ts_ms") or -1) != sig_ts:
                    return False
                if str(row.get("direction") or "").upper() != sig_dir:
                    return False
            if bool(trade.get("filled")):
                return False

            active_hash = str(trade.get("order_hash") or "").strip().lower()
            status = str(trade.get("order_status") or "").upper()
            if active_hash:
                # A signed hash is protected unless reconciliation supplied the
                # same hash plus a terminal venue state and the fill ledger is empty.
                if terminal_hash != active_hash:
                    return False
                if terminal_state not in set(PREDICT_ORDER_TERMINAL_FAILURES):
                    return False
                fill_row = self.db.execute(
                    "SELECT 1 FROM order_fills WHERE lower(order_hash)=? LIMIT 1",
                    (active_hash,),
                ).fetchone()
                if fill_row is not None:
                    return False
                status = terminal_state
            else:
                safe_statuses = {
                    "PRICE_LIMIT", "WRONG_MARKET", "NOT_SENT",
                    "NO_FRESH_BOOK", "NO_LIQUIDITY", "QUEUE_FULL"
                } | set(PREDICT_ORDER_TERMINAL_FAILURES)
                if status not in safe_statuses:
                    return False

            attempt_seq = int(
                trade.get("ef_attempt_seq")
                or self._r5_next_ef_attempt_seq_locked(cid)
            )
            archived_at = now_ms()
            cooldown_until = (
                archived_at + EF_PRICE_LIMIT_COOLDOWN_MS
                if status == "PRICE_LIMIT" else 0
            )
            archived_trade = dict(trade)
            archived_trade["ef_attempt_seq"] = attempt_seq
            if terminal_hash:
                archived_trade["r5_proven_terminal_hash"] = terminal_hash
                archived_trade["r5_proven_terminal_state"] = terminal_state
            final_reason = str(reason or trade.get("failure_reason") or status)
            self.db.execute(
                """
                INSERT INTO ef_failed_attempts(
                    candle_id,direction,signal_ts_ms,attempt_seq,order_status,reason,
                    cooldown_until_ms,prediction_json,trade_json,archived_ms
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cid, sig_dir, sig_ts, attempt_seq, status, final_reason,
                    cooldown_until,
                    json.dumps(pred, default=str, separators=(",", ":")),
                    json.dumps(archived_trade, default=str, separators=(",", ":")),
                    archived_at,
                ),
            )
            self.db.execute("DELETE FROM ef_progress WHERE candle_id=?", (cid,))
            self.db.execute("DELETE FROM trades WHERE candle_id=? AND kind='EF'", (cid,))
            self.db.execute("DELETE FROM ef_predictions WHERE candle_id=?", (cid,))
            self.db.commit()
            notice = {
                "candle_id": cid, "signal_ts_ms": sig_ts,
                "direction": sig_dir, "status": status,
                "reason": final_reason, "attempt_seq": attempt_seq,
                "archived_ms": archived_at,
                "cooldown_until_ms": cooldown_until,
            }
        # Do not destructively consume this event until Engine explicitly ACKs
        # the exact signal identity. This closes the old TRIGGERED-but-deleted
        # mismatch caused by a one-shot queue event being skipped.
        key = (cid, sig_ts, sig_dir)
        sink = None
        payload = dict(notice or {})
        with self._r5_ef_rearm_lock:
            self._r5_ef_rearm_pending[key] = payload
            sink = self._r5_ef_rearm_sink
        # The DB transaction and Store locks are already finished here. Calling
        # the Engine sink now cannot create a Store<->Engine lock inversion.
        # If the sink fails, the persistent pending notice remains for the
        # market-event fallback path to consume later.
        if callable(sink):
            try:
                sink(dict(payload))
            except Exception:
                pass
        return True

    def upsert_ef_candidate(
        self, *, candle_id: int, direction: str, candidate_ts_ms: int,
        decision_ts_ms: int, price: float, probability_up: float,
        fired: bool, abstain_reason: str, reference_vwap_10: Optional[float],
        evidence: Dict[str, Any], features: Dict[str, Any],
    ) -> None:
        """Persist one continuous base-eligible EF opportunity episode.

        A candidate starts when the unchanged legacy EF gates first become true
        and remains the same candidate until those gates drop or direction changes.
        This records every distinct opportunity without writing SQLite every tick.
        """
        try:
            payload = json.dumps(features or {}, allow_nan=False)
        except (TypeError, ValueError):
            payload = "{}"
        with self.lock:
            self.db.execute(
                """
                INSERT INTO ef_candidates(
                    candle_id,direction,ts_ms,decision_ts_ms,price,probability_up,
                    fired,abstain_reason,reference_vwap_10,settlement_probability,
                    settlement_probability_base,ef_consensus,expected_edge,
                    probability_floor,consensus_floor,edge_floor,features)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(candle_id,ts_ms,direction) DO UPDATE SET
                    decision_ts_ms=excluded.decision_ts_ms,
                    price=excluded.price,probability_up=excluded.probability_up,
                    fired=MAX(ef_candidates.fired,excluded.fired),
                    abstain_reason=excluded.abstain_reason,
                    reference_vwap_10=excluded.reference_vwap_10,
                    settlement_probability=excluded.settlement_probability,
                    settlement_probability_base=excluded.settlement_probability_base,
                    ef_consensus=excluded.ef_consensus,expected_edge=excluded.expected_edge,
                    probability_floor=excluded.probability_floor,
                    consensus_floor=excluded.consensus_floor,edge_floor=excluded.edge_floor,
                    features=excluded.features
                """,
                (
                    int(candle_id), str(direction), int(candidate_ts_ms),
                    int(decision_ts_ms), float(price), float(probability_up),
                    1 if fired else 0, str(abstain_reason or ""),
                    reference_vwap_10, evidence.get("settlement_probability"),
                    evidence.get("settlement_probability_base"),
                    evidence.get("ef_consensus"), evidence.get("expected_edge"),
                    evidence.get("probability_floor"),
                    evidence.get("consensus_floor"), evidence.get("edge_floor"),
                    payload,
                ),
            )
            self.db.commit()

    def add_ef_prediction(self, prediction: Prediction) -> bool:
        """Persist EF separately so an existing v5.4 database is never rebuilt."""
        try:
            payload = json.dumps(prediction.features or {}, allow_nan=False)
        except (TypeError, ValueError):
            payload = "{}"
        with self.lock:
            cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO ef_predictions
                (candle_id,kind,direction,ts_ms,price,probability_up,reason,features)
                VALUES (?,'EF',?,?,?,?,?,?)
                """,
                (prediction.candle_id, prediction.direction, prediction.ts_ms,
                 prediction.price, prediction.probability_up, prediction.reason,
                 payload),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def get_ef_prediction(self, candle_id: int) -> Optional[Prediction]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM ef_predictions WHERE candle_id=?", (candle_id,)
            ).fetchone()
        return self._prediction_from_row(row) if row else None

    def save_ef_progress(self, row: Dict[str, Any]) -> None:
        """Upsert causal post-fire EF path diagnostics.

        Called at EF fire and candle settlement only. Per-tick progress remains
        in Engine memory so SQLite never enters the BTC market-event hot path.
        """
        try:
            feature_json = json.dumps(row.get("fire_features") or {}, allow_nan=False)
        except (TypeError, ValueError):
            feature_json = "{}"
        with self.lock:
            self.db.execute(
                """
                INSERT INTO ef_progress(
                    candle_id,direction,fire_ts_ms,fire_price,candle_open,
                    initial_distance,closest_distance,progress_fraction,
                    crossed_open,first_cross_ms,best_side_distance,outcome_class,
                    final_actual,final_financial_pnl,final_financial_result,
                    fire_features,updated_ms)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(candle_id) DO UPDATE SET
                    direction=excluded.direction,fire_ts_ms=excluded.fire_ts_ms,
                    fire_price=excluded.fire_price,candle_open=excluded.candle_open,
                    initial_distance=excluded.initial_distance,
                    closest_distance=COALESCE(excluded.closest_distance,ef_progress.closest_distance),
                    progress_fraction=COALESCE(excluded.progress_fraction,ef_progress.progress_fraction),
                    crossed_open=MAX(ef_progress.crossed_open,excluded.crossed_open),
                    first_cross_ms=COALESCE(ef_progress.first_cross_ms,excluded.first_cross_ms),
                    best_side_distance=MAX(COALESCE(ef_progress.best_side_distance,0),
                                           COALESCE(excluded.best_side_distance,0)),
                    outcome_class=COALESCE(excluded.outcome_class,ef_progress.outcome_class),
                    final_actual=COALESCE(excluded.final_actual,ef_progress.final_actual),
                    final_financial_pnl=COALESCE(excluded.final_financial_pnl,ef_progress.final_financial_pnl),
                    final_financial_result=COALESCE(excluded.final_financial_result,ef_progress.final_financial_result),
                    fire_features=CASE WHEN excluded.fire_features<>'{}' THEN excluded.fire_features ELSE ef_progress.fire_features END,
                    updated_ms=excluded.updated_ms
                """,
                (
                    int(row["candle_id"]), str(row["direction"]),
                    int(row["fire_ts_ms"]), float(row["fire_price"]),
                    float(row["candle_open"]), float(row["initial_distance"]),
                    row.get("closest_distance"), row.get("progress_fraction"),
                    1 if row.get("crossed_open") else 0, row.get("first_cross_ms"),
                    row.get("best_side_distance"), row.get("outcome_class"),
                    row.get("final_actual"), row.get("final_financial_pnl"),
                    row.get("final_financial_result"), feature_json, now_ms(),
                ),
            )
            self.db.commit()

    def ef_progress_row(self, candle_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM ef_progress WHERE candle_id=?", (int(candle_id),)
            ).fetchone()
        return dict(row) if row else None

    def settle_candle(self, candle: Dict[str, Any]) -> bool:
        candle_id = int(candle["time"])
        actual = "UP" if float(candle["close"]) >= float(candle["open"]) else "DOWN"
        closed_ts_ms = int(candle.get("close_time_ms") or (candle_id + CANDLE_MS - 1))
        with self.lock:
            existed = self.db.execute(
                "SELECT 1 FROM candles WHERE candle_id=?", (candle_id,)
            ).fetchone()
            self.db.execute(
                """
                INSERT INTO candles(candle_id, open, high, low, close, volume,
                                    closed_ts_ms, actual)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candle_id) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    closed_ts_ms=excluded.closed_ts_ms, actual=excluded.actual
                """,
                (
                    candle_id,
                    float(candle["open"]),
                    float(candle["high"]),
                    float(candle["low"]),
                    float(candle["close"]),
                    float(candle.get("volume", 0.0)),
                    closed_ts_ms,
                    actual,
                ),
            )
            self.db.execute(
                """
                UPDATE predictions
                SET actual=?, correct=CASE WHEN direction=? THEN 1 ELSE 0 END
                WHERE candle_id=?
                """,
                (actual, actual, candle_id),
            )
            self.db.execute(
                """
                UPDATE ef_predictions
                SET actual=?, correct=CASE WHEN direction=? THEN 1 ELSE 0 END
                WHERE candle_id=?
                """,
                (actual, actual, candle_id),
            )
            self.db.execute(
                "UPDATE ef_candidates SET actual=? WHERE candle_id=?",
                (actual, candle_id),
            )
            self.db.execute(
                """
                UPDATE gated_predictions
                SET actual=?, correct=CASE WHEN direction=? THEN 1 ELSE 0 END
                WHERE candle_id=?
                """,
                (actual, actual, candle_id),
            )
            self.db.commit()
            return existed is None

    def metrics(self) -> Dict[str, Any]:
        epoch = self.metrics_epoch()
        with self.lock:
            def metric_for(kind: str) -> Dict[str, Any]:
                raw = self.db.execute(
                    "SELECT financial_result,financial_is_shadow,order_status,filled FROM trades "
                    "WHERE kind=? AND candle_id>=? AND financial_result IN ('WIN','LOSS') "
                    "AND (filled=1 OR COALESCE(financial_is_shadow,0)=1)",
                    (kind, epoch),).fetchall()
                rows = [r for r in raw if financial_order_is_final(
                    r["order_status"], bool(r["financial_is_shadow"] or 0), bool(r["filled"] or 0))]
                wins = sum(1 for r in rows if r["financial_result"] == "WIN")
                real = sum(1 for r in rows if not int(r["financial_is_shadow"] or 0))
                shadow = len(rows) - real
                return {"correct": wins, "wins": wins, "losses": len(rows)-wins,
                        "total": len(rows), "accuracy": wins/len(rows) if rows else None,
                        "real": real, "shadow": shadow, "basis": "SETTLED_PNL_SIGN"}
            main_metric = metric_for("MAIN")
            rev_metric = metric_for("REVERSAL")
            ef_metric = metric_for("EF")
            candles = self.db.execute(
                "SELECT DISTINCT candle_id FROM trades WHERE candle_id>=?", (epoch,)).fetchall()
            primary_results: List[Tuple[str,bool]] = []
            for cr in candles:
                cid=int(cr[0])
                raw=self.db.execute(
                    "SELECT kind,financial_result,financial_is_shadow,filled,order_status FROM trades "
                    "WHERE candle_id=? AND kind IN ('MAIN','REVERSAL') "
                    "AND financial_result IN ('WIN','LOSS') ORDER BY CASE kind WHEN 'REVERSAL' THEN 0 ELSE 1 END",
                    (cid,),).fetchall()
                r=next((x for x in raw if financial_order_is_final(
                    x["order_status"], bool(x["financial_is_shadow"] or 0), bool(x["filled"] or 0))), None)
                if r is not None:
                    primary_results.append((str(r["financial_result"]), bool(r["financial_is_shadow"])))
            pwins=sum(1 for result,_ in primary_results if result=="WIN")
            ptotal=len(primary_results)
            primary={"correct":pwins,"wins":pwins,"losses":ptotal-pwins,"total":ptotal,
                     "accuracy":pwins/ptotal if ptotal else None,"basis":"LEGACY_MAIN_REV_DIAGNOSTIC",
                     "real":sum(1 for _,sh in primary_results if not sh),
                     "shadow":sum(1 for _,sh in primary_results if sh)}

            combined_rows = self.db.execute(
                "SELECT candle_id,financial_pnl,financial_is_shadow,order_status,filled FROM trades "
                "WHERE candle_id>=? AND kind IN ('MAIN','REVERSAL','EF') "
                "AND financial_result IN ('WIN','LOSS') AND financial_pnl IS NOT NULL "
                "AND (filled=1 OR COALESCE(financial_is_shadow,0)=1) ORDER BY candle_id",
                (epoch,),).fetchall()
            combined_by_candle: Dict[int, Dict[str, Any]] = {}
            for r in combined_rows:
                shadow=bool(r["financial_is_shadow"] or 0)
                if not financial_order_is_final(r["order_status"], shadow, bool(r["filled"] or 0)):
                    continue
                cid=int(r["candle_id"])
                bucket=combined_by_candle.setdefault(cid,{"pnl":0.0,"real":0,"shadow":0})
                bucket["pnl"] += float(r["financial_pnl"] or 0.0)
                bucket["shadow" if shadow else "real"] += 1
            combined_outcomes: List[Tuple[str,str,float]]=[]
            for bucket in combined_by_candle.values():
                pnl=float(bucket["pnl"])
                if pnl > 0.0000001: result="WIN"
                elif pnl < -0.0000001: result="LOSS"
                else: continue
                mode=("MIXED" if bucket["real"] and bucket["shadow"] else
                      "SHADOW" if bucket["shadow"] else "REAL")
                combined_outcomes.append((result,mode,pnl))
            wins=sum(1 for result,_,_ in combined_outcomes if result=="WIN")
            total=len(combined_outcomes)
            directional_main=self.db.execute(
                "SELECT COUNT(*) total,COALESCE(SUM(correct),0) correct FROM predictions "
                "WHERE kind='MAIN' AND actual IS NOT NULL AND candle_id>=?",(epoch,)).fetchone()
            directional_ef=self.db.execute(
                "SELECT COUNT(*) total,COALESCE(SUM(correct),0) correct FROM ef_predictions "
                "WHERE actual IS NOT NULL AND candle_id>=?",(epoch,)).fetchone()
        return {
            "main":main_metric,"reversal":rev_metric,"ef":ef_metric,"main_reversal":primary,
            "combined":{"correct":wins,"wins":wins,"losses":total-wins,"total":total,
                        "accuracy":wins/total if total else None,
                        "basis":"NET_MAIN_REV_EF_PNL_SIGN_PER_CANDLE",
                        "real":sum(1 for _,mode,_ in combined_outcomes if mode=="REAL"),
                        "shadow":sum(1 for _,mode,_ in combined_outcomes if mode=="SHADOW"),
                        "mixed":sum(1 for _,mode,_ in combined_outcomes if mode=="MIXED"),
                        "net_pnl":round(sum(pnl for _,_,pnl in combined_outcomes),4)},
            "directional_diagnostic":{"main":self._metric(directional_main),
                                      "ef":self._metric(directional_ef),
                                      "basis":"CANDLE_DIRECTION_ONLY"},
        }

    @staticmethod
    def _metric(row: sqlite3.Row) -> Dict[str, Any]:
        total = int(row["total"] or 0)
        correct = int(row["correct"] or 0)
        return {
            "correct": correct,
            "total": total,
            "accuracy": (correct / total) if total else None,
        }

    def _combined_financial_by_candle_locked(
        self, candle_ids: Iterable[int]
    ) -> Dict[int, Dict[str, Any]]:
        """Net final MAIN + REVERSAL + EF PnL per candle. Caller holds lock."""
        ids=sorted({int(cid) for cid in candle_ids})
        if not ids: return {}
        marks=",".join("?" for _ in ids)
        rows=self.db.execute(
            f"SELECT candle_id,financial_pnl,financial_is_shadow,order_status,filled "
            f"FROM trades WHERE candle_id IN ({marks}) "
            f"AND kind IN ('MAIN','REVERSAL','EF') "
            f"AND financial_result IN ('WIN','LOSS') AND financial_pnl IS NOT NULL "
            f"AND (filled=1 OR COALESCE(financial_is_shadow,0)=1)", ids).fetchall()
        buckets: Dict[int,Dict[str,Any]]={}
        for row in rows:
            shadow=bool(row["financial_is_shadow"] or 0)
            if not financial_order_is_final(row["order_status"],shadow,bool(row["filled"] or 0)):
                continue
            cid=int(row["candle_id"]); bucket=buckets.setdefault(cid,{"pnl":0.0,"real":0,"shadow":0})
            bucket["pnl"] += float(row["financial_pnl"] or 0.0)
            bucket["shadow" if shadow else "real"] += 1
        out={}
        for cid,bucket in buckets.items():
            pnl=float(bucket["pnl"])
            result="WIN" if pnl>0.0000001 else "LOSS" if pnl<-0.0000001 else "FLAT"
            mode="MIXED" if bucket["real"] and bucket["shadow"] else "SHADOW" if bucket["shadow"] else "REAL"
            out[cid]={"pnl":round(pnl,4),"result":result,
                      "correct":True if result=="WIN" else False if result=="LOSS" else None,
                      "mode":mode}
        return out

    def recent_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        epoch = self.metrics_epoch()
        with self.lock:
            rows = self.db.execute(
                """
                SELECT c.candle_id, c.open, c.close, c.actual,
                       m.direction AS main_direction, m.correct AS main_correct,
                       m.ts_ms AS main_ts_ms, m.probability_up AS main_probability_up,
                       r.direction AS reversal_direction, r.correct AS reversal_correct,
                       r.ts_ms AS reversal_ts_ms, r.probability_up AS reversal_probability_up,
                       e.direction AS ef_direction, e.correct AS ef_correct,
                       e.ts_ms AS ef_ts_ms, e.probability_up AS ef_probability_up
                FROM candles c
                LEFT JOIN predictions m
                  ON m.candle_id=c.candle_id AND m.kind='MAIN'
                LEFT JOIN predictions r
                  ON r.candle_id=c.candle_id AND r.kind='REVERSAL'
                LEFT JOIN ef_predictions e ON e.candle_id=c.candle_id
                WHERE c.candle_id >= ?
                  AND (m.candle_id IS NOT NULL OR e.candle_id IS NOT NULL)
                ORDER BY c.candle_id DESC LIMIT ?
                """,
                (epoch, int(limit)),
            ).fetchall()
            combined_financial = self._combined_financial_by_candle_locked(
                int(row["candle_id"]) for row in rows
            )
        out: List[Dict[str, Any]] = []
        for row in rows:
            net = row["reversal_direction"] or row["main_direction"]
            combined = combined_financial.get(int(row["candle_id"]), {})
            out.append(
                {
                    "candle_id": int(row["candle_id"]),
                    "time": london_stamp(int(row["candle_id"])),
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                    "actual": row["actual"],
                    "main_direction": row["main_direction"],
                    "main_correct": (
                        bool(row["main_correct"])
                        if row["main_correct"] is not None else None
                    ),
                    "main_ts_ms": (
                        int(row["main_ts_ms"])
                        if row["main_ts_ms"] is not None else None
                    ),
                    "main_probability_up": (
                        float(row["main_probability_up"])
                        if row["main_probability_up"] is not None else None
                    ),
                    "reversal_direction": row["reversal_direction"],
                    "reversal_correct": (
                        bool(row["reversal_correct"])
                        if row["reversal_correct"] is not None
                        else None
                    ),
                    "reversal_ts_ms": (
                        int(row["reversal_ts_ms"])
                        if row["reversal_ts_ms"] is not None
                        else None
                    ),
                    "reversal_probability_up": (
                        float(row["reversal_probability_up"])
                        if row["reversal_probability_up"] is not None
                        else None
                    ),
                    "ef_direction": row["ef_direction"],
                    "ef_correct": (
                        bool(row["ef_correct"])
                        if row["ef_correct"] is not None else None
                    ),
                    "ef_ts_ms": (
                        int(row["ef_ts_ms"])
                        if row["ef_ts_ms"] is not None else None
                    ),
                    "ef_probability_up": (
                        float(row["ef_probability_up"])
                        if row["ef_probability_up"] is not None else None
                    ),
                    # Directional MAIN→REV remains diagnostic only. The
                    # public combined result is net MAIN + REV + EF PnL truth.
                    "net_direction": net,
                    "directional_combined_correct": (
                        net == row["actual"] if net is not None else None
                    ),
                    "combined_financial_pnl": combined.get("pnl"),
                    "combined_financial_result": combined.get("result"),
                    "combined_financial_mode": combined.get("mode"),
                    "combined_correct": combined.get("correct"),
                }
            )
        return out

    def chart_candles(self, limit: int = CHART_CANDLES) -> List[Dict[str, Any]]:
        """Return settled candles saved with predictions for reliable chart joins."""
        with self.lock:
            rows = self.db.execute(
                """
                SELECT candle_id, open, high, low, close, volume, closed_ts_ms
                FROM candles ORDER BY candle_id DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [
            {
                "time": int(row["candle_id"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "closed": True,
                "close_time_ms": int(row["closed_ts_ms"]),
            }
            for row in reversed(rows)
        ]

    def markers(self, limit: int = 720) -> List[Dict[str, Any]]:
        """Chart markers use financial WIN/LOSS; candle correctness is diagnostic."""
        epoch = self.metrics_epoch()
        with self.lock:
            rows = self.db.execute(
                """
                WITH all_predictions AS (
                    SELECT candle_id,kind,direction,ts_ms,price,probability_up,
                           reason,actual,correct FROM predictions WHERE candle_id >= ?
                    UNION ALL
                    SELECT candle_id,kind,direction,ts_ms,price,probability_up,
                           reason,actual,correct FROM ef_predictions WHERE candle_id >= ?
                )
                SELECT p.*,t.financial_result,t.financial_pnl,
                       t.financial_is_shadow,t.forbidden,t.failure_reason,
                       t.filled,t.order_status
                FROM all_predictions p
                LEFT JOIN trades t ON t.candle_id=p.candle_id AND t.kind=p.kind
                ORDER BY p.ts_ms DESC LIMIT ?
                """,
                (epoch, epoch, int(limit)),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in reversed(rows):
            result = str(row["financial_result"] or "")
            forbidden = bool(row["forbidden"] or 0)
            reason = str(row["failure_reason"] or "")
            is_shadow = bool(row["financial_is_shadow"] or 0)
            # R5: live EF is a chart trigger only after confirmed fill.
            # Shadow/Master-OFF EF remains visible for forward research.
            if (
                str(row["kind"]).upper() == "EF"
                and not is_shadow
                and not forbidden
                and not bool(row["filled"] or 0)
            ):
                continue
            out.append({
                "candle_id": int(row["candle_id"]),
                "kind": row["kind"],
                "direction": row["direction"],
                "ts_ms": int(row["ts_ms"]),
                "price": float(row["price"]),
                "probability_up": float(row["probability_up"]),
                "reason": row["reason"],
                "actual": row["actual"],
                # Existing chart renderer reads `correct`; make that PnL truth.
                "correct": (True if result == "WIN" else False if result == "LOSS" else None),
                "financial_result": result or None,
                "financial_pnl": row["financial_pnl"],
                "financial_is_shadow": is_shadow,
                "directional_correct": (
                    bool(row["correct"]) if row["correct"] is not None else None
                ),
                "forbidden": forbidden,
                "signals_off": forbidden and "manually OFF" in reason,
            })
        return out

    # ------------------------------------------------------------------
    # v4.6: gated track (v5/v7 entry rule, scored on its own)
    # ------------------------------------------------------------------
    def add_gated(self, row: Dict[str, Any]) -> bool:
        with self.lock:
            cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO gated_predictions
                (candle_id, direction, ts_ms, phase_second, price, entry_odds,
                 reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["candle_id"]),
                    str(row["direction"]),
                    int(row["ts_ms"]),
                    float(row["phase_second"]),
                    float(row["price"]),
                    float(row["entry_odds"]),
                    str(row["reason"]),
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def get_gated(self, candle_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM gated_predictions WHERE candle_id=?", (candle_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "candle_id": int(row["candle_id"]),
            "direction": row["direction"],
            "ts_ms": int(row["ts_ms"]),
            "time": london_stamp(int(row["ts_ms"])),
            "phase_second": float(row["phase_second"]),
            "price": float(row["price"]),
            "entry_odds": float(row["entry_odds"]),
            "reason": row["reason"],
            "actual": row["actual"],
            "correct": (bool(row["correct"]) if row["correct"] is not None else None),
        }

    def gated_metrics(self) -> Dict[str, Any]:
        """Accuracy is not enough here: the entry odds are the hurdle rate."""
        epoch = self.metrics_epoch()
        with self.lock:
            rows = self.db.execute(
                "SELECT entry_odds, correct FROM gated_predictions "
                "WHERE actual IS NOT NULL AND candle_id >= ?", (epoch,)
            ).fetchall()
            fired = self.db.execute(
                "SELECT COUNT(*) AS n FROM gated_predictions WHERE candle_id >= ?",
                (epoch,),
            ).fetchone()["n"]
            candles = self.db.execute(
                "SELECT COUNT(*) AS n FROM candles WHERE candle_id >= ?",
                (epoch,),
            ).fetchone()["n"]
        total = len(rows)
        correct = sum(1 for row in rows if row["correct"])
        edge = 0.0
        odds_total = 0.0
        for row in rows:
            odds = max(float(row["entry_odds"]), 1e-6)
            odds_total += odds
            edge += (1.0 / odds - 1.0) if row["correct"] else -1.0
        return {
            "correct": correct,
            "total": total,
            "accuracy": (correct / total) if total else None,
            "average_entry_odds": (odds_total / total) if total else None,
            "break_even_accuracy": (odds_total / total) if total else None,
            "edge_per_dollar": (edge / total) if total else None,
            "fired": int(fired),
            "candles": int(candles),
            "fire_rate": (fired / candles) if candles else None,
        }

    # ------------------------------------------------------------------
    # v4.5: model weights
    # ------------------------------------------------------------------
    def save_weights(self, model: "Model") -> int:
        payload = json.dumps(model.weights, allow_nan=False)
        with self.lock:
            self.db.execute(
                """
                INSERT INTO model_weights(version, ts_ms, samples, temperature,
                                          last_candle_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(version) DO UPDATE SET
                    ts_ms=excluded.ts_ms, samples=excluded.samples,
                    temperature=excluded.temperature,
                    last_candle_id=excluded.last_candle_id,
                    payload=excluded.payload
                """,
                (
                    int(model.version),
                    now_ms(),
                    int(model.samples),
                    float(model.temperature),
                    int(model.last_candle_id),
                    payload,
                ),
            )
            self.db.commit()
        return int(model.version)

    def load_weights(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM model_weights ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        try:
            weights = json.loads(row["payload"])
        except (TypeError, ValueError):
            weights = {}
        return {
            "version": int(row["version"]),
            "samples": int(row["samples"]),
            "temperature": float(row["temperature"]),
            "last_candle_id": int(row["last_candle_id"] or 0),
            "weights": weights if isinstance(weights, dict) else {},
        }

    def settled_main_count(self) -> int:
        with self.lock:
            row = self.db.execute(
                "SELECT COUNT(*) AS n FROM predictions "
                "WHERE kind='MAIN' AND actual IS NOT NULL"
            ).fetchone()
        return int(row["n"] or 0)

    # ------------------------------------------------------------------
    # v4.5: economics
    # ------------------------------------------------------------------
    def latest_candle_id(self) -> int:
        with self.lock:
            row = self.db.execute(
                "SELECT MAX(candle_id) FROM ("
                "SELECT candle_id FROM predictions UNION ALL "
                "SELECT candle_id FROM ef_predictions)").fetchone()
        return int(row[0]) if row and row[0] else 0

    def metrics_epoch(self) -> int:
        """Candle id from which signal accuracy is counted.

        Each build restarts the signal statistics so a changed rule is not
        judged on candles it never saw.
        """
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM meta WHERE key='metrics_epoch'").fetchone()
        return int(row[0]) if row else 0

    def set_metrics_epoch(self, candle_id: int) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('metrics_epoch',?)",
                (str(int(candle_id)),))
            self.db.commit()

    def ensure_signal_epoch(self, started_ms: Optional[int] = None) -> int:
        """Start v7's visible results once without deleting core evidence.

        Predictions, feature snapshots and core model weights remain in place.
        The epoch only hides pre-upgrade signals, markers, orders and P&L from
        the fresh dashboard. Its dedicated key prevents a phone restart from
        resetting the figures again.
        """
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM meta WHERE key=?", (SIGNAL_EPOCH_KEY,)
            ).fetchone()
            if row is None:
                epoch = int(started_ms if started_ms is not None else now_ms())
                self.db.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?)",
                    (SIGNAL_EPOCH_KEY, str(epoch)),
                )
            else:
                epoch = int(row[0])
            self.db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('metrics_epoch',?)",
                (str(epoch),),
            )
            self.db.commit()
        return epoch

    def state_x_context(self, ts_ms: int, candle_id: int) -> Dict[str, Any]:
        """Prior-only causal history used by one current SX observation."""
        current = int(ts_ms)
        with self.lock:
            recent = self.db.execute(
                "SELECT seconds_into_candle,aligned_return_1s_bps,"
                "aligned_delta_30s FROM state_x_observations "
                "WHERE inputs_ready=1 AND ts_ms>=? AND ts_ms<=? "
                "ORDER BY ts_ms,candle_id,kind",
                (current - STATE_X_WINDOW_MS, current),
            ).fetchall()
            baseline = self.db.execute(
                "SELECT late_metric_15m,aligned_1s_metric_15m "
                "FROM state_x_observations WHERE inputs_ready=1 "
                "AND ts_ms>=? AND ts_ms<? AND late_metric_15m IS NOT NULL "
                "AND aligned_1s_metric_15m IS NOT NULL ORDER BY ts_ms",
                (current - STATE_X_BASELINE_MS, current),
            ).fetchall()
            candidate_rows = self.db.execute(
                "SELECT DISTINCT candle_id FROM state_x_observations "
                "WHERE original_candidate=1 AND ts_ms>=? AND ts_ms<=? "
                "AND candle_id<>?",
                (current - STATE_X_WINDOW_MS, current, int(candle_id)),
            ).fetchall()
            first = self.db.execute(
                "SELECT MIN(ts_ms) FROM state_x_observations "
                "WHERE inputs_ready=1"
            ).fetchone()
        return {
            "seconds_into_candle": [
                float(row["seconds_into_candle"])
                for row in recent if row["seconds_into_candle"] is not None
            ],
            "aligned_return_1s_bps": [
                float(row["aligned_return_1s_bps"])
                for row in recent if row["aligned_return_1s_bps"] is not None
            ],
            "aligned_delta_30s": [
                float(row["aligned_delta_30s"])
                for row in recent if row["aligned_delta_30s"] is not None
            ],
            "baseline_late_metric_15m": [
                float(row["late_metric_15m"]) for row in baseline
            ],
            "baseline_aligned_1s_metric_15m": [
                float(row["aligned_1s_metric_15m"]) for row in baseline
            ],
            "candidate_candle_ids": [int(row[0]) for row in candidate_rows],
            "first_observation_ms": (
                int(first[0]) if first is not None and first[0] is not None else None
            ),
        }

    def add_state_x_observation(self, row: Dict[str, Any]) -> bool:
        """Persist one genuine signal observation for causal rolling history."""
        with self.lock:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO state_x_observations("
                "candle_id,kind,direction,ts_ms,seconds_into_candle,"
                "aligned_return_1s_bps,aligned_delta_30s,late_metric_15m,"
                "aligned_1s_metric_15m,aligned_delta30_median_15m,"
                "late_p80_6h,aligned_1s_p80_6h,original_candidate,"
                "original_confirmed,rejection_balance,refined_trigger,"
                "trigger_reason,inputs_ready) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?)",
                (
                    int(row["candle_id"]), str(row["kind"]),
                    str(row["direction"]), int(row["ts_ms"]),
                    row.get("seconds_into_candle"),
                    row.get("aligned_return_1s_bps"),
                    row.get("aligned_delta_30s"),
                    row.get("late_metric_15m"),
                    row.get("aligned_1s_metric_15m"),
                    row.get("aligned_delta30_median_15m"),
                    row.get("late_p80_6h"), row.get("aligned_1s_p80_6h"),
                    1 if row.get("original_candidate") else 0,
                    1 if row.get("original_confirmed") else 0,
                    row.get("rejection_balance"),
                    1 if row.get("refined_trigger") else 0,
                    str(row.get("trigger_reason") or ""),
                    1 if row.get("inputs_ready") else 0,
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def record_trade(self, row: Dict[str, Any]) -> bool:
        """Create one immutable signal/order slot.

        ``INSERT OR IGNORE`` is intentional: a duplicate signal callback must
        never replace a live order or erase its venue identifiers.
        """
        try:
            attempt_log = json.dumps(row.get("attempt_log") or [], allow_nan=False)
        except (TypeError, ValueError):
            attempt_log = "[]"
        columns = (
            "candle_id", "kind", "direction", "ts_ms",
            "seconds_into_candle", "quoted_price", "fill_price", "slippage",
            "delay_ms", "attempts", "filled", "break_even", "spread",
            "book_size", "stake", "shares", "fee_rate", "market_id",
            "market_title", "book_age_ms", "failure_reason", "attempt_log",
            "forbidden", "execution_mode", "order_id", "order_hash",
            "order_status", "submitted_ms", "confirmed_ms", "filled_value",
            "retry_count", "state_x", "state_x_active",
            "state_x_trigger_time", "state_x_end_time",
            "sx_late_metric_15m", "sx_late_p80_6h",
            "sx_aligned_1s_metric_15m", "sx_aligned_1s_p80_6h",
            "sx_rejection_balance", "sx_aligned_delta30_median_15m",
            "sx_trigger_reason", "financial_result", "financial_pnl",
            "financial_source", "financial_is_shadow",
            "execution_eligibility", "execution_vwap", "ef_attempt_seq",
        )
        ef_attempt_seq = row.get("ef_attempt_seq")
        if str(row.get("kind") or "").upper() == "EF" and ef_attempt_seq is None:
            with self.lock:
                ef_attempt_seq = self._r5_next_ef_attempt_seq_locked(int(row["candle_id"]))
        values = (
            int(row["candle_id"]), row["kind"], row["direction"],
            int(row["ts_ms"]), float(row["seconds_into_candle"]),
            row.get("quoted_price"), row.get("fill_price"), row.get("slippage"),
            row.get("delay_ms"), row.get("attempts"),
            1 if row.get("filled") else 0, row.get("break_even"),
            row.get("spread"), row.get("book_size"), row.get("stake"),
            row.get("shares"), row.get("fee_rate"), row.get("market_id"),
            row.get("market_title"), row.get("book_age_ms"),
            row.get("failure_reason"), attempt_log,
            1 if row.get("forbidden") else 0,
            row.get("execution_mode", "LIVE"), row.get("order_id"),
            row.get("order_hash"), row.get("order_status", "QUEUED"),
            row.get("submitted_ms"), row.get("confirmed_ms"),
            row.get("filled_value"), int(row.get("retry_count") or 0),
            str(row.get("state_x") or ""),
            1 if row.get("state_x_active") else 0,
            row.get("state_x_trigger_time"), row.get("state_x_end_time"),
            row.get("sx_late_metric_15m"), row.get("sx_late_p80_6h"),
            row.get("sx_aligned_1s_metric_15m"),
            row.get("sx_aligned_1s_p80_6h"),
            row.get("sx_rejection_balance"),
            row.get("sx_aligned_delta30_median_15m"),
            str(row.get("sx_trigger_reason") or ""),
            row.get("financial_result"), row.get("financial_pnl"),
            row.get("financial_source"),
            1 if row.get("financial_is_shadow") else 0,
            row.get("execution_eligibility"), row.get("execution_vwap"),
            ef_attempt_seq,
        )
        with self.lock:
            cursor = self.db.execute(
                f"INSERT OR IGNORE INTO trades({','.join(columns)}) VALUES("
                + ",".join("?" for _ in columns) + ")",
                values,
            )
            self.db.commit()
            return cursor.rowcount == 1

    def update_trade_execution(
        self, candle_id: int, kind: str, **changes: Any
    ) -> None:
        """Update only execution fields; signal identity cannot be mutated."""
        allowed = {
            "quoted_price", "fill_price", "slippage", "delay_ms", "attempts",
            "filled", "break_even", "spread", "book_size", "stake", "shares",
            "fee_rate", "market_id", "market_title", "book_age_ms",
            "failure_reason", "attempt_log", "forbidden", "execution_mode",
            "order_id", "order_hash", "order_status", "submitted_ms",
            "confirmed_ms", "filled_value", "retry_count",
            "fee_collateral", "fee_shares",
            "first_submit_ms", "last_attempt_ms",
            "state_x", "state_x_active", "state_x_trigger_time",
            "state_x_end_time", "sx_late_metric_15m", "sx_late_p80_6h",
            "sx_aligned_1s_metric_15m", "sx_aligned_1s_p80_6h",
            "sx_rejection_balance", "sx_aligned_delta30_median_15m",
            "sx_trigger_reason", "financial_result", "financial_pnl",
            "financial_source", "financial_is_shadow",
            "execution_eligibility", "execution_vwap", "ef_attempt_seq",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsafe trade fields: {sorted(unknown)}")
        if not changes:
            return
        values: List[Any] = []
        assignments: List[str] = []
        for name, value in changes.items():
            if name == "attempt_log":
                value = json.dumps(value or [], separators=(",", ":"),
                                   allow_nan=False)
            if name in {"filled", "forbidden", "state_x_active", "financial_is_shadow"} and value is not None:
                value = 1 if value else 0
            assignments.append(f"{name}=?")
            values.append(value)
        values.extend((int(candle_id), str(kind)))
        with self.lock:
            self.db.execute(
                f"UPDATE trades SET {','.join(assignments)} "
                "WHERE candle_id=? AND kind=?", values)
            self.db.commit()

    def apply_order_fill(
        self,
        candle_id: int,
        kind: str,
        order_hash: str,
        settlement_id: str,
        executed_price: float,
        executed_shares: float,
        executed_value: float,
        fee_amount: float,
        fee_type: str,
        quoted_price: float,
        confirmed_ms: int,
    ) -> Optional[Dict[str, float]]:
        """Persist and aggregate one venue fill in a single transaction.

        ``(order_hash, settlement_id)`` is the idempotency key supplied by the
        wallet stream. Keeping it in sqlite prevents a reconnect or process
        restart from counting the same partial fill twice.
        """
        fee_type = str(fee_type or "").upper()
        fee_amount = max(0.0, float(fee_amount or 0.0))
        if fee_type not in {"COLLATERAL", "SHARES"}:
            fee_type = ""
            fee_amount = 0.0
        with self.lock:
            try:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO order_fills("
                    "order_hash,settlement_id,candle_id,kind,executed_price,"
                    "executed_shares,executed_value,fee_amount,fee_type,"
                    "confirmed_ms) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(order_hash), str(settlement_id), int(candle_id),
                        str(kind), float(executed_price),
                        float(executed_shares), float(executed_value),
                        fee_amount, fee_type or None, int(confirmed_ms),
                    ),
                )
                if cursor.rowcount != 1:
                    self.db.commit()
                    return None
                aggregate = self.db.execute(
                    "SELECT COALESCE(SUM(executed_shares),0) AS shares,"
                    "COALESCE(SUM(executed_value),0) AS value,"
                    "COALESCE(SUM(CASE WHEN fee_type='COLLATERAL' "
                    "THEN fee_amount ELSE 0 END),0) AS fee_collateral,"
                    "COALESCE(SUM(CASE WHEN fee_type='SHARES' "
                    "THEN fee_amount ELSE 0 END),0) AS fee_shares "
                    "FROM order_fills WHERE order_hash=?",
                    (str(order_hash),),
                ).fetchone()
                shares = float(aggregate["shares"] or 0.0)
                value = float(aggregate["value"] or 0.0)
                fee_collateral = float(aggregate["fee_collateral"] or 0.0)
                fee_shares = float(aggregate["fee_shares"] or 0.0)
                if shares <= 0.0 or value < 0.0:
                    raise ValueError("invalid aggregate Predict.fun fill")
                average = value / shares
                updated = self.db.execute(
                    "UPDATE trades SET filled=1,fill_price=?,shares=?,stake=?,"
                    "filled_value=?,fee_collateral=?,fee_shares=?,slippage=?,"
                    "confirmed_ms=?,failure_reason=NULL WHERE candle_id=? "
                    "AND kind=? AND order_hash=?",
                    (
                        round(average, 8), round(shares, 8),
                        round(value + fee_collateral, 8), round(value, 8),
                        round(fee_collateral, 8), round(fee_shares, 8),
                        round(average - float(quoted_price or 0.0), 8),
                        int(confirmed_ms), int(candle_id), str(kind),
                        str(order_hash),
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("fill has no matching local order row")
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return {
            "shares": shares,
            "value": value,
            "stake": value + fee_collateral,
            "fill_price": average,
            "fee_collateral": fee_collateral,
            "fee_shares": fee_shares,
        }

    def trade_row(self, candle_id: int, kind: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM trades WHERE candle_id=? AND kind=?",
                (int(candle_id), str(kind)),
            ).fetchone()
        return dict(row) if row is not None else None

    def recoverable_live_orders(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Orders whose signed hash must survive a crash or phone restart.

        Wallet-event subscriptions have no replay snapshot. Restoring these
        rows lets the executor reconcile by the immutable signed hash instead
        of assuming an interrupted request failed and risking a duplicate.
        """
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM trades WHERE order_hash IS NOT NULL "
                "AND TRIM(order_hash)<>'' AND correct IS NULL "
                "AND COALESCE(forbidden,0)=0 AND (filled=1 OR "
                "UPPER(COALESCE(order_status,'')) IN "
                "('SUBMITTING','UNKNOWN','ACCEPTED','MATCHING','OPEN',"
                "'PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING')) "
                "ORDER BY submitted_ms,ts_ms LIMIT ?",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        return [dict(row) for row in rows]

    def recalculate_settled_trade(self, candle_id: int, kind: str) -> None:
        """Reprice P&L if another confirmed partial fill arrives after close."""
        with self.lock:
            row=self.db.execute(
                "SELECT rowid,direction,actual,fill_price,stake,shares,fee_rate,"
                "fee_collateral,fee_shares,order_status FROM trades WHERE candle_id=? "
                "AND kind=? AND actual IS NOT NULL AND filled=1",
                (int(candle_id),str(kind))).fetchone()
            if row is None or row["fill_price"] is None:
                return
            if not financial_order_is_final(row["order_status"], False, True):
                return
            correct=row["direction"]==row["actual"]
            stake=float(row["stake"] or 0.0); shares=float(row["shares"] or 0.0)
            has_exact_fee=row["fee_collateral"] is not None or row["fee_shares"] is not None
            if has_exact_fee:
                payout_shares=max(0.0,shares-float(row["fee_shares"] or 0.0))
            else:
                fee=clamp(safe_float(row["fee_rate"],0.0),0.0,0.25)
                payout_shares=shares*(1.0-fee)
            pnl=payout_shares-stake if correct else -stake
            financial_result="WIN" if pnl>0.0000001 else "LOSS" if pnl<-0.0000001 else "FLAT"
            self.db.execute(
                "UPDATE trades SET correct=?,pnl=?,financial_pnl=?,financial_result=?,"
                "financial_source='PREDICT_FUN_CONFIRMED_FILL_SETTLEMENT',financial_is_shadow=0 WHERE rowid=?",
                (1 if correct else 0,round(pnl,4),round(pnl,4),financial_result,int(row["rowid"])))
            if correct:
                self._register_payout_claim_locked(candle_id,str(kind),payout_shares,now_ms())
            else:
                self._drop_payout_claim_locked(candle_id,str(kind))
            self.db.commit()

    def settle_trades_and_report(
        self, candle_id: int, actual: str
    ) -> List[Tuple[str, bool]]:
        """Emit idempotent shared-streak events from real settled PnL sign only."""
        with self.lock:
            self.settle_trades(candle_id, actual)
            rows = self.db.execute(
                "SELECT kind,financial_result FROM trades WHERE candle_id=? "
                "AND filled=1 AND COALESCE(forbidden,0)=0 "
                "AND COALESCE(financial_is_shadow,0)=0 "
                "AND financial_result IN ('WIN','LOSS')",
                (int(candle_id),),
            ).fetchall()
            by_kind = {str(r["kind"]): str(r["financial_result"]) == "WIN" for r in rows}
            candidates: List[Tuple[str, bool]] = []
            unresolved_primary = self.db.execute(
                "SELECT 1 FROM trades WHERE candle_id=? AND kind IN ('MAIN','REVERSAL') "
                "AND financial_result IS NULL AND COALESCE(forbidden,0)=0 "
                "AND COALESCE(financial_is_shadow,0)=0 "
                "AND UPPER(COALESCE(order_status,'')) IN "
                "('WAIT_VWAP','QUEUED','SIGNING','SUBMITTING','UNKNOWN','ACCEPTED','MATCHING','OPEN','PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING') LIMIT 1",
                (int(candle_id),),
            ).fetchone()
            if unresolved_primary is None:
                if "REVERSAL" in by_kind:
                    candidates.append(("MAIN_REV", by_kind["REVERSAL"]))
                elif "MAIN" in by_kind:
                    candidates.append(("MAIN_REV", by_kind["MAIN"]))
            if "EF" in by_kind:
                candidates.append(("EF", by_kind["EF"]))
            emitted: List[Tuple[str, bool]] = []
            for source, won in candidates:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO streak_events(candle_id,source,won,created_ms) VALUES(?,?,?,?)",
                    (int(candle_id), source, 1 if won else 0, now_ms()),
                )
                if cursor.rowcount == 1:
                    emitted.append((source, won))
            self.db.commit()
        return emitted

    def settle_trades(self, candle_id: int, actual: str) -> None:
        """Settle real fills and labelled Master-OFF shadows by PnL sign.

        Failed/unfilled live orders have no financial result. Directional candle
        correctness remains diagnostic only. Confirmed local fill economics plus
        binary settlement are used per order; venue aggregate position PnL is not
        ambiguously attributed across multiple bot/manual positions.
        """
        with self.lock:
            rows=self.db.execute("SELECT rowid,* FROM trades WHERE candle_id=? AND correct IS NULL",
                                 (int(candle_id),)).fetchall()
            venue_fresh=self._positions_fresh_locked(now_ms())
            for r in rows:
                mode=str(r["execution_mode"] or "LIVE").upper(); is_shadow=mode=="SHADOW"
                filled=bool(r["filled"] or 0)
                if not financial_order_is_final(r["order_status"],is_shadow,filled):
                    continue
                directional_correct=1 if r["direction"]==actual else 0
                financial_pnl=None; source=None; payout_shares=0.0
                if filled and r["fill_price"] is not None:
                    stake=float(r["stake"] if r["stake"] is not None else r["fill_price"])
                    shares=float(r["shares"] if r["shares"] is not None else 1.0)
                    has_exact_fee=r["fee_collateral"] is not None or r["fee_shares"] is not None
                    if has_exact_fee:
                        payout_shares=max(0.0,shares-float(r["fee_shares"] or 0.0))
                    else:
                        fee_rate=clamp(safe_float(r["fee_rate"],0.0),0.0,0.25)
                        payout_shares=shares*(1.0-fee_rate)
                    financial_pnl=payout_shares-stake if directional_correct else -stake
                    source="PREDICT_FUN_CONFIRMED_FILL_SETTLEMENT"
                elif is_shadow and r["quoted_price"] is not None and r["stake"] is not None:
                    quote=float(r["quoted_price"]); stake=float(r["stake"] or 0.0)
                    if quote>0.0 and stake>0.0:
                        shares=float(r["shares"] or (stake/quote))
                        fee_rate=clamp(safe_float(r["fee_rate"],PREDICT_FEE_RATE),0.0,0.25)
                        payout_shares=shares*(1.0-fee_rate)
                        financial_pnl=payout_shares-stake if directional_correct else -stake
                        source="SHADOW_EXECUTABLE_QUOTE"
                result=None
                if financial_pnl is not None:
                    result="WIN" if financial_pnl>0.0000001 else "LOSS" if financial_pnl<-0.0000001 else "FLAT"
                pnl_write=round(financial_pnl,4) if financial_pnl is not None else 0.0
                self.db.execute(
                    "UPDATE trades SET actual=?,correct=?,pnl=?,financial_pnl=?,financial_result=?,"
                    "financial_source=?,financial_is_shadow=? WHERE rowid=?",
                    (actual,directional_correct,pnl_write,
                     round(financial_pnl,4) if financial_pnl is not None else None,
                     result,source,1 if is_shadow else 0,int(r["rowid"])))
                if (not is_shadow and financial_pnl is not None and financial_pnl>0.0 and filled):
                    if payout_shares<=0.0:
                        shares=float(r["shares"] or 0.0)
                        payout_shares=max(0.0,shares-float(r["fee_shares"] or 0.0))
                    self._register_payout_claim_locked(candle_id,str(r["kind"]),payout_shares,now_ms())
                elif not is_shadow:
                    self._drop_payout_claim_locked(candle_id,str(r["kind"]))
            self.db.commit()

    def _seed_controls(self) -> None:
        """Seed shared SYSTEM state and v7.2 per-signal execution toggles.

        SYSTEM remains the only owner of stake/streak and is forced OFF at
        every process launch. Individual toggles persist. The one-time v7.2
        migration deliberately seeds MAIN/REVERSAL/EF ON so stale pre-v7 rows
        cannot unexpectedly disable a stream when upgrading from v7.1.
        """
        with self.lock:
            old_main = self.db.execute(
                "SELECT stake_config,win_streak,loss_streak FROM trade_controls "
                "WHERE kind='MAIN'"
            ).fetchone()
            seed_stake = (
                old_main[0] if old_main is not None
                else json.dumps(dict(DEFAULT_STAKE_CONFIG))
            )
            seed_wins = int(old_main[1] or 0) if old_main is not None else 0
            seed_losses = int(old_main[2] or 0) if old_main is not None else 0
            self.db.execute(
                "INSERT OR IGNORE INTO trade_controls "
                "(kind,manual_enabled,stake_config,win_streak,loss_streak,"
                "pending,updated_ms) VALUES(?,0,?,?,?,NULL,?)",
                (SYSTEM_CONTROL_KIND, seed_stake, seed_wins, seed_losses,
                 now_ms()),
            )
            # Global arming never survives a restart.
            self.db.execute(
                "UPDATE trade_controls SET manual_enabled=0,pending=NULL,"
                "updated_ms=? WHERE kind=?",
                (now_ms(), SYSTEM_CONTROL_KIND),
            )

            # State X is independent from the fail-closed master switch. It is
            # OFF only on first introduction; thereafter both the operator's
            # choice and an active timer survive every process restart.
            self.db.execute(
                "INSERT OR IGNORE INTO trade_controls "
                "(kind,manual_enabled,stake_config,win_streak,loss_streak,"
                "pending,updated_ms) VALUES(?,0,?,0,0,?,?)",
                (
                    STATE_X_CONTROL_KIND,
                    seed_stake,
                    json.dumps(StateXProtection._blank_state()),
                    now_ms(),
                ),
            )

            # v7.1 had no individual switches. Seed each stream ON exactly
            # once, then preserve the user's per-stream choice on later starts.
            toggle_seeded = self.db.execute(
                "SELECT 1 FROM meta WHERE key='v72_signal_toggles_seeded'"
            ).fetchone()
            shared = self.db.execute(
                "SELECT stake_config,win_streak,loss_streak FROM trade_controls "
                "WHERE kind=?", (SYSTEM_CONTROL_KIND,)
            ).fetchone()
            shared_stake = (
                shared[0] if shared is not None
                else json.dumps(dict(DEFAULT_STAKE_CONFIG))
            )
            shared_wins = int(shared[1] or 0) if shared is not None else 0
            shared_losses = int(shared[2] or 0) if shared is not None else 0
            for kind in TRADE_KINDS:
                self.db.execute(
                    "INSERT OR IGNORE INTO trade_controls "
                    "(kind,manual_enabled,stake_config,win_streak,loss_streak,"
                    "pending,updated_ms) VALUES(?,1,?,?,?,NULL,?)",
                    (kind, shared_stake, shared_wins, shared_losses, now_ms()),
                )
                if toggle_seeded is None:
                    self.db.execute(
                        "UPDATE trade_controls SET manual_enabled=1,pending=NULL,"
                        "updated_ms=? WHERE kind=?", (now_ms(), kind)
                    )
            if toggle_seeded is None:
                self.db.execute(
                    "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                    ("v72_signal_toggles_seeded", str(now_ms())),
                )

            seeded = self.db.execute(
                "SELECT COUNT(*) FROM meta WHERE key='ban_rules_seeded'"
            ).fetchone()[0]
            if not seeded:
                for rule in DEFAULT_BAN_RULES:
                    self.db.execute(
                        "INSERT OR IGNORE INTO ban_rules (id, payload, updated_ms) "
                        "VALUES (?, ?, ?)",
                        (rule["id"], json.dumps(rule), now_ms()),
                    )
                self.db.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES "
                    "('ban_rules_seeded', '1')"
                )
            self.db.commit()

    def ban_rules(self) -> List[Dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM ban_rules ORDER BY id").fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(json.loads(row[0]))
            except (TypeError, ValueError):
                continue
        return out

    def save_ban_rule(self, rule: Dict[str, Any]) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO ban_rules (id, payload, updated_ms) "
                "VALUES (?, ?, ?)",
                (str(rule["id"]), json.dumps(rule), now_ms()))
            self.db.commit()

    def delete_ban_rule(self, rule_id: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM ban_rules WHERE id=?", (str(rule_id),))
            self.db.commit()

    def control_row(self, kind: str) -> Dict[str, Any]:
        with self.lock:
            row = self.db.execute(
                "SELECT manual_enabled, stake_config, win_streak, loss_streak, "
                "pending FROM trade_controls WHERE kind=?", (kind,)).fetchone()
        if row is None:
            return {
                "kind": kind, "manual_enabled": False,
                "stake": dict(DEFAULT_STAKE_CONFIG),
                "win_streak": 0, "loss_streak": 0, "pending": None,
            }
        try:
            stake = json.loads(row[1])
        except (TypeError, ValueError):
            stake = dict(DEFAULT_STAKE_CONFIG)
        merged = dict(DEFAULT_STAKE_CONFIG)
        merged.update(stake or {})
        try:
            pending = json.loads(row[4]) if row[4] else None
        except (TypeError, ValueError):
            pending = None
        return {
            "kind": kind,
            "manual_enabled": bool(row[0]),
            "stake": merged,
            "win_streak": int(row[2] or 0),
            "loss_streak": int(row[3] or 0),
            "pending": pending,
        }

    def write_control(
        self,
        kind: str,
        manual_enabled: Optional[bool] = None,
        stake: Optional[Dict[str, Any]] = None,
        win_streak: Optional[int] = None,
        loss_streak: Optional[int] = None,
        pending: Optional[Dict[str, Any]] = "keep",
    ) -> None:
        with self.lock:
            # The read and replacement are one critical section. This prevents
            # a simultaneous result update and UI toggle from restoring stale
            # streak, stake, pending, or master values.
            current = self.control_row(kind)
            new_manual = (current["manual_enabled"] if manual_enabled is None
                          else bool(manual_enabled))
            new_stake = current["stake"] if stake is None else stake
            new_win = (current["win_streak"] if win_streak is None
                       else int(win_streak))
            new_loss = (current["loss_streak"] if loss_streak is None
                        else int(loss_streak))
            new_pending = current["pending"] if pending == "keep" else pending
            self.db.execute(
                "INSERT OR REPLACE INTO trade_controls "
                "(kind, manual_enabled, stake_config, win_streak, loss_streak, "
                " pending, updated_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, 1 if new_manual else 0, json.dumps(new_stake),
                 new_win, new_loss,
                 json.dumps(new_pending) if new_pending else None, now_ms()))
            self.db.commit()

    def open_position_kinds(self, ts_ms: Optional[int] = None) -> List[str]:
        """Kinds with capital committed or an externally ambiguous order.

        WAIT_VWAP/QUEUED/SIGNING rows are local-only and expire with the candle.
        R6 treats WAIT_VWAP as a configuration-open EF intent so its frozen
        shared stake cannot be changed underneath the continuously hot order.
        A filled row or a signed-hash submission stays open until it is settled or the
        venue proves a terminal state, including after a process restart.
        """
        marks = ",".join("?" for _ in TRADE_KINDS)
        current = now_ms() if ts_ms is None else int(ts_ms)
        params = tuple(TRADE_KINDS) + (CANDLE_MS, current)
        with self.lock:
            rows = self.db.execute(
                f"SELECT DISTINCT kind FROM trades WHERE kind IN ({marks}) "
                f"AND correct IS NULL AND COALESCE(forbidden,0)=0 AND "
                f"(filled=1 OR "
                f"(candle_id + ? > ? AND UPPER(COALESCE(order_status,'')) IN "
                f"('WAIT_VWAP','HOT_POST','HOT_RETRY','HOT_RETRY_POST','HOT_RETRY_WAIT',"
                f"'QUEUED','SIGNING','SUBMITTING','UNKNOWN','ACCEPTED',"
                f"'MATCHING','OPEN','PENDING','PARTIALLYFILLED',"
                f"'FILLED_DETAILS_PENDING')) OR "
                f"(order_hash IS NOT NULL AND TRIM(order_hash)<>'' AND "
                f"UPPER(COALESCE(order_status,'')) IN "
                f"('SUBMITTING','UNKNOWN','ACCEPTED','MATCHING','OPEN',"
                f"'PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING'))) ",
                params,
            ).fetchall()
        return [r[0] for r in rows]

    def unsettled_trade_candle_ids(self) -> List[int]:
        """Candle ids containing trade rows that still need a final result."""
        with self.lock:
            rows = self.db.execute(
                "SELECT DISTINCT candle_id FROM trades WHERE correct IS NULL "
                "ORDER BY candle_id"
            ).fetchall()
        return [int(r[0]) for r in rows]

    # ---- v7.7: unredeemed winnings ------------------------------------
    def _register_payout_claim_locked(
        self, candle_id: int, kind: str, payout_usd: float, settled_ms: int
    ) -> None:
        """Record a settled win whose USDT has not landed in the wallet yet.

        ``credited_usd`` is preserved on conflict: a late partial fill can
        reprice the payout without forgetting money already observed arriving.
        """
        if str(kind) not in CAPITAL_KINDS:
            return
        payout = max(0.0, float(payout_usd or 0.0))
        if payout <= PREDICT_CLAIM_EPSILON_USD:
            self._drop_payout_claim_locked(candle_id, kind)
            return
        self.db.execute(
            "INSERT INTO payout_claims(candle_id,kind,payout_usd,settled_ms) "
            "VALUES(?,?,?,?) ON CONFLICT(candle_id,kind) DO UPDATE SET "
            "payout_usd=excluded.payout_usd",
            (int(candle_id), str(kind), round(payout, 8), int(settled_ms)),
        )

    def _drop_payout_claim_locked(self, candle_id: int, kind: str) -> None:
        self.db.execute(
            "DELETE FROM payout_claims WHERE candle_id=? AND kind=?",
            (int(candle_id), str(kind)),
        )

    def _credit_pending_payouts_locked(self, wallet: float, stamp: int) -> float:
        """Retire outstanding claims against an observed wallet increase.

        Only a real rise in smart-account USDT can credit a claim, oldest
        first. A rise from any other source (a deposit, a refund) simply
        retires a claim early, which under-states pending money and is the
        safe direction. A claim that is never observed arriving expires after
        PREDICT_CLAIM_TTL_SEC so it can never inflate capital indefinitely.
        """
        previous = getattr(self, "_last_wallet_seen_usd", None)
        self._last_wallet_seen_usd = float(wallet)
        if previous is None:
            return 0.0
        increment = float(wallet) - float(previous)
        if increment <= PREDICT_CLAIM_EPSILON_USD:
            return 0.0
        remaining = increment
        rows = self.db.execute(
            "SELECT candle_id,kind,payout_usd,credited_usd FROM payout_claims "
            "WHERE payout_usd - credited_usd > ? ORDER BY settled_ms,candle_id",
            (PREDICT_CLAIM_EPSILON_USD,),
        ).fetchall()
        credited_total = 0.0
        for row in rows:
            if remaining <= PREDICT_CLAIM_EPSILON_USD:
                break
            outstanding = float(row["payout_usd"]) - float(row["credited_usd"])
            take = min(outstanding, remaining)
            self.db.execute(
                "UPDATE payout_claims SET credited_usd=credited_usd+?,"
                "credited_ms=? WHERE candle_id=? AND kind=?",
                (
                    round(take, 8), int(stamp),
                    int(row["candle_id"]), str(row["kind"]),
                ),
            )
            remaining -= take
            credited_total += take
        if credited_total > 0.0:
            self.db.commit()
        return credited_total

    def _pending_payout_locked(self, current_ms: int) -> float:
        """Settled winnings still waiting to become spendable USDT."""
        cutoff = int(current_ms - PREDICT_CLAIM_TTL_SEC * 1000.0)
        row = self.db.execute(
            "SELECT COALESCE(SUM(payout_usd - credited_usd),0) FROM "
            "payout_claims WHERE settled_ms >= ? AND "
            "payout_usd - credited_usd > ?",
            (cutoff, PREDICT_CLAIM_EPSILON_USD),
        ).fetchone()[0]
        return max(0.0, float(row or 0.0))

    def pending_payout_usd(self) -> float:
        with self.lock:
            return self._pending_payout_locked(now_ms())

    def open_payout_claims(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Outstanding unredeemed winnings, newest first, for the dashboard."""
        cutoff = int(now_ms() - PREDICT_CLAIM_TTL_SEC * 1000.0)
        with self.lock:
            rows = self.db.execute(
                "SELECT candle_id,kind,payout_usd,credited_usd,settled_ms "
                "FROM payout_claims WHERE settled_ms >= ? AND "
                "payout_usd - credited_usd > ? ORDER BY settled_ms DESC "
                "LIMIT ?",
                (cutoff, PREDICT_CLAIM_EPSILON_USD, max(1, int(limit))),
            ).fetchall()
        return [
            {
                "candle_id": int(r["candle_id"]),
                "kind": str(r["kind"]),
                "outstanding": round(
                    float(r["payout_usd"]) - float(r["credited_usd"]), 4
                ),
                "settled_ms": int(r["settled_ms"]),
            }
            for r in rows
        ]

    # ---- v7.7: venue truth vs local ledger ----------------------------
    # With no deposit or withdrawal the following is an identity:
    #     equity = wallet USDT + unredeemed winnings + cost of open positions
    #     equity(now) - equity(anchor) == realised P&L(now) - realised(anchor)
    # A filled order moves USDT into open-position cost; settlement moves that
    # cost into an unredeemed claim and books P&L; the claim then becomes USDT.
    # Anything left over is money the local ledger cannot explain: a deposit, a
    # withdrawal, gas, or an accounting bug. Reporting it makes the difference
    # between "local P&L" and "what the venue actually did" visible instead of
    # assumed.
    WALLET_TRUTH_ANCHOR_KEY = "v77_wallet_truth_anchor"

    def _open_position_cost_locked(self) -> float:
        marks = ",".join("?" for _ in CAPITAL_KINDS)
        value = self.db.execute(
            f"SELECT COALESCE(SUM(stake),0) FROM trades WHERE "
            f"kind IN ({marks}) AND COALESCE(filled,0)=1 AND correct IS NULL "
            f"AND COALESCE(forbidden,0)=0",
            CAPITAL_KINDS,
        ).fetchone()[0]
        return max(0.0, float(value or 0.0))

    def _realised_locked(self) -> float:
        marks = ",".join("?" for _ in CAPITAL_KINDS)
        value = self.db.execute(
            f"SELECT COALESCE(SUM(financial_pnl),0) FROM trades WHERE "
            f"kind IN ({marks}) AND financial_result IN ('WIN','LOSS') "
            f"AND filled=1 AND COALESCE(financial_is_shadow,0)=0 "
            f"AND COALESCE(forbidden,0)=0 AND COALESCE(state_x,'')<>'SX' AND UPPER(COALESCE(order_status,'')) NOT IN ('PARTIALLYFILLED','FILLED_DETAILS_PENDING')",
            CAPITAL_KINDS,
        ).fetchone()[0]
        return float(value or 0.0)

    def _anchor_wallet_truth_locked(self, wallet: float, stamp: int) -> None:
        """Fix the reconciliation origin at the first proved wallet read."""
        row = self.db.execute(
            "SELECT value FROM meta WHERE key=?",
            (self.WALLET_TRUTH_ANCHOR_KEY,),
        ).fetchone()
        if row is not None:
            return
        anchor = {
            "ms": int(stamp),
            "equity": round(
                float(wallet)
                + self._pending_payout_locked(int(stamp))
                + self._open_position_cost_locked(),
                8,
            ),
            "realised": round(self._realised_locked(), 8),
        }
        self.db.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            (self.WALLET_TRUTH_ANCHOR_KEY, json.dumps(anchor)),
        )
        self.db.commit()

    def _wallet_truth_locked(
        self, wallet: float, pending: float, current_ms: int
    ) -> Dict[str, Any]:
        row = self.db.execute(
            "SELECT value FROM meta WHERE key=?",
            (self.WALLET_TRUTH_ANCHOR_KEY,),
        ).fetchone()
        if row is None:
            return {"anchored": False, "venue_delta": None,
                    "ledger_delta": None, "unexplained": None}
        try:
            anchor = json.loads(row[0])
        except (TypeError, ValueError):
            return {"anchored": False, "venue_delta": None,
                    "ledger_delta": None, "unexplained": None}
        equity = (
            float(wallet) + float(pending) + self._open_position_cost_locked()
        )
        venue_delta = equity - float(anchor.get("equity", equity))
        ledger_delta = self._realised_locked() - float(anchor.get("realised", 0.0))
        return {
            "anchored": True,
            "anchor_ms": int(anchor.get("ms", current_ms)),
            "equity": round(equity, 2),
            "venue_delta": round(venue_delta, 2),
            "ledger_delta": round(ledger_delta, 2),
            "unexplained": round(venue_delta - ledger_delta, 2),
        }

    # ---- v7.8: venue positions ----------------------------------------
    def replace_venue_positions(
        self, positions: List[Dict[str, Any]], stamp: Optional[int] = None
    ) -> None:
        """Mirror a complete GET /v1/positions page set.

        The venue view is authoritative and complete, so the table is replaced
        rather than merged: a position that has gone (redeemed, or sold) must
        disappear here too or it would keep inflating equity.
        """
        checked = now_ms() if stamp is None else int(stamp)
        with self.lock:
            self.db.execute("DELETE FROM venue_positions")
            for entry in positions:
                self.db.execute(
                    "INSERT OR REPLACE INTO venue_positions("
                    "position_id,market_id,market_title,outcome_name,"
                    "index_set,condition_id,shares,value_usd,avg_buy_price,"
                    "pnl_usd,best_bid,best_ask,outcome_status,market_status,"
                    "candle_id,kind,direction,updated_ms) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(entry.get("position_id") or ""),
                        str(entry.get("market_id") or ""),
                        str(entry.get("market_title") or ""),
                        str(entry.get("outcome_name") or ""),
                        entry.get("index_set"),
                        str(entry.get("condition_id") or ""),
                        float(entry.get("shares") or 0.0),
                        entry.get("value_usd"),
                        entry.get("avg_buy_price"),
                        entry.get("pnl_usd"),
                        entry.get("best_bid"),
                        entry.get("best_ask"),
                        entry.get("outcome_status"),
                        entry.get("market_status"),
                        entry.get("candle_id"),
                        entry.get("kind"),
                        entry.get("direction"),
                        checked,
                    ),
                )
            self.db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                ("v78_positions_checked_ms", str(checked)),
            )
            self.db.commit()

    def _positions_checked_ms_locked(self) -> Optional[int]:
        row = self.db.execute(
            "SELECT value FROM meta WHERE key=?",
            ("v78_positions_checked_ms",),
        ).fetchone()
        try:
            return int(row[0]) if row else None
        except (TypeError, ValueError):
            return None

    def _positions_fresh_locked(self, current_ms: int) -> bool:
        checked = self._positions_checked_ms_locked()
        if checked is None:
            return False
        return (current_ms - checked) <= PREDICT_POSITIONS_STALE_SEC * 1000.0

    def _venue_open_value_locked(self) -> float:
        """Live mark of positions the venue still shows as unresolved."""
        value = self.db.execute(
            "SELECT COALESCE(SUM(value_usd),0) FROM venue_positions "
            "WHERE outcome_status IS NULL OR outcome_status NOT IN "
            "('WON','LOST')"
        ).fetchone()[0]
        return max(0.0, float(value or 0.0))

    def _venue_unredeemed_locked(self) -> float:
        """WON positions still holding shares: won, not yet paid out.

        One dollar per share is the settlement value of a winning outcome
        token, so this is exact rather than inferred. `valueUsd` is not used
        here because a resolved outcome has no book to mark against.
        """
        value = self.db.execute(
            "SELECT COALESCE(SUM(shares),0) FROM venue_positions "
            "WHERE outcome_status='WON' AND shares > 0"
        ).fetchone()[0]
        return max(0.0, float(value or 0.0))

    def venue_open_positions(self) -> List[Dict[str, Any]]:
        """Live open positions for the dashboard, venue values only."""
        with self.lock:
            fresh = self._positions_fresh_locked(now_ms())
            rows = self.db.execute(
                "SELECT * FROM venue_positions WHERE shares > 0 AND "
                "(outcome_status IS NULL OR outcome_status NOT IN "
                "('WON','LOST')) ORDER BY value_usd DESC"
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "kind": r["kind"] or "--",
                "direction": r["direction"] or (r["outcome_name"] or "--"),
                "shares": round(float(r["shares"] or 0.0), 4),
                "buy_price": (
                    round(float(r["avg_buy_price"]), 4)
                    if r["avg_buy_price"] is not None else None
                ),
                "used_usd": (
                    round(float(r["avg_buy_price"]) * float(r["shares"]), 2)
                    if r["avg_buy_price"] is not None else None
                ),
                "value_usd": (
                    round(float(r["value_usd"]), 2)
                    if r["value_usd"] is not None else None
                ),
                "pnl_usd": (
                    round(float(r["pnl_usd"]), 2)
                    if r["pnl_usd"] is not None else None
                ),
                "market_title": r["market_title"] or "",
                "fresh": fresh,
            })
        return out

    def venue_unredeemed_positions(self) -> List[Dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT kind,direction,shares,market_title FROM "
                "venue_positions WHERE outcome_status='WON' AND shares > 0 "
                "ORDER BY shares DESC"
            ).fetchall()
        return [
            {
                "kind": r["kind"] or "--",
                "direction": r["direction"] or "--",
                "shares": round(float(r["shares"] or 0.0), 4),
                "payout_usd": round(float(r["shares"] or 0.0), 2),
                "market_title": r["market_title"] or "",
            }
            for r in rows
        ]

    def leg_pnl(self) -> Dict[str, Dict[str, Any]]:
        """Realised P&L per signal, from real fill prices and real fees."""
        out: Dict[str, Dict[str, Any]] = {}
        with self.lock:
            for kind in CAPITAL_KINDS:
                row = self.db.execute(
                    "SELECT COALESCE(SUM(financial_pnl),0) p, COUNT(*) n, "
                    "COALESCE(SUM(CASE WHEN financial_result='WIN' THEN 1 ELSE 0 END),0) w "
                    "FROM trades WHERE kind=? AND financial_result IN ('WIN','LOSS') "
                    "AND filled=1 AND COALESCE(financial_is_shadow,0)=0 "
                    "AND COALESCE(forbidden,0)=0 "
                    "AND COALESCE(state_x,'')<>'SX' AND UPPER(COALESCE(order_status,'')) NOT IN ('PARTIALLYFILLED','FILLED_DETAILS_PENDING')",
                    (kind,),
                ).fetchone()
                out[kind] = {
                    "pnl": round(float(row["p"] or 0.0), 2),
                    "settled": int(row["n"] or 0),
                    "wins": int(row["w"] or 0),
                }
        return out

    def match_position_to_trade(
        self, market_id: str, outcome_name: str
    ) -> Dict[str, Any]:
        """Attach our signal/direction to a venue position.

        Matching is by market plus outcome side, newest filled trade first.
        A position with no local match keeps null fields rather than being
        guessed at, so a manual trade never shows up as a bot signal.
        """
        if not market_id:
            return {"candle_id": None, "kind": None, "direction": None}
        name = str(outcome_name or "").strip().lower()
        if name in ("yes", "up"):
            direction = "UP"
        elif name in ("no", "down"):
            direction = "DOWN"
        else:
            direction = None
        with self.lock:
            if direction is None:
                row = self.db.execute(
                    "SELECT candle_id,kind,direction FROM trades WHERE "
                    "market_id=? AND COALESCE(filled,0)=1 "
                    "ORDER BY ts_ms DESC LIMIT 1",
                    (str(market_id),),
                ).fetchone()
            else:
                row = self.db.execute(
                    "SELECT candle_id,kind,direction FROM trades WHERE "
                    "market_id=? AND direction=? AND COALESCE(filled,0)=1 "
                    "ORDER BY ts_ms DESC LIMIT 1",
                    (str(market_id), direction),
                ).fetchone()
        if row is None:
            return {"candle_id": None, "kind": None, "direction": direction}
        return {
            "candle_id": int(row["candle_id"]),
            "kind": str(row["kind"]),
            "direction": str(row["direction"]),
        }

    def set_live_wallet_balance(
        self, balance: Optional[float], checked_ms: Optional[int] = None
    ) -> None:
        """Publish Predict.fun smart-account USDT into the capital authority.

        LiveExecutor already obtains this balance from predict-sdk. Store owns
        sizing, so the same proved venue balance must be visible here too. Any
        rise since the previous read also retires v7.7 payout claims.
        """
        stamp = now_ms() if checked_ms is None else int(checked_ms)
        value = None if balance is None else max(0.0, float(balance))
        with self.lock:
            self._live_wallet_balance_usd = value
            self._live_wallet_checked_ms = stamp
            if value is not None:
                self._credit_pending_payouts_locked(value, stamp)
                self._anchor_wallet_truth_locked(value, stamp)
                self._seed_live_streak_stake_locked(value)

    def _seed_live_streak_stake_locked(self, wallet_balance: float) -> None:
        """One-time v7.1 migration from the legacy $10 startup placeholder.

        Only streak mode is auto-seeded. An operator-selected fixed stake stays
        fixed, and percentage mode already sizes directly from live balance.
        Existing win/loss streak counters are preserved.
        """
        key = "v71_live_stake_seeded"
        if self.db.execute(
            "SELECT 1 FROM meta WHERE key=?", (key,)
        ).fetchone() is not None:
            return
        row = self.db.execute(
            "SELECT stake_config FROM trade_controls WHERE kind=?",
            (SYSTEM_CONTROL_KIND,),
        ).fetchone()
        if row is None:
            return
        try:
            config = json.loads(row[0])
        except (TypeError, ValueError):
            config = dict(DEFAULT_STAKE_CONFIG)
        if not isinstance(config, dict):
            config = dict(DEFAULT_STAKE_CONFIG)
        if str(config.get("mode", STAKE_MODE_STREAK)) == STAKE_MODE_STREAK:
            minimum = float(config.get("min_stake", MIN_STAKE_USD))
            maximum = float(config.get("max_stake", MAX_STAKE_USD))
            percent = float(config.get("percent", 10.0))
            seeded = float(wallet_balance) * percent / 100.0
            seeded = max(minimum, min(maximum, seeded))
            # If the wallet cannot fund the configured minimum, next_stake()
            # correctly returns zero; do not invent a smaller hidden stake.
            config["current_stake"] = round(seeded, 2)
            self.db.execute(
                "UPDATE trade_controls SET stake_config=?,updated_ms=? "
                "WHERE kind=?",
                (json.dumps(config), now_ms(), SYSTEM_CONTROL_KIND),
            )
        self.db.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            (key, str(now_ms())),
        )
        self.db.commit()

    def capital_state(self) -> Dict[str, Any]:
        """Live Predict.fun USDT balance and truly free order capital.

        Production source of truth is the Predict.fun smart-account USDT read
        by predict-sdk. Local settled P&L remains a performance statistic; it
        is never added to an assumed starting bankroll.

        Filled collateral is already absent from the on-chain USDT balance, so
        subtracting filled positions again would double-count it. We reserve
        only still-unfilled/ambiguous live orders that may consume the wallet.
        """
        marks = ",".join("?" for _ in CAPITAL_KINDS)
        current_ms = now_ms()
        with self.lock:
            realised = self.db.execute(
                f"SELECT COALESCE(SUM(financial_pnl), 0) FROM trades "
                f"WHERE kind IN ({marks}) AND financial_result IN ('WIN','LOSS') "
                f"AND filled=1 AND COALESCE(financial_is_shadow,0)=0 "
                f"AND COALESCE(forbidden,0)=0 AND COALESCE(state_x,'')<>'SX' "
                f"AND UPPER(COALESCE(order_status,'')) NOT IN ('PARTIALLYFILLED','FILLED_DETAILS_PENDING')",
                CAPITAL_KINDS,
            ).fetchone()[0]
            settled = self.db.execute(
                f"SELECT COUNT(*) FROM trades WHERE kind IN ({marks}) "
                f"AND financial_result IN ('WIN','LOSS') AND filled=1 "
                f"AND COALESCE(financial_is_shadow,0)=0 "
                f"AND COALESCE(forbidden,0)=0 AND COALESCE(state_x,'')<>'SX' "
                f"AND UPPER(COALESCE(order_status,'')) NOT IN ('PARTIALLYFILLED','FILLED_DETAILS_PENDING')",
                CAPITAL_KINDS,
            ).fetchone()[0]

            # Offline self-tests intentionally retain the old synthetic capital
            # model. Production never falls back to it.
            if "--self-test" in sys.argv and getattr(
                self, "_live_wallet_balance_usd", None
            ) is None:
                reserved = self.db.execute(
                    f"SELECT COALESCE(SUM(stake), 0) FROM trades "
                    f"WHERE kind IN ({marks}) AND correct IS NULL "
                    f"AND COALESCE(forbidden,0)=0 AND "
                    f"(filled=1 OR "
                    f"(candle_id + ? > ? AND UPPER(COALESCE(order_status,'')) IN "
                    f"('QUEUED','SIGNING','SUBMITTING','UNKNOWN','ACCEPTED',"
                    f"'MATCHING','OPEN','PENDING','PARTIALLYFILLED',"
                    f"'FILLED_DETAILS_PENDING')) OR "
                    f"(order_hash IS NOT NULL AND TRIM(order_hash)<>'' AND "
                    f"UPPER(COALESCE(order_status,'')) IN "
                    f"('SUBMITTING','UNKNOWN','ACCEPTED','MATCHING','OPEN',"
                    f"'PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING'))) ",
                    tuple(CAPITAL_KINDS) + (CANDLE_MS, current_ms),
                ).fetchone()[0]
                balance = STARTING_CAPITAL_USD + float(realised or 0.0)
                free = max(0.0, balance - float(reserved or 0.0))
                return {
                    "starting": STARTING_CAPITAL_USD,
                    "balance": round(balance, 2),
                    # The synthetic bankroll already books the win, so there is
                    # nothing left unredeemed in this offline path.
                    "wallet": round(balance, 2),
                    "pending_payout": 0.0,
                    "pending_source": "SELF_TEST_FALLBACK",
                    "open_position_value": 0.0,
                    "equity": round(balance, 2),
                    "positions_fresh": False,
                    "wallet_free": round(free, 2),
                    "reserved": round(float(reserved or 0.0), 2),
                    "free": round(free, 2),
                    "realised": round(float(realised or 0.0), 2),
                    "next_stake": capital_stake(free),
                    "settled_trades": int(settled or 0),
                    "risk_fraction": CAPITAL_RISK_FRACTION,
                    "max_stake": MAX_STAKE_USD,
                    "source": "SELF_TEST_FALLBACK",
                    "fresh": True,
                    "balance_age_sec": 0.0,
                    "truth": {"anchored": False, "venue_delta": None,
                              "ledger_delta": None, "unexplained": None},
                }

            wallet = getattr(self, "_live_wallet_balance_usd", None)
            checked = int(getattr(self, "_live_wallet_checked_ms", 0) or 0)
            age_sec = (
                None if not checked
                else max(0.0, (current_ms - checked) / 1000.0)
            )
            fresh = bool(
                wallet is not None
                and age_sec is not None
                and age_sec <= PREDICT_BALANCE_STALE_SEC
            )

            # The wallet balance already reflects executed fills. Reserve only
            # orders not yet proved filled/terminal whose signed intent may still
            # consume USDT. This prevents overspending without double-subtracting
            # open positions already paid for on-chain.
            reserved = self.db.execute(
                f"SELECT COALESCE(SUM(stake), 0) FROM trades "
                f"WHERE kind IN ({marks}) AND correct IS NULL "
                f"AND COALESCE(forbidden,0)=0 AND COALESCE(filled,0)=0 AND "
                f"("
                f"(candle_id + ? > ? AND UPPER(COALESCE(order_status,'')) IN "
                f"('QUEUED','SIGNING','SUBMITTING','UNKNOWN','ACCEPTED',"
                f"'MATCHING','OPEN','PENDING','PARTIALLYFILLED',"
                f"'FILLED_DETAILS_PENDING')) OR "
                f"(order_hash IS NOT NULL AND TRIM(order_hash)<>'' AND "
                f"UPPER(COALESCE(order_status,'')) IN "
                f"('SUBMITTING','UNKNOWN','ACCEPTED','MATCHING','OPEN',"
                f"'PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING'))"
                f")",
                tuple(CAPITAL_KINDS) + (CANDLE_MS, current_ms),
            ).fetchone()[0]

            pending = self._pending_payout_locked(current_ms)
            # v7.8: when the venue view is fresh, its WON-with-shares total
            # replaces the v7.7 inference outright. The inferred figure is a
            # fallback for when positions cannot be read, not a second opinion.
            positions_fresh = self._positions_fresh_locked(current_ms)
            venue_unredeemed = (
                self._venue_unredeemed_locked() if positions_fresh else 0.0
            )
            open_value = (
                self._venue_open_value_locked() if positions_fresh else 0.0
            )
            if positions_fresh:
                pending = venue_unredeemed
                pending_source = "PREDICT_FUN_POSITIONS"
            else:
                pending_source = "INFERRED_CLAIM_LEDGER"

            if not fresh:
                return {
                    "starting": None,
                    "balance": 0.0,
                    "wallet": 0.0,
                    "pending_payout": round(pending, 2),
                    "pending_source": pending_source,
                    "open_position_value": round(open_value, 2),
                    "equity": round(open_value, 2),
                    "positions_fresh": positions_fresh,
                    "wallet_free": 0.0,
                    "reserved": round(float(reserved or 0.0), 2),
                    "free": 0.0,
                    "realised": round(float(realised or 0.0), 2),
                    "next_stake": 0.0,
                    "settled_trades": int(settled or 0),
                    "risk_fraction": CAPITAL_RISK_FRACTION,
                    "max_stake": MAX_STAKE_USD,
                    "source": "PREDICT_FUN_USDT_UNAVAILABLE",
                    "fresh": False,
                    "balance_age_sec": age_sec,
                    "truth": {"anchored": False, "venue_delta": None,
                              "ledger_delta": None, "unexplained": None},
                }

            # v7.7: `wallet` is spendable now and stays the funding authority.
            # `balance` adds winnings that are settled but not yet redeemed, so
            # streak/percent sizing compounds from the real bankroll instead of
            # from whatever the auto-claim happens to have finished paying.
            spendable = max(0.0, float(wallet))
            balance = spendable + pending
            free = max(0.0, balance - float(reserved or 0.0))
            wallet_free = max(0.0, spendable - float(reserved or 0.0))
            control = self.control_row(SYSTEM_CONTROL_KIND)
            configured = configured_stake(control["stake"], balance)
            next_stake = configured if free + 1e-9 >= configured else 0.0
            return {
                "starting": None,
                "balance": round(balance, 2),
                "wallet": round(spendable, 2),
                "pending_payout": round(pending, 2),
                "pending_source": pending_source,
                # v7.8 item 18: equity is everything the venue says is ours.
                # It is a reporting figure only - sizing still uses `balance`
                # and funding still uses `wallet`, so an open position can
                # never fund a new order.
                "open_position_value": round(open_value, 2),
                "equity": round(balance + open_value, 2),
                "positions_fresh": positions_fresh,
                "wallet_free": round(wallet_free, 2),
                "reserved": round(float(reserved or 0.0), 2),
                "free": round(free, 2),
                "realised": round(float(realised or 0.0), 2),
                "next_stake": round(next_stake, 2),
                "settled_trades": int(settled or 0),
                "risk_fraction": CAPITAL_RISK_FRACTION,
                "max_stake": MAX_STAKE_USD,
                "source": "PREDICT_FUN_USDT",
                "fresh": True,
                "balance_age_sec": age_sec,
                "truth": self._wallet_truth_locked(spendable, pending, current_ms),
            }


    def trade_summary(
        self, limit: Optional[int] = None, range_key: str = "1D"
    ) -> Dict[str, Any]:
        """Full-range realised PnL plus independent terminal execution stats.

        PnL uses only final, real, filled orders with settled WIN/LOSS truth.
        Fill rate uses every *terminal attempted* real order in the range, so a
        failed submission cannot disappear merely because it has no PnL row.
        Active/ambiguous/partial lifecycles are excluded from both until final.
        """
        epoch = self.metrics_epoch()
        range_key = str(range_key or "1D").upper()
        if range_key not in {"1D", "1W", "ALL"}:
            range_key = "1D"
        duration = {"1D": 86_400_000, "1W": 604_800_000}.get(range_key)
        cutoff = max(epoch, now_ms() - duration) if duration else epoch
        unresolved_sql = (
            "('QUEUED','SIGNING','SUBMITTING','UNKNOWN','ACCEPTED','MATCHING',"
            "'OPEN','PENDING','PARTIALLYFILLED','FILLED_DETAILS_PENDING')"
        )
        with self.lock:
            rows = self.db.execute(
                "SELECT candle_id,kind,fill_price,filled,correct,financial_pnl,attempts,"
                "delay_ms,stake,shares,order_status "
                "FROM trades WHERE financial_result IN ('WIN','LOSS') "
                "AND filled=1 AND COALESCE(financial_is_shadow,0)=0 "
                "AND COALESCE(forbidden,0)=0 "
                "AND COALESCE(state_x,'')<>'SX' "
                "AND UPPER(COALESCE(order_status,'')) NOT IN ('PARTIALLYFILLED','FILLED_DETAILS_PENDING') "
                "AND candle_id >= ? "
                "ORDER BY candle_id, CASE kind WHEN 'MAIN' THEN 0 "
                "WHEN 'REVERSAL' THEN 1 WHEN 'EF' THEN 2 ELSE 3 END",
                (cutoff,),
            ).fetchall()
            attempts = self.db.execute(
                "SELECT candle_id,kind,fill_price,filled,attempts,delay_ms,stake,shares,"
                "order_status,attempt_log FROM trades WHERE candle_id>=? "
                "AND COALESCE(financial_is_shadow,0)=0 "
                "AND COALESCE(forbidden,0)=0 AND COALESCE(state_x,'')<>'SX' "
                "AND COALESCE(attempts,0)>0 "
                f"AND UPPER(COALESCE(order_status,'')) NOT IN {unresolved_sql} "
                "ORDER BY candle_id, CASE kind WHEN 'MAIN' THEN 0 "
                "WHEN 'REVERSAL' THEN 1 WHEN 'EF' THEN 2 ELSE 3 END",
                (cutoff,),
            ).fetchall()

        terminal_attempts = list(attempts)
        filled_attempts = [r for r in terminal_attempts if int(r["filled"] or 0)]
        failed_attempts = len(terminal_attempts) - len(filled_attempts)
        total = sum(float(r["financial_pnl"] or 0.0) for r in rows)
        staked = sum(
            float(r["stake"] if r["stake"] is not None else r["fill_price"] or 0.0)
            for r in rows
        )
        curve: List[float] = []
        curve_points: List[Dict[str, Any]] = []
        running = 0.0
        by_kind: Dict[str, float] = {}
        for r in rows:
            running += float(r["financial_pnl"] or 0.0)
            curve.append(round(running, 4))
            curve_points.append({
                "ts_ms": int(r["candle_id"]) + CANDLE_MS,
                "pnl": round(running, 4),
            })
            by_kind[str(r["kind"])] = (
                by_kind.get(str(r["kind"]), 0.0) + float(r["financial_pnl"] or 0.0)
            )

        prices = [
            float(r["fill_price"]) for r in filled_attempts if r["fill_price"] is not None
        ]
        shares = [
            float(r["shares"]) for r in filled_attempts if r["shares"] is not None
        ]
        # Two different first-attempt questions are reported separately:
        # 1) Did Predict return an accepted HTTP response for attempt 1?
        # 2) Did the order ultimately fill without requiring attempt 2?
        # Mixing them hid noMarketMatch-style post-acceptance failures.
        first_attempt_failures = sum(
            1 for r in terminal_attempts
            if int(r["attempts"] or 0) > 1
            or (int(r["attempts"] or 0) == 1 and not int(r["filled"] or 0))
        )
        first_http_statuses = [
            first_attempt_http_status(r["attempt_log"]) for r in terminal_attempts
        ]
        first_http_observed = sum(1 for status in first_http_statuses if status is not None)
        first_http_accepted = sum(1 for status in first_http_statuses if status == "ACCEPTED")
        first_no_retry_fills = sum(
            1 for r in terminal_attempts
            if int(r["attempts"] or 0) == 1 and int(r["filled"] or 0) == 1
        )
        first_attempt_by_kind: Dict[str, Dict[str, Any]] = {}
        for r, http_status in zip(terminal_attempts, first_http_statuses):
            kind = str(r["kind"])
            bucket = first_attempt_by_kind.setdefault(
                kind, {
                    "attempted": 0, "http_observed": 0, "http_accepted": 0,
                    "http_acceptance_rate": None, "no_retry_filled": 0,
                    "no_retry_fill_rate": None, "required_retry_or_failed": 0,
                }
            )
            bucket["attempted"] += 1
            if http_status is not None:
                bucket["http_observed"] += 1
                if http_status == "ACCEPTED":
                    bucket["http_accepted"] += 1
            no_retry_fill = (
                int(r["attempts"] or 0) == 1 and int(r["filled"] or 0) == 1
            )
            if no_retry_fill:
                bucket["no_retry_filled"] += 1
            else:
                bucket["required_retry_or_failed"] += 1
        for bucket in first_attempt_by_kind.values():
            bucket["http_acceptance_rate"] = (
                bucket["http_accepted"] / bucket["http_observed"]
                if bucket["http_observed"] else None
            )
            bucket["no_retry_fill_rate"] = (
                bucket["no_retry_filled"] / bucket["attempted"]
                if bucket["attempted"] else None
            )
        delays = [float(r["delay_ms"] or 0.0) for r in terminal_attempts]
        return {
            "range": range_key,
            "count": len(rows),
            "filled": len(filled_attempts),
            "failed": failed_attempts,
            "attempted": len(terminal_attempts),
            "fill_rate": (
                len(filled_attempts) / len(terminal_attempts)
                if terminal_attempts else None
            ),
            "pnl": round(total, 4),
            "staked": round(staked, 4),
            "return_on_stake": (total / staked) if staked else None,
            "per_100": round(100.0 * total / len(rows), 2) if rows else None,
            "avg_price": round(sum(prices) / len(prices), 4) if prices else None,
            "avg_shares": round(sum(shares) / len(shares), 4) if shares else None,
            "avg_delay_ms": round(sum(delays) / len(delays)) if delays else None,
            "first_attempt_failures": first_attempt_failures,
            "first_attempt_failure_rate": (
                first_attempt_failures / len(terminal_attempts)
                if terminal_attempts else None
            ),
            "first_attempt_acceptance_observed": first_http_observed,
            "first_attempt_http_accepted": first_http_accepted,
            "first_attempt_acceptance_rate": (
                first_http_accepted / first_http_observed
                if first_http_observed else None
            ),
            "first_attempt_no_retry_fills": first_no_retry_fills,
            "first_attempt_no_retry_fill_rate": (
                first_no_retry_fills / len(terminal_attempts)
                if terminal_attempts else None
            ),
            "first_attempt_by_kind": first_attempt_by_kind,
            "retries": sum(1 for r in terminal_attempts if int(r["attempts"] or 0) > 1),
            "by_kind": {k: round(v, 4) for k, v in by_kind.items()},
            "curve": curve,
            "curve_points": curve_points,
        }

    def settled_history(self, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """Recent settled candles, newest first, paged straight from sqlite."""
        epoch = self.metrics_epoch()
        with self.lock:
            total = self.db.execute(
                "SELECT COUNT(DISTINCT candle_id) FROM ("
                "SELECT candle_id FROM predictions WHERE actual IS NOT NULL "
                "AND candle_id >= ? UNION ALL "
                "SELECT candle_id FROM ef_predictions WHERE actual IS NOT NULL "
                "AND candle_id >= ?)", (epoch, epoch)
            ).fetchone()[0]
            ids = [int(r[0]) for r in self.db.execute(
                "SELECT DISTINCT candle_id FROM ("
                "SELECT candle_id FROM predictions WHERE actual IS NOT NULL "
                "AND candle_id >= ? UNION ALL "
                "SELECT candle_id FROM ef_predictions WHERE actual IS NOT NULL "
                "AND candle_id >= ?) "
                "ORDER BY candle_id DESC LIMIT ? OFFSET ?",
                (epoch, epoch, int(limit), int(offset))).fetchall()]
            rows = []
            if ids:
                marks = ",".join("?" * len(ids))
                rows = self.db.execute(
                    f"WITH all_predictions AS ("
                    f"SELECT candle_id,kind,direction,actual,correct,ts_ms "
                    f"FROM predictions UNION ALL "
                    f"SELECT candle_id,kind,direction,actual,correct,ts_ms "
                    f"FROM ef_predictions) "
                    f"SELECT p.candle_id,p.kind,p.direction,p.actual,p.correct,"
                    f"p.ts_ms,t.quoted_price,t.fill_price,t.filled,t.attempts,"
                    f"t.shares,t.forbidden,t.failure_reason,t.stake,t.financial_pnl,"
                    f"t.financial_result,t.financial_is_shadow,t.order_status,"
                    f"t.state_x,t.state_x_active,"
                    f"t.sx_trigger_reason "
                    f"FROM all_predictions p LEFT JOIN trades t "
                    f"ON t.candle_id=p.candle_id AND t.kind=p.kind "
                    f"WHERE p.candle_id IN ({marks}) AND p.actual IS NOT NULL",
                    ids).fetchall()
            combined_financial = self._combined_financial_by_candle_locked(ids)
        grouped: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            cid = int(r["candle_id"])
            entry = grouped.setdefault(cid, {"candle_id": cid,
                                             "actual": r["actual"]})
            entry[r["kind"].lower()] = {
                "direction": r["direction"],
                "correct": (
                    1 if r["financial_result"] == "WIN" else
                    0 if r["financial_result"] == "LOSS" else None
                ),
                "directional_correct": (
                    None if r["correct"] is None else int(r["correct"])
                ),
                "financial_result": r["financial_result"],
                "financial_is_shadow": bool(r["financial_is_shadow"] or 0),
                "at": round((int(r["ts_ms"]) - cid) / 1000.0),
                "quoted_price": r["quoted_price"],
                "fill_price": r["fill_price"],
                "filled": None if r["filled"] is None else int(r["filled"]),
                "attempts": r["attempts"],
                "shares": r["shares"],
                "stake": r["stake"],
                "pnl": r["financial_pnl"],
                "order_status": r["order_status"],
                "forbidden": bool(r["forbidden"] or 0),
                "state_x": str(r["state_x"] or ""),
                "state_x_active": bool(r["state_x_active"] or 0),
                "sx_trigger_reason": str(r["sx_trigger_reason"] or ""),
                "signals_off": (
                    bool(r["forbidden"] or 0)
                    and "manually OFF" in str(r["failure_reason"] or "")
                ),
            }
        for cid, entry in grouped.items():
            combined = combined_financial.get(cid, {})
            entry["combined_financial_pnl"] = combined.get("pnl")
            entry["combined_financial_result"] = combined.get("result")
            entry["combined_financial_mode"] = combined.get("mode")
            entry["combined_correct"] = combined.get("correct")
        return {"total": int(total), "offset": int(offset), "limit": int(limit),
                "rows": sorted(grouped.values(), key=lambda x: -x["candle_id"])}

    def recent_orders(
        self, kind: str, offset: int = 0, limit: int = 10
    ) -> Dict[str, Any]:
        """Paged execution rows for Data, including archived failed EF attempts."""
        kind = str(kind).upper()
        if kind not in TRADE_KINDS:
            raise ValueError(f"unknown signal: {kind}")
        epoch = self.metrics_epoch()
        fetch_count = max(1, int(offset) + int(limit))
        with self.lock:
            active_total = int(self.db.execute(
                "SELECT COUNT(*) FROM trades WHERE kind=? AND candle_id>=?",
                (kind, epoch),
            ).fetchone()[0])
            active_rows = self.db.execute(
                "WITH all_predictions AS ("
                "SELECT candle_id,kind,price FROM predictions UNION ALL "
                "SELECT candle_id,kind,price FROM ef_predictions) "
                "SELECT t.*,p.price AS signal_price FROM trades t "
                "LEFT JOIN all_predictions p ON p.candle_id=t.candle_id "
                "AND p.kind=t.kind WHERE t.kind=? AND t.candle_id>=? "
                "ORDER BY t.ts_ms DESC LIMIT ?",
                (kind, epoch, fetch_count),
            ).fetchall()
            failed_total = 0
            failed_rows: List[sqlite3.Row] = []
            if kind == "EF":
                failed_total = int(self.db.execute(
                    "SELECT COUNT(*) FROM ef_failed_attempts WHERE candle_id>=?",
                    (epoch,),
                ).fetchone()[0])
                failed_rows = self.db.execute(
                    "SELECT * FROM ef_failed_attempts WHERE candle_id>=? "
                    "ORDER BY signal_ts_ms DESC LIMIT ?",
                    (epoch, fetch_count),
                ).fetchall()

        out: List[Dict[str, Any]] = []
        for row in active_rows:
            status = str(row["order_status"] or "")
            forbidden = bool(row["forbidden"] or 0)
            state_x = str(row["state_x"] or "") == "SX"
            if forbidden and state_x:
                status = "F+SX"
            elif forbidden:
                status = "F"
            elif state_x:
                status = "SX"
            elif not status:
                status = "FILLED" if row["filled"] else "NOT FILLED"
            out.append({
                "candle_id": int(row["candle_id"]),
                "ts_ms": int(row["ts_ms"]),
                "utc": london_stamp(int(row["ts_ms"])),
                "seconds_into_candle": row["seconds_into_candle"],
                "kind": row["kind"], "direction": row["direction"],
                "signal_price": row["signal_price"],
                "quoted_price": row["quoted_price"],
                "fill_price": row["fill_price"], "stake": row["stake"],
                "shares": row["shares"], "delay_ms": row["delay_ms"],
                "last_attempt_ms": row["last_attempt_ms"],
                "book_age_ms": row["book_age_ms"], "fee_rate": row["fee_rate"],
                "fee_collateral": row["fee_collateral"],
                "fee_shares": row["fee_shares"],
                "market_id": row["market_id"], "order_id": row["order_id"],
                "order_hash": row["order_hash"], "status": status,
                "attempts": int(row["attempts"] or 0),
                "ef_attempt_seq": (
                    int(row["ef_attempt_seq"] or 0) or None
                    if kind == "EF" else None
                ),
                "archived_failed_attempt": False,
                "filled": bool(row["filled"] or 0), "forbidden": forbidden,
                "state_x": "SX" if state_x else "",
                "state_x_active": bool(row["state_x_active"] or 0),
                "state_x_trigger_time": row["state_x_trigger_time"],
                "state_x_end_time": row["state_x_end_time"],
                "sx_trigger_reason": str(row["sx_trigger_reason"] or ""),
                "actual": row["actual"],
                "correct": (
                    True if row["financial_result"] == "WIN" else
                    False if row["financial_result"] == "LOSS" else None
                ),
                "directional_correct": (
                    None if row["correct"] is None else bool(row["correct"])
                ),
                "financial_result": row["financial_result"],
                "financial_is_shadow": bool(row["financial_is_shadow"] or 0),
                "pnl": row["financial_pnl"], "failure_reason": row["failure_reason"],
            })

        if kind == "EF":
            for failed in failed_rows:
                try:
                    trade = json.loads(failed["trade_json"] or "{}")
                except (TypeError, ValueError):
                    trade = {}
                try:
                    pred = json.loads(failed["prediction_json"] or "{}")
                except (TypeError, ValueError):
                    pred = {}
                stamp = int(failed["signal_ts_ms"] or trade.get("ts_ms") or 0)
                status = str(failed["order_status"] or trade.get("order_status") or "FAILED")
                out.append({
                    "candle_id": int(failed["candle_id"]),
                    "ts_ms": stamp, "utc": london_stamp(stamp),
                    "seconds_into_candle": trade.get("seconds_into_candle"),
                    "kind": "EF",
                    "direction": str(failed["direction"] or trade.get("direction") or pred.get("direction") or ""),
                    "signal_price": pred.get("price"),
                    "quoted_price": trade.get("quoted_price"),
                    "fill_price": trade.get("fill_price"),
                    "stake": trade.get("stake"), "shares": trade.get("shares"),
                    "delay_ms": trade.get("delay_ms"),
                    "last_attempt_ms": trade.get("last_attempt_ms"),
                    "book_age_ms": trade.get("book_age_ms"),
                    "fee_rate": trade.get("fee_rate"),
                    "fee_collateral": trade.get("fee_collateral"),
                    "fee_shares": trade.get("fee_shares"),
                    "market_id": trade.get("market_id"),
                    "order_id": trade.get("order_id"),
                    "order_hash": trade.get("order_hash"),
                    "status": f"{status} · REARMED",
                    "attempts": int(trade.get("attempts") or 0),
                    "ef_attempt_seq": int(failed["attempt_seq"] or 0) or None,
                    "archived_failed_attempt": True,
                    "filled": False, "forbidden": False,
                    "state_x": str(trade.get("state_x") or ""),
                    "state_x_active": bool(trade.get("state_x_active") or 0),
                    "state_x_trigger_time": trade.get("state_x_trigger_time"),
                    "state_x_end_time": trade.get("state_x_end_time"),
                    "sx_trigger_reason": str(trade.get("sx_trigger_reason") or ""),
                    "actual": None, "correct": None, "directional_correct": None,
                    "financial_result": None, "financial_is_shadow": False,
                    "pnl": None, "failure_reason": str(failed["reason"] or ""),
                    "cooldown_until_ms": failed["cooldown_until_ms"],
                })

        out.sort(key=lambda item: int(item.get("ts_ms") or 0), reverse=True)
        page = out[int(offset):int(offset) + int(limit)]
        total = active_total + failed_total
        return {"kind": kind, "total": total, "offset": int(offset),
                "limit": int(limit), "rows": page}

    def latest_trade(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM trades WHERE COALESCE(forbidden,0)=0 "
                "ORDER BY ts_ms DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row is not None else None


    def add_outcome_event(self, event: Dict[str, Any]) -> bool:
        """Store one settled candle: what was called, and whether it was right.

        Replaces the monetary event. No stake, no share price, no profit -
        this model has no market feed, so those numbers were priced against
        its own opinion and could only ever confirm themselves.
        """
        with self.lock:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO outcome_events("
                "candle_id,ts_ms,actual,main_direction,main_correct,"
                "main_confidence,reversal_direction,reversal_correct,"
                "net_direction,net_correct) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    int(event["candle_id"]), int(event["ts_ms"]),
                    str(event["actual"]), str(event["main_direction"]),
                    int(event["main_correct"]),
                    float(event["main_confidence"]),
                    event.get("reversal_direction"),
                    event.get("reversal_correct"),
                    str(event["net_direction"]), int(event["net_correct"]),
                ),
            )
            self.db.commit()
            return cursor.rowcount > 0

    def confidence_calibration(self) -> List[Dict[str, Any]]:
        """Accuracy grouped by the confidence the model assigned.

        This is the number that matters now: a model whose 0.8 calls are right
        80 percent of the time is usable, whatever its headline accuracy.
        """
        with self.lock:
            rows = self.db.execute(
                "SELECT main_confidence, main_correct FROM outcome_events"
            ).fetchall()
        buckets = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        out: List[Dict[str, Any]] = []
        for low, high in buckets:
            hits = [r for r in rows if low <= float(r[0]) < high]
            correct = sum(1 for r in hits if int(r[1]) == 1)
            out.append({
                "band": f"{low:.1f}-{min(high, 1.0):.1f}",
                "count": len(hits),
                "correct": correct,
                "accuracy": (correct / len(hits)) if hits else None,
            })
        return out

    def add_pnl_event(self, event: Dict[str, Any]) -> bool:
        with self.lock:
            cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO pnl_events
                (candle_id, ts_ms, actual, main_direction, main_entry_price,
                 main_stake, main_shares, main_pnl, reversal_direction,
                 reversal_entry_price, reversal_stake, reversal_shares,
                 reversal_pnl, net_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(event["candle_id"]),
                    int(event["ts_ms"]),
                    str(event["actual"]),
                    str(event["main_direction"]),
                    float(event["main_entry_price"]),
                    float(event["main_stake"]),
                    float(event["main_shares"]),
                    float(event["main_pnl"]),
                    event.get("reversal_direction"),
                    event.get("reversal_entry_price"),
                    event.get("reversal_stake"),
                    event.get("reversal_shares"),
                    event.get("reversal_pnl"),
                    float(event["net_pnl"]),
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def cumulative_pnl(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Full cumulative curve plus the P&L per 100 settled trades."""
        epoch = self.metrics_epoch()
        with self.lock:
            rows = self.db.execute(
                """
                SELECT candle_id, net_pnl, main_pnl, reversal_pnl, main_stake,
                       reversal_stake
                FROM pnl_events WHERE candle_id >= ? ORDER BY candle_id
                """, (epoch,)
            ).fetchall()
        cumulative = 0.0
        curve: List[Dict[str, Any]] = []
        main_total = 0.0
        reversal_total = 0.0
        staked = 0.0
        wins = 0
        for row in rows:
            net = float(row["net_pnl"])
            cumulative += net
            main_total += float(row["main_pnl"] or 0.0)
            reversal_total += float(row["reversal_pnl"] or 0.0)
            staked += float(row["main_stake"] or 0.0) + float(row["reversal_stake"] or 0.0)
            if net > 0:
                wins += 1
            curve.append(
                {
                    "candle_id": int(row["candle_id"]),
                    "net_pnl": net,
                    "cumulative": cumulative,
                }
            )
        count = len(curve)
        return {
            "count": count,
            "cumulative_pnl": cumulative,
            "main_pnl": main_total,
            "reversal_pnl": reversal_total,
            "staked": staked,
            "return_on_stake": (cumulative / staked) if staked else None,
            "profitable_candles": wins,
            "pnl_per_100_trades": (
                cumulative / count * PNL_TRADE_BLOCK if count else None
            ),
            "curve": (curve if limit is None else curve[-int(limit):]),
        }

    def export_csv(self) -> bytes:
        """Every prediction with the complete state that produced it.

        The features were always stored but never exported, which made it
        impossible to ask why a call was made after the fact. Each row now
        carries the full input vector, the confidence breakdown and the timing,
        so any hypothesis about traps, wicks or volatility can be tested
        against real settled candles instead of argued from theory.
        """
        epoch = self.metrics_epoch()
        with self.lock:
            rows = self.db.execute(
                "WITH all_predictions AS ("
                "SELECT candle_id,kind,direction,ts_ms,price,probability_up,"
                "reason,actual,correct,features FROM predictions UNION ALL "
                "SELECT candle_id,kind,direction,ts_ms,price,probability_up,"
                "reason,actual,correct,features FROM ef_predictions UNION ALL "
                "SELECT candle_id,'EF_CANDIDATE' AS kind,direction,ts_ms,price,"
                "probability_up,COALESCE(abstain_reason,'') AS reason,actual,NULL AS correct,"
                "features FROM ef_candidates) "
                "SELECT p.*,t.quoted_price AS trade_quoted_price,"
                "t.fill_price AS trade_fill_price,t.shares AS trade_shares,"
                "t.attempts AS trade_attempts,t.filled AS trade_filled,"
                "t.delay_ms AS trade_delay_ms,t.market_id AS trade_market_id,"
                "t.order_status AS trade_order_status,t.order_id AS trade_order_id,"
                "t.order_hash AS trade_order_hash,t.forbidden AS trade_forbidden,"
                "t.fee_collateral AS trade_fee_collateral,"
                "t.fee_shares AS trade_fee_shares,"
                "t.stake AS trade_stake,t.pnl AS trade_pnl,"
                "t.state_x AS trade_state_x,"
                "t.state_x_active AS trade_state_x_active,"
                "t.state_x_trigger_time AS trade_state_x_trigger_time,"
                "t.state_x_end_time AS trade_state_x_end_time,"
                "t.sx_late_metric_15m AS trade_sx_late_metric_15m,"
                "t.sx_late_p80_6h AS trade_sx_late_p80_6h,"
                "t.sx_aligned_1s_metric_15m AS trade_sx_aligned_1s_metric_15m,"
                "t.sx_aligned_1s_p80_6h AS trade_sx_aligned_1s_p80_6h,"
                "t.sx_rejection_balance AS trade_sx_rejection_balance,"
                "t.sx_aligned_delta30_median_15m AS "
                "trade_sx_aligned_delta30_median_15m,"
                "t.sx_trigger_reason AS trade_sx_trigger_reason,"
                "t.financial_result AS trade_financial_result,"
                "t.financial_pnl AS trade_financial_pnl,"
                "t.financial_source AS trade_financial_source,"
                "t.financial_is_shadow AS trade_financial_is_shadow,"
                "t.execution_eligibility AS trade_execution_eligibility,"
                "t.execution_vwap AS trade_execution_vwap "
                "FROM all_predictions p LEFT JOIN trades t "
                "ON t.candle_id=p.candle_id AND t.kind=p.kind "
                "WHERE p.candle_id >= ? ORDER BY p.candle_id, p.kind", (epoch,)
            ).fetchall()
        base = [
            "candle_id", "kind", "direction", "timestamp_utc",
            "seconds_into_candle", "price", "candle_open", "lead_usd",
            "probability_up", "confidence", "book_quote", "live_fill_price",
            "shares", "attempts", "filled", "delay_ms", "predict_market_id",
            "order_status", "order_id", "order_hash", "forbidden",
            "fee_collateral", "fee_shares", "actual", "correct",
        ]
        factor_columns = [
            "blend", "f_volume", "f_rejection", "f_runway", "f_feasibility",
            "reject_up", "reject_down", "required_move", "expected_move",
            "sigma_per_root_second",
        ]
        state_x_columns = [
            "state_x", "state_x_active", "state_x_trigger_time",
            "state_x_end_time", "sx_late_metric_15m", "sx_late_p80_6h",
            "sx_aligned_1s_metric_15m", "sx_aligned_1s_p80_6h",
            "sx_rejection_balance", "sx_aligned_delta30_median_15m",
            "sx_trigger_reason",
        ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(base + factor_columns + list(MODEL_FEATURE_NAMES)
                        + list(EF_EXPORT_FIELDS)
                        + ["pressure_text", "pressure_score", "fair_p_up",
                           "volume_ratio", "upper_wick_ratio",
                           "lower_wick_ratio", "financial_result",
                           "financial_pnl", "financial_source",
                           "financial_is_shadow", "execution_eligibility",
                           "execution_vwap", "directional_correct",
                           "reason", "stake", "pnl"]
                        + state_x_columns)
        for row in rows:
            try:
                features = json.loads(row["features"] or "{}")
            except (TypeError, ValueError):
                features = {}
            candle_id = int(row["candle_id"])
            ts_ms = int(row["ts_ms"])
            seconds_in = round((ts_ms - candle_id) / 1000.0, 1)
            price = safe_float(row["price"], 0.0)
            candle_open = safe_float(features.get("candle_open"), 0.0)
            probability_up = safe_float(row["probability_up"], 0.5)
            record = [
                candle_id,
                row["kind"],
                row["direction"],
                london_stamp(ts_ms),
                seconds_in,
                price,
                candle_open or "",
                round(price - candle_open, 2) if candle_open else "",
                probability_up,
                round(abs(probability_up - 0.5) * 2.0, 4),
                row["trade_quoted_price"] if row["trade_quoted_price"] is not None else "",
                row["trade_fill_price"] if row["trade_fill_price"] is not None else "",
                row["trade_shares"] if row["trade_shares"] is not None else "",
                row["trade_attempts"] if row["trade_attempts"] is not None else "",
                row["trade_filled"] if row["trade_filled"] is not None else "",
                row["trade_delay_ms"] if row["trade_delay_ms"] is not None else "",
                row["trade_market_id"] or "",
                row["trade_order_status"] or "",
                row["trade_order_id"] or "",
                row["trade_order_hash"] or "",
                int(row["trade_forbidden"] or 0),
                (row["trade_fee_collateral"]
                 if row["trade_fee_collateral"] is not None else ""),
                (row["trade_fee_shares"]
                 if row["trade_fee_shares"] is not None else ""),
                row["actual"] or "",
                "" if row["correct"] is None else int(row["correct"]),
            ]
            for name in factor_columns:
                record.append(features.get(name, ""))
            for name in MODEL_FEATURE_NAMES:
                record.append(features.get(name, ""))
            for name in EF_EXPORT_FIELDS:
                record.append(features.get(name, ""))
            record.extend([
                features.get("pressure_text", ""),
                features.get("pressure_score", ""),
                features.get("fair_p_up", ""),
                features.get("volume_ratio", ""),
                features.get("upper_wick_ratio", ""),
                features.get("lower_wick_ratio", ""),
                row["trade_financial_result"] or "",
                (row["trade_financial_pnl"]
                 if row["trade_financial_pnl"] is not None else ""),
                row["trade_financial_source"] or "",
                int(row["trade_financial_is_shadow"] or 0),
                row["trade_execution_eligibility"] or "",
                (row["trade_execution_vwap"]
                 if row["trade_execution_vwap"] is not None else ""),
                "" if row["correct"] is None else int(row["correct"]),
                row["reason"],
                row["trade_stake"] if row["trade_stake"] is not None else "",
                row["trade_pnl"] if row["trade_pnl"] is not None else "",
            ])
            record.extend([
                str(row["trade_state_x"] or ""),
                int(row["trade_state_x_active"] or 0),
                (row["trade_state_x_trigger_time"]
                 if row["trade_state_x_trigger_time"] is not None else ""),
                (row["trade_state_x_end_time"]
                 if row["trade_state_x_end_time"] is not None else ""),
                (row["trade_sx_late_metric_15m"]
                 if row["trade_sx_late_metric_15m"] is not None else ""),
                (row["trade_sx_late_p80_6h"]
                 if row["trade_sx_late_p80_6h"] is not None else ""),
                (row["trade_sx_aligned_1s_metric_15m"]
                 if row["trade_sx_aligned_1s_metric_15m"] is not None else ""),
                (row["trade_sx_aligned_1s_p80_6h"]
                 if row["trade_sx_aligned_1s_p80_6h"] is not None else ""),
                (row["trade_sx_rejection_balance"]
                 if row["trade_sx_rejection_balance"] is not None else ""),
                (row["trade_sx_aligned_delta30_median_15m"]
                 if row["trade_sx_aligned_delta30_median_15m"] is not None
                 else ""),
                str(row["trade_sx_trigger_reason"] or ""),
            ])
            writer.writerow(record)
        return output.getvalue().encode("utf-8")

    @staticmethod
    def _prediction_from_row(row: sqlite3.Row) -> Prediction:
        return Prediction(
            candle_id=int(row["candle_id"]),
            kind=row["kind"],
            direction=row["direction"],
            ts_ms=int(row["ts_ms"]),
            price=float(row["price"]),
            probability_up=float(row["probability_up"]),
            reason=row["reason"],
            actual=row["actual"],
            correct=(bool(row["correct"]) if row["correct"] is not None else None),
            features=Store._features_from_row(row),
        )

    @staticmethod
    def _features_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            raw = row["features"]
        except (IndexError, KeyError):
            return {}
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


class PredictBook:
    """Current Predict.fun BTC 5m market and websocket-backed live book.

    The book is quoted for the Yes outcome, so the No side is the complement
    of the Yes bid, which is what the venue documents.
    """

    def __init__(self, testnet: Optional[bool] = None) -> None:
        self.api_key = os.environ.get("PREDICT_API_KEY", "").strip()
        configured_environment = os.environ.get(
            "PREDICT_BOOK_ENV", ""
        ).strip().lower()
        environment_aliases = {
            "mainnet": "mainnet", "production": "mainnet", "prod": "mainnet",
            "testnet": "testnet", "sandbox": "testnet", "test": "testnet",
        }
        if configured_environment and configured_environment not in environment_aliases:
            raise RuntimeError(
                "PREDICT_BOOK_ENV must be mainnet or testnet"
            )
        configured_environment = environment_aliases.get(
            configured_environment, configured_environment
        )
        forced_mainnet = os.environ.get(
            "PREDICT_USE_MAINNET", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        forced_testnet = os.environ.get(
            "PREDICT_USE_TESTNET", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if testnet is None:
            # v7 defaults to the real production market. Testnet can still be
            # selected for book diagnostics, but LiveExecutor refuses to arm.
            if configured_environment:
                testnet = configured_environment == "testnet"
            elif forced_mainnet and forced_testnet:
                raise RuntimeError(
                    "conflicting Predict.fun environment flags"
                )
            elif forced_testnet:
                testnet = True
            elif forced_mainnet:
                testnet = False
            else:
                testnet = False
        self.testnet = bool(testnet)
        self.environment = "testnet" if self.testnet else "mainnet"
        self.base = PREDICT_BASE_TESTNET if self.testnet else PREDICT_BASE_MAINNET
        self.book_scope = (
            "separate BNB Testnet sandbox book"
            if self.testnet
            else "production book shown in the predict.fun app"
        )
        self.market_id: Optional[Any] = None
        self.market_title = ""
        self.market_candle_id: Optional[int] = None
        self.decimal_precision = 4
        self.fee_rate = PREDICT_FEE_RATE
        self.market_checked_ms = 0
        self._candidates: List[Dict[str, Any]] = []
        self._current_market: Dict[str, Any] = {}
        self.book: Dict[str, Any] = {}
        self.book_ms = 0
        self.ws_connected = False
        self.wallet_ws_ready = False
        self.ws_last_message_ms = 0
        self.ws_reconnects = 0
        self.status = "starting"
        self.error = ""
        self.requests = 0
        self.server_rate_limit: Optional[int] = None
        self.server_rate_remaining: Optional[int] = None
        self.server_rate_reset_sec: Optional[int] = None
        self.rate_block_until = 0.0
        self._request_times: Deque[float] = deque()
        self._search_request_times: Deque[float] = deque()
        self._lock = threading.RLock()
        self._book_version = 0
        self._update_sink: Optional[Any] = None

    def set_update_sink(self, sink: Optional[Any]) -> None:
        """Register a non-blocking book-update notifier.

        The callback must do no book work itself; R6 uses it only to wake the
        dedicated EF hot-order container after a websocket ladder update.
        """
        with self._lock:
            self._update_sink = sink if callable(sink) else None

    def current_version(self) -> int:
        with self._lock:
            return int(self._book_version)

    def apply_ws_book(self, data: Dict[str, Any]) -> bool:
        """Atomically install an official ``predictOrderbook`` snapshot/update."""
        if not isinstance(data, dict):
            return False
        incoming_market = data.get("marketId")
        if incoming_market is not None and str(incoming_market) != str(self.market_id):
            return False
        asks, bids = data.get("asks"), data.get("bids")
        if not isinstance(asks, list) or not isinstance(bids, list):
            return False
        stamp = int(data.get("updateTimestampMs") or now_ms())
        sink = None
        version = 0
        with self._lock:
            # Ignore a late frame from an older snapshot.
            if stamp < self.book_ms:
                return False
            self.book = {"asks": asks, "bids": bids}
            self.book_ms = stamp
            self._book_version += 1
            version = int(self._book_version)
            sink = self._update_sink
            self.ws_last_message_ms = now_ms()
            self.status = "live websocket"
            self.error = ""
        if callable(sink):
            try:
                sink(version, stamp)
            except Exception:
                # A hot-order wakeup can never break the authoritative book.
                pass
        return True

    def set_ws_state(self, connected: bool, error: str = "") -> None:
        with self._lock:
            if connected and not self.ws_connected:
                self.ws_reconnects += 1
            self.ws_connected = bool(connected)
            if error:
                self.error = str(error)[:180]

    def reset_ws_session(self) -> None:
        """Require a fresh orderbook snapshot after every reconnect."""
        with self._lock:
            self.wallet_ws_ready = False
            self.ws_last_message_ms = 0
            self.book = {}
            self.book_ms = 0
            self.status = "awaiting websocket orderbook snapshot"

    def websocket_fresh(self) -> bool:
        with self._lock:
            return bool(
                self.ws_connected
                and self.ws_last_message_ms
                and now_ms() - self.ws_last_message_ms <= PREDICT_WS_STALE_MS
                and self.status == "live websocket"
                and self.book_ms
            )

    @staticmethod
    def _bool_field(item: Dict[str, Any], *names: str) -> bool:
        for name in names:
            if name in item:
                return bool(item.get(name))
        return False

    def market_contract(self, direction: str) -> Dict[str, Any]:
        """Return signing fields for UP/YES or DOWN/NO from market metadata."""
        with self._lock:
            item = dict(self._current_market)
            market_id = self.market_id
            fee_rate = self.fee_rate
        outcomes = item.get("outcomes") or item.get("marketOutcomes") or []
        wanted = {"UP", "YES"} if direction == "UP" else {"DOWN", "NO"}
        chosen: Optional[Dict[str, Any]] = None
        for outcome in outcomes if isinstance(outcomes, list) else []:
            if not isinstance(outcome, dict):
                continue
            label = str(
                outcome.get("name") or outcome.get("label")
                or outcome.get("title") or outcome.get("side") or ""
            ).strip().upper()
            if label in wanted:
                chosen = outcome
                break
        if chosen is None and isinstance(outcomes, list) and len(outcomes) >= 2:
            chosen = outcomes[0 if direction == "UP" else 1]
        token_id = None if chosen is None else (
            chosen.get("onChainId") or chosen.get("tokenId")
            or chosen.get("id")
        )
        if token_id is None:
            raise RuntimeError(f"market {market_id} has no {direction} token id")
        return {
            "token_id": str(token_id),
            "is_neg_risk": self._bool_field(item, "isNegRisk", "is_neg_risk"),
            "is_yield_bearing": self._bool_field(
                item, "isYieldBearing", "is_yield_bearing"),
            "fee_rate_bps": int(round(fee_rate * 10_000.0)),
        }

    def sdk_book_data(self, direction: str) -> Dict[str, Any]:
        """Return the token-side ladder expected by the official SDK."""
        snap = self.ladder_snapshot()
        if not self.websocket_fresh():
            raise RuntimeError("Predict.fun websocket session is stale")
        if direction == "UP":
            asks, bids = snap["asks"], snap["bids"]
        elif direction == "DOWN":
            # The API book is YES-centric. Complement it into a NO book.
            asks = sorted([[round(1.0 - p, 8), q] for p, q in snap["bids"]])
            bids = sorted(
                [[round(1.0 - p, 8), q] for p, q in snap["asks"]],
                reverse=True,
            )
        else:
            raise ValueError(f"unknown direction: {direction}")
        return {
            "market_id": int(self.market_id),
            "update_timestamp_ms": int(snap["book_ms"]),
            "book_version": int(snap.get("book_version") or 0),
            "asks": [tuple(level) for level in asks],
            "bids": [tuple(level) for level in bids],
        }

    @staticmethod
    def _positive_header_int(headers: Any, name: str) -> Optional[int]:
        try:
            value = int(str(headers.get(name, "")).strip())
        except (AttributeError, TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def _capture_rate_headers(self, headers: Any) -> None:
        limit = self._positive_header_int(headers, "RateLimit-Limit")
        remaining = self._positive_header_int(headers, "RateLimit-Remaining")
        reset = self._positive_header_int(headers, "RateLimit-Reset")
        with self._lock:
            if limit is not None:
                self.server_rate_limit = limit
            if remaining is not None:
                self.server_rate_remaining = remaining
            if reset is not None:
                self.server_rate_reset_sec = reset
            if remaining == 0:
                # Honour the venue's reset window without hammering it from
                # the discovery loop. Cap malformed epoch-style values.
                cooldown = max(1, min(300, int(reset or 60)))
                self.rate_block_until = max(
                    self.rate_block_until, time.monotonic() + cooldown
                )

    def effective_local_limit(self) -> int:
        """Use 75% of the lowest limit the venue has advertised."""
        with self._lock:
            advertised = self.server_rate_limit
            if advertised is None or advertised <= 0:
                return PREDICT_LOCAL_LIMIT_RPM
            return min(
                PREDICT_LOCAL_LIMIT_RPM,
                max(1, int(advertised * 0.75)),
            )

    def rate_cooldown_seconds(self) -> int:
        with self._lock:
            return max(0, int(math.ceil(
                self.rate_block_until - time.monotonic()
            )))

    @staticmethod
    def _prune_window(times: Deque[float], current: float) -> None:
        cutoff = current - 60.0
        while times and times[0] <= cutoff:
            times.popleft()

    def _reserve_request(self, path: str) -> None:
        current = time.monotonic()
        with self._lock:
            self._prune_window(self._request_times, current)
            self._prune_window(self._search_request_times, current)
            if current < self.rate_block_until:
                raise RuntimeError(
                    "Predict.fun API cooldown active for "
                    f"{self.rate_cooldown_seconds()}s"
                )
            local_limit = self.effective_local_limit()
            if len(self._request_times) >= local_limit:
                raise RuntimeError(
                    "Predict.fun local rate guard reached "
                    f"({local_limit}/min)"
                )
            if (
                path == "/v1/search"
                and len(self._search_request_times)
                >= PREDICT_LOCAL_SEARCH_LIMIT_RPM
            ):
                raise RuntimeError(
                    "Predict.fun search rate guard reached "
                    f"({PREDICT_LOCAL_SEARCH_LIMIT_RPM}/min)"
                )
            self._request_times.append(current)
            if path == "/v1/search":
                self._search_request_times.append(current)
            self.requests += 1

    def _requests_last_minute(self) -> int:
        current = time.monotonic()
        with self._lock:
            self._prune_window(self._request_times, current)
            return len(self._request_times)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.testnet and not self.api_key:
            raise RuntimeError(
                "production Predict.fun book requires PREDICT_API_KEY; "
                "testnet is a different sandbox book"
            )
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Accept": "application/json", "User-Agent": f"btc-model/{VERSION}"}
        # Testnet does not need a key. Do not send a stale mainnet credential to
        # it even if PREDICT_API_KEY is still exported in the Termux shell.
        if self.api_key and not self.testnet:
            headers["x-api-key"] = self.api_key
        self._reserve_request(path)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=PREDICT_TIMEOUT) as response:
                self._capture_rate_headers(response.headers)
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self._capture_rate_headers(exc.headers)
            if exc.code == 429:
                reset = self.server_rate_reset_sec
                detail = f"; reset in {reset}s" if reset is not None else ""
                raise RuntimeError(
                    "Predict.fun rate limit reached" + detail
                ) from exc
            if exc.code in (401, 403):
                if self.testnet:
                    raise RuntimeError(
                        "Predict.fun testnet rejected an unauthenticated request"
                    ) from exc
                raise RuntimeError(
                    "Predict.fun mainnet rejected PREDICT_API_KEY"
                ) from exc
            raise

    @staticmethod
    def _parse_time_ms(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            number = float(value)
            return int(number if number > 10_000_000_000 else number * 1000.0)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000.0)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _flatten_markets(payload: Any) -> List[Dict[str, Any]]:
        """Accept both /v1/search and /v1/markets response shapes."""
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", payload)
        items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            direct = data.get("markets") or data.get("items") or []
            if isinstance(direct, list):
                items.extend(item for item in direct if isinstance(item, dict))
            categories = data.get("categories") or []
            if isinstance(categories, list):
                for category in categories:
                    if not isinstance(category, dict):
                        continue
                    for market in category.get("markets") or []:
                        if not isinstance(market, dict):
                            continue
                        enriched = dict(market)
                        enriched["_category_title"] = category.get("title")
                        enriched["_category_slug"] = category.get("slug")
                        enriched["_category_starts_at"] = category.get("startsAt")
                        enriched["_category_ends_at"] = category.get("endsAt")
                        enriched["_category_variant_data"] = category.get("variantData")
                        items.append(enriched)
        top_level = payload.get("markets") or []
        if isinstance(top_level, list):
            items.extend(item for item in top_level if isinstance(item, dict))
        unique: Dict[str, Dict[str, Any]] = {}
        for item in items:
            market_id = item.get("id") if item.get("id") is not None else item.get("marketId")
            if market_id is not None:
                unique[str(market_id)] = item
        return list(unique.values())

    @classmethod
    def _rank_markets(
        cls, items: Iterable[Dict[str, Any]], candle_id: int
    ) -> List[Dict[str, Any]]:
        expected_epoch = str(int(candle_id // 1000))
        ranked: List[Tuple[int, int, Dict[str, Any]]] = []

        clock_range = re.compile(
            r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*"
            r"[-\u2013\u2014]\s*"
            r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\b",
            re.IGNORECASE,
        )

        def title_duration_minutes(text: str) -> Optional[int]:
            match = clock_range.search(str(text or ""))
            if not match:
                return None

            def minute_of_day(
                hour: str, minute: Optional[str], suffix: str
            ) -> Optional[int]:
                try:
                    h = int(hour)
                    m = int(minute or 0)
                except (TypeError, ValueError):
                    return None
                if not 1 <= h <= 12 or not 0 <= m <= 59:
                    return None
                h = h % 12
                if suffix.upper() == "PM":
                    h += 12
                return h * 60 + m

            start = minute_of_day(
                match.group(1), match.group(2), match.group(3)
            )
            end = minute_of_day(
                match.group(4), match.group(5), match.group(6)
            )
            if start is None or end is None:
                return None
            duration = (end - start) % (24 * 60)
            return 24 * 60 if duration == 0 else duration

        for item in items:
            variant = (
                item.get("variantData")
                or item.get("_category_variant_data")
                or {}
            )

            own_blob = " ".join(
                str(item.get(key, ""))
                for key in (
                    "title", "slug", "name", "question", "description",
                    "categorySlug",
                )
            ) + " " + str(variant.get("priceFeedSymbol", ""))
            own_blob = own_blob.lower()

            combined_blob = (
                own_blob
                + " "
                + " ".join(
                    str(item.get(key, ""))
                    for key in ("_category_title", "_category_slug")
                ).lower()
            )

            btc = "btc" in combined_blob or "bitcoin" in combined_blob
            if not btc:
                continue

            own_start_ms = cls._parse_time_ms(item.get("startsAt"))
            own_end_ms = cls._parse_time_ms(item.get("endsAt"))
            parent_start_ms = cls._parse_time_ms(
                item.get("_category_starts_at")
            )
            parent_end_ms = cls._parse_time_ms(
                item.get("_category_ends_at")
            )

            own_duration_ms = (
                own_end_ms - own_start_ms
                if own_start_ms is not None and own_end_ms is not None
                else None
            )
            parent_duration_ms = (
                parent_end_ms - parent_start_ms
                if parent_start_ms is not None and parent_end_ms is not None
                else None
            )

            title_text = str(
                item.get("title")
                or item.get("question")
                or item.get("name")
                or ""
            )
            title_minutes = title_duration_minutes(title_text)

            isolated_five_minute = bool(re.search(
                r"(?<!\d)5\s*(?:m\b|[-_ ]?min(?:ute)?s?\b)",
                own_blob,
            ))
            explicit_other_minute = bool(re.search(
                r"(?<!\d)(?:10|15|20|30|45|60)\s*"
                r"(?:m\b|[-_ ]?min(?:ute)?s?\b)",
                own_blob,
            ))

            # Child-owned evidence only decides duration.
            if own_duration_ms is not None:
                five_minute = own_duration_ms == CANDLE_MS
            elif title_minutes is not None:
                five_minute = title_minutes == 5
            elif explicit_other_minute:
                five_minute = False
            else:
                five_minute = isolated_five_minute

            if not five_minute:
                continue

            trading = str(item.get("tradingStatus") or "").upper()
            status = str(item.get("status") or "").upper()
            if trading and trading != "OPEN":
                continue
            if status in {"CLOSED", "RESOLVED", "CANCELLED", "INVALID"}:
                continue
            if item.get("isVisible") is False:
                continue

            own_epoch_match = expected_epoch in own_blob
            parent_epoch_match = expected_epoch in combined_blob
            own_window_match = bool(
                own_start_ms is not None
                and own_end_ms is not None
                and own_start_ms <= candle_id < own_end_ms
                and own_duration_ms == CANDLE_MS
            )
            parent_window_match = bool(
                parent_start_ms is not None
                and parent_end_ms is not None
                and parent_start_ms <= candle_id < parent_end_ms
                and parent_duration_ms == CANDLE_MS
            )

            exact_candle = (
                own_epoch_match
                or own_window_match
                or parent_window_match
                or (parent_epoch_match and parent_window_match)
            )
            if not exact_candle:
                continue

            score = 0
            if own_epoch_match:
                score += 1100
            elif parent_epoch_match:
                score += 900
            if own_window_match:
                score += 1000
            elif parent_window_match:
                score += 700
            if own_duration_ms == CANDLE_MS:
                score += 300
            elif title_minutes == 5:
                score += 250
            elif isolated_five_minute:
                score += 150
            if trading == "OPEN":
                score += 250
            if status in {"OPEN", "REGISTERED", "ACTIVE", ""}:
                score += 100
            if str(variant.get("type", "")).upper() == "CRYPTO_UP_DOWN":
                score += 80

            created = cls._parse_time_ms(item.get("createdAt")) or 0
            ranked.append((score, created, item))

        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in ranked]

    def _select_market(self, item: Dict[str, Any], candle_id: int) -> None:
        market_id = item.get("id") if item.get("id") is not None else item.get("marketId")
        market_title = str(
            item.get("title") or item.get("question") or item.get("categorySlug")
            or item.get("_category_title") or f"market {market_id}"
        )[:90]
        raw_precision = item.get("decimalPrecision")
        decimal_precision = max(
            0, min(8, int(4 if raw_precision is None else raw_precision))
        )
        fee_bps = safe_float(item.get("feeRateBps"), PREDICT_FEE_RATE * 10_000.0)
        fee_rate = clamp(fee_bps / 10_000.0, 0.0, 0.25)
        with self._lock:
            changed = str(market_id) != str(self.market_id)
            self.market_id = market_id
            self.market_title = market_title
            self.market_candle_id = int(candle_id)
            self.decimal_precision = decimal_precision
            self.fee_rate = fee_rate
            self._current_market = dict(item)
            if changed:
                self.book = {}
                self.book_ms = 0

    def find_market(self, candle_id: Optional[int] = None) -> List[Dict[str, Any]]:
        candle_id = int(candle_id if candle_id is not None else candle_id_from_ms(now_ms()))
        errors: List[str] = []
        candidates: List[Dict[str, Any]] = []
        market_items: List[Dict[str, Any]] = []

        # Testnet search can be temporarily unavailable even while the market
        # and order-book APIs are healthy. Prefer the typed market listing and
        # follow its cursor only until the exact current candle is found.
        try:
            after: Optional[str] = None
            for _page in range(PREDICT_MARKET_MAX_PAGES):
                params: Dict[str, Any] = {
                    "first": PREDICT_SEARCH_LIMIT,
                    "status": "OPEN",
                    "marketVariant": "CRYPTO_UP_DOWN",
                }
                if after:
                    params["after"] = after
                payload = self._get("/v1/markets", params)
                market_items.extend(self._flatten_markets(payload))
                candidates = self._rank_markets(market_items, candle_id)
                if candidates:
                    break
                raw_cursor = payload.get("cursor") if isinstance(payload, dict) else None
                if not raw_cursor:
                    break
                after = str(raw_cursor)
        except Exception as exc:
            errors.append(f"markets: {exc}")

        # Search is a compatibility fallback. Its documented 50 RPM limit has
        # a separate local guard, and it is never needed on the healthy path.
        if not candidates:
            try:
                payload = self._get(
                    "/v1/search",
                    {
                        "query": "BTC Up or Down 5m",
                        "includeResolved": "false",
                        "limit": PREDICT_SEARCH_LIMIT,
                    },
                )
                candidates = self._rank_markets(
                    self._flatten_markets(payload), candle_id
                )
            except Exception as exc:
                errors.append(f"search: {exc}")
        self._candidates = candidates
        if not candidates:
            if (
                self.market_id is not None
                and self.market_candle_id == candle_id
                and self.websocket_fresh()
            ):
                # A transient discovery failure must not discard a healthy
                # subscribed market that is still the exact current candle.
                self.error = ("; ".join(errors) or "market refresh empty")[-180:]
                return [dict(self._current_market)]
            self.market_id = None
            self.market_title = ""
            self.market_candle_id = candle_id
            self.status = "no current BTC 5m market"
            self.error = "; ".join(errors)[-180:]
            return []
        same_live_market = (
            str(candidates[0].get("id") if candidates[0].get("id") is not None
                else candidates[0].get("marketId")) == str(self.market_id)
            and self.websocket_fresh()
        )
        self._select_market(candidates[0], candle_id)
        if not same_live_market:
            self.status = "market found"
        self.error = ""
        return candidates

    def refresh(self, candle_id: Optional[int] = None) -> None:
        current_candle = int(
            candle_id if candle_id is not None else candle_id_from_ms(now_ms())
        )
        if not self.testnet and not self.api_key:
            self.market_id = None
            self.market_title = ""
            self.market_candle_id = current_candle
            self.status = "mainnet data key required"
            self.error = (
                "set PREDICT_API_KEY to read the production app book; "
                "live execution remains locked"
            )
            return
        now = now_ms()
        if (
            self.market_id is None
            and self.market_candle_id == current_candle
            and self.market_checked_ms
            and now - self.market_checked_ms < PREDICT_REDISCOVER_SEC * 1000
        ):
            return
        discovery = (
            self.market_id is None
            or self.market_candle_id != current_candle
            or now - self.market_checked_ms > PREDICT_MARKET_REFRESH_SEC * 1000
        )
        if discovery:
            self.market_checked_ms = now
            candidates = self.find_market(current_candle)
        else:
            # WebSocket owns book freshness. REST is only discovery plus one
            # bootstrap snapshot per market, saving almost all request budget.
            return
        if not candidates:
            return
        with self._lock:
            have_current_book = bool(
                self.book_ms and self.market_candle_id == current_candle
            )
            if have_current_book and self.websocket_fresh():
                self.status = "live websocket"
                return
            # REST supplies one bootstrap only. It never polls an existing
            # ladder; subsequent price changes come from predictOrderbook.
            if have_current_book:
                return

        empty_book: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
        failures: List[str] = []
        # A stale first match caused v5.4's repeated 404. Probe ranked, open
        # candidates and retain the first current market that actually has a book.
        for item in candidates[:12]:
            self._select_market(item, current_candle)
            try:
                payload = self._get(f"/v1/markets/{self.market_id}/orderbook")
            except urllib.error.HTTPError as exc:
                failures.append(f"{self.market_id}: HTTP {exc.code}")
                if exc.code == 404:
                    continue
                self.status = "book unreachable"
                self.error = f"book: HTTP {exc.code}"[:180]
                return
            except Exception as exc:
                self.status = "book unreachable"
                self.error = f"book: {exc}"[:180]
                return
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                data = payload if isinstance(payload, dict) else {}
            asks = data.get("asks") or []
            bids = data.get("bids") or []
            if not asks and not bids:
                if empty_book is None:
                    empty_book = (item, data)
                continue
            update_ms = int(data.get("updateTimestampMs") or now_ms())
            with self._lock:
                self.book = {"asks": asks, "bids": bids}
                self.book_ms = update_ms
                self.status = "live"
                self.error = ""
            return

        if empty_book is not None:
            item, data = empty_book
            self._select_market(item, current_candle)
            with self._lock:
                self.book = {"asks": [], "bids": []}
                self.book_ms = int(data.get("updateTimestampMs") or now_ms())
                if self.testnet:
                    self.status = "testnet sandbox book empty"
                    self.error = (
                        "testnet is separate from the predict.fun app and "
                        "does not mirror its liquidity"
                    )
                else:
                    self.status = "mainnet book empty"
                    self.error = "current production market has no liquidity"
            return
        self.market_id = None
        self.status = "no live order book"
        self.error = ("; ".join(failures) or "no ranked market returned a book")[-180:]

    def ladder_snapshot(self) -> Dict[str, Any]:
        """Full Predict.fun book with its age for SDK order construction.

        Both sides are retained at every level so the official SDK can walk
        the live ladder at the requested dollar stake before signing.
        """
        with self._lock:
            asks = list(self.book.get("asks") or [])
            bids = list(self.book.get("bids") or [])
            book_ms = self.book_ms
            book_version = int(self._book_version)
            status = self.status
            market_id = self.market_id
            fee_rate = self.fee_rate
        age = max(0, now_ms() - book_ms) if book_ms else None

        def ladder(rows: Iterable[Any]) -> List[List[float]]:
            out: List[List[float]] = []
            for row in rows:
                try:
                    price, size = float(row[0]), float(row[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if 0.0 <= price <= 1.0 and size > 0.0:
                    out.append([price, size])
            return out

        return {
            "status": status,
            "book_age_ms": age,
            "book_ms": book_ms,
            "book_version": book_version,
            "market_id": market_id,
            "fee_rate": fee_rate,
            "asks": ladder(asks),
            "bids": ladder(bids),
        }

    def quote(self, direction: str) -> Dict[str, Any]:
        """What buying `direction` would cost right now."""
        with self._lock:
            asks = list(self.book.get("asks") or [])
            bids = list(self.book.get("bids") or [])
            age = max(0, now_ms() - self.book_ms) if self.book_ms else None
            precision = self.decimal_precision
            fee_rate = self.fee_rate
            market_id = self.market_id
            market_title = self.market_title
            session_fresh = bool(
                self.ws_connected
                and self.ws_last_message_ms
                and now_ms() - self.ws_last_message_ms <= PREDICT_WS_STALE_MS
                and self.status == "live websocket"
                and self.book_ms
            )
        if age is None or not session_fresh:
            return {"price": None, "size": None, "spread": None,
                    "age_ms": age, "source": "stale websocket session",
                    "break_even": None, "market_id": market_id,
                    "market_title": market_title, "fee_rate": fee_rate}

        def levels(rows: Iterable[Any]) -> List[Tuple[float, float]]:
            out: List[Tuple[float, float]] = []
            for row in rows:
                try:
                    price, size = float(row[0]), float(row[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if 0.0 <= price <= 1.0 and size > 0.0:
                    out.append((price, size))
            return out

        clean_asks = levels(asks)
        clean_bids = levels(bids)
        best_ask = min(clean_asks, default=(None, None), key=lambda level: level[0])
        best_bid = max(clean_bids, default=(None, None), key=lambda level: level[0])
        ask_price, ask_size = best_ask
        bid_price, bid_size = best_bid
        # UP lifts the Yes ask. DOWN is the No side, which is one minus the
        # Yes bid: selling Yes at the bid is the same trade as buying No.
        if direction == "UP":
            price, size = ask_price, ask_size
        elif direction == "DOWN":
            price = None if bid_price is None else round(1.0 - bid_price, precision)
            size = bid_size
        else:
            raise ValueError(f"unknown Predict.fun direction: {direction}")
        spread = (
            None if ask_price is None or bid_price is None
            else round(ask_price - bid_price, precision)
        )
        if price is None or size is None:
            return {"price": None, "size": None, "spread": spread,
                    "age_ms": age, "source": self.status, "break_even": None,
                    "market_id": market_id, "market_title": market_title,
                    "fee_rate": fee_rate}
        price = round(float(price), precision)
        return {
            "price": price,
            "size": round(size, 2),
            "spread": spread,
            "age_ms": age,
            "source": self.status,
            "break_even": round(price / max(1.0 - fee_rate, 1e-9), 4),
            "market_id": market_id,
            "market_title": market_title,
            "fee_rate": fee_rate,
        }

    def executable_vwap(self, direction: str, stake_usd: float) -> Dict[str, Any]:
        """Walk the fresh websocket ladder and return executable BUY VWAP.

        This is an execution-only check. EF direction/quality is already final
        before this method is called. No minimum share price is imposed.
        """
        snap = self.ladder_snapshot()
        if snap.get("book_age_ms") is None or not self.websocket_fresh():
            return {"ok": False, "vwap": None, "max_price": None, "shares": 0.0,
                    "reason": "NO_FRESH_BOOK", "book_age_ms": snap.get("book_age_ms")}
        if str(direction).upper() == "UP":
            levels = [(float(p), float(q)) for p, q in snap.get("asks", [])]
        elif str(direction).upper() == "DOWN":
            levels = [(round(1.0 - float(p), self.decimal_precision), float(q))
                      for p, q in snap.get("bids", [])]
        else:
            raise ValueError(f"unknown Predict.fun direction: {direction}")
        levels = sorted((p, q) for p, q in levels if 0.0 < p <= 1.0 and q > 0.0)
        remaining = max(0.0, float(stake_usd))
        if remaining <= 0.0:
            return {"ok": False, "vwap": None, "max_price": None, "shares": 0.0,
                    "reason": "NO_STAKE", "book_age_ms": snap.get("book_age_ms")}
        spent = shares = 0.0
        worst = None
        for price, qty in levels:
            capacity = price * qty
            take_value = min(remaining, capacity)
            if take_value <= 0.0:
                continue
            take_shares = take_value / price
            spent += take_value
            shares += take_shares
            remaining -= take_value
            worst = price
            if remaining <= PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD:
                remaining = 0.0
                break
        if remaining > PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD or shares <= 0.0:
            return {"ok": False, "vwap": (spent / shares if shares else None),
                    "max_price": worst, "shares": shares, "reason": "NO_LIQUIDITY",
                    "book_age_ms": snap.get("book_age_ms")}
        return {"ok": True, "vwap": spent / shares, "max_price": worst,
                "shares": shares, "reason": "ELIGIBLE",
                "book_age_ms": snap.get("book_age_ms")}

    def snapshot(self) -> Dict[str, Any]:
        documented_limit = (
            PREDICT_TESTNET_LIMIT_RPM
            if self.testnet else PREDICT_MAINNET_LIMIT_RPM
        )
        return {
            "status": self.status,
            "error": self.error,
            "market": self.market_title,
            "market_id": self.market_id,
            "environment": self.environment,
            "book_scope": self.book_scope,
            "execution": "LIVE" if not self.testnet else "LOCKED_TESTNET",
            "transport": "websocket",
            "ws_connected": self.ws_connected,
            "wallet_ws_ready": self.wallet_ws_ready,
            "ws_last_message_age_ms": (
                max(0, now_ms() - self.ws_last_message_ms)
                if self.ws_last_message_ms else None
            ),
            "ws_reconnects": self.ws_reconnects,
            "api_key_required": not self.testnet,
            "api_key_configured": bool(self.api_key) and not self.testnet,
            "stored_key_ignored": bool(self.api_key) and self.testnet,
            "candle_id": self.market_candle_id,
            "decimal_precision": self.decimal_precision,
            "fee_rate": self.fee_rate,
            "age_ms": max(0, now_ms() - self.book_ms) if self.book_ms else None,
            "requests": self.requests,
            "requests_last_minute": self._requests_last_minute(),
            "local_rate_guard_rpm": self.effective_local_limit(),
            "rate_cooldown_seconds": self.rate_cooldown_seconds(),
            "documented_limit_rpm": documented_limit,
            "documented_testnet_limit_rpm": PREDICT_TESTNET_LIMIT_RPM,
            "server_rate_limit": self.server_rate_limit,
            "server_rate_remaining": self.server_rate_remaining,
            "server_rate_reset_sec": self.server_rate_reset_sec,
            "up": self.quote("UP"),
            "down": self.quote("DOWN"),
        }


class PredictWebSocket(threading.Thread):
    """Official Predict.fun orderbook + wallet-event socket."""

    def __init__(
        self,
        book: PredictBook,
        stop: threading.Event,
        wallet_event: Optional[Any] = None,
        auth: Optional["PredictAuthSession"] = None,
    ) -> None:
        super().__init__(name="predict-ws", daemon=True)
        self.book = book
        self.stop_event = stop
        self.wallet_event = wallet_event
        self.auth = auth
        self._app: Any = None
        self._send_lock = threading.Lock()
        self._subscription_lock = threading.RLock()
        self._request_id = 0
        self._subscribed_market = ""
        self._wallet_subscribed = False
        self._wallet_token = ""
        self._wallet_generation = 0
        self._pending_requests: Dict[int, Tuple[str, str]] = {}
        self._opened_ms = 0

    def _send(self, payload: Dict[str, Any]) -> bool:
        app = self._app
        if app is None or not self.book.ws_connected:
            return False
        try:
            with self._send_lock:
                app.send(json.dumps(payload, separators=(",", ":")))
            return True
        except Exception as exc:
            self.book.set_ws_state(False, f"websocket send: {exc}")
            return False

    def _subscribe(self, topic: str) -> bool:
        self._request_id += 1
        request_id = self._request_id
        sent = self._send({
            "method": "subscribe",
            "requestId": request_id,
            "params": [topic],
        })
        if sent:
            self._pending_requests[request_id] = ("subscribe", topic)
        return sent

    def _unsubscribe(self, topic: str) -> bool:
        self._request_id += 1
        request_id = self._request_id
        sent = self._send({
            "method": "unsubscribe",
            "requestId": request_id,
            "params": [topic],
        })
        if sent:
            self._pending_requests[request_id] = ("unsubscribe", topic)
        return sent

    def ensure_subscriptions(self) -> None:
        with self._subscription_lock:
            market_id = self.book.market_id
            if market_id is not None and str(market_id) != self._subscribed_market:
                if self._subscribed_market:
                    self._unsubscribe(f"predictOrderbook/{self._subscribed_market}")
                if self._subscribe(f"predictOrderbook/{market_id}"):
                    self._subscribed_market = str(market_id)
            if self.auth is not None:
                token, generation = self.auth.token_and_generation()
            else:
                # An unauthenticated instance may still display the public
                # orderbook, but it can never claim wallet readiness.
                token, generation = "", 0
            if self._wallet_subscribed and (
                not token or generation != self._wallet_generation
                or token != self._wallet_token
            ):
                # Do not unsubscribe a secret-bearing old topic on a live socket.
                # A clean reconnect gives the renewed JWT one unambiguous session.
                self.book.wallet_ws_ready = False
                self.book.set_ws_state(
                    False, "authenticated session changed; reconnecting"
                )
                self.close()
                return
            if token and not self._wallet_subscribed:
                # Never log this topic: it contains the wallet JWT.
                if self._subscribe(f"predictWalletEvents/{token}"):
                    self._wallet_subscribed = True
                    self._wallet_token = token
                    self._wallet_generation = generation

    def _on_open(self, _app: Any) -> None:
        self.book.set_ws_state(True)
        self.book.reset_ws_session()
        self._opened_ms = now_ms()
        with self._subscription_lock:
            self._subscribed_market = ""
            self._wallet_subscribed = False
            self._wallet_token = ""
            self._wallet_generation = 0
            self._pending_requests.clear()
            self.ensure_subscriptions()

    def _on_message(self, _app: Any, raw: str) -> None:
        if _app is not self._app:
            return
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(frame, dict):
            return
        with self.book._lock:
            self.book.ws_last_message_ms = now_ms()
        if frame.get("type") == "R":
            try:
                request_id = int(frame.get("requestId"))
            except (TypeError, ValueError):
                request_id = -1
            with self._subscription_lock:
                method, topic = self._pending_requests.pop(
                    request_id, ("", "")
                )
                success = bool(frame.get("success", False))
                if topic.startswith("predictWalletEvents/"):
                    self.book.wallet_ws_ready = success and method == "subscribe"
                    if method == "subscribe" and not success:
                        self._wallet_subscribed = False
                        if self.auth is not None:
                            self.auth.invalidate(
                                "wallet WebSocket subscription rejected"
                            )
                            self.close()
                elif (topic.startswith("predictOrderbook/")
                      and method == "subscribe" and not success):
                    if topic.rsplit("/", 1)[-1] == self._subscribed_market:
                        self._subscribed_market = ""
            if not success:
                error = frame.get("error") or {}
                self.book.error = (
                    f"websocket subscription: {error.get('code') or 'failed'}"
                )[:180]
            return
        if frame.get("type") != "M":
            return
        topic = str(frame.get("topic") or "")
        data = frame.get("data")
        if topic == "heartbeat":
            self._send({"method": "heartbeat", "data": data})
        elif topic.startswith("predictOrderbook/") and isinstance(data, dict):
            self.book.apply_ws_book(data)
        elif topic.startswith("predictWalletEvents/") and isinstance(data, dict):
            if self.wallet_event is not None:
                self.wallet_event(data)

    def _on_error(self, _app: Any, error: Any) -> None:
        if _app is not self._app:
            return
        self.book.wallet_ws_ready = False
        self.book.set_ws_state(False, f"websocket: {error}")

    def _on_close(
        self, _app: Any, _code: Any = None, _reason: Any = None
    ) -> None:
        if _app is not self._app:
            return
        self._opened_ms = 0
        self.book.wallet_ws_ready = False
        self.book.set_ws_state(False, "websocket disconnected")

    def _watch_stale_session(self, app: Any) -> None:
        """Close a half-open socket after two missed venue heartbeats."""
        while app is self._app and not self.stop_event.wait(0.5):
            with self.book._lock:
                connected = self.book.ws_connected
                last_message = self.book.ws_last_message_ms
            reference = last_message or self._opened_ms
            if self.auth is not None and self._wallet_subscribed:
                token, generation = self.auth.token_and_generation()
                if (
                    not token or generation != self._wallet_generation
                    or token != self._wallet_token
                ):
                    self.book.wallet_ws_ready = False
                    self.book.set_ws_state(
                        False, "authenticated session renewed; reconnecting"
                    )
                    try:
                        app.close()
                    except Exception:
                        pass
                    return
            if (
                connected and reference
                and now_ms() - reference > PREDICT_WS_RECONNECT_MS
            ):
                self.book.set_ws_state(
                    False, "websocket heartbeat stale; reconnecting"
                )
                try:
                    app.close()
                except Exception:
                    pass
                return

    def close(self) -> None:
        try:
            if self._app is not None:
                self._app.close()
        except Exception:
            pass

    def run(self) -> None:
        try:
            import websocket
        except Exception:
            self.book.set_ws_state(
                False, "install websocket-client for Predict.fun live book"
            )
            return
        backoff = 0.5
        while not self.stop_event.is_set():
            if not self.book.api_key:
                self.book.set_ws_state(False, "PREDICT_API_KEY is required")
                self.stop_event.wait(2.0)
                continue
            try:
                session_started = time.monotonic()
                self._app = websocket.WebSocketApp(
                    PREDICT_WS_URL,
                    header=[f"x-api-key: {self.book.api_key}"],
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                threading.Thread(
                    target=self._watch_stale_session,
                    args=(self._app,),
                    name="predict-ws-watchdog",
                    daemon=True,
                ).start()
                self._app.run_forever(ping_interval=0)
                if time.monotonic() - session_started > 30.0:
                    backoff = 0.5
            except Exception as exc:
                self.book.set_ws_state(False, f"websocket: {exc}")
            if self.stop_event.is_set():
                break
            self.stop_event.wait(backoff)
            backoff = min(8.0, backoff * 1.7)


def _camel_key(name: str) -> str:
    head, *tail = str(name).split("_")
    return head + "".join(piece[:1].upper() + piece[1:] for piece in tail)


def _plain_json(value: Any) -> Any:
    """Convert SDK dataclasses/enums into the API's camelCase JSON shape."""
    # Predict SDK Side and SignatureType are IntEnum. IntEnum instances expose
    # __dict__, so the old generic-object branch turned BUY/EOA into {}.
    # Preserve their integer wire representation before inspecting __dict__.
    if isinstance(value, int) and hasattr(value, "value"):
        return int(value)
    if is_dataclass(value):
        value = asdict(value)
    elif hasattr(value, "model_dump"):
        value = value.model_dump()
    elif hasattr(value, "dict") and callable(value.dict):
        value = value.dict()
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        value = {
            key: item for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    if isinstance(value, dict):
        return {_camel_key(str(k)): _plain_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class PredictAuthSession:
    """Renewable, verified Predict.fun JWT shared by REST and WebSocket.

    A supplied ``PREDICT_JWT`` is accepted only after ``/v1/account`` confirms
    that it belongs to ``PREDICT_ACCOUNT_ADDRESS``. Missing, rejected, or
    expiring tokens are renewed from the venue's dynamic message. Secrets are
    never persisted or included in status strings.
    """

    def __init__(
        self, book: PredictBook, api_key: str, signer_address: str,
        builder: Any,
    ) -> None:
        self.book = book
        self.api_key = str(api_key or "").strip()
        self.signer_address = str(signer_address or "").strip()
        self.builder = builder
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._token = os.getenv("PREDICT_JWT", "").strip()
        self._generation = 1 if self._token else 0
        self._claims = self._decode_claims(self._token)
        self._verified = False
        self._invalidated = False
        self._last_verified_ms = 0
        self._last_refresh_ms = 0
        self._failures = 0
        self._next_attempt = 0.0
        self.status = (
            "provided JWT awaiting account verification"
            if self._token else "awaiting automatic authentication"
        )
        self.error = ""

    @staticmethod
    def _decode_claims(token: str) -> Dict[str, Any]:
        try:
            pieces = str(token).split(".")
            if len(pieces) != 3:
                return {}
            encoded = pieces[1] + "=" * (-len(pieces[1]) % 4)
            decoded = base64.urlsafe_b64decode(encoded.encode("ascii"))
            claims = json.loads(decoded.decode("utf-8"))
            return claims if isinstance(claims, dict) else {}
        except Exception:
            return {}

    def _redact(self, value: Any) -> str:
        text = str(value or "")
        for secret in (self._token, self.api_key):
            if secret:
                text = text.replace(secret, "<redacted>")
        return text[:180]

    def _expiry_seconds_locked(self) -> Optional[float]:
        try:
            return float(self._claims.get("exp"))
        except (TypeError, ValueError):
            return None

    def _refresh_due_locked(self) -> bool:
        if not self._token or self._invalidated:
            return True
        expiry = self._expiry_seconds_locked()
        if expiry is None:
            return False
        try:
            issued = float(self._claims.get("iat"))
            lifetime = max(0.0, expiry - issued)
        except (TypeError, ValueError):
            lifetime = 3600.0
        skew = max(
            PREDICT_AUTH_MIN_REFRESH_SKEW_SEC,
            min(PREDICT_AUTH_MAX_REFRESH_SKEW_SEC, lifetime * 0.10),
        )
        return expiry - time.time() <= skew

    def _usable_locked(self) -> bool:
        if not self._token or not self._verified or self._invalidated:
            return False
        expiry = self._expiry_seconds_locked()
        return expiry is None or expiry - time.time() > 5.0

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            expiry = self._expiry_seconds_locked()
            return {
                "ready": self._usable_locked(),
                "status": self.status,
                "error": self.error,
                "generation": self._generation,
                "verified": self._verified and not self._invalidated,
                "last_verified_ms": self._last_verified_ms,
                "last_refresh_ms": self._last_refresh_ms,
                "expires_in_sec": (
                    None if expiry is None
                    else max(0, int(expiry - time.time()))
                ),
            }

    def token_and_generation(self) -> Tuple[str, int]:
        with self._lock:
            if not self._usable_locked():
                return "", self._generation
            return self._token, self._generation

    def invalidate(self, reason: str) -> None:
        with self._lock:
            self._invalidated = True
            self._verified = False
            self._next_attempt = 0.0
            self.status = "authentication renewal required"
            self.error = self._redact(reason)
        with self.book._lock:
            self.book.wallet_ws_ready = False

    def _http(
        self, method: str, path: str,
        payload: Optional[Dict[str, Any]] = None, token: str = "",
    ) -> Tuple[int, Any]:
        self.book._reserve_request(path)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"btc-model/{VERSION}",
            "x-api-key": self.api_key,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = (
            json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            if payload is not None else None
        )
        request = urllib.request.Request(
            PREDICT_BASE_MAINNET + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(
                request, timeout=PREDICT_TIMEOUT
            ) as response:
                self.book._capture_rate_headers(response.headers)
                raw = response.read()
                try:
                    data: Any = json.loads(raw.decode()) if raw else {}
                except (UnicodeDecodeError, ValueError):
                    data = {}
                return int(response.status), data
        except urllib.error.HTTPError as exc:
            self.book._capture_rate_headers(exc.headers)
            raw = exc.read()
            try:
                data = json.loads(raw.decode()) if raw else {}
            except Exception:
                data = {}
            return int(exc.code), data

    def _verify_token(self, token: str) -> Tuple[bool, str]:
        code, payload = self._http("GET", "/v1/account", token=token)
        if code != 200 or not isinstance(payload, dict):
            return False, f"account verification HTTP {code}"
        data = payload.get("data") or {}
        address = str(data.get("address") or "") if isinstance(data, dict) else ""
        if not address:
            return False, "account verification returned no address"
        if address.lower() != self.signer_address.lower():
            return False, "authenticated account does not match PREDICT_ACCOUNT_ADDRESS"
        return True, ""

    def _record_failure(self, error: Any) -> bool:
        with self._lock:
            self._failures += 1
            delay = min(
                PREDICT_AUTH_RETRY_MAX_SEC,
                max(1.0, 2.0 ** min(self._failures - 1, 6)),
            )
            expiry = self._expiry_seconds_locked()
            if expiry is not None and self._token and not self._invalidated:
                # Never let exponential backoff sleep through the usable
                # remainder of the current token.
                delay = min(delay, max(1.0, expiry - time.time() - 5.0))
            self._next_attempt = time.monotonic() + delay
            usable = self._usable_locked()
            self.status = (
                "authenticated; renewal retry scheduled"
                if usable else "authentication blocked"
            )
            self.error = self._redact(error)
            return usable

    def ensure_token(self, force: bool = False) -> bool:
        """Verify or renew the token; safe for repeated background calls."""
        with self._lock:
            if self._usable_locked() and not self._refresh_due_locked():
                return True
            if not force and time.monotonic() < self._next_attempt:
                return self._usable_locked()
        with self._refresh_lock:
            with self._lock:
                if self._usable_locked() and not self._refresh_due_locked():
                    return True
                if not force and time.monotonic() < self._next_attempt:
                    return self._usable_locked()
                old_token = self._token
                old_needs_refresh = self._refresh_due_locked()
                old_verified = self._verified and not self._invalidated
            try:
                # A non-expiring supplied token still has to prove that it is
                # for the configured smart account before it is shared.
                if old_token and not old_needs_refresh and not old_verified:
                    verified, why = self._verify_token(old_token)
                    if verified:
                        with self._lock:
                            self._verified = True
                            self._invalidated = False
                            self._last_verified_ms = now_ms()
                            self._failures = 0
                            self._next_attempt = 0.0
                            self.status = "authenticated and account verified"
                            self.error = ""
                        return True
                    self.invalidate(why)

                if not self.api_key:
                    raise RuntimeError("PREDICT_API_KEY is required for authentication")
                if not re.fullmatch(r"0x[0-9a-fA-F]{40}", self.signer_address):
                    raise RuntimeError("PREDICT_ACCOUNT_ADDRESS is not a valid address")
                if self.builder is None or not hasattr(
                    self.builder, "sign_predict_account_message"
                ):
                    raise RuntimeError(
                        "predict-sdk with smart-account message signing is required"
                    )
                code, response = self._http("GET", "/v1/auth/message")
                data = response.get("data") if isinstance(response, dict) else None
                message = data.get("message") if isinstance(data, dict) else None
                if code != 200 or not isinstance(message, str) or not message:
                    raise RuntimeError(f"auth message HTTP {code}")
                if len(message) > 4096:
                    raise RuntimeError("auth message exceeded safe length")
                signature = self.builder.sign_predict_account_message(message)
                if not isinstance(signature, str) or not signature.startswith("0x"):
                    raise RuntimeError("predict-sdk returned an invalid auth signature")
                code, response = self._http(
                    "POST", "/v1/auth",
                    {
                        "signer": self.signer_address,
                        "signature": signature,
                        "message": message,
                    },
                )
                data = response.get("data") if isinstance(response, dict) else None
                token = data.get("token") if isinstance(data, dict) else None
                if code != 200 or not isinstance(token, str) or not token.strip():
                    raise RuntimeError(f"JWT exchange HTTP {code}")
                token = token.strip()
                verified, why = self._verify_token(token)
                if not verified:
                    raise RuntimeError(why)
                claims = self._decode_claims(token)
                try:
                    expiry = float(claims.get("exp"))
                except (TypeError, ValueError):
                    expiry = None
                if expiry is not None and expiry - time.time() <= 5.0:
                    raise RuntimeError("venue returned an already expired JWT")
                with self._lock:
                    self._token = token
                    self._claims = claims
                    self._generation += 1
                    self._verified = True
                    self._invalidated = False
                    self._last_verified_ms = now_ms()
                    self._last_refresh_ms = now_ms()
                    self._failures = 0
                    self._next_attempt = 0.0
                    self.status = "authenticated and account verified"
                    self.error = ""
                return True
            except Exception as exc:
                return self._record_failure(exc)


class LiveExecutor(threading.Thread):
    """Serial, idempotent Predict.fun live-order executor.

    One worker preserves order sequence and keeps signing off the signal hot
    path. Signed hashes are registered before POST. Unknown submissions remain
    under reconciliation and can never be replaced merely because a response
    was late.
    """

    def __init__(
        self, store: Store, controls: TradeControls, book: PredictBook,
        stop: threading.Event,
    ) -> None:
        super().__init__(name="predict-orders", daemon=True)
        self.store = store
        self.controls = controls
        self.book = book
        self.stop_event = stop
        self.api_key = os.getenv("PREDICT_API_KEY", "").strip()
        self.private_key = (
            os.getenv("PREDICT_PRIVATE_KEY", "").strip()
            or os.getenv("PRIVY_WALLET_PRIVATE_KEY", "").strip()
        )
        self.predict_account = os.getenv("PREDICT_ACCOUNT_ADDRESS", "").strip()
        self.jobs: "queue.Queue[Tuple[Prediction, str]]" = queue.Queue(maxsize=128)
        self._builder: Any = None
        # R6.4: direction-owned EF signers. UP and DOWN never wait on the
        # same SDK builder/lock, while MAIN/REV keep the original builder.
        self._ef_builders: Dict[str, Any] = {"UP": None, "DOWN": None}
        self._ef_builder_locks: Dict[str, threading.Lock] = {
            "UP": threading.Lock(), "DOWN": threading.Lock(),
        }
        self._ef_builder_next_attempt: Dict[str, float] = {"UP": 0.0, "DOWN": 0.0}
        self._preflight_builder: Any = None
        self._builder_init_lock = threading.Lock()
        self._builder_failures = 0
        self._builder_next_attempt = 0.0
        self._sdk: Dict[str, Any] = {}
        self._sdk_error = ""
        self._readiness_lock = threading.RLock()
        self._preflight_lock = threading.Lock()
        self._approval_key: Optional[Tuple[bool, bool]] = None
        self._approval_ready = False
        self._approval_missing: List[str] = []
        self._approval_error = ""
        self._approval_checked_ms = 0
        self._wallet_balance_usd: Optional[float] = None
        self._balance_error = ""
        self._balance_checked_ms = 0
        # v7.8: venue positions poller state
        self._positions_error = ""
        self._positions_checked_ms = 0
        self._positions_count = 0
        self._positions_wake = threading.Event()
        self._events: Dict[str, Dict[str, Any]] = {}
        self._contexts: Dict[str, Dict[str, Any]] = {}
        self._event_lock = threading.RLock()
        self.last_status = "safe startup - master OFF"
        self.last_error = ""
        self.last_order_ms = 0
        # Executor-local latency: signer age, final viability and fire->POST.
        self.latency = LatencyTelemetry()
        self._last_reconcile = 0.0
        self._load_sdk()
        self.auth = PredictAuthSession(
            self.book, self.api_key, self.predict_account,
            self._preflight_builder,
        )
        self._restore_contexts()
        # R5: reconciliation GETs never run on the serial fresh-order worker.
        self._r5_retry_jobs = queue.SimpleQueue()
        # EF QUEUE_FULL is provably no-order, but re-arm only once executor
        # capacity exists again; otherwise the same signal can hot-loop.
        self._r5_deferred_ef_releases = queue.SimpleQueue()
        self._r5_dispatch_wake = threading.Event()
        # Reconstruct a crash-interrupted QUEUE_FULL cleanup. No POST could have
        # happened because enqueue() itself failed.
        for failed in self.store.r5_hashless_queue_full_rows():
            prediction = self.store.get_ef_prediction(int(failed["candle_id"]))
            if prediction is not None:
                self.defer_ef_release_when_queue_available(
                    prediction,
                    str(failed.get("failure_reason") or "execution queue full"),
                )
        # R5 hot REST transport: one TLS context, independent GET/POST lanes.
        self._r5_ssl_context = ssl.create_default_context()
        r5_url = urllib.parse.urlparse(PREDICT_BASE_MAINNET)
        self._r5_http_host = str(r5_url.hostname or "api.predict.fun")
        self._r5_http_port = int(r5_url.port or 443)
        self._r5_http_connections = {"GET": None, "POST": None}
        self._r5_http_locks = {"GET": threading.Lock(), "POST": threading.Lock()}
        # R6 EF hot-execution container. UP and DOWN signed market orders are
        # continuously refreshed off the Predict.fun websocket book. A BTC EF
        # signal only arms an identity/stake; the one authoritative economic
        # check is full-stake VWAP < $0.50 on the already-running hot state.
        self._ef_hot_lock = threading.RLock()
        self._ef_hot_wake: Dict[str, threading.Event] = {
            "UP": threading.Event(), "DOWN": threading.Event(),
        }
        self._ef_hot_orders: Dict[str, Dict[str, Any]] = {"UP": {}, "DOWN": {}}
        self._ef_hot_active: Optional[Dict[str, Any]] = None
        self._ef_hot_stake_hint = 0.0
        self._ef_hot_threads: Dict[str, threading.Thread] = {}
        self.book.set_update_sink(self._ef_hot_book_update)

    def _ef_hot_book_update(self, _version: int, _book_ms: int) -> None:
        """Websocket callback: wake both independent signer lanes only."""
        for event in self._ef_hot_wake.values():
            event.set()

    def set_ef_hot_stake(self, stake: float) -> None:
        try:
            value = round(max(0.0, float(stake)), 2)
        except (TypeError, ValueError):
            value = 0.0
        with self._ef_hot_lock:
            if abs(value - self._ef_hot_stake_hint) <= 1e-9:
                return
            self._ef_hot_stake_hint = value
            # A differently-sized signed order is not valid for the new shared stake.
            self._ef_hot_orders = {"UP": {}, "DOWN": {}}
        for event in self._ef_hot_wake.values():
            event.set()

    @staticmethod
    def _ef_hot_public_state(state: Dict[str, Any]) -> Dict[str, Any]:
        public = dict(state or {})
        # Never expose signed payloads/hashes or SDK amount internals to UI/API.
        for key in ("payload", "order_hash", "amounts"):
            public.pop(key, None)
        return public

    def ef_hot_snapshot(self) -> Dict[str, Any]:
        with self._ef_hot_lock:
            active = self._ef_hot_active
            return {
                "stake": self._ef_hot_stake_hint,
                "active": (
                    None if active is None else {
                        "candle_id": int(active["prediction"].candle_id),
                        "direction": str(active["prediction"].direction),
                        "attempt": int(active.get("attempt") or 1),
                        "inflight": bool(active.get("inflight")),
                        "min_book_version": int(active.get("min_book_version") or 0),
                    }
                ),
                "UP": self._ef_hot_public_state(self._ef_hot_orders.get("UP") or {}),
                "DOWN": self._ef_hot_public_state(self._ef_hot_orders.get("DOWN") or {}),
            }

    def ef_hot_quote(self, direction: str) -> Dict[str, Any]:
        side = str(direction or "").upper()
        with self._ef_hot_lock:
            state = dict(self._ef_hot_orders.get(side) or {})
        return self._ef_hot_public_state(state)

    def arm_ef_hot(
        self, prediction: Prediction, stake: float, *, attempt: int = 1,
        first_submit_ms: Optional[int] = None, min_book_version: int = 0,
        vwap_confirmed: bool = False, previous_order_hash: str = "",
    ) -> None:
        """Arm one EF identity without queueing/rebuilding on the signal path.

        ``vwap_confirmed`` is sticky for one execution batch. The first POST is
        allowed only after the authoritative full-stake VWAP is below $0.50.
        Confirmed-terminal retries 2-4 stay inside that same batch and therefore
        never re-enter the VWAP gate. ``previous_order_hash`` prevents a retry
        from accidentally resubmitting the exact signed payload that just died.
        """
        self.set_ef_hot_stake(stake)
        with self._ef_hot_lock:
            self._ef_hot_active = {
                "prediction": prediction,
                "stake": float(stake),
                "attempt": max(1, int(attempt)),
                "first_submit_ms": int(first_submit_ms or 0),
                "min_book_version": max(0, int(min_book_version)),
                "vwap_confirmed": bool(vwap_confirmed),
                "previous_order_hash": self._hash_key(previous_order_hash),
                "armed_ns": mono_ns(),
                "inflight": False,
            }
        event = self._ef_hot_wake.get(str(prediction.direction).upper())
        if event is not None:
            event.set()

    def clear_ef_hot(
        self, candle_id: Optional[int] = None, signal_ts_ms: Optional[int] = None
    ) -> None:
        with self._ef_hot_lock:
            active = self._ef_hot_active
            if active is None:
                return
            pred = active.get("prediction")
            if pred is None:
                self._ef_hot_active = None
                return
            if candle_id is not None and int(pred.candle_id) != int(candle_id):
                return
            if signal_ts_ms is not None and int(pred.ts_ms) != int(signal_ts_ms):
                return
            self._ef_hot_active = None

    def _ef_hot_refresh_stake_hint(self) -> None:
        """Refresh likely shared stake off the hot signal path."""
        try:
            capital = self.store.capital_state()
            cfg = self.store.control_row(SYSTEM_CONTROL_KIND)["stake"]
            stake = configured_stake(cfg, float(capital.get("balance", 0.0)))
            if float(capital.get("free", 0.0)) + 1e-9 < stake:
                stake = 0.0
            self.set_ef_hot_stake(stake)
        except Exception:
            return

    def _ef_hot_build_side(
        self, direction: str, candle_id: int, stake: float
    ) -> Dict[str, Any]:
        """Sign one EF FOK from one atomic ladder snapshot.

        _build_payload copies contract + SDK ladder under the PredictBook lock,
        derives the full-stake VWAP and this build's dynamic isMinAmountOut tier
        from that SAME copy, then signs after releasing the book lock.
        """
        side = str(direction or "").upper()
        builder = self._ef_builders.get(side)
        if builder is None:
            raise RuntimeError(f"EF {side} builder is not ready")
        pred = Prediction(
            int(candle_id), "EF", side, now_ms(), 0.0, 0.5,
            "R6.4 EF direction-owned hot prebuild",
        )
        sign_ns = mono_ns()
        order_hash, payload, amounts = self._build_payload(
            pred, float(stake), builder=builder, dynamic_ef_slippage=True,
        )
        sign_ms = (mono_ns() - sign_ns) / 1_000_000.0
        self.latency.observe_ms("ef_hot_sign_ms", sign_ms)
        min_out_shares = None
        try:
            min_out_shares = int(amounts.get("taker_amount_wei") or 0) / 10**18
        except Exception:
            min_out_shares = None
        return {
            "direction": side,
            "candle_id": int(candle_id),
            "stake": float(stake),
            "quote": float(amounts.get("price") or 0.0),
            "vwap": finite_float(amounts.get("execution_vwap")),
            "max_price": finite_float(amounts.get("execution_max_price")),
            "shares": finite_float(amounts.get("execution_shares")),
            "min_out_shares": min_out_shares,
            "signed_effective_max_price": finite_float(amounts.get("max_price")),
            "book_ms": int(amounts.get("book_ms") or 0),
            "book_version": int(amounts.get("book_version") or 0),
            "built_ms": now_ms(),
            "sign_ms": sign_ms,
            "slippage_bps": int(
                amounts.get("slippage_bps")
                or ef_slippage_bps(amounts.get("execution_vwap"))
            ),
            "execution_ok": bool(amounts.get("execution_ok")),
            "order_hash": order_hash,
            "payload": payload,
            "amounts": amounts,
        }

    def _ef_hot_refresh_side(self, direction: str) -> None:
        """Refresh exactly one direction; never wait for the opposite signer."""
        side = str(direction or "").upper()
        if side not in ("UP", "DOWN"):
            return
        if not self._ensure_ef_builder(side):
            return
        with self.book._lock:
            candle_id = self.book.market_candle_id
        if candle_id is None or not self.book.websocket_fresh():
            return
        with self._ef_hot_lock:
            stake = float(self._ef_hot_stake_hint or 0.0)
        if stake <= 0.0:
            return
        before_version = self.book.current_version()
        try:
            state = self._ef_hot_build_side(side, int(candle_id), stake)
        except Exception as exc:
            state = {
                "direction": side, "candle_id": int(candle_id),
                "stake": stake, "quote": None, "vwap": None,
                "max_price": None, "shares": None, "min_out_shares": None,
                "signed_effective_max_price": None, "book_ms": 0,
                "book_version": int(before_version), "built_ms": now_ms(),
                "sign_ms": 0.0, "slippage_bps": ef_slippage_bps(None),
                "execution_ok": False, "payload": None,
                "error": str(exc)[:160],
            }
        with self._ef_hot_lock:
            # A stake edit that raced signing invalidates this payload.
            if abs(float(self._ef_hot_stake_hint or 0.0) - stake) > 1e-9:
                return
            previous = self._ef_hot_orders.get(side) or {}
            if int(state.get("book_version") or 0) >= int(
                previous.get("book_version") or 0
            ):
                self._ef_hot_orders[side] = state
        # If a websocket update landed while cryptography was running, make
        # sure this lane immediately catches up. This closes Event set/clear
        # races without forcing the opposite direction to rebuild.
        if self.book.current_version() > int(state.get("book_version") or 0):
            self._ef_hot_wake[side].set()

    def _ef_hot_refresh(self) -> None:
        """Compatibility helper; live UP/DOWN signer lanes are independent."""
        self._ef_hot_refresh_side("UP")
        self._ef_hot_refresh_side("DOWN")

    def _ef_hot_viability(
        self, state: Dict[str, Any], stake: float
    ) -> Dict[str, Any]:
        """Check the CURRENT ladder against the signed min-output envelope.

        A newer websocket version is not a rejection. The prepared FOK remains
        usable whenever the current full dollar stake can still return at least
        the minimum shares encoded by isMinAmountOut. No $0.10/$0.50 execution
        ceiling is introduced here.
        """
        live = self.book.executable_vwap(str(state.get("direction") or ""), float(stake))
        live_vwap = finite_float(live.get("vwap"))
        live_shares = finite_float(live.get("shares"))
        min_out = finite_float(state.get("min_out_shares"))
        result = {
            "ok": False,
            "reason": "",
            "live_vwap": live_vwap,
            "live_shares": live_shares,
            "min_out_shares": min_out,
            "book_age_ms": live.get("book_age_ms"),
        }
        if not live.get("ok") or live_vwap is None or live_shares is None:
            result["reason"] = str(live.get("reason") or "NO_FRESH_BOOK")
            return result
        if min_out is None or min_out <= 0.0:
            result["reason"] = "SIGNED_MIN_OUT_UNAVAILABLE"
            return result
        # Half-share-wei numerical slack only; never economic tolerance.
        if live_shares + 5e-13 < min_out:
            result["reason"] = (
                f"BOOK_BEYOND_SIGNED_MIN_OUT live={live_shares:.8f} "
                f"signed_min={min_out:.8f}"
            )
            return result
        result["ok"] = True
        result["reason"] = "VIABLE"
        return result

    def _ef_hot_transition_after_terminal(
        self, prediction: Prediction, used_state: Dict[str, Any], attempt: int,
        first_submit_ms: int, terminal_state: str,
    ) -> None:
        """Advance the SAME VWAP-qualified EF batch after a proven-dead order.

        One EF gets one authoritative VWAP confirmation, then at most four POST
        attempts (attempt 1 + three replacements). Attempts 2-4 do NOT re-check
        the $0.50 VWAP rule. After the fourth confirmed terminal failure the EF
        is finished permanently for that signal; a later cheaper share can never
        resurrect it or send it back to WAIT_VWAP.
        """
        row = self.store.trade_row(prediction.candle_id, "EF") or {}
        if bool(row.get("filled")):
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)
            return
        max_attempts = PREDICT_ORDER_MAX_RETRIES + 1
        terminal = str(terminal_state or "FAILED").upper()
        if int(attempt) >= max_attempts:
            # Keep the venue's actual terminal state visible. RETRY_EXHAUSTED is
            # an eligibility/reason label, not a synthetic replacement status.
            self.store.update_trade_execution(
                prediction.candle_id, "EF", order_hash=None, order_id=None,
                order_status=terminal,
                failure_reason=(
                    f"{terminal}: EF failed after {max_attempts} attempts; signal closed"
                )[:180],
                execution_eligibility="RETRY_EXHAUSTED",
            )
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)
            return

        # The first VWAP approval remains authoritative for this whole batch.
        # Retire the proven-dead hash and immediately prepare the next hot POST.
        # A distinct signed hash is required, but a NEW price confirmation is not.
        prior_hash = self._hash_key(used_state.get("order_hash"))
        next_attempt = int(attempt) + 1
        self.store.update_trade_execution(
            prediction.candle_id, "EF", order_hash=None, order_id=None,
            order_status="HOT_RETRY",
            failure_reason=(
                f"{terminal} confirmed; immediate EF retry {next_attempt}/{max_attempts} "
                "under original VWAP confirmation"
            )[:180],
            execution_eligibility="VWAP_CONFIRMED_RETRY",
        )
        self.arm_ef_hot(
            prediction, float(row.get("stake") or used_state.get("stake") or 0.0),
            attempt=next_attempt, first_submit_ms=int(first_submit_ms),
            min_book_version=0, vwap_confirmed=True,
            previous_order_hash=prior_hash,
        )
        # Force only the fired direction to refresh; the opposite lane is independent.
        event = self._ef_hot_wake.get(str(prediction.direction).upper())
        if event is not None:
            event.set()

    def _ef_hot_execute_ready(
        self, active: Dict[str, Any], state: Dict[str, Any]
    ) -> None:
        prediction = active["prediction"]
        side = str(prediction.direction).upper()
        stake = float(active.get("stake") or 0.0)
        attempt = int(active.get("attempt") or 1)
        first_submit_ms = int(active.get("first_submit_ms") or 0) or now_ms()
        signed_vwap = finite_float(state.get("vwap"))
        if signed_vwap is None or not state.get("execution_ok"):
            return

        # Check current full-stake liquidity against the signed min-output
        # envelope. This does NOT care whether Predict has emitted a newer
        # websocket version; only actual executable economics matter.
        fence_ns = mono_ns()
        viability = self._ef_hot_viability(state, stake)
        self.latency.observe_ms(
            "ef_pre_submit_viability_ms", (mono_ns() - fence_ns) / 1_000_000.0
        )
        if not viability.get("ok"):
            with self._ef_hot_lock:
                current = self._ef_hot_orders.get(side) or {}
                if self._hash_key(current.get("order_hash")) == self._hash_key(
                    state.get("order_hash")
                ):
                    self._ef_hot_orders[side] = {}
            self.latency.inc("ef_local_rebuild_before_post")
            self.store.update_trade_execution(
                prediction.candle_id, "EF",
                order_status="HOT_REBUILD",
                failure_reason=(
                    f"{viability.get('reason')}; re-signing locally, no POST sent"
                )[:180],
                execution_eligibility="LOCAL_REBUILD",
            )
            self._ef_hot_wake[side].set()
            return

        live_vwap = finite_float(viability.get("live_vwap"))
        if live_vwap is None:
            return
        # Preserve the existing ONE full-stake EF VWAP qualification for the
        # first venue attempt. The dynamic tolerance itself is not a price gate.
        batch_qualified = bool(active.get("vwap_confirmed"))
        if not batch_qualified and live_vwap >= EF_MAX_SHARE_PRICE:
            self.store.update_trade_execution(
                prediction.candle_id, "EF", order_status="WAIT_VWAP",
                quoted_price=live_vwap, execution_vwap=live_vwap,
                failure_reason=(
                    f"waiting for full-stake EF VWAP < {EF_MAX_SHARE_PRICE:.2f}"
                ),
                execution_eligibility="WAIT_VWAP",
                book_age_ms=viability.get("book_age_ms"),
            )
            return

        ready = self.readiness(required_stake=stake)
        if not ready.get("ready"):
            retry_wait = bool(batch_qualified or attempt > 1)
            self.store.update_trade_execution(
                prediction.candle_id, "EF",
                order_status="HOT_RETRY_WAIT" if retry_wait else "WAIT_VWAP",
                failure_reason=(
                    "hot executor not ready: " + ", ".join(ready.get("missing") or [])
                )[:180],
                execution_eligibility=(
                    "WAIT_READINESS_RETRY" if retry_wait else "WAIT_READINESS"
                ),
            )
            return

        row = self.store.trade_row(prediction.candle_id, "EF") or {}
        if not self._r5_job_matches_trade(prediction, row) or bool(row.get("filled")):
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)
            return
        if str(row.get("order_hash") or "").strip():
            return
        if str(row.get("order_status") or "").upper() in {
            "SUBMITTING", "UNKNOWN", "ACCEPTED", "MATCHING", "OPEN",
            "PENDING", "PARTIALLYFILLED", "FILLED_DETAILS_PENDING",
        }:
            return
        remaining = prediction.candle_id + CANDLE_MS - now_ms()
        if remaining < PREDICT_ORDER_MIN_REMAINING_MS:
            self.store.update_trade_execution(
                prediction.candle_id, "EF", order_status="TOO_LATE",
                failure_reason="insufficient candle time for safe EF submission",
                execution_eligibility="TOO_LATE",
            )
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)
            return

        if not batch_qualified:
            with self._ef_hot_lock:
                current = self._ef_hot_active
                if current is not None:
                    cpred = current.get("prediction")
                    if (cpred is not None
                            and int(cpred.candle_id) == int(prediction.candle_id)
                            and int(cpred.ts_ms) == int(prediction.ts_ms)):
                        current["vwap_confirmed"] = True
            batch_qualified = True

        eligibility = "VWAP_CONFIRMED" if attempt == 1 else "VWAP_CONFIRMED_RETRY"
        self.store.update_trade_execution(
            prediction.candle_id, "EF", quoted_price=live_vwap,
            execution_vwap=live_vwap, execution_eligibility=eligibility,
            order_status="HOT_POST" if attempt == 1 else "HOT_RETRY_POST",
            failure_reason=None, book_age_ms=viability.get("book_age_ms"),
        )
        try:
            attempt_log = json.loads(row.get("attempt_log") or "[]")
            if not isinstance(attempt_log, list):
                attempt_log = []
        except Exception:
            attempt_log = []

        prepared = (state["order_hash"], state["payload"], state["amounts"])
        armed_ns = int(active.get("armed_ns") or 0)
        post_ns = mono_ns()
        if armed_ns:
            self.latency.observe_ms(
                "ef_fire_to_attempt_ms", (post_ns - armed_ns) / 1_000_000.0
            )
        self.latency.observe_ms(
            "ef_hot_order_age_ms",
            max(0, now_ms() - int(state.get("built_ms") or now_ms())),
        )
        outcome = self._attempt(
            prediction, "EF", stake, attempt, attempt_log, first_submit_ms,
            prepared=prepared,
        )
        self.last_order_ms = now_ms()
        self.last_status = f"EF HOT {outcome}"
        if outcome == "LOCAL_REBUILD":
            with self._ef_hot_lock:
                current = self._ef_hot_orders.get(side) or {}
                if self._hash_key(current.get("order_hash")) == self._hash_key(
                    state.get("order_hash")
                ):
                    self._ef_hot_orders[side] = {}
            self._ef_hot_wake[side].set()
            return
        if outcome == "TERMINAL":
            terminal_row = self.store.trade_row(prediction.candle_id, "EF") or {}
            terminal_state = str(terminal_row.get("order_status") or "FAILED").upper()
            self._ef_hot_transition_after_terminal(
                prediction, state, attempt, first_submit_ms, terminal_state
            )
        elif outcome == "FILLED":
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)
        elif outcome in {"BLOCKED"}:
            self.clear_ef_hot(prediction.candle_id, prediction.ts_ms)

    def _ef_hot_try_fire(self) -> None:
        with self._ef_hot_lock:
            active = None if self._ef_hot_active is None else dict(self._ef_hot_active)
            if active is None or bool(active.get("inflight")):
                return
            pred = active.get("prediction")
            if pred is None:
                return
            side = str(pred.direction).upper()
            state = dict(self._ef_hot_orders.get(side) or {})
            previous_hash = self._hash_key(active.get("previous_order_hash"))
            current_hash = self._hash_key(state.get("order_hash"))
            # R6.4 deliberately does NOT require state.book_version == current.
            # Final min-output viability decides whether a newer ladder matters.
            valid = bool(
                state
                and int(state.get("candle_id") or -1) == int(pred.candle_id)
                and abs(float(state.get("stake") or 0.0)
                        - float(active.get("stake") or 0.0)) <= 1e-9
                and int(state.get("book_version") or 0)
                    >= int(active.get("min_book_version") or 0)
                and state.get("payload") is not None
                and (not previous_hash or current_hash != previous_hash)
            )
            if not valid:
                return
            if self._ef_hot_active is None:
                return
            self._ef_hot_active["inflight"] = True
        try:
            self._ef_hot_execute_ready(active, state)
        finally:
            with self._ef_hot_lock:
                current = self._ef_hot_active
                if current is not None:
                    cpred = current.get("prediction")
                    if (cpred is not None
                            and int(cpred.candle_id) == int(pred.candle_id)
                            and int(cpred.ts_ms) == int(pred.ts_ms)):
                        current["inflight"] = False

    def _ef_hot_loop_side(self, direction: str) -> None:
        """Independent event-driven signer/executor lane for one EF side.

        The already-prepared payload always gets first refusal.  An EF arm
        therefore does not pay signing latency after the signal fires.  If the
        prepared signature no longer fits the newest live min-output envelope,
        _ef_hot_try_fire() clears it; only then do we rebuild this side and try
        once more.  With no active EF, the first try is a cheap no-op and a book
        event simply refreshes the prepared order as usual.
        """
        side = str(direction).upper()
        event = self._ef_hot_wake[side]
        while not self.stop_event.is_set():
            # Timeout is only for shutdown responsiveness. No event = no re-sign.
            if not event.wait(0.25):
                continue
            event.clear()
            try:
                # Critical latency order: POST a viable prebuilt signature before
                # doing any new cryptographic signing after an EF arm/book event.
                self._ef_hot_try_fire()
                self._ef_hot_refresh_side(side)
                # A stale prebuilt may have been rejected locally above.  The
                # freshly rebuilt side can now be posted in this same wake cycle.
                self._ef_hot_try_fire()
            except Exception as exc:
                self.last_error = f"EF hot {side}: {exc}"[:180]

    def defer_ef_release_when_queue_available(
        self, prediction: Prediction, reason: str
    ) -> None:
        """QUEUE_FULL is no-order proof; release after capacity returns."""
        self._r5_deferred_ef_releases.put(
            (prediction, "QUEUE_FULL", str(reason or "execution queue full"))
        )
        self._r5_dispatch_wake.set()

    def _r5_process_deferred_ef_release(self) -> bool:
        if self.jobs.full():
            return False
        try:
            prediction, status, reason = self._r5_deferred_ef_releases.get_nowait()
        except queue.Empty:
            return False
        row = self.store.trade_row(prediction.candle_id, "EF") or {}
        if (
            self._r5_job_matches_trade(prediction, row)
            and not bool(row.get("filled"))
            and not str(row.get("order_hash") or "").strip()
            and str(row.get("order_status") or "").upper() == str(status).upper()
        ):
            self.store.r5_release_failed_ef(
                prediction.candle_id, prediction.ts_ms, prediction.direction,
                str(reason or status),
            )
        return True

    def _load_sdk(self) -> None:
        try:
            from predict_sdk import (
                ApprovalScope, Book, BuildOrderInput, ChainId,
                MarketHelperValueInput, OrderBuilder, OrderBuilderOptions, Side,
            )
            self._sdk = {
                "ApprovalScope": ApprovalScope, "Book": Book,
                "BuildOrderInput": BuildOrderInput,
                "ChainId": ChainId, "MarketHelperValueInput": MarketHelperValueInput,
                "OrderBuilder": OrderBuilder,
                "OrderBuilderOptions": OrderBuilderOptions, "Side": Side,
            }
        except Exception as exc:
            self._builder = None
            self._preflight_builder = None
            self._sdk_error = str(exc)[:180]

    def _ensure_builders(self, force: bool = False) -> bool:
        """Create signer-backed SDK builders off normal application startup."""
        if self._builder is not None and self._preflight_builder is not None:
            return True
        if not self._sdk:
            return False
        if not self.private_key:
            self._sdk_error = "PREDICT_PRIVATE_KEY is required"
            return False
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", self.predict_account):
            self._sdk_error = "PREDICT_ACCOUNT_ADDRESS is not a valid address"
            return False
        if not force and time.monotonic() < self._builder_next_attempt:
            return False
        if not self._builder_init_lock.acquire(blocking=force):
            return False
        try:
            if self._builder is not None and self._preflight_builder is not None:
                return True
            if not force and time.monotonic() < self._builder_next_attempt:
                return False
            order_builder = self._sdk["OrderBuilder"]
            options_type = self._sdk["OrderBuilderOptions"]
            chain_id = self._sdk["ChainId"].BNB_MAINNET
            if self._builder is None:
                self._builder = order_builder.make(
                    chain_id, self.private_key,
                    options_type(predict_account=self.predict_account),
                )
            if self._preflight_builder is None:
                # Auth, approval and balance RPCs never share the order-signing
                # builder, so a slow background read cannot delay a signal.
                self._preflight_builder = order_builder.make(
                    chain_id, self.private_key,
                    options_type(predict_account=self.predict_account),
                )
            self.auth.builder = self._preflight_builder
            self._builder_failures = 0
            self._builder_next_attempt = 0.0
            self._sdk_error = ""
            return True
        except Exception as exc:
            self._builder_failures += 1
            self._builder_next_attempt = time.monotonic() + min(
                60.0, max(1.0, 2.0 ** min(self._builder_failures - 1, 6))
            )
            self._sdk_error = str(exc)[:180]
            return False
        finally:
            self._builder_init_lock.release()

    def _ensure_ef_builder(self, direction: str) -> bool:
        """Create one direction-owned EF signer without touching MAIN/REV."""
        side = str(direction or "").upper()
        if side not in ("UP", "DOWN"):
            return False
        if self._ef_builders.get(side) is not None:
            return True
        if not self._ensure_builders():
            return False
        if not self._sdk or not self.private_key:
            return False
        if time.monotonic() < float(self._ef_builder_next_attempt.get(side) or 0.0):
            return False
        lock = self._ef_builder_locks[side]
        if not lock.acquire(blocking=False):
            return False
        try:
            if self._ef_builders.get(side) is not None:
                return True
            order_builder = self._sdk["OrderBuilder"]
            options_type = self._sdk["OrderBuilderOptions"]
            self._ef_builders[side] = order_builder.make(
                self._sdk["ChainId"].BNB_MAINNET, self.private_key,
                options_type(predict_account=self.predict_account),
            )
            self._ef_builder_next_attempt[side] = 0.0
            return True
        except Exception as exc:
            self._ef_builder_next_attempt[side] = time.monotonic() + 5.0
            self._sdk_error = f"EF {side} builder: {exc}"[:180]
            return False
        finally:
            lock.release()

    def _market_preflight_key(self) -> Optional[Tuple[bool, bool]]:
        with self.book._lock:
            if self.book.market_id is None or not self.book._current_market:
                return None
            item = dict(self.book._current_market)
        return (
            PredictBook._bool_field(item, "isNegRisk", "is_neg_risk"),
            PredictBook._bool_field(
                item, "isYieldBearing", "is_yield_bearing"
            ),
        )

    def _configured_required_stake(self) -> float:
        capital = self.store.capital_state()
        config = self.store.control_row(SYSTEM_CONTROL_KIND)["stake"]
        return configured_stake(config, float(capital["balance"]))

    @staticmethod
    def _approval_check_value(check: Any, name: str, default: Any = None) -> Any:
        if isinstance(check, dict):
            return check.get(name, default)
        return getattr(check, name, default)

    def refresh_live_readiness(
        self, force: bool = False, required_stake: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Refresh auth and on-chain reads without touching order state."""
        if not self._preflight_lock.acquire(blocking=force):
            return self.readiness(required_stake=required_stake)
        try:
            if not self._ensure_builders(force=force):
                return self.readiness(required_stake=required_stake)
            auth_ready = self.auth.ensure_token(force=force)
            builder = self._preflight_builder
            market_key = self._market_preflight_key()
            if not auth_ready or builder is None or market_key is None:
                return self.readiness(required_stake=required_stake)
            current_ms = now_ms()
            with self._readiness_lock:
                approval_age = (
                    float("inf") if not self._approval_checked_ms
                    else (current_ms - self._approval_checked_ms) / 1000.0
                )
                approval_due_after = (
                    PREDICT_APPROVAL_RECHECK_SEC
                    if self._approval_ready and self._approval_key == market_key
                    else PREDICT_PREFLIGHT_RETRY_SEC
                )
                approval_due = (
                    force or self._approval_key != market_key
                    or approval_age >= approval_due_after
                )
                balance_age = (
                    float("inf") if not self._balance_checked_ms
                    else (current_ms - self._balance_checked_ms) / 1000.0
                )
                balance_due = force or balance_age >= (
                    PREDICT_BALANCE_RECHECK_SEC
                    if self._wallet_balance_usd is not None
                    else PREDICT_PREFLIGHT_RETRY_SEC
                )
            if approval_due:
                try:
                    scope = self._sdk["ApprovalScope"](
                        operation="TRADE",
                        is_neg_risk=market_key[0],
                        is_yield_bearing=market_key[1],
                        side=self._sdk["Side"].BUY,
                    )
                    steps = builder.get_approval_steps(scope)
                    checks = builder.check_approvals(steps)
                    missing_steps: List[str] = []
                    for check in checks:
                        if bool(self._approval_check_value(
                            check, "satisfied", False
                        )):
                            continue
                        step = self._approval_check_value(check, "step", {})
                        step_id = self._approval_check_value(
                            step, "id", "required BUY approval"
                        )
                        missing_steps.append(str(step_id)[:80])
                    with self._readiness_lock:
                        self._approval_key = market_key
                        self._approval_missing = missing_steps
                        self._approval_ready = not missing_steps
                        self._approval_error = ""
                        self._approval_checked_ms = now_ms()
                except Exception as exc:
                    with self._readiness_lock:
                        self._approval_key = market_key
                        self._approval_ready = False
                        self._approval_missing = []
                        self._approval_error = str(exc)[:180]
                        self._approval_checked_ms = now_ms()
            if balance_due:
                try:
                    raw_balance = int(builder.balance_of("USDT"))
                    if raw_balance < 0:
                        raise RuntimeError("negative USDT balance")
                    wallet_balance = raw_balance / 10**18
                    checked_ms = now_ms()
                    with self._readiness_lock:
                        self._wallet_balance_usd = wallet_balance
                        self._balance_error = ""
                        self._balance_checked_ms = checked_ms
                    self.store.set_live_wallet_balance(wallet_balance, checked_ms)
                except Exception as exc:
                    checked_ms = now_ms()
                    with self._readiness_lock:
                        self._wallet_balance_usd = None
                        self._balance_error = str(exc)[:180]
                        self._balance_checked_ms = checked_ms
                    self.store.set_live_wallet_balance(None, checked_ms)
            return self.readiness(required_stake=required_stake)
        finally:
            self._preflight_lock.release()

    def readiness(
        self, required_stake: Optional[float] = None
    ) -> Dict[str, Any]:
        missing: List[str] = []
        if self.book.testnet:
            missing.append("PREDICT_BOOK_ENV must be mainnet")
        if not self.api_key:
            missing.append("PREDICT_API_KEY")
        if not self.private_key:
            missing.append("PREDICT_PRIVATE_KEY")
        if not self.predict_account:
            missing.append("PREDICT_ACCOUNT_ADDRESS")
        elif not re.fullmatch(r"0x[0-9a-fA-F]{40}", self.predict_account):
            missing.append("valid PREDICT_ACCOUNT_ADDRESS")
        auth = self.auth.snapshot()
        if not auth["ready"]:
            detail = str(auth.get("error") or auth.get("status") or "not ready")
            missing.append(f"Predict.fun authentication ({detail})")
        cooldown = self.book.rate_cooldown_seconds()
        if cooldown:
            missing.append(f"Predict.fun API cooldown ({cooldown}s)")
        if self._builder is None:
            missing.append(
                "current predict-sdk"
                + (f" ({self._sdk_error})" if self._sdk_error else "")
            )
        market_key = self._market_preflight_key()
        current_ms = now_ms()
        with self._readiness_lock:
            approval_ready = self._approval_ready
            approval_key = self._approval_key
            approval_missing = list(self._approval_missing)
            approval_error = self._approval_error
            approval_checked_ms = self._approval_checked_ms
            wallet_balance = self._wallet_balance_usd
            balance_error = self._balance_error
            balance_checked_ms = self._balance_checked_ms
        approval_age = (
            float("inf") if not approval_checked_ms
            else (current_ms - approval_checked_ms) / 1000.0
        )
        balance_age = (
            float("inf") if not balance_checked_ms
            else (current_ms - balance_checked_ms) / 1000.0
        )
        if market_key is not None:
            if approval_key != market_key or approval_age > PREDICT_APPROVAL_STALE_SEC:
                missing.append("fresh on-chain BUY approval check")
            elif not approval_ready:
                detail = approval_error or ", ".join(approval_missing)
                missing.append(
                    "on-chain BUY approval" + (f" ({detail})" if detail else "")
                )
        if wallet_balance is None or balance_age > PREDICT_BALANCE_STALE_SEC:
            missing.append(
                "fresh smart-account USDT balance"
                + (f" ({balance_error})" if balance_error else "")
            )
        required = (
            self._configured_required_stake()
            if required_stake is None else max(0.0, float(required_stake))
        )
        if wallet_balance is not None and wallet_balance + 1e-9 < required:
            missing.append(
                f"smart-account USDT ${wallet_balance:.2f} below "
                f"shared stake ${required:.2f}"
            )
        if not self.book.ws_connected:
            missing.append("Predict.fun websocket")
        if not self.book.wallet_ws_ready:
            missing.append("authenticated wallet websocket")
        if self.book.status != "live websocket":
            missing.append("websocket orderbook snapshot")
        if self.book.market_id is None:
            missing.append("current BTC 5m market")
        if not self.book.websocket_fresh():
            missing.append("fresh websocket session and orderbook")
        return {
            "ready": not missing,
            "missing": missing,
            "mode": "LIVE MAINNET",
            "queued": self.jobs.qsize(),
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_order_ms": self.last_order_ms,
            "slippage_bps": PREDICT_ORDER_SLIPPAGE_BPS,
            "max_retries": PREDICT_ORDER_MAX_RETRIES,
            "auth": auth,
            "approvals": {
                "ready": approval_ready and approval_key == market_key,
                "missing": approval_missing,
                "error": approval_error,
                "checked_ms": approval_checked_ms,
            },
            "wallet_balance_usd": wallet_balance,
            "wallet_balance_checked_ms": balance_checked_ms,
            "required_stake_usd": required,
            "ef_slippage_bps": None,
            "ef_slippage_policy": {
                "bands": [
                    {"lt_vwap": upper, "slippage_bps": bps}
                    for upper, bps in EF_SLIPPAGE_BANDS
                ],
                "fallback_bps": EF_SLIPPAGE_FALLBACK_BPS,
                "is_min_amount_out": True,
                "basis": "desired_price_rise_converted_to_min_out",
            },
            "ef_hot": self.ef_hot_snapshot(),
        }

    def enqueue(self, prediction: Prediction, kind: str) -> bool:
        try:
            self.jobs.put_nowait((prediction, kind))
            self._r5_dispatch_wake.set()
            return True
        except queue.Full:
            self.last_error = "execution intent queue full"
            return False

    @staticmethod
    def _hash_key(value: Any) -> str:
        return str(value or "").strip().lower()

    def _restore_contexts(self) -> None:
        """Reattach signed in-flight orders after a process restart."""
        for row in self.store.recoverable_live_orders():
            kind = str(row.get("kind") or "")
            candle_id = int(row.get("candle_id") or 0)
            stored_hash = str(row.get("order_hash") or "").strip()
            order_hash = self._hash_key(stored_hash)
            if not order_hash or kind not in TRADE_KINDS:
                continue
            if stored_hash != order_hash:
                self.store.update_trade_execution(
                    candle_id, kind, order_hash=order_hash
                )
            prediction = (
                self.store.get_ef_prediction(candle_id)
                if kind == "EF"
                else self.store.get_prediction(candle_id, kind)
            )
            self._contexts[order_hash] = {
                "candle_id": candle_id,
                "kind": kind,
                "prediction": prediction,
                "stake": float(row.get("stake") or 0.0),
                "attempt": max(1, int(row.get("attempts") or 1)),
                "quoted_price": float(row.get("quoted_price") or 0.0),
                "has_fill": bool(row.get("filled") or 0),
                "filled_shares": float(row.get("shares") or 0.0),
                "filled_value": float(
                    row.get("filled_value")
                    or (row.get("stake") if row.get("filled") else 0.0)
                    or 0.0
                ),
                "next_check": time.monotonic(),
                "reconcile_count": 0,
                "restored": True,
                "market_id": row.get("market_id"),
            }

    # ---- v7.8: venue positions ----------------------------------------
    @staticmethod
    def _shares_from_amount(amount: Any, decimals: int = 18) -> float:
        """`amount` is a bigint string in wei-style base units."""
        try:
            return float(int(str(amount).strip())) / float(10 ** decimals)
        except (TypeError, ValueError):
            try:
                return float(amount)
            except (TypeError, ValueError):
                return 0.0

    @staticmethod
    def _level_price(level: Any) -> Optional[float]:
        if isinstance(level, dict):
            try:
                return float(level.get("price"))
            except (TypeError, ValueError):
                return None
        try:
            return float(level)
        except (TypeError, ValueError):
            return None

    def _parse_positions(self, data: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(data, list):
            return out
        for entry in data:
            if not isinstance(entry, dict):
                continue
            market = entry.get("market") if isinstance(
                entry.get("market"), dict) else {}
            outcome = entry.get("outcome") if isinstance(
                entry.get("outcome"), dict) else {}
            market_id = str(market.get("id") or "")
            shares = self._shares_from_amount(entry.get("amount"))

            def maybe(value: Any) -> Optional[float]:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            record = {
                "position_id": str(entry.get("id") or ""),
                "market_id": market_id,
                "market_title": str(market.get("title") or ""),
                "outcome_name": str(outcome.get("name") or ""),
                "index_set": outcome.get("indexSet"),
                "condition_id": str(market.get("conditionId") or ""),
                "shares": shares,
                "value_usd": maybe(entry.get("valueUsd")),
                "avg_buy_price": maybe(entry.get("averageBuyPriceUsd")),
                "pnl_usd": maybe(entry.get("pnlUsd")),
                "best_bid": self._level_price(outcome.get("bestBid")),
                "best_ask": self._level_price(outcome.get("bestAsk")),
                "outcome_status": outcome.get("status"),
                "market_status": market.get("status"),
            }
            record.update(self.store.match_position_to_trade(
                market_id, record["outcome_name"]
            ))
            out.append(record)
        return out

    def refresh_positions(self) -> Tuple[bool, str]:
        """Pull the venue's own view of everything we hold.

        Paginated with the documented `first`/`after` cursor. A partial page
        set is discarded rather than written, because replace_venue_positions
        treats what it receives as complete and a truncated list would silently
        delete real positions.
        """
        if not self.predict_account:
            return False, "PREDICT_ACCOUNT_ADDRESS is not set"
        collected: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        try:
            for _page in range(10):
                params = {"first": PREDICT_POSITIONS_PAGE}
                if cursor:
                    params["after"] = cursor
                path = (
                    f"{PREDICT_POSITIONS_PATH}/{self.predict_account}?"
                    + urllib.parse.urlencode(params)
                )
                code, payload = self._request("GET", path)
                if code != 200 or not isinstance(payload, dict):
                    return False, f"positions HTTP {code}"
                if not payload.get("success", True):
                    return False, "positions request rejected"
                collected.extend(self._parse_positions(payload.get("data")))
                cursor = payload.get("cursor")
                if not cursor:
                    break
        except PredictRequestNotSent as exc:
            return False, str(exc)[:120]
        except Exception as exc:
            return False, str(exc)[:120]
        stamp = now_ms()
        self.store.replace_venue_positions(collected, stamp)
        with self._readiness_lock:
            self._positions_error = ""
            self._positions_checked_ms = stamp
            self._positions_count = len(collected)
        return True, ""

    def _positions_loop(self) -> None:
        """Poll positions slowly, and promptly after anything fills."""
        while not self.stop_event.is_set():
            due = PREDICT_POSITIONS_POLL_SEC
            if self._positions_wake.is_set():
                self._positions_wake.clear()
                due = PREDICT_POSITIONS_FAST_SEC
                time.sleep(due)
            ok, error = self.refresh_positions()
            if not ok:
                with self._readiness_lock:
                    self._positions_error = error
                    self._positions_checked_ms = now_ms()
            self._positions_wake.wait(timeout=PREDICT_POSITIONS_POLL_SEC)

    def note_fill_for_positions(self) -> None:
        """Called after a fill so the venue view catches up quickly."""
        self._positions_wake.set()

    def _r5_new_http_connection(self) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(
            self._r5_http_host,
            self._r5_http_port,
            timeout=PREDICT_TIMEOUT,
            context=self._r5_ssl_context,
        )

    def _r5_http_connection(self, lane: str) -> http.client.HTTPSConnection:
        lane = "POST" if str(lane).upper() == "POST" else "GET"
        conn = self._r5_http_connections.get(lane)
        if conn is None:
            conn = self._r5_new_http_connection()
            self._r5_http_connections[lane] = conn
        return conn

    def _r5_drop_http_connection(self, lane: str) -> None:
        lane = "POST" if str(lane).upper() == "POST" else "GET"
        conn = self._r5_http_connections.get(lane)
        self._r5_http_connections[lane] = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _r5_background_prewarm_post_connection(self) -> None:
        """Warm temporary POST TLS without holding the order-lane lock."""
        temp = None
        try:
            temp = self._r5_new_http_connection()
            temp.connect()
            with self._r5_http_locks["POST"]:
                existing = self._r5_http_connections.get("POST")
                if existing is None or getattr(existing, "sock", None) is None:
                    if existing is not None:
                        try:
                            existing.close()
                        except Exception:
                            pass
                    self._r5_http_connections["POST"] = temp
                    temp = None
        except Exception as exc:
            self.last_error = f"Predict.fun HTTPS prewarm: {exc}"[:180]
        finally:
            if temp is not None:
                try:
                    temp.close()
                except Exception:
                    pass

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Any]:
        """Predict.fun REST using the proven urllib transport.

        R5 briefly replaced this with a hand-managed persistent
        ``http.client.HTTPSConnection``. In live AWS use that transport turned
        every order submission into an immediate ambiguous UNKNOWN. The order
        protocol itself was not the problem: pre-R5 builds used this urllib
        path successfully. Restore only the transport while preserving R5's
        exact-hash UNKNOWN safety and background reconciliation semantics.
        """
        token, _generation = self.auth.token_and_generation()
        if not token:
            raise PredictRequestNotSent(
                "verified Predict.fun authentication is unavailable"
            )
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": f"btc-model/{VERSION}",
                "x-api-key": self.api_key,
                "Authorization": f"Bearer {token}",
            }
            body = (
                json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
                if payload is not None else None
            )
            request = urllib.request.Request(
                PREDICT_BASE_MAINNET + path,
                data=body, headers=headers, method=str(method).upper(),
            )
            self.book._reserve_request(path)
        except PredictRequestNotSent:
            raise
        except Exception as exc:
            raise PredictRequestNotSent(str(exc)) from exc

        try:
            with urllib.request.urlopen(
                request, timeout=PREDICT_TIMEOUT
            ) as response:
                self.book._capture_rate_headers(response.headers)
                raw = response.read()
                if not raw:
                    data: Any = {}
                else:
                    try:
                        data = json.loads(raw.decode())
                    except (UnicodeDecodeError, ValueError):
                        data = {"raw": raw.decode(errors="replace")[:180]}
                code = int(response.status)
                if code in (401, 403):
                    self.auth.invalidate(
                        f"authenticated REST request returned HTTP {code}"
                    )
                return code, data
        except urllib.error.HTTPError as exc:
            self.book._capture_rate_headers(exc.headers)
            raw = exc.read()
            try:
                data = json.loads(raw.decode()) if raw else {}
            except Exception:
                data = {"error": f"HTTP {exc.code}"}
            code = int(exc.code)
            if code in (401, 403):
                self.auth.invalidate(
                    f"authenticated REST request returned HTTP {code}"
                )
            return code, data

    @staticmethod
    def _vwap_from_sdk_book_data(
        book_data: Dict[str, Any], stake: float
    ) -> Dict[str, Any]:
        """Full-stake executable VWAP from the exact ladder used to sign.

        For DOWN, ``sdk_book_data`` has already complemented the YES ladder
        into a NO ladder, so the asks are directly executable BUY levels.
        """
        remaining = max(0.0, float(stake))
        shares = 0.0
        spent = 0.0
        worst = None
        levels = []
        for row in list(book_data.get("asks") or []):
            try:
                price, qty = float(row[0]), float(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            if 0.0 < price <= 1.0 and qty > 0.0:
                levels.append((price, qty))
        levels.sort(key=lambda item: item[0])
        for price, qty in levels:
            if remaining <= PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD:
                break
            take_value = min(remaining, price * qty)
            if take_value <= 0.0:
                continue
            take_shares = take_value / price
            spent += take_value
            shares += take_shares
            remaining -= take_value
            worst = price
        ok = bool(
            shares > 0.0
            and remaining <= PREDICT_STAKE_QUANTIZATION_TOLERANCE_USD
        )
        return {
            "ok": ok,
            "vwap": (spent / shares if shares > 0.0 else None),
            "max_price": worst,
            "shares": shares,
            "spent": spent,
            "remaining": max(0.0, remaining),
        }

    def _build_payload(
        self, prediction: Prediction, stake: float,
        *, slippage_bps: Optional[int] = None, builder: Any = None,
        dynamic_ef_slippage: bool = False,
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        sdk = self._sdk
        signer = builder if builder is not None else self._builder
        if signer is None:
            raise RuntimeError("Predict.fun order builder is unavailable")
        # Contract metadata and its ladder must come from the same market.
        # Copy both under one short lock, then release it before SDK signing so
        # websocket updates are never held up by cryptography.
        with self.book._lock:
            if self.book.market_candle_id != prediction.candle_id:
                raise RuntimeError(
                    "Predict.fun book does not match the signal candle"
                )
            contract = self.book.market_contract(prediction.direction)
            book_data = self.book.sdk_book_data(prediction.direction)
        execution = self._vwap_from_sdk_book_data(book_data, stake)
        # EF dynamic tolerance is derived from THIS exact copied ladder, not a
        # second quote read. That keeps the full-stake VWAP, min-out tolerance
        # and signed amounts causally atomic even while websocket updates race
        # in the background. MAIN/REVERSAL continue using their fixed setting.
        if dynamic_ef_slippage:
            slip = ef_slippage_bps(execution.get("vwap"))
        else:
            slip = int(
                PREDICT_ORDER_SLIPPAGE_BPS
                if slippage_bps is None else slippage_bps
            )
        book = sdk["Book"](**{
            key: value for key, value in book_data.items() if key != "book_version"
        })
        amounts = signer.get_market_order_amounts(
            sdk["MarketHelperValueInput"](
                side=sdk["Side"].BUY,
                value_wei=int(round(stake * 10**18)),
                slippage_bps=slip,
                is_min_amount_out=True,
            ),
            book,
        )
        order = signer.build_order(
            "MARKET",
            sdk["BuildOrderInput"](
                side=sdk["Side"].BUY,
                token_id=contract["token_id"],
                maker_amount=str(amounts.maker_amount),
                taker_amount=str(amounts.taker_amount),
                fee_rate_bps=contract["fee_rate_bps"],
            ),
        )
        typed = signer.build_typed_data(
            order,
            is_neg_risk=contract["is_neg_risk"],
            is_yield_bearing=contract["is_yield_bearing"],
        )
        signed = signer.sign_typed_data_order(typed)
        order_hash = self._hash_key(signer.build_typed_data_hash(typed))
        signed_json = _plain_json(signed)
        if not isinstance(signed_json, dict):
            raise RuntimeError("predict-sdk returned an invalid signed order")
        signed_json["hash"] = order_hash
        maker_amount_wei = int(amounts.maker_amount)
        taker_amount_wei = int(amounts.taker_amount)
        if maker_amount_wei <= 0 or taker_amount_wei <= 0:
            raise RuntimeError("predict-sdk returned invalid market-order amounts")
        price_per_share_wei = int(amounts.price_per_share)
        quoted_price = price_per_share_wei / 10**18
        if not 0.0 < quoted_price <= 1.0:
            raise RuntimeError("predict-sdk returned an invalid share price")
        planned_stake = maker_amount_wei / 10**18
        max_price = maker_amount_wei / taker_amount_wei
        amount_meta = {
            "amount": str(amounts.amount),
            "price": quoted_price,
            "planned_stake": planned_stake,
            "max_price": max_price,
            # Exact signed minimum share output for final live-ladder viability.
            "taker_amount_wei": taker_amount_wei,
            "market_id": str(book_data["market_id"]),
            "book_ms": int(book_data.get("update_timestamp_ms") or 0),
            "book_version": int(book_data.get("book_version") or 0),
            "execution_vwap": execution.get("vwap"),
            "execution_max_price": execution.get("max_price"),
            "execution_shares": execution.get("shares"),
            "execution_ok": bool(execution.get("ok")),
            "slippage_bps": int(amounts.slippage_bps),
            "is_min_amount_out": bool(amounts.is_min_amount_out),
        }
        payload = {
            "data": {
                "timestamp": now_ms(),
                "pricePerShare": str(price_per_share_wei),
                "strategy": "MARKET",
                "slippageBps": str(amounts.slippage_bps),
                "isFillOrKill": True,
                "isPostOnly": False,
                "isMinAmountOut": bool(amounts.is_min_amount_out),
                "amount": str(amounts.amount),
                "order": signed_json,
            }
        }
        return order_hash, payload, amount_meta

    @staticmethod
    def _event_state(event: Dict[str, Any]) -> str:
        nested_order = event.get("order") if isinstance(event, dict) else None
        nested_status = (
            nested_order.get("status") if isinstance(nested_order, dict) else ""
        )
        return re.sub(r"[^A-Za-z]", "", str(
            event.get("type") or event.get("status") or nested_status or ""
        )).upper()

    def on_wallet_event(self, event: Dict[str, Any]) -> None:
        order_hash = self._hash_key(
            event.get("orderHash") or event.get("order_hash")
        )
        if not order_hash:
            return
        with self._event_lock:
            self._events[order_hash] = dict(event)
        self._apply_event(order_hash, event)

    def _apply_event(self, order_hash: str, event: Dict[str, Any]) -> str:
        order_hash = self._hash_key(order_hash)
        with self._event_lock:
            context = self._contexts.get(order_hash)
            if context is None:
                return self._event_state(event)
            state = self._event_state(event)
            candle_id, kind = context["candle_id"], context["kind"]
            order_id = event.get("orderId") or event.get("order_id")
            changes: Dict[str, Any] = {
                "order_status": state or "WALLET_EVENT",
            }
            if order_id is not None:
                changes["order_id"] = str(order_id)
            fill = event.get("fill") or {}
            if state == "ORDERTRANSACTIONSUCCESS" and isinstance(fill, dict):
                try:
                    settlement_id = str(
                        event.get("settlementId")
                        or json.dumps(fill, sort_keys=True)
                    )
                    size = int(str(
                        fill.get("executedSizeWei") or "0"
                    )) / 10**18
                    value = int(str(
                        fill.get("executedValueWei") or "0"
                    )) / 10**18
                    price = int(str(
                        fill.get("executedPriceWei") or "0"
                    )) / 10**18
                    if size <= 0.0 or value < 0.0 or not 0.0 < price <= 1.0:
                        raise ValueError("non-positive fill values")
                    fee = event.get("fee") or {}
                    if not isinstance(fee, dict):
                        fee = {}
                    fee_amount = int(str(
                        fee.get("amountWei") or "0"
                    )) / 10**18
                    fee_type = str(fee.get("type") or "").upper()
                    try:
                        confirmed_ms = int(event.get("timestamp") or now_ms())
                    except (TypeError, ValueError):
                        confirmed_ms = now_ms()
                    aggregate = self.store.apply_order_fill(
                        candle_id=candle_id,
                        kind=kind,
                        order_hash=order_hash,
                        settlement_id=settlement_id,
                        executed_price=price,
                        executed_shares=size,
                        executed_value=value,
                        fee_amount=fee_amount,
                        fee_type=fee_type,
                        quoted_price=float(context.get("quoted_price") or 0.0),
                        confirmed_ms=confirmed_ms,
                    )
                    if aggregate is not None:
                        context["filled_shares"] = aggregate["shares"]
                        context["filled_value"] = aggregate["value"]
                    context["has_fill"] = True
                    # v7.8: a fill changes what we hold, so pull the venue's
                    # position view promptly instead of waiting a full cycle.
                    self.note_fill_for_positions()
                except (TypeError, ValueError, RuntimeError) as exc:
                    changes.update({
                        "order_status": "FILLED_DETAILS_PENDING",
                        "failure_reason": (
                            f"wallet fill could not be verified: {exc}"
                        )[:180],
                    })
                    context["next_check"] = time.monotonic()
                    self.last_error = changes["failure_reason"]
            elif state in PREDICT_ORDER_TERMINAL_FAILURES:
                changes["failure_reason"] = str(
                    event.get("reason") or state
                )[:180]
            self.store.update_trade_execution(candle_id, kind, **changes)
            has_fill = bool(context.get("has_fill"))
        if has_fill:
            self.store.recalculate_settled_trade(candle_id, kind)
            if str(kind).upper() == "EF":
                pred = context.get("prediction") if isinstance(context, dict) else None
                self.clear_ef_hot(
                    int(candle_id), int(pred.ts_ms) if pred is not None else None
                )
        if has_fill or state in PREDICT_ORDER_TERMINAL_FAILURES:
            self._grade_if_closed(candle_id)
        return state

    def _grade_if_closed(self, candle_id: int) -> None:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT actual FROM candles WHERE candle_id=?", (int(candle_id),)
            ).fetchone()
        if row is None:
            return
        for source, won in self.store.settle_trades_and_report(
            candle_id, str(row["actual"])
        ):
            self.controls.record_result(source, won)

    def _rest_match_fills(self, order_hash: str) -> int:
        """Recover missed wallet events from Predict.fun match history.

        The authenticated wallet topic intentionally has no replay snapshot.
        This path is therefore used only for crash/reconnect recovery, and only
        for the exact signed hash. Normal fills remain websocket-only.
        """
        context = self._contexts.get(order_hash)
        if context is None:
            return 0
        market_id = context.get("market_id") or self.book.market_id
        params: Dict[str, Any] = {"first": 50}
        if market_id is not None:
            params["marketId"] = market_id
        if self.predict_account:
            params["signerAddress"] = self.predict_account
        code, payload = self._request(
            "GET", "/v1/orders/matches?" + urllib.parse.urlencode(params)
        )
        if code >= 400 or not isinstance(payload, dict):
            return 0
        matches = payload.get("data") or []
        if not isinstance(matches, list):
            return 0
        recovered = 0
        for match_index, item in enumerate(matches):
            if not isinstance(item, dict):
                continue
            legs: List[Tuple[str, Dict[str, Any]]] = []
            taker = item.get("taker")
            if isinstance(taker, dict):
                legs.append(("taker", taker))
            makers = item.get("makers") or []
            if isinstance(makers, list):
                legs.extend(
                    (f"maker{index}", leg)
                    for index, leg in enumerate(makers)
                    if isinstance(leg, dict)
                )
            for leg_name, leg in legs:
                nested = leg.get("order") if isinstance(leg.get("order"), dict) else {}
                leg_hash = str(
                    leg.get("hash") or leg.get("orderHash")
                    or nested.get("hash") or ""
                )
                if leg_hash.lower() != order_hash.lower():
                    continue
                try:
                    size = float(item.get("amountFilled") or leg.get("amount") or 0.0)
                    price = float(item.get("priceExecuted") or leg.get("price") or 0.0)
                except (TypeError, ValueError):
                    continue
                if size <= 0.0 or not (0.0 < price <= 1.0):
                    continue
                fee = leg.get("fee") if isinstance(leg.get("fee"), dict) else None
                fee_event: Optional[Dict[str, Any]] = None
                if fee is not None:
                    try:
                        fee_amount = float(fee.get("amount") or 0.0)
                    except (TypeError, ValueError):
                        fee_amount = 0.0
                    fee_event = {
                        "amountWei": str(max(0, int(round(fee_amount * 10**18)))),
                        "type": str(fee.get("type") or ""),
                    }
                settlement = str(
                    item.get("transactionHash") or item.get("executedAt")
                    or f"match-{match_index}"
                )
                event: Dict[str, Any] = {
                    "type": "orderTransactionSuccess",
                    "orderHash": order_hash,
                    "settlementId": f"{settlement}:{leg_name}",
                    "timestamp": now_ms(),
                    "fill": {
                        "executedPriceWei": str(int(round(price * 10**18))),
                        "executedSizeWei": str(int(round(size * 10**18))),
                        "executedValueWei": str(int(round(size * price * 10**18))),
                    },
                }
                if fee_event is not None:
                    event["fee"] = fee_event
                self._apply_event(order_hash, event)
                recovered += 1
        return recovered

    def _rest_state(self, order_hash: str) -> Tuple[str, Dict[str, Any]]:
        try:
            code, payload = self._request("GET", f"/v1/orders/{order_hash}")
        except PREDICT_AMBIGUOUS_TRANSPORT_ERRORS:
            return "UNKNOWN", {}
        if code == 404:
            return "UNKNOWN", payload if isinstance(payload, dict) else {}
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}
        state = self._event_state(data)
        if code >= 400 and not state:
            state = "FAILED" if code in (400, 409, 410) else "UNKNOWN"
        context = self._contexts.get(order_hash)
        if context is not None and (
            state in {"FILLED", "MATCHED", "PARTIALLYFILLED"}
            or safe_float(data.get("amountFilled"), 0.0) > 0.0
        ):
            try:
                self._rest_match_fills(order_hash)
            except Exception as exc:
                self.last_error = f"fill recovery: {exc}"[:180]
        if state in PREDICT_ORDER_TERMINAL_FAILURES:
            terminal_event = dict(data)
            terminal_event.setdefault("status", state)
            self._apply_event(order_hash, terminal_event)
        elif context is not None and context.get("has_fill"):
            self.store.update_trade_execution(
                context["candle_id"], context["kind"], order_status=state or "FILLED"
            )
        elif context is not None and state in {
            "FILLED", "MATCHED", "PARTIALLYFILLED"
        }:
            # Never invent size/value from an aggregate status. Keep capital
            # reserved and retry exact-hash recovery until fill detail arrives.
            self.store.update_trade_execution(
                context["candle_id"], context["kind"],
                order_status="FILLED_DETAILS_PENDING",
                failure_reason=f"venue reports {state}; recovering exact fills",
            )
        elif state and context is not None:
            self.store.update_trade_execution(
                context["candle_id"], context["kind"], order_status=state
            )
        return state or "UNKNOWN", data

    def _wait_for_state(self, order_hash: str) -> str:
        deadline = time.monotonic() + PREDICT_ORDER_STATUS_TIMEOUT_SEC
        while time.monotonic() < deadline and not self.stop_event.is_set():
            with self._event_lock:
                event = self._events.get(order_hash)
            if event is not None:
                state = self._apply_event(order_hash, event)
                if state in PREDICT_ORDER_TERMINAL_FAILURES:
                    return "TERMINAL"
                if self._contexts[order_hash].get("has_fill"):
                    return "FILLED"
            self.stop_event.wait(0.04)
        state, _ = self._rest_state(order_hash)
        if self._contexts[order_hash].get("has_fill"):
            return "FILLED"
        if state in PREDICT_ORDER_TERMINAL_FAILURES:
            return "TERMINAL"
        return "UNKNOWN"

    def _submit_signed_order(
        self,
        prediction: Prediction,
        kind: str,
        stake: float,
        attempt: int,
        attempt_log: List[Dict[str, Any]],
        start: int,
        order_hash: str,
        payload: Dict[str, Any],
        amounts: Dict[str, Any],
        first_submit_ms: int,
    ) -> Tuple[str, Optional[int], Any]:
        """Apply the final controls and perform one linearized venue POST."""
        quoted = float(amounts["price"])
        with self.controls.submit_gate:
            current_ms = now_ms()
            # Attempt 1 is a fresh QUEUED intent by construction, so it cannot
            # have a prior submission. Avoid a redundant SQLite read on the
            # latency-critical first POST; retries still recover the original
            # submit timestamp exactly as before.
            if int(attempt) <= 1:
                existing: Dict[str, Any] = {}
                prior_submit_ms = None
            else:
                existing = self.store.trade_row(prediction.candle_id, kind) or {}
                prior_submit_ms = (
                    int(existing.get("first_submit_ms") or 0) or None
                    if existing.get("submitted_ms") is not None
                    else None
                )
            sx_blocked, sx_fields = self.controls.state_x.execution_block(
                current_ms, prior_submit_ms
            )
            allowed, why = self.controls.may_execute(kind, current_ms)
            if not allowed:
                changes: Dict[str, Any] = {
                    "filled": False,
                    "order_status": (
                        "FORBIDDEN" if attempt == 1 else "RETRY_BLOCKED"
                    ),
                    "failure_reason": (
                        f"FORBIDDEN: {why}" if attempt == 1
                        else f"safe retry blocked: {why}"
                    ),
                }
                if attempt == 1:
                    changes["forbidden"] = True
                if sx_blocked:
                    changes.update(sx_fields)
                self.store.update_trade_execution(
                    prediction.candle_id, kind, **changes
                )
                return "BLOCKED", None, None
            if sx_blocked:
                self.store.update_trade_execution(
                    prediction.candle_id,
                    kind,
                    filled=False,
                    stake=None,
                    order_status="STATE_X",
                    failure_reason="STATE X: current trade vetoed",
                    **sx_fields,
                )
                return "BLOCKED", None, None
            planned_stake = float(amounts.get("planned_stake", stake))
            stake_shortfall = max(0.0, float(stake) - planned_stake)
            if not _full_shared_stake_available(stake, planned_stake):
                self.store.update_trade_execution(
                    prediction.candle_id, kind, filled=False,
                    order_status="NO_LIQUIDITY", quoted_price=quoted,
                    failure_reason=(
                        f"full shared stake unavailable: requested ${stake:.4f}, "
                        f"executable ${planned_stake:.4f}, "
                        f"shortfall ${stake_shortfall:.4f}"
                    ),
                )
                return "BLOCKED", None, None
            signed_market_id = amounts.get("market_id")
            if signed_market_id is None and existing:
                signed_market_id = existing.get("market_id")
            context = {
                "candle_id": prediction.candle_id,
                "kind": kind,
                "prediction": prediction,
                "stake": stake,
                "attempt": attempt,
                "quoted_price": quoted,
                "has_fill": False,
                "filled_shares": 0.0,
                "filled_value": 0.0,
                "market_id": signed_market_id,
                "first_submit_ms": int(first_submit_ms),
                "book_version": int(amounts.get("book_version") or 0),
                "reconcile_count": 0,
                "restored": False,
            }
            with self._event_lock:
                self._contexts[order_hash] = context
            execution_changes: Dict[str, Any] = {
                "order_hash": order_hash,
                "order_status": "SUBMITTING",
                "submitted_ms": start,
                # v7.7: submitted_ms is this attempt's clock and is overwritten
                # by every replacement. first_submit_ms is written with the
                # same value on each attempt, so it stays the origin of the
                # whole order and delay_ms can report the real total.
                "first_submit_ms": first_submit_ms,
                "attempts": attempt,
                "retry_count": attempt - 1,
                "quoted_price": quoted,
                "attempt_log": attempt_log,
            }
            if signed_market_id is not None:
                execution_changes["market_id"] = signed_market_id
            self.store.update_trade_execution(
                prediction.candle_id, kind, **execution_changes
            )

            # R6.4 final EF fence: crash journal first, then re-check the newest
            # live ladder against the exact signed min-output immediately before
            # calling the network transport. A stale signature is rebuilt locally
            # and consumes ZERO Predict venue attempts. Book-version change alone
            # is never a reason to rebuild. MAIN/REV are untouched.
            if str(kind).upper() == "EF":
                fence_ns = mono_ns()
                try:
                    min_out_shares = int(amounts.get("taker_amount_wei") or 0) / 10**18
                except Exception:
                    min_out_shares = 0.0
                viability = self._ef_hot_viability(
                    {
                        "direction": prediction.direction,
                        "min_out_shares": min_out_shares,
                    },
                    stake,
                )
                self.latency.observe_ms(
                    "ef_final_fence_ms", (mono_ns() - fence_ns) / 1_000_000.0
                )
                if not viability.get("ok"):
                    with self._event_lock:
                        self._contexts.pop(order_hash, None)
                    attempt_log.append({
                        "attempt": attempt,
                        "order_hash": order_hash,
                        "submitted_ms": start,
                        "status": "LOCAL_REBUILD",
                        "detail": str(viability.get("reason") or "stale signed ladder"),
                    })
                    rollback: Dict[str, Any] = {
                        "order_hash": None,
                        "order_status": "HOT_REBUILD",
                        "submitted_ms": None,
                        "attempts": max(0, int(attempt) - 1),
                        "retry_count": max(0, int(attempt) - 2),
                        "failure_reason": (
                            f"{viability.get('reason')}; no HTTP POST sent"
                        )[:180],
                        "attempt_log": attempt_log,
                    }
                    if int(attempt) <= 1:
                        rollback["first_submit_ms"] = None
                    self.store.update_trade_execution(
                        prediction.candle_id, kind, **rollback
                    )
                    self.latency.inc("ef_final_fence_local_rebuild")
                    return "LOCAL_REBUILD", None, None

            request_ns = mono_ns()
            try:
                code, response = self._request("POST", "/v1/orders", payload)
                if str(kind).upper() == "EF":
                    self.latency.observe_ms(
                        "ef_post_roundtrip_ms",
                        (mono_ns() - request_ns) / 1_000_000.0,
                    )
            except PredictRequestNotSent as exc:
                # The local auth/rate/serialization gate ran before urlopen,
                # so this hash is provably absent from the venue. Remove it
                # from the recoverable set instead of reserving capital forever.
                with self._event_lock:
                    self._contexts.pop(order_hash, None)
                attempt_log.append({
                    "attempt": attempt, "order_hash": order_hash,
                    "submitted_ms": start, "status": "NOT_SENT",
                    "detail": type(exc).__name__,
                })
                self.store.update_trade_execution(
                    prediction.candle_id, kind,
                    order_hash=None, order_status="NOT_SENT",
                    submitted_ms=None,
                    failure_reason=f"local pre-submit gate: {str(exc)[:120]}",
                    attempt_log=attempt_log,
                )
                return "BLOCKED", None, None
            except PREDICT_AMBIGUOUS_TRANSPORT_ERRORS as exc:
                # The request may have reached the venue. Preserve the signed
                # hash and reconcile; never replace this ambiguity.
                attempt_log.append({
                    "attempt": attempt, "order_hash": order_hash,
                    "submitted_ms": start, "status": "UNKNOWN",
                    "detail": type(exc).__name__,
                })
                self.store.update_trade_execution(
                    prediction.candle_id, kind, order_status="UNKNOWN",
                    failure_reason=(
                        "submission response unknown; reconciling by hash"
                    ),
                    attempt_log=attempt_log,
                )
                self._contexts[order_hash]["next_check"] = time.monotonic()
                return "UNKNOWN", None, None
        return "RESPONSE", code, response

    def _attempt(
        self, prediction: Prediction, kind: str, stake: float, attempt: int,
        attempt_log: List[Dict[str, Any]],
        first_submit_ms: Optional[int] = None,
        prepared: Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]] = None,
    ) -> str:
        start = now_ms()
        if first_submit_ms is None:
            # A retry raised from _reconcile_unknowns has no caller-supplied
            # origin. Recover the one already journalled on the order row so a
            # late replacement still reports total, not per-attempt, latency.
            row = self.store.trade_row(prediction.candle_id, kind) or {}
            first_submit_ms = int(row.get("first_submit_ms") or 0) or start
        first_submit_ms = int(first_submit_ms)
        if prepared is None:
            order_hash, payload, amounts = self._build_payload(prediction, stake)
        else:
            order_hash, payload, amounts = prepared
        order_hash = self._hash_key(order_hash)
        phase, code, response = self._submit_signed_order(
            prediction, kind, stake, attempt, attempt_log, start,
            order_hash, payload, amounts, first_submit_ms,
        )
        if phase != "RESPONSE":
            return phase
        if code is None:
            raise RuntimeError("Predict.fun submission returned no HTTP status")
        data = response.get("data", response) if isinstance(response, dict) else {}
        order_id = data.get("orderId") if isinstance(data, dict) else None
        accepted_hash = self._hash_key(
            data.get("orderHash") if isinstance(data, dict) else None
        )
        if accepted_hash and accepted_hash != order_hash:
            # A response that names a different order is not proof that our
            # signed hash failed. Fail closed and reconcile only our hash.
            attempt_log.append({
                "attempt": attempt, "order_hash": order_hash,
                "submitted_ms": start, "status": "HASH_MISMATCH",
                "server_hash": accepted_hash,
            })
            self.store.update_trade_execution(
                prediction.candle_id, kind, order_status="UNKNOWN",
                failure_reason="venue response hash differed; reconciling signed hash",
                attempt_log=attempt_log,
            )
            self._contexts[order_hash]["next_check"] = time.monotonic()
            return "UNKNOWN"
        if code >= 400:
            state = self._event_state(data if isinstance(data, dict) else {})
            # 4xx validation/market responses prove the venue rejected this
            # submission. Auth/rate failures need operator action; 5xx remains
            # ambiguous because the server may have accepted before failing.
            explicit_rejection = code in (400, 404, 409, 410, 422)
            terminal = (
                state in PREDICT_ORDER_TERMINAL_FAILURES or explicit_rejection
            )
            recorded_state = state or (
                "FAILED" if explicit_rejection else f"HTTP_{code}"
            )
            attempt_log.append({
                "attempt": attempt, "order_hash": order_hash,
                "submitted_ms": start,
                "attempt_ms": now_ms() - start,
                "total_ms": now_ms() - first_submit_ms,
                "status": recorded_state,
            })
            self.store.update_trade_execution(
                prediction.candle_id, kind,
                order_id=str(order_id) if order_id is not None else None,
                order_status=recorded_state,
                failure_reason=str(response)[:180],
                delay_ms=now_ms() - first_submit_ms,
                last_attempt_ms=now_ms() - start,
                attempt_log=attempt_log,
            )
            if terminal or code in (401, 403, 429):
                # A definitive HTTP rejection means this signed hash cannot
                # fill. Keep it in the attempt journal, not in the active
                # order slot or reconciliation map.
                with self._event_lock:
                    self._contexts.pop(order_hash, None)
                self.store.update_trade_execution(
                    prediction.candle_id, kind, order_hash=None
                )
            if terminal:
                return "TERMINAL"
            if code in (401, 403, 429):
                # The venue explicitly refused the HTTP request, but retrying
                # cannot fix credentials or rate limits and would add latency.
                return "BLOCKED"
            self._contexts[order_hash]["next_check"] = time.monotonic()
            return "UNKNOWN"
        attempt_log.append({
            "attempt": attempt, "order_hash": order_hash,
            "order_id": order_id, "submitted_ms": start,
            "accepted_ms": now_ms(),
            "attempt_ms": now_ms() - start,
            "total_ms": now_ms() - first_submit_ms,
            "status": "ACCEPTED",
        })
        self.store.update_trade_execution(
            prediction.candle_id, kind,
            order_id=str(order_id) if order_id is not None else None,
            order_hash=order_hash, order_status="ACCEPTED",
            # v7.7: total time from the FIRST submission of this order, so a
            # retried order no longer hides the cost of its earlier attempts.
            delay_ms=now_ms() - first_submit_ms,
            last_attempt_ms=now_ms() - start,
            attempt_log=attempt_log,
        )
        outcome = self._wait_for_state(order_hash)
        if outcome == "UNKNOWN":
            self.store.update_trade_execution(
                prediction.candle_id, kind, order_status="UNKNOWN",
                failure_reason="accepted; awaiting wallet/REST confirmation",
                attempt_log=attempt_log,
            )
            self._contexts[order_hash]["next_check"] = time.monotonic()
        return outcome

    @staticmethod
    def _r5_job_matches_trade(prediction: Prediction, trade: Dict[str, Any]) -> bool:
        # Exact opportunity fence for at-least-once queue delivery.
        try:
            same_ts = int(trade.get("ts_ms") or -1) == int(prediction.ts_ms)
        except Exception:
            same_ts = False
        same_dir = (
            str(trade.get("direction") or "").upper()
            == str(prediction.direction or "").upper()
        )
        return bool(same_ts and same_dir)

    def _r5_release_ef_if_definitive(
        self, prediction: Optional[Prediction], kind: str
    ) -> None:
        # Hashless local/pre-submit failures can release immediately.
        if prediction is None or str(kind).upper() != "EF":
            return
        row = self.store.trade_row(prediction.candle_id, "EF") or {}
        if not self._r5_job_matches_trade(prediction, row):
            return
        if bool(row.get("filled")) or str(row.get("order_hash") or "").strip():
            return
        status = str(row.get("order_status") or "").upper()
        safe_statuses = {
            "PRICE_LIMIT", "WRONG_MARKET", "NOT_SENT", "NO_FRESH_BOOK",
            "NO_LIQUIDITY", "QUEUE_FULL"
        } | set(PREDICT_ORDER_TERMINAL_FAILURES)
        if status not in safe_statuses:
            return
        self.store.r5_release_failed_ef(
            prediction.candle_id,
            prediction.ts_ms,
            prediction.direction,
            str(row.get("failure_reason") or status),
        )

    def _r5_no_other_live_context_locked(
        self, order_hash: str, candle_id: int, kind: str
    ) -> bool:
        key = self._hash_key(order_hash)
        for other_hash, other in self._contexts.items():
            if self._hash_key(other_hash) == key:
                continue
            if (
                int(other.get("candle_id") or -1) == int(candle_id)
                and str(other.get("kind") or "").upper() == str(kind).upper()
                and not bool(other.get("has_fill"))
            ):
                return False
        return True

    def _r5_prepare_terminal_retry(
        self, order_hash: str, context: Dict[str, Any], state: str
    ) -> bool:
        # Retire exactly one proven-dead hash before queueing its replacement.
        key = self._hash_key(order_hash)
        terminal = str(state or "").upper()
        if not key or terminal not in set(PREDICT_ORDER_TERMINAL_FAILURES):
            return False
        prediction = context.get("prediction")
        kind = str(context.get("kind") or "")
        if prediction is None or kind not in TRADE_KINDS:
            return False
        with self._event_lock:
            current = self._contexts.get(key)
            if current is not context or bool(current.get("has_fill")):
                return False
            if self.store.r5_order_hash_has_fill(key):
                return False
            row = self.store.trade_row(prediction.candle_id, kind) or {}
            if not self._r5_job_matches_trade(prediction, row):
                return False
            if self._hash_key(row.get("order_hash")) != key:
                return False
            if not self._r5_no_other_live_context_locked(
                key, prediction.candle_id, kind
            ):
                return False
            # UNKNOWN keeps accounting unresolved while the safe replacement
            # waits behind all fresh signal work on the serial POST worker.
            self.store.update_trade_execution(
                prediction.candle_id,
                kind,
                order_hash=None,
                order_status="UNKNOWN",
                failure_reason=f"{terminal}: old hash terminal; safe replacement queued"[:180],
            )
            self._contexts.pop(key, None)
            self._events.pop(key, None)
        return True

    def _r5_release_ef_after_terminal_proof(
        self, order_hash: str, context: Dict[str, Any], state: str
    ) -> bool:
        # Hash-bearing EF release requires terminal state + no fill + exact identity.
        key = self._hash_key(order_hash)
        terminal = str(state or "").upper()
        if not key or terminal not in set(PREDICT_ORDER_TERMINAL_FAILURES):
            return False
        prediction = context.get("prediction")
        if prediction is None or str(context.get("kind") or "").upper() != "EF":
            return False
        with self._event_lock:
            current = self._contexts.get(key)
            if current is not context or bool(current.get("has_fill")):
                return False
            if self.store.r5_order_hash_has_fill(key):
                return False
            row = self.store.trade_row(prediction.candle_id, "EF") or {}
            if not self._r5_job_matches_trade(prediction, row):
                return False
            if self._hash_key(row.get("order_hash")) != key:
                return False
            if not self._r5_no_other_live_context_locked(
                key, prediction.candle_id, "EF"
            ):
                return False
            released = self.store.r5_release_failed_ef(
                prediction.candle_id,
                prediction.ts_ms,
                prediction.direction,
                str(row.get("failure_reason") or terminal),
                proven_terminal_hash=key,
                proven_terminal_state=terminal,
            )
            if released:
                self._contexts.pop(key, None)
                self._events.pop(key, None)
            return bool(released)

    def _r5_execute_retry(self, retry: Tuple[Any, ...]) -> None:
        # Terminal-proof replacements POST only from the serial order worker.
        prediction, kind, stake, attempt, logs = retry
        row = self.store.trade_row(prediction.candle_id, kind) or {}
        if (
            not self._r5_job_matches_trade(prediction, row)
            or bool(row.get("filled"))
            or str(row.get("order_hash") or "").strip()
        ):
            try:
                self.latency.inc("stale_retry_job")
            except Exception:
                pass
            return
        try:
            self._attempt(prediction, kind, float(stake), int(attempt), list(logs))
        finally:
            self._r5_release_ef_if_definitive(prediction, kind)

    def _execute_r4(
        self, prediction: Prediction, kind: str,
        trade: Optional[Dict[str, Any]] = None,
    ) -> None:
        # _execute() already fetched and identity-checked this row. Reuse it on
        # the normal worker path to avoid a redundant SQLite read before sign.
        if trade is None:
            trade = self.store.trade_row(prediction.candle_id, kind)
        if trade is None:
            return
        if (
            bool(trade.get("filled"))
            or str(trade.get("order_hash") or "").strip()
            or str(trade.get("order_status") or "").upper() != "QUEUED"
        ):
            # Queue delivery is at-least-once; the sqlite order slot is not.
            # Never turn a repeated job into a repeated live submission.
            return
        current_ms = now_ms()
        sx_blocked, sx_fields = self.controls.state_x.execution_block(current_ms)
        allowed, why = self.controls.may_execute(kind, current_ms)
        if not allowed:
            changes = {
                "filled": False,
                "forbidden": True,
                "order_status": "FORBIDDEN",
                "failure_reason": f"FORBIDDEN: {why}",
            }
            if sx_blocked:
                changes.update(sx_fields)
            self.store.update_trade_execution(prediction.candle_id, kind, **changes)
            return
        if sx_blocked:
            self.store.update_trade_execution(
                prediction.candle_id,
                kind,
                filled=False,
                stake=None,
                order_status="STATE_X",
                failure_reason="STATE X: current trade vetoed",
                **sx_fields,
            )
            return
        stake = float(trade.get("stake") or 0.0)
        # Reuse the already allocated row stake so readiness does not perform a
        # second configured-stake lookup on the order hot path.
        ready = self.readiness(required_stake=stake)
        if not ready["ready"]:
            reason = "not ready: " + ", ".join(ready["missing"])
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="NOT_SENT", failure_reason=reason,
            )
            self.last_error = reason[:180]
            return
        with self.book._lock:
            selected_market = dict(self.book._current_market)
            selected_market_candle = self.book.market_candle_id
        strict_five_minute_match = bool(
            selected_market
            and self.book._rank_markets(
                [selected_market], prediction.candle_id
            )
        )
        if (
            selected_market_candle != prediction.candle_id
            or not strict_five_minute_match
        ):
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="WRONG_MARKET",
                failure_reason=(
                    "Predict.fun selected market is not the exact BTC "
                    "5-minute signal candle"
                ),
            )
            return
        live_quote = self.book.quote(prediction.direction)
        live_price = live_quote.get("price")
        if live_price is None:
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="NO_FRESH_BOOK",
                failure_reason="no fresh Predict.fun websocket quote",
            )
            return
        remaining = prediction.candle_id + CANDLE_MS - now_ms()
        if remaining < PREDICT_ORDER_MIN_REMAINING_MS:
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="TOO_LATE",
                failure_reason="insufficient candle time for safe submission",
            )
            return
        capital = self.store.capital_state()
        floor = float(
            self.store.control_row(SYSTEM_CONTROL_KIND)["stake"].get(
                "min_stake", MIN_STAKE_USD
            )
        )
        # capital.free already excludes this queued row. Add its own reserve
        # back when proving that the previously allocated full stake is still
        # funded; otherwise a 100%-of-wallet stake would reject itself.
        # v7.7: funding uses `wallet`, never `balance`. Unredeemed winnings
        # size the next stake but cannot pay for this order.
        available_for_this_order = max(
            0.0,
            float(capital.get("wallet", capital["balance"]))
            - max(0.0, float(capital["reserved"]) - stake),
        )
        if stake < floor or available_for_this_order + 1e-9 < stake:
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="NO_CAPITAL",
                failure_reason=(
                    f"available capital ${available_for_this_order:.2f} "
                    f"cannot fund full shared stake ${stake:.2f}"
                ),
            )
            return
        with self._readiness_lock:
            wallet_balance = self._wallet_balance_usd
            wallet_checked_ms = self._balance_checked_ms
        wallet_age_sec = (
            float("inf") if not wallet_checked_ms
            else (now_ms() - wallet_checked_ms) / 1000.0
        )
        if (
            wallet_balance is None
            or wallet_age_sec > PREDICT_BALANCE_STALE_SEC
            or wallet_balance + 1e-9 < stake
        ):
            detail = (
                "no fresh on-chain balance"
                if wallet_balance is None or wallet_age_sec > PREDICT_BALANCE_STALE_SEC
                else f"wallet ${wallet_balance:.2f} below stake ${stake:.2f}"
            )
            self.store.update_trade_execution(
                prediction.candle_id, kind, filled=False,
                order_status="NO_WALLET_CAPITAL",
                failure_reason=f"smart-account funding check failed: {detail}",
            )
            return
        self.store.update_trade_execution(
            prediction.candle_id, kind, order_status="SIGNING"
        )
        attempt_log: List[Dict[str, Any]] = []
        outcome = "UNKNOWN"
        # v7.7: one origin for every attempt of this order. delay_ms is then
        # the total the operator actually waited, not the last retry alone.
        first_submit_ms = now_ms()
        for attempt in range(1, PREDICT_ORDER_MAX_RETRIES + 2):
            outcome = self._attempt(
                prediction, kind, stake, attempt, attempt_log, first_submit_ms
            )
            if outcome != "TERMINAL":
                break
            row = self.store.trade_row(prediction.candle_id, kind) or {}
            if row.get("filled") or attempt > PREDICT_ORDER_MAX_RETRIES:
                break
            if prediction.candle_id + CANDLE_MS - now_ms() < PREDICT_ORDER_MIN_REMAINING_MS:
                break
            # Terminal failure is proof the previous order cannot fill. Refresh
            # the amount calculation from the newest websocket book immediately.
        self.last_order_ms = now_ms()
        self.last_status = f"{kind} {outcome}"

    def _execute(self, prediction: Prediction, kind: str) -> None:
        """R5 identity fence + preserved R4 execution + definitive EF release."""
        trade = self.store.trade_row(prediction.candle_id, kind)
        if trade is None:
            return
        if not self._r5_job_matches_trade(prediction, trade):
            try:
                self.latency.inc("stale_execution_job")
            except Exception:
                pass
            return
        try:
            self._execute_r4(prediction, kind, trade)
        finally:
            self._r5_release_ef_if_definitive(prediction, kind)

    def _reconcile_unknowns(self) -> None:
        # Paced exact-hash reconciliation; never submits a POST itself.
        current = time.monotonic()
        if current - self._last_reconcile < PREDICT_ORDER_RECONCILE_SEC:
            return
        for order_hash, context in list(self._contexts.items()):
            already_complete = (
                context.get("has_fill") and not context.get("restored")
            )
            if already_complete or current < context.get("next_check", float("inf")):
                continue
            self._last_reconcile = current
            try:
                with self._event_lock:
                    wallet_event = self._events.get(order_hash)
                wallet_state = (
                    self._event_state(wallet_event)
                    if isinstance(wallet_event, dict) else ""
                )
                if wallet_state in PREDICT_ORDER_TERMINAL_FAILURES:
                    state = wallet_state
                else:
                    state, _ = self._rest_state(order_hash)
            except Exception as exc:
                self.last_error = f"reconcile: {exc}"[:180]
                context["next_check"] = current + 1.0
                break

            if context.get("has_fill"):
                context["restored"] = False
                context["next_check"] = float("inf")
                break

            if state in PREDICT_ORDER_TERMINAL_FAILURES:
                prediction = context.get("prediction")
                kind = str(context.get("kind") or "")
                attempt = int(context.get("attempt") or 1)
                if prediction is not None and kind.upper() == "EF":
                    # R6.1 retry semantics: the original VWAP approval covers
                    # one four-attempt batch. Retire the proven-dead hash and
                    # continue attempts 2-4 immediately with no new price gate.
                    if self._r5_prepare_terminal_retry(order_hash, context, state):
                        used_state = {
                            "book_version": int(context.get("book_version") or 0),
                            "stake": float(context.get("stake") or 0.0),
                        }
                        self._ef_hot_transition_after_terminal(
                            prediction, used_state, attempt,
                            int(context.get("first_submit_ms") or now_ms()), state,
                        )
                    else:
                        with self._event_lock:
                            current_context = self._contexts.get(
                                self._hash_key(order_hash)
                            )
                            if current_context is context:
                                current_context["next_check"] = float("inf")
                else:
                    allowed, _ = self.controls.may_execute(kind, now_ms())
                    can_retry = bool(
                        prediction is not None
                        and allowed
                        and attempt <= PREDICT_ORDER_MAX_RETRIES
                        and prediction.candle_id + CANDLE_MS - now_ms()
                        >= PREDICT_ORDER_MIN_REMAINING_MS
                    )
                    queued_retry = False
                    if can_retry:
                        row = self.store.trade_row(prediction.candle_id, kind) or {}
                        try:
                            logs = json.loads(row.get("attempt_log") or "[]")
                        except Exception:
                            logs = []
                        if self._r5_prepare_terminal_retry(order_hash, context, state):
                            self._r5_retry_jobs.put((
                                prediction, kind, float(context["stake"]),
                                attempt + 1, logs,
                            ))
                            self._r5_dispatch_wake.set()
                            queued_retry = True
                    if not queued_retry:
                        with self._event_lock:
                            current_context = self._contexts.get(
                                self._hash_key(order_hash)
                            )
                            if current_context is context:
                                current_context["next_check"] = float("inf")
            else:
                count = int(context.get("reconcile_count") or 0) + 1
                context["reconcile_count"] = count
                context["next_check"] = current + min(
                    30.0,
                    PREDICT_ORDER_RECONCILE_SEC * (2 ** min(count, 6)),
                )
            break

    def _r5_sweep_hashless_price_limits(self) -> int:
        """Release any PRICE_LIMIT EF that cannot possibly be live.

        The normal order-worker finally block remains the fast path. This sweep
        is the fail-safe for any lifecycle race/exception that leaves a hashless
        PRICE_LIMIT row active: it archives the attempt and emits the same
        persistent re-arm tombstone for Engine to consume.
        """
        released = 0
        for row in self.store.r5_hashless_price_limit_rows():
            if self.store.r5_release_failed_ef(
                int(row["candle_id"]),
                int(row["ts_ms"]),
                str(row.get("direction") or ""),
                str(row.get("failure_reason") or "PRICE_LIMIT"),
            ):
                released += 1
        return released

    def _r5_reconciliation_worker(self) -> None:
        # REST fallback is isolated from the fresh serial POST dispatcher.
        while not self.stop_event.is_set():
            try:
                self._reconcile_unknowns()
            except Exception as exc:
                self.last_error = f"reconcile worker: {exc}"[:180]
            self.stop_event.wait(0.05)

    def _readiness_worker(self) -> None:
        """Keep stake/auth/approvals/balance warm without delaying EF prep."""
        while not self.stop_event.is_set():
            try:
                # Publish the shared stake BEFORE any potentially slow auth/RPC
                # readiness work. Both direction-owned signer lanes can then
                # prebuild as soon as a fresh Predict book exists.
                self._ef_hot_refresh_stake_hint()
                for event in self._ef_hot_wake.values():
                    event.set()
                self.refresh_live_readiness()
            except Exception as exc:
                # This worker never changes master state and never submits a
                # transaction. Its only failure mode is a closed readiness gate.
                self.last_error = f"live readiness: {exc}"[:180]
            try:
                # Keep the fixed SX timer honest even when no dashboard is
                # open and no signal lands exactly at expiry. This only clears
                # the persisted pause and emits its one terminal notification.
                self.controls.state_x.snapshot()
            except Exception as exc:
                self.last_error = f"State X timer: {exc}"[:180]
            self.stop_event.wait(1.0)

    def run(self) -> None:
        # Seed stake synchronously from local DB/capital state so the first
        # eligible candle never waits for slow readiness/auth work.
        self._ef_hot_refresh_stake_hint()
        for side in ("UP", "DOWN"):
            thread = threading.Thread(
                target=self._ef_hot_loop_side,
                args=(side,),
                name=f"predict-ef-hot-{side.lower()}",
                daemon=True,
            )
            self._ef_hot_threads[side] = thread
            thread.start()
            self._ef_hot_wake[side].set()
        threading.Thread(
            target=self._readiness_worker,
            name="predict-readiness", daemon=True,
        ).start()
        threading.Thread(
            target=self._r5_reconciliation_worker,
            name="predict-reconcile", daemon=True,
        ).start()
        threading.Thread(
            target=self._positions_loop,
            name="predict-positions", daemon=True,
        ).start()
        while not self.stop_event.is_set():
            # Clear before probing queues so an enqueue racing this section
            # leaves the event set and the wait returns immediately.
            self._r5_dispatch_wake.clear()
            did_work = False
            try:
                prediction, kind = self.jobs.get_nowait()
            except queue.Empty:
                prediction = kind = None
            if prediction is not None:
                did_work = True
                try:
                    self._execute(prediction, kind)
                except Exception as exc:
                    self.last_error = str(exc)[:180]
                    self.last_status = f"{kind} ERROR"
                    self.store.update_trade_execution(
                        prediction.candle_id, kind, filled=False,
                        order_status="ERROR", failure_reason=self.last_error,
                    )
                finally:
                    self.jobs.task_done()

            # A QUEUE_FULL EF had no possible POST. Once fresh capacity exists,
            # archive/re-arm it before terminal replacements.
            try:
                if self._r5_process_deferred_ef_release():
                    did_work = True
            except Exception as exc:
                self.last_error = f"deferred EF release: {exc}"[:180]

            # Proven-terminal replacements are lower priority than fresh work.
            if not did_work:
                try:
                    retry = self._r5_retry_jobs.get_nowait()
                except queue.Empty:
                    retry = None
                if retry is not None:
                    did_work = True
                    try:
                        self._r5_execute_retry(retry)
                    except Exception as exc:
                        self.last_error = f"safe retry: {exc}"[:180]

            if not did_work:
                self._r5_dispatch_wake.wait(0.05)


def book_worker(
    engine: "Engine", socket_thread: PredictWebSocket, stop: threading.Event
) -> None:
    """Discover each five-minute market; WebSocket owns book updates."""
    while not stop.is_set():
        try:
            with engine.lock:
                candle_id = int(engine.candle["time"]) if engine.candle else None
            engine.book.refresh(candle_id)
            socket_thread.ensure_subscriptions()
        except Exception as exc:
            engine.book.error = f"discovery: {exc}"[:180]
        stop.wait(PREDICT_DISCOVERY_POLL_SEC)


class Engine:
    def __init__(self, store: Store) -> None:
        self.store = store
        # One authority for bans, toggles and staking. Signal code never
        # asks these questions itself.
        self.controls = TradeControls(store)
        self.lock = threading.RLock()
        self.started_ms = now_ms()
        self.stop_event = threading.Event()
        self.latency = LatencyTelemetry()
        self.market_events: "queue.Queue[Tuple[str, Dict[str, Any], int, int]]" = queue.Queue(
            maxsize=max(256, int(os.getenv("BTC_MARKET_QUEUE_MAX", "8192")))
        )
        self.market_queue_dropped = 0
        self.market_queue_max_depth = 0
        self.market_queue_overflow = threading.Event()
        self._processor_thread: Optional[threading.Thread] = None
        # EF execution lifecycle has its own tiny watchdog. It is deliberately
        # separate from the BTC market processor so failed-order cleanup can
        # never depend on another Binance/depth event or add SQLite work to the
        # signal hot path.
        self._ef_lifecycle_thread: Optional[threading.Thread] = None
        self._ef_lifecycle_last_identity: Optional[Tuple[int, int, str]] = None
        self._ef_lifecycle_next_db_mono = 0.0
        self._pending_closed_candle: Optional[Tuple[Dict[str, Any], int]] = None
        self._pending_restore_candle_id: Optional[int] = None

        self.trade_ticks: Deque[Tuple[int, float, float, float]] = deque(maxlen=80_000)
        self.price_ticks: Deque[Tuple[int, float]] = deque(maxlen=80_000)
        self.delta_250ms = RollingDelta(250)
        self.delta_1s = RollingDelta(1_000)
        self.delta_2s = RollingDelta(2_000)
        self.delta_5s = RollingDelta(5_000)
        self.delta_30s = RollingDelta(30_000)
        self.ofi_1s = RollingSignedMean(1_000)
        self.ofi_5s = RollingSignedMean(5_000)
        self.price_path = RollingPricePath(30_000)
        self.open_sides = RollingOpenSides(30_000)

        self.depth: Dict[str, Any] = {"bids": [], "asks": [], "ts_ms": 0}
        self.previous_top: Optional[Tuple[float, float, float, float]] = None
        # EF owns these rings. MAIN/REVERSAL never read them.
        self.ef_depth_history: Deque[Dict[str, Any]] = deque(maxlen=320)
        # EF measures ages in milliseconds, so every EF input is stamped with
        # ONE clock: the local receive clock. depth5@100ms carries no exchange
        # "E" field while aggTrade does, so a monotonic max over both freezes
        # between sparse trades and collapses depth timestamps into lumps.
        self.ef_trade_ticks: Deque[Tuple[int, float, float, float]] = deque(maxlen=80_000)
        self.clock_skew_ms: Optional[int] = None
        # Per-stream arrival tracking. "live" is set by the first message of
        # any stream, so a dead depth subscription is invisible behind healthy
        # aggTrade traffic. EF needs depth history, so it starves silently.
        self.stream_stats: Dict[str, Dict[str, Any]] = {
            name: {"count": 0, "last_ms": 0, "rate": 0.0,
                   "max_gap_ms": 0, "window_count": 0, "window_started": 0.0}
            for name in ("aggTrade", "depth", "kline")
        }
        self.ef_flow_series: Deque[Tuple[int, int]] = deque(maxlen=500)
        self.ef_spoof_state: Dict[str, Any] = {}
        # v4.5: aggressive cluster detection on top-of-book quote volume
        self.bid_volume_history: Deque[float] = deque(maxlen=CLUSTER_WINDOW)
        self.ask_volume_history: Deque[float] = deque(maxlen=CLUSTER_WINDOW)
        self.aggressive_bid_cluster = 0.0
        self.aggressive_ask_cluster = 0.0
        # v4.5: per-candle aggressive volume profile
        self.candle_buy_quote = 0.0
        self.candle_sell_quote = 0.0
        self.candle: Optional[Dict[str, Any]] = None
        self.candles: Deque[Dict[str, Any]] = deque(maxlen=CHART_CANDLES)
        self.feature: Dict[str, Any] = {}
        self.feature_compute_us = 0
        self.event_count = 0
        self.event_rate = 0.0
        self.rate_count = 0
        self.rate_started = time.monotonic()

        # v4.5: persisted, self-adapting model
        self.model = Model.load(store)
        self.last_learning: Dict[str, Any] = {
            "status": "waiting for settled candles",
            "settled_main": store.settled_main_count(),
            "required": MODEL_MIN_SAMPLES,
        }
        self.pnl_summary: Dict[str, Any] = store.cumulative_pnl(limit=1)

        self.current_main: Optional[Prediction] = None
        self.current_reversal: Optional[Prediction] = None
        self.current_ef: Optional[Prediction] = None
        self.current_gated: Optional[Dict[str, Any]] = None
        self.last_confidence: Dict[str, Any] = {}
        self.last_fill: Optional[Dict[str, Any]] = None
        self.book = PredictBook()
        self.executor = LiveExecutor(
            self.store, self.controls, self.book, self.stop_event
        )
        # R6: no executor PRICE_LIMIT callback/re-arm lifecycle. EF remains the
        # same signal while its hot container waits for VWAP confirmation/retry.
        self.main_streak_dir = ""
        self.main_streak_start_ms = 0
        self.main_streak_reads = 0
        self.ef_candidate_direction = ""
        self.ef_candidate_since_ms = 0
        self.ef_candidate_reads = 0
        # Execution-only re-arm state. BTC EF metrics continue updating while
        # this short PRICE_LIMIT cooldown is active.
        self.ef_rearm_cooldown_until_ms = 0
        self.ef_rearm_cooldown_reason = ""
        self.ef_rearm_attempt_seq = 0
        self.ef_last_compute_ms = 0
        self.ef_metrics: Dict[str, Any] = {}
        self.ef_monitor: Dict[str, Any] = {
            "status": "watching through candle close for exhaustion",
            "ready": False,
        }
        # Causal post-fire path tracker. Updated in memory on BTC trades and
        # persisted only at fire/settlement so diagnostics never block callbacks.
        self.ef_post_progress: Optional[Dict[str, Any]] = None
        # Rejection tracking. A wick is the drawn record of price probing a
        # level and being pushed back. That event is visible in the ticks the
        # moment it happens, so it is measured here rather than read off a
        # candle shape that only exists once the move is over.
        self.candle_high_seen = 0.0
        self.candle_low_seen = 0.0
        self.reject_up = 0.0      # supply rejected an upward probe
        self.reject_down = 0.0    # demand rejected a downward probe
        self.reject_ts = 0.0
        self._reset_main_streak()      # last decay timestamp, seconds
        # One price sample per feature tick, capped like v5/v7's 300-entry ring.
        # v8.1 GPT adaptive scale state. The open bucket is kept separate
        # from the last completed close so intra-second message paths cannot
        # leak into the one-second return. The expensive window scan is
        # cached once per completed bucket, never repeated per websocket event.
        self._adapt_returns: Deque[Tuple[int, float]] = deque(
            maxlen=ADAPT_SLOW_SEC + 600)
        self._adapt_bucket: Optional[int] = None
        self._adapt_bucket_close: float = 0.0
        self._adapt_completed_bucket: Optional[int] = None
        self._adapt_completed_close: float = 0.0
        self._adapt_ratio_raw: float = 1.0
        self._adapt_ratio_cache: float = 1.0
        self.pressure_history: Deque[Tuple[float, float]] = deque(
            maxlen=PRESSURE_HISTORY
        )
        self.gated_block = "waiting for the odds window"
        self.main_block = "waiting for pressure and odds to agree"
        self.reversal_candidate_since_ms = 0
        self.reversal_samples = 0
        self.reversal_evidence: Dict[str, Any] = {
            "checks": {},
            "passed_checks": 0,
            "required_checks": REVERSAL_CHECK_COUNT,
        }
        self.last_open_side = 0
        self.open_cross_count = 0

        self.feed_status = "starting"
        self.feed_url = ""
        # v5.9: explicit WS market-data state. Guarded by the existing Engine
        # RLock so REST fallback cannot race a first WS event or disconnect.
        self.ws_live = False
        self.last_event_local_ms = 0
        self.last_exchange_ms = 0
        self.logical_ts_ms = 0
        self.exchange_latency_ms: Optional[int] = None
        self.last_error = ""
        self.last_error_ms = 0
        self.chart_revision = 0
        self.state_revision = 0

    def load_history(self, candles: Iterable[Dict[str, Any]]) -> None:
        """Merge REST history and recover trades stranded by a restart.

        Durable signal restoration is intentionally outside Engine.lock so a
        background chart bootstrap cannot block the market processor on SQLite.
        """
        history = [dict(candle) for candle in candles]
        self._recover_trades_from_history(history)
        restore_candle_id: Optional[int] = None
        with self.lock:
            live_candle = dict(self.candle) if self.candle else None
            merged: Dict[int, Dict[str, Any]] = {
                int(candle["time"]): dict(candle) for candle in history
            }
            if live_candle is not None:
                merged[int(live_candle["time"])] = live_candle
            ordered = [merged[key] for key in sorted(merged)][-CHART_CANDLES:]
            self.candles.clear()
            self.candles.extend(ordered)
            if self.candle is None and self.candles:
                self.candle = dict(self.candles[-1])
                restore_candle_id = int(self.candle["time"])
                self.reversal_candidate_since_ms = 0
                self.reversal_samples = 0
                self.last_open_side = 0
                self.open_cross_count = 0
                self.open_sides = RollingOpenSides(30_000)
            self.chart_revision += 1
        if restore_candle_id is not None:
            self._restore_candle_state(restore_candle_id)

    def _recover_trades_from_history(
        self, candles: Iterable[Dict[str, Any]]
    ) -> None:
        """Settle historical rows when REST already knows the candle outcome.

        This is recovery only. It does not create predictions, orders or new
        entries; it completes data that was already in SQLite before restart.
        """
        pending = set(self.store.unsettled_trade_candle_ids())
        if not pending:
            return
        recovered = False
        for candle in candles:
            candle_id = int(candle.get("time") or 0)
            if candle_id not in pending or not bool(candle.get("closed")):
                continue
            actual = (
                "UP" if float(candle["close"]) >= float(candle["open"]) else "DOWN"
            )
            self.store.settle_candle(candle)
            for kind, won in self.store.settle_trades_and_report(candle_id, actual):
                try:
                    self.controls.record_result(kind, won)
                except Exception as problem:
                    self.record_error(f"recovered stake streak: {problem}")
            pending.discard(candle_id)
            recovered = True
        if recovered:
            try:
                self.controls.flush_pending(SYSTEM_CONTROL_KIND)
            except Exception as problem:
                self.record_error(f"recovered pending config: {problem}")

    def record_error(self, message: str) -> None:
        with self.lock:
            self.last_error = str(message)[:500]
            self.last_error_ms = now_ms()
            self.state_revision += 1

    def set_feed_status(self, status: str, url: str = "") -> None:
        with self.lock:
            self.feed_status = status
            if url:
                self.feed_url = url
            self.state_revision += 1

    def set_ws_live(self, live: bool) -> None:
        with self.lock:
            self.ws_live = bool(live)

    def is_ws_live(self) -> bool:
        with self.lock:
            return bool(self.ws_live)

    def start_processor(self) -> None:
        if self._processor_thread is None or not self._processor_thread.is_alive():
            self._processor_thread = threading.Thread(
                target=self._market_processor_loop, name="btc-engine", daemon=True)
            self._processor_thread.start()

    def _r5_reconcile_ef_lifecycle_once(self) -> bool:
        """Make EF execution truth authoritative even if a callback is lost.

        This is intentionally *not* signal logic. It runs off the BTC market
        processor and performs no Predict.fun/Binance network work. The normal
        Store->Engine push remains the zero-poll fast path; this watchdog is an
        independent fallback for the exact stale-EF failure seen live.
        """
        changed = False

        # Cooldown expiry is lifecycle state, not signal logic. Do not wait for
        # the next Binance/Predict.fun event to make the dashboard re-arm.
        with self.lock:
            cooldown_until = int(self.ef_rearm_cooldown_until_ms or 0)
            if (
                self.current_ef is None
                and cooldown_until > 0
                and now_ms() >= cooldown_until
            ):
                self.ef_rearm_cooldown_until_ms = 0
                self.ef_rearm_cooldown_reason = ""
                self.ef_rearm_attempt_seq = 0
                self._reset_ef_candidate()
                self.ef_monitor = {
                    **dict(self.ef_metrics or {}),
                    "status": "WATCHING",
                    "reason": "PRICE_LIMIT cooldown complete; watching for a fresh BTC EF",
                    "ready": False,
                }
                self.chart_revision += 1
                changed = True

        # A Store release normally pushes directly into the Engine. Re-apply
        # every still-unacknowledged tombstone here as a second independent
        # delivery path. This is an in-memory map read, not SQLite.
        try:
            pending = self.store.r5_pending_ef_rearm_notices()
        except Exception as exc:
            self.record_error(f"EF lifecycle notice read: {exc}")
            pending = []
        for event in pending:
            before = None
            with self.lock:
                if self.current_ef is not None:
                    before = (
                        int(self.current_ef.candle_id),
                        int(self.current_ef.ts_ms),
                        str(self.current_ef.direction or "").upper(),
                    )
            try:
                self._r5_apply_rearm_notice_immediate(dict(event))
            except Exception as exc:
                self.record_error(f"EF lifecycle notice apply: {exc}")
                continue
            with self.lock:
                after = None if self.current_ef is None else (
                    int(self.current_ef.candle_id),
                    int(self.current_ef.ts_ms),
                    str(self.current_ef.direction or "").upper(),
                )
            if before != after:
                changed = True

        # If no EF is displayed there is nothing stale to repair. This early
        # return keeps SQLite completely idle between EF signals.
        with self.lock:
            current = self.current_ef
            current_cid = int(self.candle.get("time") or -1) if self.candle else -1
            identity = None if current is None else (
                int(current.candle_id), int(current.ts_ms),
                str(current.direction or "").upper(),
            )
        if identity is None or identity[0] != current_cid:
            self._ef_lifecycle_last_identity = None
            self._ef_lifecycle_next_db_mono = 0.0
            return changed

        # Poll durable state aggressively only around a newly-fired EF, where a
        # signed PRICE_LIMIT is decided. Once the order is accepted/settled,
        # back off to one safety read per second. The normal push path is still
        # immediate, so this watchdog cannot become execution latency.
        mono_now = time.monotonic()
        if identity != self._ef_lifecycle_last_identity:
            self._ef_lifecycle_last_identity = identity
            self._ef_lifecycle_next_db_mono = 0.0
        if mono_now < float(self._ef_lifecycle_next_db_mono or 0.0):
            return changed

        cid, sig_ts, sig_dir = identity
        next_delay = 1.0
        try:
            active = self.store.trade_row(cid, "EF")
            if active is not None:
                active_matches = (
                    int(active.get("ts_ms") or -1) == sig_ts
                    and str(active.get("direction") or "").upper() == sig_dir
                )
                status = str(active.get("order_status") or "").upper()
                no_hash = not str(active.get("order_hash") or "").strip()
                no_fill = not bool(active.get("filled"))
                if active_matches and no_fill and no_hash and status == "PRICE_LIMIT":
                    if self.store.r5_release_failed_ef(
                        cid, sig_ts, sig_dir,
                        str(active.get("failure_reason") or "PRICE_LIMIT"),
                    ):
                        changed = True
                        active = None
                elif active_matches and no_fill and no_hash and status in {
                    "QUEUED", "SIGNING"
                }:
                    # PRICE_LIMIT is decided during this short pre-submit stage.
                    next_delay = 0.05
                else:
                    next_delay = 1.0

            # Last-resort repair: the failed attempt can already be archived
            # while the old Prediction object survived in memory. Match the
            # exact timestamp+direction; never clear a newer same-candle EF.
            if active is None:
                failed = self.store.latest_ef_failed_attempt(cid)
                if failed is not None:
                    failed_ts = int(failed.get("signal_ts_ms") or -1)
                    failed_dir = str(failed.get("direction") or "").upper()
                    failed_status = str(failed.get("order_status") or "").upper()
                    if (
                        failed_ts == sig_ts
                        and failed_dir == sig_dir
                        and failed_status in {
                            "PRICE_LIMIT", "WRONG_MARKET", "NOT_SENT",
                            "NO_FRESH_BOOK", "NO_LIQUIDITY", "QUEUE_FULL",
                        } | set(PREDICT_ORDER_TERMINAL_FAILURES)
                    ):
                        self._r5_apply_rearm_notice_immediate({
                            "candle_id": cid,
                            "signal_ts_ms": sig_ts,
                            "direction": sig_dir,
                            "status": failed_status,
                            "reason": str(failed.get("reason") or failed_status),
                            "attempt_seq": int(failed.get("attempt_seq") or 0),
                            "archived_ms": int(failed.get("archived_ms") or 0),
                            "cooldown_until_ms": int(failed.get("cooldown_until_ms") or 0),
                        })
                        changed = True
                # Missing active row gets a quicker follow-up in case persistence
                # is between signal insert and trade insert on another thread.
                if not changed:
                    next_delay = 0.10
        except Exception as exc:
            self.record_error(f"EF lifecycle durable repair: {exc}")
            next_delay = 0.25
        self._ef_lifecycle_next_db_mono = time.monotonic() + max(0.05, next_delay)
        return changed

    def _ef_lifecycle_loop(self) -> None:
        """Independent failed-EF cleanup; never runs on the signal hot path."""
        while not self.stop_event.is_set():
            try:
                self._r5_reconcile_ef_lifecycle_once()
            except Exception as exc:
                self.record_error(f"EF lifecycle watchdog: {exc}")
            # <=100 ms fallback response. Normal Store push is still immediate;
            # when no EF is active this loop performs zero SQLite reads.
            self.stop_event.wait(0.10)

    def _market_processor_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                stream, data, received_ms, recv_mono_ns = self.market_events.get(timeout=0.10)
            except queue.Empty:
                continue
            try:
                self.latency.observe_ms("market_queue_wait",
                    (mono_ns() - recv_mono_ns) / 1_000_000.0)
                self._process_message(stream, data, received_ms, recv_mono_ns)
            except Exception as exc:
                self.record_error(f"engine processor: {exc}")
            finally:
                self.market_events.task_done()

    def handle_message(
        self, stream: str, data: Dict[str, Any], received_ms: int,
        received_mono_ns: Optional[int] = None,
    ) -> bool:
        """Non-blocking websocket ingress; all feature/signal work is off-callback."""
        recv_mono = int(received_mono_ns if received_mono_ns is not None else mono_ns())
        try:
            self.market_events.put_nowait((str(stream), data, int(received_ms), recv_mono))
            depth = self.market_events.qsize()
            self.market_queue_max_depth = max(self.market_queue_max_depth, depth)
            return True
        except queue.Full:
            self.market_queue_dropped += 1
            self.latency.inc("market_queue_full")
            self.market_queue_overflow.set()
            self.last_error = "Binance engine queue full; reconnect required"
            self.last_error_ms = int(received_ms)
            return False

    def _process_message(
        self, stream: str, data: Dict[str, Any], received_ms: int,
        received_mono_ns: Optional[int] = None,
    ) -> None:
        ingress_mono = int(received_mono_ns if received_mono_ns is not None else mono_ns())
        start_ns = mono_ns()
        exchange_event = data.get("E")
        event_ms = int(exchange_event) if exchange_event is not None else None
        wait_start = mono_ns()
        pending_close: Optional[Tuple[Dict[str, Any], int]] = None
        restore_candle_id: Optional[int] = None
        with self.lock:
            lock_acquired = mono_ns()
            self.last_event_local_ms = received_ms
            if exchange_event is not None and event_ms is not None:
                self.last_exchange_ms = event_ms
                self.exchange_latency_ms = max(0, received_ms - event_ms)
                self.clock_skew_ms = int(received_ms - event_ms)
                self.logical_ts_ms = max(self.logical_ts_ms, event_ms)
                self._r5_exchange_anchor_ms = int(self.logical_ts_ms)
                self._r5_exchange_anchor_mono_ns = int(ingress_mono)
                processing_ts = max(
                    int(self.logical_ts_ms),
                    int(getattr(self, "_r5_processing_floor_ms", self.logical_ts_ms)),
                )
                self._r5_processing_floor_ms = int(processing_ts)
            else:
                anchor_ms = int(getattr(
                    self, "_r5_exchange_anchor_ms", self.logical_ts_ms or received_ms
                ))
                anchor_mono = int(getattr(
                    self, "_r5_exchange_anchor_mono_ns", ingress_mono
                ))
                elapsed_ms = max(
                    0, (int(ingress_mono) - anchor_mono) // 1_000_000
                )
                # Depth advances feature/OFI/EF processing time only; never logical_ts_ms.
                processing_ts = max(
                    int(self.logical_ts_ms or anchor_ms),
                    anchor_ms + elapsed_ms,
                    int(getattr(self, "_r5_processing_floor_ms", 0)),
                )
                self._r5_processing_floor_ms = int(processing_ts)
            self.event_count += 1
            self.rate_count += 1
            elapsed_rate = time.monotonic() - self.rate_started
            if elapsed_rate >= 1.0:
                self.event_rate = self.rate_count / elapsed_rate
                self.rate_count = 0
                self.rate_started = time.monotonic()
            if "aggTrade" in stream:
                self._note_stream("aggTrade", received_ms)
                self._on_trade(data, processing_ts, received_ms)
            elif "depth" in stream:
                self._note_stream("depth", received_ms)
                self._on_depth(data, processing_ts, received_ms)
            elif "kline" in stream:
                self._note_stream("kline", received_ms)
                self._on_kline(data, processing_ts)
            else:
                return
            feature_start = mono_ns()
            self._compute_features(processing_ts)
            self.latency.observe_ms("feature_compute", (mono_ns()-feature_start)/1_000_000.0)
            ef_updated = (("depth" in stream) or (processing_ts - self.ef_last_compute_ms >= EF_COMPUTE_INTERVAL_MS))
            if ef_updated:
                ef_start=mono_ns()
                self._compute_ef_metrics(processing_ts)
                self.ef_last_compute_ms = processing_ts
                self.latency.observe_ms("ef_compute", (mono_ns()-ef_start)/1_000_000.0)
            if self._pending_closed_candle is not None:
                pending_close = self._pending_closed_candle
                self._pending_closed_candle = None
            if self._pending_restore_candle_id is not None:
                restore_candle_id = self._pending_restore_candle_id
                self._pending_restore_candle_id = None
            lock_released=mono_ns()
        # SQLite, control persistence and order-intent handoff happen only after
        # Engine.lock is released. One dedicated processor thread preserves order.
        if restore_candle_id is not None:
            self._restore_candle_state(restore_candle_id)
        if pending_close is not None:
            self._settle_candle(pending_close[0], pending_close[1])
        decision_start=mono_ns()
        self._prediction_logic(processing_ts)
        if ef_updated:
            self._watch_ef(processing_ts)
        self.latency.observe_ms("prediction_decision", (mono_ns()-decision_start)/1_000_000.0)
        with self.lock:
            self.feature_compute_us = max(0, (mono_ns() - start_ns)//1_000)
            self.state_revision += 1
        self.latency.observe_ms("engine_lock_wait", (lock_acquired-wait_start)/1_000_000.0)
        self.latency.observe_ms("engine_lock_hold", (lock_released-lock_acquired)/1_000_000.0)
        self.latency.observe_ms("event_total", (mono_ns()-ingress_mono)/1_000_000.0)

    def _on_trade(self, data: Dict[str, Any], ts_ms: int,
                  recv_ms: Optional[int] = None) -> None:
        price = float(data["p"])
        qty = float(data["q"])
        quote = price * qty
        # m=True means the buyer was maker, so the aggressive side was SELL.
        signed_quote = -quote if bool(data.get("m")) else quote
        self.trade_ticks.append((ts_ms, price, qty, signed_quote))
        # EF-only mirror on the local clock. MAIN/REVERSAL keep reading
        # trade_ticks on the logical clock exactly as before.
        self.ef_trade_ticks.append(
            (int(recv_ms if recv_ms is not None else now_ms()),
             price, qty, signed_quote))
        self.price_ticks.append((ts_ms, price))
        self.delta_250ms.add(ts_ms, signed_quote)
        self.delta_1s.add(ts_ms, signed_quote)
        self.delta_2s.add(ts_ms, signed_quote)
        self.delta_5s.add(ts_ms, signed_quote)
        self.delta_30s.add(ts_ms, signed_quote)
        self.price_path.add(ts_ms, price)
        if signed_quote >= 0.0:
            self.candle_buy_quote += quote
        else:
            self.candle_sell_quote += quote
        self._update_open_position_stats(ts_ms, price)
        self._prune_ticks(ts_ms)
        if self.candle:
            self.candle["close"] = price
            self.candle["high"] = max(float(self.candle["high"]), price)
            self.candle["low"] = min(float(self.candle["low"]), price)
            progress = self.ef_post_progress
            if progress and int(progress.get("candle_id", -1)) == int(self.candle["time"]):
                open_price = float(progress["candle_open"])
                direction = str(progress["direction"])
                initial = max(float(progress.get("initial_distance") or 0.0), 1e-12)
                distance = abs(price - open_price)
                progress["closest_distance"] = min(
                    float(progress.get("closest_distance", initial)), distance
                )
                progress["progress_fraction"] = clamp(
                    1.0 - float(progress["closest_distance"]) / initial, 0.0, 1.0
                )
                signed_side = (price - open_price) * (1.0 if direction == "UP" else -1.0)
                if signed_side >= 0.0:
                    progress["crossed_open"] = True
                    if progress.get("first_cross_ms") is None:
                        progress["first_cross_ms"] = int(ts_ms)
                    progress["best_side_distance"] = max(
                        float(progress.get("best_side_distance") or 0.0), signed_side
                    )

    def _note_stream(self, name: str, received_ms: int) -> None:
        """Track arrivals per stream, using the local clock so a skewed
        exchange timestamp cannot hide a gap."""
        row = self.stream_stats.get(name)
        if row is None:
            return
        if row["last_ms"]:
            gap = max(0, int(received_ms) - int(row["last_ms"]))
            if gap > int(row["max_gap_ms"]):
                row["max_gap_ms"] = gap
        row["last_ms"] = int(received_ms)
        row["count"] = int(row["count"]) + 1
        row["window_count"] = int(row["window_count"]) + 1
        started = float(row["window_started"] or 0.0)
        now = time.monotonic()
        if not started:
            row["window_started"] = now
        elif now - started >= 2.0:
            row["rate"] = row["window_count"] / (now - started)
            row["window_count"] = 0
            row["window_started"] = now

    def _stream_health(self, current_ms: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, row in self.stream_stats.items():
            age = (current_ms - int(row["last_ms"])) if row["last_ms"] else None
            out[name] = {
                "count": int(row["count"]),
                "rate": round(float(row["rate"]), 2),
                "age_ms": age,
                "max_gap_ms": int(row["max_gap_ms"]),
            }
        return out

    def _on_depth(self, data: Dict[str, Any], ts_ms: int,
                  recv_ms: Optional[int] = None) -> None:
        bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
        if not bids or not asks:
            return
        current_top = (bids[0][0], bids[0][1], asks[0][0], asks[0][1])
        if self.previous_top is not None:
            # v4.5: OFI is the absolute quote change at the top of book.
            # There is no division by resting depth, so a thin book no longer
            # inflates the reading.
            value = self._quote_ofi(self.previous_top, current_top)
            self.ofi_1s.add(ts_ms, value)
            self.ofi_5s.add(ts_ms, value)
        self.previous_top = current_top
        self.depth = {"bids": bids, "asks": asks, "ts_ms": ts_ms}
        self.ef_depth_history.append({
            "ts_ms": int(ts_ms),
            "recv_ms": int(recv_ms if recv_ms is not None else now_ms()),
            "bids": list(bids), "asks": list(asks)
        })
        self._update_aggressive_clusters(bids, asks)

    def _on_kline(self, data: Dict[str, Any], ts_ms: int) -> None:
        raw = data["k"]
        incoming = {
            "time": int(raw["t"]),
            "open": float(raw["o"]),
            "high": float(raw["h"]),
            "low": float(raw["l"]),
            "close": float(raw["c"]),
            "volume": float(raw["v"]),
            "closed": bool(raw.get("x")),
            "close_time_ms": int(raw.get("T") or (int(raw["t"]) + CANDLE_MS - 1)),
        }
        incoming_id = int(incoming["time"])
        current_id = int(self.candle["time"]) if self.candle else None
        if current_id != incoming_id:
            self._start_candle(incoming)
        else:
            self.candle = incoming
            self._upsert_chart_candle(incoming)

        if incoming["closed"]:
            # Settlement performs SQLite/accounting work. Defer it until the
            # processor has released Engine.lock.
            self._pending_closed_candle = (dict(incoming), int(ts_ms))
            # The next kline stream event starts the new candle. We do not invent it.

    # ------------------------------------------------------------------
    # v4.5 settlement: grade, then economics, then learning
    # ------------------------------------------------------------------
    def _settle_candle(self, candle: Dict[str, Any], ts_ms: int) -> None:
        candle_id = int(candle["time"])
        self.executor.clear_ef_hot(candle_id)
        newly_closed = self.store.settle_candle(candle)
        actual = "UP" if float(candle["close"]) >= float(candle["open"]) else "DOWN"
        if self.current_main and self.current_main.candle_id == candle_id:
            self.current_main.actual = actual
            self.current_main.correct = self.current_main.direction == actual
        if self.current_reversal and self.current_reversal.candle_id == candle_id:
            self.current_reversal.actual = actual
            self.current_reversal.correct = self.current_reversal.direction == actual
        if self.current_ef and self.current_ef.candle_id == candle_id:
            self.current_ef.actual = actual
            self.current_ef.correct = self.current_ef.direction == actual
        if newly_closed:
            self.chart_revision += 1

        main = self.store.get_prediction(candle_id, "MAIN")
        # EF is an independent position, so it must settle even on a
        # candle where MAIN never qualified.
        # Settle, then update streaks from FILLED results only, then release
        # any configuration parked while a position was open. The open trade
        # itself is never resized or reinterpreted.
        for kind, won in self.store.settle_trades_and_report(candle_id, actual):
            try:
                self.controls.record_result(kind, won)
            except Exception as problem:
                self.record_error(f"stake streak: {problem}")
        progress = self.ef_post_progress
        if progress and int(progress.get("candle_id", -1)) == candle_id:
            crossed = bool(progress.get("crossed_open"))
            fraction = clamp(safe_float(progress.get("progress_fraction")), 0.0, 1.0)
            ef_direction = str(progress.get("direction") or "")
            outcome_class = classify_ef_post_progress(
                fraction, crossed, actual, ef_direction
            )
            trade = self.store.trade_row(candle_id, "EF") or {}
            progress.update({
                "outcome_class": outcome_class, "final_actual": actual,
                "final_financial_pnl": trade.get("financial_pnl"),
                "final_financial_result": trade.get("financial_result"),
            })
            try:
                self.store.save_ef_progress(progress)
            except Exception as problem:
                self.record_error(f"EF progress persistence: {problem}")
            self.ef_post_progress = None
        try:
            self.controls.flush_pending(SYSTEM_CONTROL_KIND)
        except Exception as problem:
            self.record_error(f"pending config: {problem}")
        if main is None:
            return
        reversal = self.store.get_prediction(candle_id, "REVERSAL")
        self._record_confidence_outcome(candle_id, actual, main, reversal, ts_ms)
        self._online_sgd_step(candle_id, actual, main)

    def _record_confidence_outcome(
        self,
        candle_id: int,
        actual: str,
        main: Prediction,
        reversal: Optional[Prediction],
        ts_ms: int,
    ) -> None:
        """Record how each confidence factor scored, not a monetary result.

        Confirmed Predict.fun fills and P&L live in ``trades``. This event is
        deliberately limited to model calibration: whether assigned confidence
        tracked the later Binance candle result.
        """
        event: Dict[str, Any] = {
            "candle_id": candle_id,
            "ts_ms": ts_ms,
            "actual": actual,
            "main_direction": main.direction,
            "main_correct": 1 if main.direction == actual else 0,
            "main_confidence": abs(main.probability_up - 0.5) * 2.0,
            "reversal_direction": None,
            "reversal_correct": None,
            "net_direction": main.direction,
        }
        if reversal is not None:
            event.update({
                "reversal_direction": reversal.direction,
                "reversal_correct": 1 if reversal.direction == actual else 0,
                "net_direction": reversal.direction,
            })
        event["net_correct"] = 1 if event["net_direction"] == actual else 0
        self.store.add_outcome_event(event)

    def _online_sgd_step(self, candle_id: int, actual: str, main: Prediction) -> None:
        settled = self.store.settled_main_count()
        if candle_id <= self.model.last_candle_id:
            return
        if settled < MODEL_MIN_SAMPLES:
            self.last_learning = {
                "status": (
                    f"collecting evidence: {settled}/{MODEL_MIN_SAMPLES} settled MAIN"
                ),
                "settled_main": settled,
                "required": MODEL_MIN_SAMPLES,
                "version": self.model.version,
            }
            return
        features = main.features or {}
        if not features:
            self.last_learning = {
                "status": "no feature snapshot on that MAIN row",
                "settled_main": settled,
                "required": MODEL_MIN_SAMPLES,
                "version": self.model.version,
            }
            return
        info = self.model.sgd_step(features, actual == "UP")
        self.model.last_candle_id = candle_id
        self.store.save_weights(self.model)
        moved = sorted(
            info["deltas"].items(), key=lambda item: abs(item[1]), reverse=True
        )[:3]
        self.last_learning = {
            "status": "weights updated",
            "settled_main": settled,
            "required": MODEL_MIN_SAMPLES,
            "candle_id": candle_id,
            "version": info["version"],
            "updates": info["samples"],
            "probability_up": info["probability_up"],
            "error": info["error"],
            "largest_moves": [
                {"name": name, "delta": delta} for name, delta in moved
            ],
        }
        self.chart_revision += 1

    def _model_feature_snapshot(self) -> Dict[str, Any]:
        """The complete state that produced a prediction.

        The thirteen model inputs come first and keep their exact names, so
        replay and online learning are unaffected. Everything after them is
        context: the gauge reading, the odds, the candle shape and the four
        confidence factors. Without this a settled prediction can be counted
        but never explained, which is what made the wick and volatility
        questions untestable.
        """
        snapshot: Dict[str, Any] = {
            name: safe_float(self.feature.get(name))
            for name in MODEL_FEATURE_NAMES
        }
        snapshot.update({
            "candle_open": safe_float(self.candle.get("open")),
            "pressure_text": str(self.feature.get("pressure_text", "")),
            "pressure_score": safe_float(self.feature.get("pressure_score")),
            "pressure_imb": safe_float(self.feature.get("pressure_imb")),
            "pressure_delta": safe_float(self.feature.get("pressure_delta")),
            "pressure_mom": safe_float(self.feature.get("pressure_mom")),
            "fair_p_up": safe_float(self.feature.get("fair_p_up")),
            "volume_ratio": safe_float(self.feature.get("volume_ratio")),
            "upper_wick_ratio": safe_float(self.feature.get("upper_wick_ratio")),
            "lower_wick_ratio": safe_float(self.feature.get("lower_wick_ratio")),
            "body_usd": safe_float(self.feature.get("body_usd")),
            "path_efficiency": safe_float(self.feature.get("path_efficiency")),
            "open_cross_count": safe_float(self.feature.get("open_cross_count")),
            "phase_second": safe_float(self.feature.get("phase_second")),
            "sigma_per_root_second": round(self._sigma_per_root_second(), 4),
        })
        for key, value in (self.last_confidence or {}).items():
            snapshot[
                {"volume": "f_volume", "rejection": "f_rejection",
                 "runway": "f_runway", "feasibility": "f_feasibility",
                 "combined": "confidence"}
                .get(key, key)
            ] = value
        return snapshot

    def _start_candle(self, candle: Dict[str, Any]) -> None:
        self.candle = dict(candle)
        open_price = safe_float(candle.get("open"), 0.0)
        self.candle_high_seen = open_price
        self.candle_low_seen = open_price
        self.reject_up = 0.0
        self.reject_down = 0.0
        self.reject_ts = 0.0
        self._reset_main_streak()
        # Durable reconnect/idempotency state is restored after Engine.lock is
        # released by the processor; no SQLite belongs in this hot lock.
        self.current_main = None
        self.current_reversal = None
        self.current_ef = None
        self.current_gated = None
        self.ef_post_progress = None
        self._pending_restore_candle_id = int(candle["time"])
        self.gated_block = "waiting for the odds window"
        self.main_block = "waiting for pressure and odds to agree"
        self.ef_candidate_direction = ""
        self.ef_candidate_since_ms = 0
        self.ef_candidate_reads = 0
        self.ef_rearm_cooldown_until_ms = 0
        self.ef_rearm_cooldown_reason = ""
        self.ef_rearm_attempt_seq = 0
        self.ef_metrics = {}
        self.ef_monitor = {
            "status": "watching through candle close for exhaustion",
            "ready": False,
        }
        self.reversal_candidate_since_ms = 0
        self.reversal_samples = 0
        self.reversal_evidence = {
            "checks": {},
            "passed_checks": 0,
            "required_checks": REVERSAL_CHECK_COUNT,
        }
        self.last_open_side = 0
        self.open_cross_count = 0
        self.open_sides = RollingOpenSides(30_000)
        self.candle_buy_quote = 0.0
        self.candle_sell_quote = 0.0
        self._upsert_chart_candle(candle)
        self.chart_revision += 1

    def _restore_candle_state(self, candle_id: int) -> None:
        """Restore already-persisted signals outside Engine.lock after reconnect."""
        main = self.store.get_prediction(int(candle_id), "MAIN")
        reversal = self.store.get_prediction(int(candle_id), "REVERSAL")
        ef = self.store.get_ef_prediction(int(candle_id))
        ef_trade = self.store.trade_row(int(candle_id), "EF")
        gated = self.store.get_gated(int(candle_id))
        progress_row = self.store.ef_progress_row(int(candle_id))
        progress = None
        if progress_row is not None and progress_row.get("outcome_class") is None:
            try:
                fire_features = json.loads(progress_row.get("fire_features") or "{}")
            except (TypeError, ValueError):
                fire_features = {}
            progress = {**progress_row, "crossed_open": bool(progress_row.get("crossed_open")),
                        "fire_features": fire_features}
        with self.lock:
            if not self.candle or int(self.candle.get("time") or 0) != int(candle_id):
                return
            if self.current_main is None:
                self.current_main = main
            if self.current_reversal is None:
                self.current_reversal = reversal
            if self.current_ef is None:
                self.current_ef = ef
            if self.current_gated is None:
                self.current_gated = gated
            if self.ef_post_progress is None and progress is not None:
                self.ef_post_progress = progress
        if ef is not None and isinstance(ef_trade, dict):
            status = str(ef_trade.get("order_status") or "").upper()
            no_hash = not str(ef_trade.get("order_hash") or "").strip()
            no_fill = not bool(ef_trade.get("filled"))
            if (
                status in {"WAIT_VWAP", "QUEUED", "SIGNING", "PRICE_LIMIT"}
                and no_hash and no_fill
                and float(ef_trade.get("stake") or 0.0) > 0.0
            ):
                # R6 restart migration: old hashless QUEUED/SIGNING/PRICE_LIMIT
                # rows become the SAME live EF waiting for hot VWAP confirmation.
                if status != "WAIT_VWAP":
                    self.store.update_trade_execution(
                        int(candle_id), "EF", order_status="WAIT_VWAP",
                        failure_reason=(
                            f"R6 restored {status}; waiting for full-stake EF VWAP < "
                            f"{EF_MAX_SHARE_PRICE:.2f}"
                        ),
                        execution_eligibility="WAIT_VWAP",
                    )
                self.executor.arm_ef_hot(
                    ef, float(ef_trade.get("stake") or 0.0),
                    attempt=max(1, int(ef_trade.get("attempts") or 0) + 1),
                    first_submit_ms=int(ef_trade.get("first_submit_ms") or 0) or None,
                    min_book_version=self.book.current_version(),
                )

    def _upsert_chart_candle(self, candle: Dict[str, Any]) -> None:
        candle = {
            "time": int(candle["time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0.0)),
            "closed": bool(candle.get("closed", False)),
            "close_time_ms": int(
                candle.get("close_time_ms") or int(candle["time"]) + CANDLE_MS - 1
            ),
        }
        if self.candles and int(self.candles[-1]["time"]) == candle["time"]:
            self.candles[-1] = candle
        else:
            # REST may have already loaded this candle at another position.
            for index, old in enumerate(self.candles):
                if int(old["time"]) == candle["time"]:
                    self.candles[index] = candle
                    break
            else:
                self.candles.append(candle)

    def _update_open_position_stats(self, ts_ms: int, price: float) -> None:
        if not self.candle:
            return
        open_price = float(self.candle["open"])
        diff = price - open_price
        side = 1 if diff > OPEN_CROSS_DEADBAND_USD else -1 if diff < -OPEN_CROSS_DEADBAND_USD else 0
        self.open_sides.add(ts_ms, side)
        if side and self.last_open_side and side != self.last_open_side:
            self.open_cross_count += 1
        if side:
            self.last_open_side = side

    def _prune_ticks(self, ts_ms: int) -> None:
        cutoff = ts_ms - 35_000
        while self.trade_ticks and self.trade_ticks[0][0] < cutoff:
            self.trade_ticks.popleft()
        while self.price_ticks and self.price_ticks[0][0] < cutoff:
            self.price_ticks.popleft()

    @staticmethod
    def _quote_ofi(
        previous: Tuple[float, float, float, float],
        current: Tuple[float, float, float, float],
    ) -> float:
        """v4.5 OFI: signed change of top-of-book quote value, in $thousands.

        Classic OFI accounting on price and size, valued in quote currency and
        deliberately *not* divided by resting depth.
        """
        pbp, pbq, pap, paq = previous
        cbp, cbq, cap, caq = current
        if cbp > pbp:
            bid_term = cbq * cbp
        elif cbp == pbp:
            bid_term = (cbq - pbq) * cbp
        else:
            bid_term = -pbq * pbp
        if cap < pap:
            ask_term = caq * cap
        elif cap == pap:
            ask_term = (caq - paq) * cap
        else:
            ask_term = -paq * pap
        return (bid_term - ask_term) / OFI_QUOTE_SCALE

    def _update_aggressive_clusters(
        self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]
    ) -> None:
        """Flag bid/ask quote-volume spikes above mean + CLUSTER_SIGMA sigma."""
        bid_quote = sum(price * qty for price, qty in bids[:5])
        ask_quote = sum(price * qty for price, qty in asks[:5])
        self.aggressive_bid_cluster = self._cluster_z(self.bid_volume_history, bid_quote)
        self.aggressive_ask_cluster = self._cluster_z(self.ask_volume_history, ask_quote)
        self.bid_volume_history.append(bid_quote)
        self.ask_volume_history.append(ask_quote)

    @staticmethod
    def _cluster_z(history: Deque[float], value: float) -> float:
        """Excess z-score of `value`; zero unless it clears CLUSTER_SIGMA."""
        count = len(history)
        if count < CLUSTER_MIN_SAMPLES:
            return 0.0
        mean = sum(history) / count
        variance = sum((item - mean) ** 2 for item in history) / count
        sigma = max(math.sqrt(variance), abs(mean) * CLUSTER_SIGMA_FLOOR)
        if sigma <= 1e-9:
            return 0.0
        z = (value - mean) / sigma
        return clamp(z, 0.0, 8.0) if z >= CLUSTER_SIGMA else 0.0

    def _return_bps(self, ts_ms: int, window_ms: int, current_price: float) -> float:
        cutoff = ts_ms - window_ms
        reference: Optional[float] = None
        for tick_ms, price in reversed(self.price_ticks):
            if tick_ms <= cutoff:
                reference = price
                break
        if reference is None and self.price_ticks:
            reference = self.price_ticks[0][1]
        if not reference:
            return 0.0
        return (current_price / reference - 1.0) * 10_000.0

    def _spot_imbalance(self) -> float:
        bids = self.depth.get("bids") or []
        asks = self.depth.get("asks") or []
        bid_volume = sum(qty for _, qty in bids[:5])
        ask_volume = sum(qty for _, qty in asks[:5])
        total = bid_volume + ask_volume
        return (bid_volume - ask_volume) / total if total else 0.0

    # ------------------------------------------------------------------
    # v8.1 GPT adaptive scale
    # ------------------------------------------------------------------
    def _adapt_sample(self, ts_ms: int, price: float) -> None:
        """Record causal close-to-close returns on a one-second clock.

        The open bucket is not turned into a return until a later bucket
        arrives, at which point its final observed price is known. This is
        important: comparing the previous close with the *first* price of
        the new second measures a bucket-boundary artefact and can report
        zero volatility for a market that moves entirely inside each second.

        Empty buckets remain absent. A short gap is square-root normalised;
        a longer feed gap breaks the chain instead of becoming a price move.
        """
        if price <= 0.0 or not math.isfinite(price):
            return
        bucket = int(ts_ms) // ADAPT_BUCKET_MS
        if self._adapt_bucket is not None and bucket < self._adapt_bucket:
            return
        if self._adapt_bucket is None:
            self._adapt_bucket = bucket
            self._adapt_bucket_close = price
            return
        if bucket == self._adapt_bucket:
            self._adapt_bucket_close = price
            return

        # A newer bucket proves that the prior bucket is complete.
        if bucket - self._adapt_bucket > ADAPT_STALE_BUCKETS:
            self._adapt_ratio_raw = 1.0
            self._adapt_ratio_cache = 1.0
        completed_bucket = self._adapt_bucket
        completed_close = self._adapt_bucket_close
        appended = False
        if (
            self._adapt_completed_bucket is not None
            and self._adapt_completed_close > 0.0
        ):
            gap = completed_bucket - self._adapt_completed_bucket
            if 0 < gap <= ADAPT_STALE_BUCKETS:
                r = math.log(
                    completed_close / self._adapt_completed_close
                ) / math.sqrt(float(gap))
                if math.isfinite(r):
                    self._adapt_returns.append((completed_bucket, r))
                    appended = True
            elif gap > ADAPT_STALE_BUCKETS:
                # Never carry a pre-disconnect regime decision across a stale
                # feed. Warm history remains available, but execution uses the
                # legacy identity until fresh returns rebuild the factor.
                self._adapt_ratio_raw = 1.0
                self._adapt_ratio_cache = 1.0

        self._adapt_completed_bucket = completed_bucket
        self._adapt_completed_close = completed_close
        self._adapt_bucket = bucket
        self._adapt_bucket_close = price
        if appended:
            self._refresh_adapt_ratio()

    def _adapt_rms(self, seconds: int, minimum: int) -> float:
        """RMS of one-second log returns over a wall-clock window."""
        if not self._adapt_returns:
            return 0.0
        newest = self._adapt_returns[-1][0]
        cut = newest - int(seconds)
        vals = [r for b, r in self._adapt_returns if b >= cut]
        if len(vals) < minimum:
            return 0.0
        # Derive the clip from a robust typical magnitude, not from the RMS
        # that contains the point being clipped. Otherwise one corrupted
        # print inflates its own cap and can force the maximum regime factor.
        magnitudes = sorted(abs(v) for v in vals if math.isfinite(v))
        if len(magnitudes) < minimum:
            return 0.0
        median_abs = magnitudes[len(magnitudes) // 2]
        if median_abs <= 0.0:
            positive = [value for value in magnitudes if value > 0.0]
            required_active = max(
                8, int(math.ceil(len(magnitudes) * ADAPT_MIN_ACTIVE_SHARE))
            )
            if len(positive) < required_active:
                return 0.0
            median_abs = positive[len(positive) // 2]
        robust_sigma = 1.4826 * median_abs
        cap = ADAPT_WINSOR_SIGMAS * robust_sigma
        clipped = [max(-cap, min(cap, value)) for value in vals]
        return math.sqrt(sum(value * value for value in clipped) / len(clipped))

    @staticmethod
    def _engaged_adapt_ratio(raw: float) -> float:
        """Map a raw regime ratio to a smooth, legacy-preserving factor."""
        raw = clamp(raw, ADAPT_RATIO_LO, ADAPT_RATIO_HI)
        if ADAPT_IDENTITY_LO <= raw <= ADAPT_IDENTITY_HI:
            return 1.0
        if raw > ADAPT_IDENTITY_HI:
            width = math.log(ADAPT_FULL_HI) - math.log(ADAPT_IDENTITY_HI)
            engagement = clamp(
                (math.log(raw) - math.log(ADAPT_IDENTITY_HI)) / width,
                0.0, 1.0,
            )
        else:
            width = math.log(ADAPT_IDENTITY_LO) - math.log(ADAPT_FULL_LO)
            engagement = clamp(
                (math.log(ADAPT_IDENTITY_LO) - math.log(raw)) / width,
                0.0, 1.0,
            )
        return math.exp(math.log(raw) * engagement)

    def _refresh_adapt_ratio(self) -> None:
        """Refresh both RMS windows once, after a completed return."""
        fast = self._adapt_rms(ADAPT_FAST_SEC, ADAPT_MIN_FAST)
        slow = self._adapt_rms(ADAPT_SLOW_SEC, ADAPT_MIN_SLOW)
        if fast <= 0.0 or slow <= 0.0:
            self._adapt_ratio_raw = 1.0
            self._adapt_ratio_cache = 1.0
            return
        raw = clamp(fast / slow, ADAPT_RATIO_LO, ADAPT_RATIO_HI)
        self._adapt_ratio_raw = raw
        self._adapt_ratio_cache = self._engaged_adapt_ratio(raw)

    def adapt_ratio(self) -> float:
        """Return the cached dimensionless regime multiplier in O(1)."""
        if not ADAPT_ENABLED:
            return 1.0
        return self._adapt_ratio_cache

    def _fair_odds(self, ts_ms: int, price: float, open_price: float) -> Tuple[float, float]:
        """v5/v7 fair odds. Reports how decided the candle already is."""
        if not self.candle:
            return 0.5, 300.0
        end_ms = int(self.candle["time"]) + CANDLE_MS
        seconds_left = max((end_ms - ts_ms) / 1000.0, 1.0)
        moves = sorted(
            abs(float(c["close"]) - float(c["open"]))
            for c in list(self.candles)[-24:]
            if c.get("closed")
        )
        typical = moves[len(moves) // 2] if moves else max(price * 4e-4, 1.0)
        # v8.1 GPT: the 24-candle median adapts after a regime has persisted,
        # but lags the onset. The cached fast/slow multiplier bridges that
        # transition. Its identity band preserves the exact v8 calculation
        # during ordinary variation; no probability threshold is retuned.
        typical = typical * self.adapt_ratio()
        per_second = max(typical / math.sqrt(CANDLE_MS / 1000.0), price * 1e-6)
        sigma = per_second * math.sqrt(seconds_left)
        lead = price - open_price
        probability = 0.5 * (1.0 + math.erf(lead / (sigma * math.sqrt(2.0))))
        return clamp(probability, 0.01, 0.99), seconds_left

    def _sigma_per_root_second(self) -> float:
        """Realised dispersion per root-second, from the rolling tick ring.

        The ring is never cleared between candles, so this is available from
        the first second of a new candle rather than needing the candle to
        form. That is what makes an early call possible at all.

        Timestamps are used only to measure the span. Individual gaps are not,
        because several websocket events routinely share the same millisecond
        on a phone: dividing by those gaps discarded almost every step and
        returned zero, which silently pinned the feasibility factor at 0.5 on
        every candle.
        """
        history = list(self.pressure_history)[-VOLATILITY_WINDOW:]
        if len(history) < 12:
            return 0.0
        span_seconds = history[-1][0] - history[0][0]
        if span_seconds <= 0.0:
            return 0.0
        moves = [abs(history[i][1] - history[i - 1][1])
                 for i in range(1, len(history))]
        if not moves:
            return 0.0
        per_step = sum(moves) / len(moves)
        seconds_per_step = span_seconds / max(len(history) - 1, 1)
        if seconds_per_step <= 0.0:
            return 0.0
        # A random walk scales with the square root of time, so convert the
        # average per-tick move into the equivalent one-second dispersion.
        return per_step / math.sqrt(seconds_per_step)

    def _volume_ratio(self, phase_second: float) -> float:
        """Pace of this candle's volume against the median of recent candles."""
        if not self.candle:
            return 1.0
        volumes = sorted(
            float(c["volume"])
            for c in list(self.candles)[-24:]
            if c.get("closed") and float(c.get("volume", 0.0)) > 0.0
        )
        if not volumes:
            return 1.0
        median = volumes[len(volumes) // 2]
        if median <= 0.0:
            return 1.0
        fraction = clamp(max(phase_second, 1.0) / 300.0, 0.01, 1.0)
        paced = float(self.candle.get("volume", 0.0)) / fraction
        return paced / median

    def _compute_features(self, ts_ms: int) -> None:
        if not self.candle:
            return
        price = float(self.candle["close"])
        open_price = float(self.candle["open"])
        high = float(self.candle["high"])
        low = float(self.candle["low"])
        body = price - open_price
        raw_range = high - low
        candle_range = max(raw_range, 1e-9)
        upper_wick = max(0.0, high - max(open_price, price)) / candle_range
        lower_wick = max(0.0, min(open_price, price) - low) / candle_range
        phase_second = clamp((ts_ms - int(self.candle["time"])) / 1000.0, 0.0, 300.0)
        # v4.5 price-action shape. A candle with no range yet is neutral, never
        # "closing on the low", which would otherwise fake a bearish reading in
        # the first milliseconds after the open.
        if raw_range <= 1e-9:
            body_range_ratio = 0.0
            close_location = 0.5
        else:
            body_range_ratio = clamp(body / candle_range, -1.0, 1.0)
            close_location = clamp((price - low) / candle_range, 0.0, 1.0)
        # Complete the previous one-second bucket before fair odds reads the
        # cached factor. This adds no hold or wait to the signal path.
        self._adapt_sample(ts_ms, price)
        fair_p_up, seconds_left = self._fair_odds(ts_ms, price, open_price)
        aggressive_volume = self.candle_buy_quote + self.candle_sell_quote
        volume_profile_delta = (
            (self.candle_buy_quote - self.candle_sell_quote) / aggressive_volume
            if aggressive_volume > 0.0
            else 0.0
        )

        feature = {
            "ts_ms": ts_ms,
            "candle_id": int(self.candle["time"]),
            "phase_second": phase_second,
            "price": price,
            "body_usd": body,
            "delta_1s": self.delta_1s.value(ts_ms),
            "delta_5s": self.delta_5s.value(ts_ms),
            "delta_30s": self.delta_30s.value(ts_ms),
            "ofi_1s": self.ofi_1s.value(ts_ms),
            "ofi_5s": self.ofi_5s.value(ts_ms),
            "spot_imbalance5": self._spot_imbalance(),
            "return_250ms_bps": self._return_bps(ts_ms, 250, price),
            "return_1s_bps": self._return_bps(ts_ms, 1_000, price),
            "return_5s_bps": self._return_bps(ts_ms, 5_000, price),
            "above_open_balance_30s": self.open_sides.up_balance(ts_ms),
            "open_cross_count": self.open_cross_count,
            "path_efficiency": self.price_path.efficiency(ts_ms),
            "upper_wick_ratio": upper_wick,
            "lower_wick_ratio": lower_wick,
            # --- v4.5 ---
            "body_range_ratio": body_range_ratio,
            "close_location": close_location,
            "close_location_centred": (close_location - 0.5) * 2.0,
            "aggressive_bid_cluster": self.aggressive_bid_cluster,
            "aggressive_ask_cluster": self.aggressive_ask_cluster,
            "aggressive_cluster_bias": (
                self.aggressive_bid_cluster - self.aggressive_ask_cluster
            ),
            "volume_profile_delta": volume_profile_delta,
            "fair_p_up": fair_p_up,
            "seconds_left": seconds_left,
            "volume_ratio": self._volume_ratio(phase_second),
            "candle_buy_quote": self.candle_buy_quote,
            "candle_sell_quote": self.candle_sell_quote,
        }
        # --- tick-level rejection (the leading form of a wick) --------------
        # Price makes a new extreme, then returns while aggressive flow turns
        # against it: supply or demand refusing the level. Measured from ticks
        # so it is available immediately, rather than waiting for a candle
        # shape that only finishes forming once the move is over.
        #
        # Two corrections over the first attempt. Decay is per second, not per
        # tick, so a busy market does not saturate faster than a quiet one.
        # And a retreat only counts once it clears a floor in dollars as well
        # as in sigma, because in a quiet market sigma is small enough that
        # every ordinary wiggle looked like a rejection and both sides pinned
        # at the cap within seconds.
        now_seconds = ts_ms / 1000.0
        elapsed = max(now_seconds - self.reject_ts, 0.0) if self.reject_ts else 0.0
        self.reject_ts = now_seconds
        if elapsed > 0.0:
            keep = 0.5 ** (elapsed / REJECTION_HALF_LIFE_SEC)
            self.reject_up *= keep
            self.reject_down *= keep
        if self.candle_high_seen <= 0.0:
            self.candle_high_seen = price
            self.candle_low_seen = price

        # Rejection is aggressive volume that failed to move price.
        #
        # Measuring how far price retreated from its high does not work: a
        # pure random walk produces a fifty-eight sigma median retreat over
        # five minutes, so every candle looks rejected. The informative event
        # is buyers lifting offers near the high while the high stops rising,
        # which is absorption, and it is directional.
        tick_delta = self.delta_1s.value(ts_ms)
        near_high = (self.candle_high_seen - price) <= REJECTION_ZONE_SIGMA * max(
            self._sigma_per_root_second(), REJECTION_MIN_SCALE_USD)
        near_low = (price - self.candle_low_seen) <= REJECTION_ZONE_SIGMA * max(
            self._sigma_per_root_second(), REJECTION_MIN_SCALE_USD)
        made_high = price > self.candle_high_seen
        made_low = price < self.candle_low_seen
        if made_high:
            self.candle_high_seen = price
        if made_low:
            self.candle_low_seen = price
        # Buying pressure spent at the high without making a new high is
        # absorbed demand: the offer above is holding.
        if near_high and not made_high and tick_delta > 0.0:
            # Approach the cap asymptotically instead of adding until it pins.
            # A hard ceiling meant both sides sat at the maximum within a
            # minute, so the reading could not tell balanced from saturated.
            self.reject_up += (REJECTION_CAP - self.reject_up) * min(
                tick_delta / REJECTION_CAP, 0.5)
        # Selling pressure spent at the low without making a new low is
        # absorbed supply: the bid below is holding.
        if near_low and not made_low and tick_delta < 0.0:
            self.reject_down += (REJECTION_CAP - self.reject_down) * min(
                abs(tick_delta) / REJECTION_CAP, 0.5)
        feature["reject_up"] = self.reject_up
        feature["reject_down"] = self.reject_down

        # --- volatility normalisation --------------------------------------
        # The same delta reading means different things on a calm tape and a
        # violent one. Dividing by realised volatility makes one number carry
        # one meaning, which is the cleanest fix for the model performing
        # worst exactly where it is blindest.
        sigma_now = self._sigma_per_root_second()
        feature["sigma_per_root_second"] = sigma_now
        for src, dst in (("delta_1s", "vn_delta_1s"),
                         ("delta_5s", "vn_delta_5s"),
                         ("delta_30s", "vn_delta_30s"),
                         ("ofi_1s", "vn_ofi_1s"),
                         ("ofi_5s", "vn_ofi_5s"),
                         ("return_1s_bps", "vn_return_1s"),
                         ("return_5s_bps", "vn_return_5s")):
            feature[dst] = vol_normalise(
                safe_float(feature.get(src), 0.0), sigma_now)

        # --- regime label ---------------------------------------------------
        # Directional persistence stands in for ADX: how much of the recent
        # travel actually went somewhere.
        adx_proxy = abs(safe_float(feature.get("path_efficiency"), 0.0)) * 100.0
        feature["adx_proxy"] = adx_proxy
        wick_total = (safe_float(feature.get("upper_wick_ratio"), 0.0)
                      + safe_float(feature.get("lower_wick_ratio"), 0.0))
        regime = classify_regime(
            adx_proxy, wick_total,
            safe_float(feature.get("open_cross_count"), 0.0),
            safe_float(feature.get("volume_ratio"), 1.0))
        feature["regime"] = regime
        feature["regime_code"] = float(
            {"TRENDING": 1.0, "RANGING": 2.0, "HIGH_VOL": 3.0}.get(regime, 0.0))

        # --- v5/v7 pressure gauge -------------------------------------------
        # Book imbalance, taker delta and 10-second momentum, combined with the
        # tested weights. The momentum term is scaled by the median 10s move so
        # it means the same thing in a quiet market as in a fast one.
        self.pressure_history.append((ts_ms / 1000.0, price))
        magnitude = avg_move(self.pressure_history)
        past_price = None
        for sample_ts, sample_price in reversed(self.pressure_history):
            if (ts_ms / 1000.0) - sample_ts >= 10.0:
                past_price = sample_price
                break
        momentum = 0.0
        if past_price is not None and magnitude > 0.0:
            momentum = clamp((price - past_price) / (2.0 * magnitude), -1.0, 1.0)
        gauge_imb = feature["spot_imbalance5"]
        gauge_delta = feature["delta_30s"]
        gauge_score = pressure_score(gauge_imb, gauge_delta, momentum)
        feature["pressure_score"] = gauge_score
        feature["pressure_text"] = pressure_text(gauge_score, magnitude)
        feature["pressure_imb"] = gauge_imb
        feature["pressure_delta"] = gauge_delta
        feature["pressure_mom"] = momentum
        feature["pressure_move"] = magnitude
        feature["open_call"] = make_call(gauge_imb, gauge_delta)
        score, probability_up, components = self.model.score(feature)
        feature["direction_score"] = score
        feature["probability_up"] = probability_up
        feature["model_components"] = components
        feature["model_version"] = self.model.version
        self.feature = feature

    def _ef_spoof_flags(self, ts_ms: int) -> Tuple[bool, bool]:
        """Conservative disappearing-wall detector owned only by EF."""
        depth_ts_ms = int(self.depth.get("ts_ms") or 0)
        previous_depth_ts = int(self.ef_spoof_state.get("depth_ts_ms") or 0)
        if depth_ts_ms and depth_ts_ms == previous_depth_ts:
            active = {
                side: expiry for side, expiry in
                dict(self.ef_spoof_state.get("until") or {}).items()
                if int(expiry) > int(ts_ms)
            }
            self.ef_spoof_state["until"] = active
            return bool(active.get("bid")), bool(active.get("ask"))
        bid_qty, ask_qty = ef_depth_totals(self.depth)
        previous = dict(self.ef_spoof_state.get("last") or {})
        walls = dict(self.ef_spoof_state.get("walls") or {})
        until = dict(self.ef_spoof_state.get("until") or {})
        if previous:
            elapsed_ms = int(ts_ms) - int(previous.get("ts_ms") or 0)
            if 40 <= elapsed_ms <= 700:
                for side, quantity in (("bid", bid_qty), ("ask", ask_qty)):
                    old = safe_float(previous.get(side))
                    added = quantity - old
                    if added > max(0.75, old * 0.35):
                        walls[side] = {
                            "ts_ms": int(ts_ms), "peak": quantity,
                            "added": added,
                        }
        for side, wall in list(walls.items()):
            age_ms = int(ts_ms) - int(wall.get("ts_ms") or 0)
            quantity = bid_qty if side == "bid" else ask_qty
            removed = safe_float(wall.get("peak")) - quantity
            added = max(safe_float(wall.get("added")), 1e-9)
            if 80 <= age_ms <= 1_600 and removed >= 0.60 * added:
                cutoff = int(ts_ms) - age_ms
                executed = sum(float(row[2]) for row in self.trade_ticks
                               if int(row[0]) >= cutoff)
                if executed < 0.25 * added:
                    until[side] = int(ts_ms) + 1_500
                walls.pop(side, None)
            elif age_ms > 2_000:
                walls.pop(side, None)
        until = {side: expiry for side, expiry in until.items()
                 if int(expiry) > int(ts_ms)}
        self.ef_spoof_state = {
            "depth_ts_ms": depth_ts_ms,
            "last": {"ts_ms": int(ts_ms), "bid": bid_qty, "ask": ask_qty},
            "walls": walls,
            "until": until,
        }
        return bool(until.get("bid")), bool(until.get("ask"))

    def _compute_ef_metrics(self, ts_ms: int) -> None:
        """BTC-only EF intelligence: reversal quality + Runway v2 settlement test."""
        if not self.candle or not self.feature:
            self.ef_metrics = {}
            return
        price = safe_float(self.feature.get("price"))
        open_price = safe_float(self.candle.get("open"), price)
        high = safe_float(self.candle.get("high"), price)
        low = safe_float(self.candle.get("low"), price)
        body = price - open_price
        body_sign = 1.0 if body > 0 else -1.0 if body < 0 else 0.0
        direction = "DOWN" if body_sign > 0 else "UP" if body_sign < 0 else ""
        phase = safe_float(self.feature.get("phase_second"))
        seconds_left = max(0.0, safe_float(self.feature.get("seconds_left")))
        sigma_root = max(self._sigma_per_root_second(), 1e-6)
        recv_now = max(
            int(self.ef_depth_history[-1]["recv_ms"]) if self.ef_depth_history else 0,
            int(self.ef_trade_ticks[-1][0]) if self.ef_trade_ticks else 0, 0) or now_ms()
        if now_ms() - recv_now > 2_000:
            recv_now = now_ms()
        w250=ef_trade_window(self.ef_trade_ticks, recv_now, 250)
        w1=ef_trade_window(self.ef_trade_ticks, recv_now, 1_000)
        w2=ef_trade_window(self.ef_trade_ticks, recv_now, 2_000)
        w5=ef_trade_window(self.ef_trade_ticks, recv_now, 5_000)
        w30=ef_trade_window(self.ef_trade_ticks, recv_now, 30_000)
        path1=ef_path_stats(self.ef_trade_ticks, recv_now, 1_000)
        path5=ef_path_stats(self.ef_trade_ticks, recv_now, 5_000)
        path30=ef_path_stats(self.ef_trade_ticks, recv_now, 30_000)
        current_depth=dict(self.depth)
        prev_fast=ef_depth_at_age(self.ef_depth_history, recv_now, 120, 800)
        prev_1s=ef_depth_at_age(self.ef_depth_history, recv_now, 800, 1_800)
        bids=list(current_depth.get("bids") or []); asks=list(current_depth.get("asks") or [])
        depth_recv=int(self.ef_depth_history[-1].get("recv_ms") or 0) if self.ef_depth_history else 0
        trade_recv=int(self.ef_trade_ticks[-1][0]) if self.ef_trade_ticks else 0
        depth_age=max(0,recv_now-depth_recv) if depth_recv else 10**9
        trade_age=max(0,recv_now-trade_recv) if trade_recv else 10**9
        inputs_ready=bool(w5["count"]>=EF_MIN_TRADE_EVENTS and trade_age<=EF_MAX_TRADE_AGE_MS
                          and prev_fast is not None and prev_1s is not None and bids and asks and depth_age<=1_000)
        bid_qty,ask_qty=ef_depth_totals(current_depth)
        total=bid_qty+ask_qty
        book5=(bid_qty-ask_qty)/total if total else 0.0
        old_bid,old_ask=ef_depth_totals(prev_1s or {})
        old_book=(old_bid-old_ask)/(old_bid+old_ask) if old_bid+old_ask else 0.0
        change=ef_depth_change(prev_1s,current_depth)
        event_ofi=ef_depth_event_ofi(prev_fast,current_depth)
        microprice=0.0
        if bids and asks and total>0:
            bb,ba=float(bids[0][0]),float(asks[0][0]); spread=ba-bb
            if spread>0:
                weighted=(ba*bid_qty+bb*ask_qty)/total
                microprice=clamp((weighted-(bb+ba)/2)/max(spread/2,1e-9),-1,1)
        flow_signed=0.34*w250["delta"]+0.28*w1["delta"]+0.20*w2["delta"]+0.12*w5["delta"]+0.06*w30["delta"]
        book_signed=0.36*book5+0.20*clamp(book5-old_book,-1,1)+0.18*change["replenishment"]+0.14*event_ofi+0.12*microprice
        opposite_flow=-body_sign*flow_signed if body_sign else 0.0
        opposite_book=-body_sign*book_signed if body_sign else 0.0
        opposite_move1=max(0.0,-body_sign*path1["move"]) if body_sign else 0.0
        opposite_move5=max(0.0,-body_sign*path5["move"]) if body_sign else 0.0
        old_move1=max(0.0,body_sign*path1["move"]) if body_sign else 0.0
        old_move5=max(0.0,body_sign*path5["move"]) if body_sign else 0.0
        new_aggr=max(0.08,0.6*max(0.0,-body_sign*w1["delta"])+0.4*max(0.0,-body_sign*w5["delta"])) if body_sign else 1.0
        old_aggr=max(0.08,0.6*max(0.0,body_sign*w1["delta"])+0.4*max(0.0,body_sign*w5["delta"])) if body_sign else 1.0
        new_effectiveness=clamp((0.65*opposite_move1+0.35*opposite_move5/5.0)/(sigma_root*max(new_aggr,0.08)*2.5),0,1)
        old_effectiveness=clamp((0.65*old_move1+0.35*old_move5/5.0)/(sigma_root*max(old_aggr,0.08)*2.5),0,1)
        candle_range=max(high-low,1e-9)
        if body_sign>0:
            recovery=max(0.0,high-price)
            wick=safe_float(self.feature.get("upper_wick_ratio"))
            rejection_dyn=clamp(self.reject_up/REJECTION_CAP,0,1)
        elif body_sign<0:
            recovery=max(0.0,price-low)
            wick=safe_float(self.feature.get("lower_wick_ratio"))
            rejection_dyn=clamp(self.reject_down/REJECTION_CAP,0,1)
        else:
            recovery=wick=rejection_dyn=0.0
        retracement=clamp(recovery/candle_range,0,1)
        rejection=clamp(0.42*clamp(wick/0.35,0,1)+0.33*clamp(retracement/0.30,0,1)+0.25*rejection_dyn,0,1)
        opposite_path=clamp((-body_sign*path1["move"])/max(path1["path"],1e-9),0,1) if body_sign else 0.0
        flow_flips=0
        recent=[]
        cutoff=recv_now-5_000
        for row in self.ef_trade_ticks:
            if row[0]>=cutoff:
                sign=1 if row[3]>0 else -1 if row[3]<0 else 0
                if sign: recent.append(sign)
        flow_flips=sum(1 for i in range(1,len(recent)) if recent[i]!=recent[i-1])
        chop=clamp(0.42*(1-path30["efficiency"])+0.28*min(1,flow_flips/8)+0.20*min(1,self.open_cross_count/4)+0.10*min(1,max(0,path30["jump_ratio"]-3)/7),0,1)
        runway=ef_runway_v2(abs(body),recovery,seconds_left,sigma_root,opposite_move1,opposite_move5/5.0,
                            opposite_flow,opposite_book,rejection,opposite_path,chop,
                            new_effectiveness,old_effectiveness,phase)
        # A real local reversal is not enough; settlement feasibility must also pass.
        reversal_quality=clamp(0.30*clamp((opposite_flow+0.08)/0.65,0,1)+0.24*clamp((opposite_book+0.06)/0.48,0,1)+0.22*rejection+0.14*opposite_path+0.10*runway["effectiveness_transfer"],0,1)
        settlement_quality=runway["settlement_feasibility"]
        exceptional=runway["control_transfer"]>=0.82 and reversal_quality>=0.80 and settlement_quality>=0.72
        candidate_eligible=bool(direction and not self.candle.get("closed") and inputs_ready
                                and runway["reachability"]>=0.48
                                and runway["control_transfer"]>=0.54
                                and settlement_quality>=0.56
                                and (chop<=0.82 or exceptional))
        eligible=bool(candidate_eligible and runway["quality"]>=0.59)
        blockers=[]
        if not direction: blockers.append("price is at candle open")
        if not inputs_ready: blockers.append("waiting for fresh BTC trade/depth history")
        if runway["reachability"]<0.48: blockers.append(f"reachability {runway['reachability']:.2f}/0.48")
        if runway["control_transfer"]<0.54: blockers.append(f"control transfer {runway['control_transfer']:.2f}/0.54")
        if settlement_quality<0.56: blockers.append(f"settlement feasibility {settlement_quality:.2f}/0.56")
        if candidate_eligible and runway["quality"]<0.59: blockers.append(f"adaptive quality {runway['quality']:.2f}/0.59")
        if chop>0.82 and not exceptional: blockers.append(f"path too choppy {chop:.2f}")
        self.ef_metrics={
            "direction":direction,"candidate_eligible":candidate_eligible,"eligible":eligible,"phase_second":round(phase,3),"seconds_left":round(seconds_left,3),
            "distance_to_open":round(abs(body),4),"recovery_from_extreme":round(recovery,4),
            "reversal_quality":round(reversal_quality,4),"reachability":round(runway["reachability"],4),
            "control_transfer":round(runway["control_transfer"],4),"settlement_feasibility":round(settlement_quality,4),
            "runway_v2_score":round(runway["quality"],4),"stay_score":round(runway["stay_score"],4),
            "settlement_probability":round(runway["settlement_probability"],6),
            "settlement_probability_base":round(runway["settlement_probability_base"],6),
            "ef_consensus":round(runway["ef_consensus"],6),
            "probability_floor":round(runway["probability_floor"],6),
            "consensus_floor":round(runway["consensus_floor"],6),
            "edge_floor":round(runway["edge_floor"],6),
            "ef_uncertainty":round(runway["ef_uncertainty"],6),
            "volatility_capacity":round(runway["volatility_capacity"],4),"speed_capacity":round(runway["speed_capacity"],4),
            "opposite_flow":round(opposite_flow,4),"opposite_book":round(opposite_book,4),"rejection":round(rejection,4),
            "path_quality":round(opposite_path,4),"chop":round(chop,4),"new_side_effectiveness":round(new_effectiveness,4),
            "old_side_effectiveness":round(old_effectiveness,4),"effectiveness_transfer":round(runway["effectiveness_transfer"],4),
            "delta_250ms":round(w250["delta"],4),"delta_1s":round(w1["delta"],4),"delta_2s":round(w2["delta"],4),
            "delta_5s":round(w5["delta"],4),"delta_30s":round(w30["delta"],4),"book5":round(book5,4),
            "event_ofi":round(event_ofi,4),"microprice":round(microprice,4),"book_replenishment":round(change["replenishment"],4),
            "inputs_ready":inputs_ready,"trade_age_ms":trade_age if trade_age<10**8 else None,"depth_age_ms":depth_age if depth_age<10**8 else None,
            "main_direction":self.current_main.direction if self.current_main else None,
            "main_probability_up":self.current_main.probability_up if self.current_main else None,
            "rev_proximity":round(clamp(runway["control_transfer"]*0.65+settlement_quality*0.35,0,1),4),
            "exceptional_early":bool(exceptional and phase<30.0),"blockers":blockers[:5],
        }

    def _prediction_logic(self, ts_ms: int) -> None:
        if not self.candle or not self.feature:
            return
        self._try_main(ts_ms)
        self._watch_gated(ts_ms)
        if self.current_main and self.current_reversal is None:
            self._watch_reversal(ts_ms)

    def _try_main(self, ts_ms: int) -> None:
        """Fire when the alignment has proven itself, whenever that happens.

        MAIN is the bet and REVERSAL is insurance on it, so insurance paying
        out constantly is a symptom, not a success. Measured over 78 settled
        candles: MAIN was right on 43 of 51 candles that never needed a hedge,
        and 3 of 27 that did. The signal is sound; what was missing is any
        evidence bar before acting on it.

        REVERSAL always had that bar implicitly, because it must overturn an
        open position. MAIN had none and fired on the first flicker, which is
        why 0-10 second calls scored 44 percent against 77 percent after forty
        seconds.

        v5 and v7 shared this firing rule but sampled order flow every few
        seconds over REST, which smoothed it. This model rebuilds features ten
        to twenty times a second, so the same rule now triggers on transients
        the original never saw. Persistence restores the evidence that slower
        sampling used to supply. It is not a clock: a decisive market clears
        it in seconds, a choppy one waits or never qualifies.
        """
        if self.current_main is not None:
            return
        candle_id = int(self.candle["time"])
        phase = (ts_ms - candle_id) / 1000.0
        if phase > MAIN_LAST_SECOND:
            self.main_block = "outside the callable window"
            return

        text = str(self.feature.get("pressure_text", "BALANCED"))
        fair = safe_float(self.feature.get("fair_p_up"), 0.5)
        volume_ratio = safe_float(self.feature.get("volume_ratio"), 1.0)

        if volume_ratio < GATED_VOL_MIN:
            self._reset_main_streak()
            self.main_block = (
                f"volume {volume_ratio:.2f}x below the {GATED_VOL_MIN:g}x floor")
            return

        direction = ""
        if text.startswith("UP") and fair >= GATED_ODDS_UP:
            direction = "UP"
        elif text.startswith("DOWN") and fair <= GATED_ODDS_DOWN:
            direction = "DOWN"
        if not direction:
            self._reset_main_streak()
            self.main_block = (
                f"pressure {text} and odds {fair:.2f} disagree "
                f"(gate {GATED_ODDS_UP:.2f}/{GATED_ODDS_DOWN:.2f})")
            return

        if self.main_streak_dir != direction:
            self.main_streak_dir = direction
            self.main_streak_start_ms = ts_ms
            self.main_streak_reads = 0
        self.main_streak_reads += 1
        held_ms = ts_ms - self.main_streak_start_ms

        if held_ms < MAIN_HOLD_MS or self.main_streak_reads < MAIN_HOLD_READS:
            self.main_block = (
                f"{direction} holding {held_ms / 1000.0:.1f}s of "
                f"{MAIN_HOLD_MS / 1000.0:.0f}s, {self.main_streak_reads} of "
                f"{MAIN_HOLD_READS} reads")
            return

        self.main_block = ""
        self._emit_main(ts_ms)

    def _record_trade(self, prediction: "Prediction", kind: str) -> None:
        """Journal the decision immediately, then enqueue a real live order."""
        record_started_ns = mono_ns()
        gate_acquired = False
        try:
            # Allocate stake and create the QUEUED row in the same ordering
            # domain as master/stake/rule changes and the eventual HTTP POST.
            # This closes the tiny ON+stake race without putting network work
            # on the signal thread.
            self.controls.submit_gate.acquire()
            gate_acquired = True
            seconds_in = (prediction.ts_ms - prediction.candle_id) / 1000.0
            # State X observes only after the signal has genuinely fired. The
            # current Engine feature is the exact live snapshot at emission;
            # prediction.features is a restart/test fallback, never a new
            # calculation or substitute threshold.
            sx_source = dict(prediction.features or {})
            sx_source.update(self.feature or {})
            try:
                sx_evaluation = self.controls.state_x.observe_signal(
                    prediction, sx_source
                )
                sx_blocked = bool(sx_evaluation.get("blocked"))
                sx_fields = dict(sx_evaluation.get("fields") or {})
            except Exception as problem:
                self.record_error(f"State X observation: {problem}")
                sx_blocked, sx_fields = self.controls.state_x.execution_block(
                    prediction.ts_ms
                )
            allowed, why = self.controls.may_execute(kind, prediction.ts_ms)
            # R6 live EF does not synchronously read/sign the Predict.fun book
            # here. Its UP/DOWN hot states are already maintained off-thread.
            # MAIN/REV and shadow/blocked telemetry keep the legacy snapshots.
            quote: Dict[str, Any] = {}
            price = None
            if kind != "EF" or not allowed or sx_blocked:
                try:
                    quote = self.book.quote(prediction.direction)
                except Exception:
                    quote = {}
                price = quote.get("price")
            if not allowed:
                master_off = "master trading switch" in str(why).lower()
                shadow_stake = None
                shadow_shares = None
                execution_vwap = None
                if master_off and price is not None:
                    capital = self.store.capital_state()
                    cfg = self.store.control_row(SYSTEM_CONTROL_KIND)["stake"]
                    shadow_stake = configured_stake(cfg, max(float(capital.get("balance",0.0)), float(cfg.get("current_stake",10.0))))
                    if kind == "EF":
                        ex = self.book.executable_vwap(prediction.direction, shadow_stake)
                        execution_vwap = ex.get("vwap")
                        if not ex.get("ok") or execution_vwap is None or float(execution_vwap) > EF_MAX_SHARE_PRICE:
                            shadow_stake = None
                        elif float(execution_vwap) > 0:
                            price = float(execution_vwap)
                    if shadow_stake is not None and float(price) > 0:
                        shadow_shares = shadow_stake / float(price)
                row = {
                    "candle_id": prediction.candle_id, "kind": kind,
                    "direction": prediction.direction, "ts_ms": prediction.ts_ms,
                    "seconds_into_candle": round(seconds_in, 1),
                    "quoted_price": price, "fill_price": None,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "filled": False, "break_even": quote.get("break_even"),
                    "spread": quote.get("spread"), "book_size": quote.get("size"),
                    "stake": shadow_stake, "shares": shadow_shares,
                    "fee_rate": quote.get("fee_rate", PREDICT_FEE_RATE),
                    "market_id": quote.get("market_id"),
                    "market_title": quote.get("market_title"),
                    "book_age_ms": quote.get("age_ms"),
                    "failure_reason": (f"SHADOW: {why}" if master_off else f"FORBIDDEN: {why}"),
                    "attempt_log": [], "forbidden": not master_off,
                    "execution_mode": "SHADOW" if master_off else "LIVE",
                    "order_status": "SHADOW" if master_off else "FORBIDDEN",
                    "financial_is_shadow": bool(master_off),
                    "execution_eligibility": "MASTER_OFF_SHADOW" if master_off else "FORBIDDEN",
                    "execution_vwap": execution_vwap,
                }
                row.update(sx_fields)
                self.store.record_trade(row)
                self.last_fill = {
                    "kind": kind, "direction": prediction.direction,
                    "filled": False, "price": None, "quoted": price,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "stake": shadow_stake if master_off else 0.0,
                    "shares": shadow_shares if master_off else None,
                    "forbidden": not master_off,
                    "financial_is_shadow": bool(master_off),
                    "state_x": "SX" if sx_blocked else "",
                    "order_status": "SHADOW" if master_off else "FORBIDDEN",
                    "failure_reason": (f"SHADOW: {why}" if master_off else why),
                }
                return

            if sx_blocked:
                row = {
                    "candle_id": prediction.candle_id, "kind": kind,
                    "direction": prediction.direction, "ts_ms": prediction.ts_ms,
                    "seconds_into_candle": round(seconds_in, 1),
                    "quoted_price": price, "fill_price": None,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "filled": False, "break_even": quote.get("break_even"),
                    "spread": quote.get("spread"), "book_size": quote.get("size"),
                    "stake": None, "shares": None,
                    "fee_rate": quote.get("fee_rate", PREDICT_FEE_RATE),
                    "market_id": quote.get("market_id"),
                    "market_title": quote.get("market_title"),
                    "book_age_ms": quote.get("age_ms"),
                    "failure_reason": "STATE X: current trade vetoed",
                    "attempt_log": [], "forbidden": False,
                    "execution_mode": "LIVE", "order_status": "STATE_X",
                }
                row.update(sx_fields)
                self.store.record_trade(row)
                self.last_fill = {
                    "kind": kind, "direction": prediction.direction,
                    "filled": False, "price": None, "quoted": price,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "stake": 0.0, "shares": None, "forbidden": False,
                    "state_x": "SX", "order_status": "STATE_X",
                    "failure_reason": "current trade vetoed by State X",
                }
                return

            capital = self.store.capital_state()
            stake = self.controls.next_stake(kind, capital["free"])
            floor = float(
                self.store.control_row(SYSTEM_CONTROL_KIND)["stake"].get(
                    "min_stake", MIN_STAKE_USD
                )
            )
            if stake < floor:
                status = (
                    f"free capital ${capital['free']:.2f} cannot fund a "
                    f"${floor:.2f} shared stake"
                )
                row = {
                    "candle_id": prediction.candle_id, "kind": kind,
                    "direction": prediction.direction, "ts_ms": prediction.ts_ms,
                    "seconds_into_candle": round(seconds_in, 1),
                    "quoted_price": price, "filled": False, "stake": None,
                    "fee_rate": quote.get("fee_rate", PREDICT_FEE_RATE),
                    "market_id": quote.get("market_id"),
                    "market_title": quote.get("market_title"),
                    "book_age_ms": quote.get("age_ms"),
                    "failure_reason": status, "attempt_log": [],
                    "execution_mode": "LIVE", "order_status": "NO_CAPITAL",
                }
                row.update(sx_fields)
                self.store.record_trade(row)
                self.last_fill = {"kind": kind, "filled": False,
                                  "order_status": "NO_CAPITAL",
                                  "failure_reason": status}
                return

            if kind == "EF":
                # R6: EF bypasses the normal execution queue. The BTC signal is
                # now armed against continuously running UP/DOWN signed orders.
                # No stake is financially reserved until the single full-stake
                # VWAP < $0.50 confirmation hands the hot order to POST.
                hot = self.executor.ef_hot_quote(prediction.direction)
                hot_vwap = finite_float(hot.get("vwap"))
                hot_quote = finite_float(hot.get("quote"))
                row = {
                    "candle_id": prediction.candle_id, "kind": kind,
                    "direction": prediction.direction, "ts_ms": prediction.ts_ms,
                    "seconds_into_candle": round(seconds_in, 1),
                    "quoted_price": hot_quote, "fill_price": None,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "filled": False, "break_even": None, "spread": None,
                    "book_size": hot.get("shares"), "stake": stake, "shares": None,
                    "fee_rate": self.book.fee_rate,
                    "market_id": self.book.market_id,
                    "market_title": self.book.market_title,
                    "book_age_ms": (
                        max(0, now_ms() - int(hot.get("book_ms") or now_ms()))
                        if hot.get("book_ms") else None
                    ),
                    "failure_reason": (
                        f"waiting for full-stake EF VWAP < {EF_MAX_SHARE_PRICE:.2f}"
                    ),
                    "attempt_log": [], "forbidden": False,
                    "execution_mode": "LIVE", "order_status": "WAIT_VWAP",
                    "execution_eligibility": "WAIT_VWAP",
                    "execution_vwap": hot_vwap,
                }
                row.update(sx_fields)
                inserted = self.store.record_trade(row)
                if not inserted:
                    return
                self.executor.arm_ef_hot(prediction, stake)
                self.last_fill = {
                    "kind": "EF", "direction": prediction.direction,
                    "filled": False, "price": None, "quoted": hot_quote,
                    "slippage": None, "delay_ms": 0, "attempts": 0,
                    "stake": stake, "shares": None, "forbidden": False,
                    "order_status": "WAIT_VWAP", "market_id": row["market_id"],
                    "market_title": row["market_title"],
                    "failure_reason": row["failure_reason"],
                }
                self.latency.observe_ms(
                    "ef_hot_signal_handoff",
                    (mono_ns() - record_started_ns) / 1_000_000.0,
                )
                return

            row = {
                "candle_id": prediction.candle_id, "kind": kind,
                "direction": prediction.direction, "ts_ms": prediction.ts_ms,
                "seconds_into_candle": round(seconds_in, 1),
                "quoted_price": price, "fill_price": None,
                "slippage": None, "delay_ms": 0, "attempts": 0,
                "filled": False, "break_even": quote.get("break_even"),
                "spread": quote.get("spread"), "book_size": quote.get("size"),
                "stake": stake, "shares": None,
                "fee_rate": quote.get("fee_rate", self.book.fee_rate),
                "market_id": quote.get("market_id"),
                "market_title": quote.get("market_title"),
                "book_age_ms": quote.get("age_ms"), "failure_reason": None,
                "attempt_log": [], "forbidden": False,
                "execution_mode": "LIVE", "order_status": "QUEUED",
            }
            row.update(sx_fields)
            inserted = self.store.record_trade(row)
            if not inserted:
                # The database key is the final idempotency boundary. A
                # repeated callback or restart must never enqueue a second
                # venue order for the same candle and signal.
                return
            self.last_fill = {
                "kind": kind, "direction": prediction.direction,
                "filled": False, "price": None, "quoted": price,
                "slippage": None, "delay_ms": 0, "attempts": 0,
                "stake": stake, "shares": None, "forbidden": False,
                "order_status": "QUEUED", "market_id": row["market_id"],
                "market_title": row["market_title"],
            }
            handoff_started_ns = mono_ns()
            handed_off = self.executor.enqueue(prediction, kind)
            self.latency.observe_ms(
                "execution_queue_handoff",
                (mono_ns() - handoff_started_ns) / 1_000_000.0,
            )
            self.latency.observe_ms(
                "signal_to_intent",
                (mono_ns() - record_started_ns) / 1_000_000.0,
            )
            if not handed_off:
                queue_reason = "execution intent queue full; no order posted"
                self.store.update_trade_execution(
                    prediction.candle_id, kind, order_status="QUEUE_FULL",
                    failure_reason=queue_reason)
                self.last_fill["order_status"] = "QUEUE_FULL"
                self.last_fill["failure_reason"] = queue_reason
                if kind == "EF":
                    self.executor.defer_ef_release_when_queue_available(
                        prediction, queue_reason
                    )
        except Exception as exc:
            self.book.error = f"record: {exc}"[:180]
        finally:
            if gate_acquired:
                self.controls.submit_gate.release()

    def _reset_main_streak(self) -> None:
        self.main_streak_dir = ""
        self.main_streak_start_ms = 0
        self.main_streak_reads = 0

    def _emit_main(self, ts_ms: int) -> None:
        """One MAIN prediction per candle, always produced.

        The v5/v7 core is unchanged: the pressure gauge names a direction and
        the fair-odds model says how far the candle has already travelled.
        What is new is that neither can veto the call. Both are blended with
        the feature model into a single probability, which is then pulled
        toward a coin flip by four conditions that make a call less reliable:
        thin or violent participation, a wick rejecting the direction, an
        early call with little evidence, and a move too large for the time
        that remains.

        A hostile condition therefore lowers confidence rather than removing
        the prediction, so every candle is still called and every call is
        still measurable.
        """
        model_p_up = clamp(safe_float(self.feature.get("probability_up"), 0.5),
                           0.01, 0.99)
        fair_p_up = clamp(safe_float(self.feature.get("fair_p_up"), 0.5),
                          0.01, 0.99)
        score = clamp(safe_float(self.feature.get("pressure_score"), 0.0),
                      -1.0, 1.0)
        pressure_p_up = 0.5 + score / 2.0

        # v5/v7 weighting: order flow leads, fair odds anchors, the feature
        # model arbitrates.
        blended = (0.40 * pressure_p_up + 0.35 * fair_p_up + 0.25 * model_p_up)
        edge = blended - 0.5
        # The alignment that permitted the call names the side; the blend only
        # sizes the conviction. When the feature model outvotes both the gauge
        # and the odds, the tested pair wins and conviction drops to nothing.
        text_now = str(self.feature.get("pressure_text", "BALANCED"))
        direction = "UP" if text_now.startswith("UP") else "DOWN"
        direction_sign = 1.0 if direction == "UP" else -1.0
        # The alignment names the side; the blend sizes the conviction. When
        # the feature model outvotes both the gauge and the odds, conviction
        # is reduced rather than destroyed: zeroing it discarded a real
        # disagreement signal and produced identical 0.5 calls.
        if edge * direction_sign > 0:
            edge = abs(edge) * direction_sign
        else:
            edge = abs(edge) * direction_sign * EDGE_CONTRADICTION_KEEP

        volume_ratio = safe_float(self.feature.get("volume_ratio"), 1.0)
        upper_wick = safe_float(self.feature.get("upper_wick_ratio"), 0.0)
        lower_wick = safe_float(self.feature.get("lower_wick_ratio"), 0.0)
        seconds_in = safe_float(self.feature.get("phase_second"), 0.0)
        seconds_left = max(300.0 - seconds_in, 1.0)
        price = safe_float(self.feature.get("price"), 0.0)
        open_price = safe_float(self.candle.get("open"), price)
        sigma_root = self._sigma_per_root_second()

        # The move still required for this call to be correct: if we say UP
        # while price sits below the open, the candle must recover that gap.
        lead = price - open_price
        required = 0.0 if lead * direction_sign > 0 else abs(lead)

        reject_up = safe_float(self.feature.get("reject_up"), 0.0)
        reject_down = safe_float(self.feature.get("reject_down"), 0.0)
        f_volume = volume_factor(volume_ratio)
        f_reject = rejection_factor(direction_sign, reject_up, reject_down)
        f_runway = runway_factor(seconds_left)
        f_feasible = feasibility_factor(required, sigma_root, seconds_left)
        confidence = f_volume * f_reject * f_runway * f_feasible

        probability_up = clamp(0.5 + edge * confidence, 0.02, 0.98)
        self.last_confidence = {
            "blended": round(blended, 4),
            "volume": round(f_volume, 3),
            "rejection": round(f_reject, 3),
            "runway": round(f_runway, 3),
            "feasibility": round(f_feasible, 3),
            "reject_up": round(reject_up, 3),
            "reject_down": round(reject_down, 3),
            "combined": round(confidence, 3),
            "required_move": round(required, 2),
            "expected_move": round(sigma_root * math.sqrt(seconds_left), 2),
        }
        snapshot = self._model_feature_snapshot()
        reason = (
            f"blend {blended:.2f} (pressure {pressure_p_up:.2f}, "
            f"fair {fair_p_up:.2f}, model {model_p_up:.2f}) x confidence "
            f"{confidence:.2f} [volume {f_volume:.2f}, "
            f"rejection {f_reject:.2f} (up {reject_up:.1f} down "
            f"{reject_down:.1f}), runway {f_runway:.2f}, "
            f"feasibility {f_feasible:.2f}] "
            f"at {seconds_in:.0f}s, volume {volume_ratio:.2f}x, "
            f"needs {required:.1f} of {sigma_root * math.sqrt(seconds_left):.1f} USD"
        )
        prediction = Prediction(
            candle_id=int(self.candle["time"]),
            kind="MAIN",
            direction=direction,
            ts_ms=ts_ms,
            price=float(self.feature["price"]),
            probability_up=probability_up,
            reason=reason,
            features=snapshot,
        )
        if self.store.add_prediction(prediction):
            self.current_main = prediction
            self.chart_revision += 1
            self._record_trade(prediction, "MAIN")
        else:
            self.current_main = self.store.get_prediction(prediction.candle_id, "MAIN")

    def _watch_gated(self, ts_ms: int) -> None:
        """The v5/v7 entry: flow, fair odds and volume must all agree.

        This fires at most once per candle and is scored separately from MAIN,
        so a high hit rate here can never disguise a weak open-of-candle signal.
        """
        if self.current_gated is not None or not self.candle:
            return
        phase = float(self.feature.get("phase_second", 0.0))
        if not (GATED_MIN_SECOND <= phase <= GATED_LAST_SECOND):
            self.gated_block = "outside the odds window"
            return
        probability_up = safe_float(self.feature.get("probability_up"), 0.5)
        fair = safe_float(self.feature.get("fair_p_up"), 0.5)
        volume_ratio = safe_float(self.feature.get("volume_ratio"), 1.0)
        if volume_ratio < GATED_VOL_MIN:
            self.gated_block = f"volume {volume_ratio:.2f}x below {GATED_VOL_MIN:g}x"
            return
        direction: Optional[str] = None
        if fair >= GATED_ODDS_UP and probability_up >= 0.5 + GATED_FLOW_EDGE:
            direction = "UP"
        elif fair <= GATED_ODDS_DOWN and probability_up <= 0.5 - GATED_FLOW_EDGE:
            direction = "DOWN"
        if direction is None:
            self.gated_block = (
                f"odds {fair:.2f} and flow {probability_up:.2f} disagree"
            )
            return
        entry_odds = fair if direction == "UP" else 1.0 - fair
        if entry_odds >= GATED_MAX_ODDS:
            self.gated_block = f"odds {entry_odds:.2f} too expensive to be worth it"
            return
        row = {
            "candle_id": int(self.candle["time"]),
            "direction": direction,
            "ts_ms": ts_ms,
            "phase_second": phase,
            "price": float(self.feature["price"]),
            "entry_odds": entry_odds,
            "reason": (
                f"fair {fair:.2f}, flow {probability_up:.2f}, "
                f"volume {volume_ratio:.2f}x, {phase:.0f}s in"
            ),
        }
        if self.store.add_gated(row):
            self.current_gated = self.store.get_gated(row["candle_id"])
            self.gated_block = ""
            self.chart_revision += 1
        else:
            self.current_gated = self.store.get_gated(row["candle_id"])

    def _watch_reversal(self, ts_ms: int) -> None:
        if not self.current_main:
            return
        phase = float(self.feature.get("phase_second", 0.0))
        if not (REVERSAL_MIN_SECOND <= phase <= REVERSAL_LAST_SECOND):
            self.reversal_candidate_since_ms = 0
            self.reversal_samples = 0
            self.reversal_evidence = {
                "status": "waiting for mid-candle window",
                "checks": {},
                "passed_checks": 0,
                "required_checks": REVERSAL_CHECK_COUNT,
                "persistence_ms": 0,
                "samples": 0,
            }
            return

        # ------------------------------------------------------------------
        # v5/v7 reversal: one condition, exactly as btc_v7.py line 882.
        #
        #     if pending and live and live != pending[0] and not pending[7]:
        #
        # A position is open, the MAIN rule now names the opposite direction,
        # and this candle has not been hedged yet. That is the whole test.
        #
        # The eight-check gate that stood here was a v4 invention and fired on
        # roughly one candle in fifty-seven. A reversal only earns its keep by
        # firing on candles where MAIN was wrong, and it cannot do that if it
        # is filtered until the move is already over.
        # ------------------------------------------------------------------
        main_direction = self.current_main.direction
        text = str(self.feature.get("pressure_text", "BALANCED"))
        fair = safe_float(self.feature.get("fair_p_up"), 0.5)
        volume_ratio = safe_float(self.feature.get("volume_ratio"), 1.0)

        live: Optional[str] = None
        if volume_ratio >= GATED_VOL_MIN:
            if text.startswith("UP") and fair >= GATED_ODDS_UP:
                live = "UP"
            elif text.startswith("DOWN") and fair <= GATED_ODDS_DOWN:
                live = "DOWN"

        if live is None:
            self.reversal_state = {
                "status": "watching",
                "detail": f"pressure {text}, odds {fair:.2f}, "
                          f"volume {volume_ratio:.2f}x",
            }
            return
        if live == main_direction:
            self.reversal_state = {
                "status": "watching",
                "detail": f"signal still agrees with MAIN {main_direction}",
            }
            return

        self.reversal_state = {
            "status": "firing",
            "detail": f"signal flipped {main_direction} to {live}: "
                      f"{text}, odds {fair:.2f}",
        }
        self._emit_reversal(ts_ms, live, self.reversal_state["detail"])

    def _emit_reversal(self, ts_ms: int, direction: str, detail: str) -> None:
        """Record the hedge leg. Direction comes from the flipped MAIN rule."""
        assert self.current_main is not None
        probability_up = (
            safe_float(self.feature.get("fair_p_up"), 0.5)
            if direction == "UP"
            else 1.0 - safe_float(self.feature.get("fair_p_up"), 0.5)
        )
        seconds_in = (ts_ms - int(self.candle["time"])) / 1000.0
        reason = f"v5/v7 reversal at {seconds_in:.0f}s: {detail}"
        prediction = Prediction(
            candle_id=int(self.candle["time"]),
            kind="REVERSAL",
            direction=direction,
            ts_ms=ts_ms,
            price=float(self.feature["price"]),
            probability_up=clamp(probability_up, 0.0, 1.0),
            reason=reason,
            features=self._model_feature_snapshot(),
        )
        if self.store.add_prediction(prediction):
            self.current_reversal = prediction
            self._record_trade(prediction, "REVERSAL")
            self.chart_revision += 1
            self.reversal_evidence["status"] = f"TRIGGERED {direction}"
        else:
            self.current_reversal = self.store.get_prediction(
                prediction.candle_id, "REVERSAL"
            )

    def _reset_ef_candidate(self) -> None:
        self.ef_candidate_direction = ""
        self.ef_candidate_since_ms = 0
        self.ef_candidate_reads = 0

    def _r5_force_system_price_limit(self, event: Dict[str, Any]) -> None:
        """Forget an EF immediately when the execution system hits PRICE_LIMIT.

        This path deliberately does not wait for Store archival, a Binance tick,
        a Predict.fun depth frame, or another EF opportunity. Only the exact
        in-memory signal identity can be cleared. A newer same-candle EF is never
        touched. After exactly the execution cooldown, the independent lifecycle
        loop flips the monitor to WATCHING even if no market event arrives.
        """
        cid = int(event.get("candle_id") or -1)
        sig_ts = int(event.get("signal_ts_ms") or -1)
        sig_dir = str(event.get("direction") or "").upper()
        detected = int(event.get("detected_ms") or now_ms())
        cooldown_until = detected + EF_PRICE_LIMIT_COOLDOWN_MS
        with self.lock:
            current_cid = int(self.candle.get("time") or -1) if self.candle else -1
            if current_cid != cid:
                return
            current = self.current_ef
            if current is not None:
                exact = (
                    int(current.candle_id) == cid
                    and int(current.ts_ms) == sig_ts
                    and str(current.direction or "").upper() == sig_dir
                )
                if not exact:
                    # Never clear a newer/different EF identity.
                    return
                self.current_ef = None
                self.ef_post_progress = None
            self._reset_ef_candidate()
            self.ef_rearm_cooldown_until_ms = cooldown_until
            self.ef_rearm_cooldown_reason = "PRICE_LIMIT"
            self.ef_rearm_attempt_seq = 0
            self.ef_monitor = {
                **dict(self.ef_metrics or {}),
                "status": "COOLDOWN",
                "reason": (
                    f"system PRICE_LIMIT; forgot EF immediately; "
                    f"re-watch in {EF_PRICE_LIMIT_COOLDOWN_MS / 1000.0:.1f}s"
                ),
                "ready": False,
                "cooldown_until_ms": cooldown_until,
            }
            self.chart_revision += 1

    def _r5_apply_rearm_notice_immediate(self, event: Dict[str, Any]) -> None:
        """Immediately tombstone an archived EF in Engine memory.

        Store calls this only *after* the failed attempt is durably archived and
        deleted from the active EF/trade slot. This makes dashboard state follow
        execution truth immediately: PRICE_LIMIT -> COOLDOWN -> WATCHING, without
        depending on another depth/trade event to clear ``current_ef``.
        """
        cid = int(event.get("candle_id") or -1)
        sig_ts = int(event.get("signal_ts_ms") or -1)
        sig_dir = str(event.get("direction") or "").upper()
        status = str(event.get("status") or "").upper()
        ack = False
        with self.lock:
            current_cid = int(self.candle.get("time") or -1) if self.candle else -1
            if current_cid > cid >= 0:
                ack = True
            elif current_cid != cid:
                return
            else:
                current = self.current_ef
                if current is not None and int(current.candle_id) == cid:
                    if int(current.ts_ms) > sig_ts:
                        # A genuinely newer same-candle attempt already exists.
                        ack = True
                    else:
                        # The archive is authoritative for this equal/older EF.
                        self.current_ef = None
                        self.ef_post_progress = None
                self._reset_ef_candidate()
                cooldown_until = int(event.get("cooldown_until_ms") or 0)
                if status == "PRICE_LIMIT" and cooldown_until > now_ms():
                    self.ef_rearm_cooldown_until_ms = max(
                        int(self.ef_rearm_cooldown_until_ms or 0), cooldown_until
                    )
                    self.ef_rearm_cooldown_reason = "PRICE_LIMIT"
                    self.ef_rearm_attempt_seq = int(event.get("attempt_seq") or 0)
                    remaining_ms = max(0, cooldown_until - now_ms())
                    self.ef_monitor = {
                        **dict(self.ef_metrics or {}),
                        "status": "COOLDOWN",
                        "reason": (
                            f"EF attempt #{int(event.get('attempt_seq') or 0)} hit PRICE_LIMIT; "
                            f"re-watch in {remaining_ms / 1000.0:.1f}s"
                        ),
                        "ready": False,
                        "cooldown_until_ms": cooldown_until,
                        "attempt_seq": int(event.get("attempt_seq") or 0),
                    }
                else:
                    self.ef_monitor = {
                        **dict(self.ef_metrics or {}),
                        "status": "WATCHING",
                        "reason": (
                            f"previous EF attempt #{int(event.get('attempt_seq') or 0)} "
                            f"execution failed ({status}); watching for a new opportunity"
                        ),
                        "ready": False,
                        "attempt_seq": int(event.get("attempt_seq") or 0),
                    }
                self.chart_revision += 1
                ack = True
        if ack:
            self.store.r5_ack_ef_rearm_notice(cid, sig_ts, sig_dir)

    def _r5_rearm_failed_ef(self, ts_ms: int) -> bool:
        """Apply exact failed-EF lifecycle events and ACK only after handling.

        R5 used a SimpleQueue and discarded events when current_ef was None or
        did not yet match. That could leave a deleted PRICE_LIMIT attempt stuck
        as TRIGGERED in Engine memory forever. R5.1 keeps events pending until
        the exact identity is cleared (or is provably stale because a newer
        candle/attempt already exists).
        """
        pending = self.store.r5_pending_ef_rearm_notices()
        if not pending:
            return False
        changed = False
        current_cid = int(self.candle.get("time") or -1) if self.candle else -1
        for event in pending:
            cid = int(event.get("candle_id") or -1)
            sig_ts = int(event.get("signal_ts_ms") or -1)
            sig_dir = str(event.get("direction") or "").upper()
            status = str(event.get("status") or "").upper()

            # A prior-candle notice cannot affect the current candle. ACK it;
            # the database archive is already the durable audit trail.
            if current_cid > cid >= 0:
                self.store.r5_ack_ef_rearm_notice(cid, sig_ts, sig_dir)
                continue
            if current_cid != cid:
                continue

            exact = bool(
                self.current_ef is not None
                and int(self.current_ef.candle_id) == cid
                and int(self.current_ef.ts_ms) == sig_ts
                and str(self.current_ef.direction or "").upper() == sig_dir
            )
            newer_same_candle = bool(
                self.current_ef is not None
                and int(self.current_ef.candle_id) == cid
                and int(self.current_ef.ts_ms) > sig_ts
            )
            stale_same_candle = bool(
                self.current_ef is not None
                and int(self.current_ef.candle_id) == cid
                and int(self.current_ef.ts_ms) <= sig_ts
            )
            if self.current_ef is not None and not exact:
                if newer_same_candle:
                    # The old event arrived after a newer EF was already formed;
                    # never clear the newer identity. The old archive is enough.
                    self.store.r5_ack_ef_rearm_notice(cid, sig_ts, sig_dir)
                    continue
                if not stale_same_candle:
                    continue

            if status in set(PREDICT_ORDER_TERMINAL_FAILURES):
                self._r5_ef_terminal_latch = (cid, sig_dir)
            if exact or stale_same_candle:
                # The Store notice is an authoritative tombstone: it is emitted
                # only after the corresponding unfilled EF rows were archived
                # and deleted. Protect a genuinely newer same-candle attempt,
                # but never let an equal/older in-memory EF keep the UI TRIGGERED.
                self.current_ef = None
                self.ef_post_progress = None
            self._reset_ef_candidate()

            cooldown_until = int(event.get("cooldown_until_ms") or 0)
            if status == "PRICE_LIMIT" and cooldown_until > int(ts_ms):
                self.ef_rearm_cooldown_until_ms = max(
                    int(self.ef_rearm_cooldown_until_ms or 0), cooldown_until
                )
                self.ef_rearm_cooldown_reason = "PRICE_LIMIT"
                self.ef_rearm_attempt_seq = int(event.get("attempt_seq") or 0)
            remaining_ms = max(0, int(self.ef_rearm_cooldown_until_ms or 0) - int(ts_ms))
            if remaining_ms > 0:
                self.ef_monitor = {
                    "status": "COOLDOWN",
                    "reason": (
                        f"EF attempt #{int(event.get('attempt_seq') or 0)} hit PRICE_LIMIT; "
                        f"re-watch in {remaining_ms / 1000.0:.1f}s"
                    ),
                    "ready": False,
                    "rearmed_ms": int(ts_ms),
                    "cooldown_until_ms": int(self.ef_rearm_cooldown_until_ms),
                    "attempt_seq": int(event.get("attempt_seq") or 0),
                }
            else:
                self.ef_monitor = {
                    "status": "WATCHING",
                    "reason": (
                        f"previous EF attempt #{int(event.get('attempt_seq') or 0)} "
                        f"execution failed ({status}); watching for a new opportunity"
                    ),
                    "ready": False,
                    "rearmed_ms": int(ts_ms),
                    "attempt_seq": int(event.get("attempt_seq") or 0),
                }
            self.chart_revision += 1
            self.store.r5_ack_ef_rearm_notice(cid, sig_ts, sig_dir)
            changed = True
        return changed

    def _watch_ef(self, ts_ms: int) -> None:
        """Production EF using the r6.2 Early-EF BTC prep gate.

        The directional candidate and all inputs come from the causal BTC EF
        prep state already computed in memory. Predict.fun is not read here.
        Once the Early-EF thresholds pass, execution is handed immediately to
        the existing R6 hot executor.
        """
        if not self.candle or not self.feature:
            return
        if self.current_ef is not None:
            self.ef_monitor = {
                **dict(self.ef_metrics),
                "status": f"TRIGGERED {self.current_ef.direction}",
                "ready": True,
            }
            return

        evidence = dict(self.ef_metrics or {})
        direction = str(evidence.get("direction") or "").upper()
        inputs_ready = bool(evidence.get("inputs_ready"))
        prep_candidate = inputs_ready and direction in ("UP", "DOWN")
        terminal_latch = getattr(self, "_r5_ef_terminal_latch", None)

        if not prep_candidate:
            if terminal_latch is not None:
                self._r5_ef_terminal_latch = None
            self._reset_ef_candidate()
            self.ef_monitor = {
                **evidence,
                "status": (
                    (evidence.get("blockers") or ["waiting for fresh BTC prep evidence"])[0]
                ),
                "ready": False,
            }
            return

        if terminal_latch is not None:
            latch_cid, latch_dir = terminal_latch
            current_cid = int(self.candle.get("time") or 0)
            if latch_cid != current_cid or direction != latch_dir:
                self._r5_ef_terminal_latch = None
            else:
                self.ef_monitor = {
                    **evidence,
                    "status": "previous terminal-rejected EF still represents the same BTC prep opportunity",
                    "ready": False,
                }
                return

        # One continuous candidate episode per direction. This is bookkeeping
        # only; it adds no persistence delay or read-count gate.
        if self.ef_candidate_direction != direction:
            self.ef_candidate_direction = direction
            self.ef_candidate_since_ms = int(ts_ms)
            self.ef_candidate_reads = 0
        self.ef_candidate_reads += 1
        candidate_ts = int(self.ef_candidate_since_ms or ts_ms)

        # Exact Early-EF A/B formula promoted from last night's forward test.
        reach = clamp(safe_float(evidence.get("reachability")), 0.0, 1.0)
        control = clamp(safe_float(evidence.get("control_transfer")), 0.0, 1.0)
        settle = clamp(safe_float(evidence.get("settlement_feasibility")), 0.0, 1.0)
        quality = clamp(safe_float(evidence.get("runway_v2_score")), 0.0, 1.0)
        chop = clamp(safe_float(evidence.get("chop")), 0.0, 1.0)
        sign = 1.0 if direction == "UP" else -1.0
        d250 = sign * safe_float(evidence.get("delta_250ms"))
        d1 = sign * safe_float(evidence.get("delta_1s"))
        d2 = sign * safe_float(evidence.get("delta_2s"))
        slow = 0.60 * d1 + 0.40 * d2
        acceleration = d250 - slow
        accel_support = clamp((acceleration + 0.18) / 0.42, 0.0, 1.0)
        fast_support = clamp((d250 + 0.12) / 0.52, 0.0, 1.0)
        early_score = clamp(
            0.27 * reach + 0.27 * control + 0.22 * settle
            + 0.12 * quality + 0.07 * accel_support + 0.05 * fast_support,
            0.0, 1.0,
        )

        blockers: List[str] = []
        if reach < EF_EARLY_REACH_MIN:
            blockers.append(f"reach {reach:.2f}/{EF_EARLY_REACH_MIN:.2f}")
        if control < EF_EARLY_CONTROL_MIN:
            blockers.append(f"control {control:.2f}/{EF_EARLY_CONTROL_MIN:.2f}")
        if settle < EF_EARLY_SETTLEMENT_MIN:
            blockers.append(f"settle {settle:.2f}/{EF_EARLY_SETTLEMENT_MIN:.2f}")
        if quality < EF_EARLY_QUALITY_MIN:
            blockers.append(f"quality {quality:.2f}/{EF_EARLY_QUALITY_MIN:.2f}")
        if chop > EF_EARLY_CHOP_MAX:
            blockers.append(f"chop {chop:.2f}/{EF_EARLY_CHOP_MAX:.2f}")
        if early_score < EF_EARLY_SCORE_MIN:
            blockers.append(f"early score {early_score:.3f}/{EF_EARLY_SCORE_MIN:.3f}")

        evidence.update({
            "early_prep_score": early_score,
            "flow_acceleration": acceleration,
            "aligned_delta_250ms": d250,
            "aligned_delta_1s": d1,
            "aligned_delta_2s": d2,
            "expected_edge": None,
            "reference_vwap_10": None,
            "abstain_reason": "; ".join(blockers),
        })
        side_probability = clamp(
            safe_float(evidence.get("settlement_probability"), 0.5), 0.01, 0.99
        )
        probability_up = side_probability if direction == "UP" else 1.0 - side_probability

        def record_candidate(fired: bool, reason: str) -> None:
            candidate_evidence = dict(evidence)
            candidate_evidence["abstain_reason"] = str(reason or "")
            snapshot = self._model_feature_snapshot()
            for key, value in candidate_evidence.items():
                if key != "blockers":
                    snapshot["ef_" + key] = value
            snapshot["ef_reference_vwap_10"] = None
            snapshot["ef_abstain_reason"] = str(reason or "")
            self.store.upsert_ef_candidate(
                candle_id=int(self.candle["time"]), direction=direction,
                candidate_ts_ms=candidate_ts, decision_ts_ms=int(ts_ms),
                price=float(self.feature["price"]), probability_up=probability_up,
                fired=bool(fired), abstain_reason=str(reason or ""),
                reference_vwap_10=None, evidence=candidate_evidence,
                features=snapshot,
            )

        if blockers:
            if self.ef_candidate_reads == 1:
                record_candidate(False, blockers[0])
            self.ef_monitor = {
                **evidence,
                "status": blockers[0],
                "blockers": blockers,
                "ready": False,
            }
            return

        # BTC decision is final here. No Predict.fun quote or book lookup is
        # allowed to delay/veto the signal. The existing hot executor owns all
        # execution economics, dynamic min-out tolerance and retry safety.
        execution = {
            "reason": "EXECUTOR_PENDING",
            "vwap": None,
            "max_price": None,
            "shares": None,
        }
        self._emit_ef(ts_ms, direction, evidence, execution, True)
        record_candidate(True, "")

    def _emit_ef(
        self, ts_ms: int, direction: str, evidence: Dict[str, Any],
        execution: Dict[str, Any], execution_eligible: bool,
    ) -> None:
        """Persist the BTC EF; Predict.fun execution is downstream only."""
        quality=clamp(safe_float(evidence.get("runway_v2_score"),0.5),0.0,1.0)
        side_probability=clamp(safe_float(evidence.get("settlement_probability"),0.5),0.01,0.99)
        probability_up=side_probability if direction=="UP" else 1.0-side_probability
        reason=(f"BTC-only EF Runway v2 {direction}: reversal {safe_float(evidence.get('reversal_quality')):.2f}, "
                f"reach {safe_float(evidence.get('reachability')):.2f}, control {safe_float(evidence.get('control_transfer')):.2f}, "
                f"settlement {safe_float(evidence.get('settlement_feasibility')):.2f}, "
                f"pclose {safe_float(evidence.get('settlement_probability')):.3f}, "
                f"consensus {safe_float(evidence.get('ef_consensus')):.3f}; "
                f"execution {execution.get('reason','EXECUTOR_PENDING')}")
        snapshot=self._model_feature_snapshot()
        for key,value in evidence.items():
            if key!="blockers": snapshot["ef_"+key]=value
        attempt_seq = self.store.next_ef_attempt_seq(int(self.candle["time"]))
        snapshot.update({
            "ef_attempt_seq": attempt_seq,
            "ef_execution_vwap":execution.get("vwap"),"ef_execution_max_price":execution.get("max_price"),
            "ef_execution_shares":execution.get("shares"),"ef_execution_eligible":1.0 if execution_eligible else 0.0,
            "ef_execution_reason":str(execution.get("reason") or ""),
        })
        prediction=Prediction(int(self.candle["time"]),"EF",direction,int(ts_ms),float(self.feature["price"]),probability_up,reason,features=snapshot)
        if not self.store.add_ef_prediction(prediction):
            self.current_ef=self.store.get_ef_prediction(prediction.candle_id)
            return
        self.current_ef=prediction
        open_price=float(self.candle.get("open", prediction.price))
        initial_distance=abs(float(prediction.price)-open_price)
        self.ef_post_progress={
            "candle_id":prediction.candle_id,"direction":direction,
            "fire_ts_ms":prediction.ts_ms,"fire_price":float(prediction.price),
            "candle_open":open_price,"initial_distance":initial_distance,
            "closest_distance":initial_distance,"progress_fraction":0.0,
            "crossed_open":False,"first_cross_ms":None,"best_side_distance":0.0,
            "fire_features":snapshot,
        }
        if execution_eligible:
            self._record_trade(prediction,"EF")
        else:
            quote=self.book.quote(direction)
            row={
                "candle_id":prediction.candle_id,"kind":"EF","direction":direction,"ts_ms":prediction.ts_ms,
                "seconds_into_candle":round((prediction.ts_ms-prediction.candle_id)/1000.0,1),
                "quoted_price":execution.get("vwap") if execution.get("vwap") is not None else quote.get("price"),
                "fill_price":None,"slippage":None,"delay_ms":0,"attempts":0,"filled":False,
                "break_even":quote.get("break_even"),"spread":quote.get("spread"),"book_size":quote.get("size"),
                "stake":None,"shares":None,"fee_rate":quote.get("fee_rate",PREDICT_FEE_RATE),
                "market_id":quote.get("market_id"),"market_title":quote.get("market_title"),"book_age_ms":quote.get("age_ms"),
                "failure_reason":f"EF EXECUTION INELIGIBLE: {execution.get('reason','UNKNOWN')}","attempt_log":[],
                "forbidden":False,"execution_mode":"ELIGIBILITY_ONLY","order_status":str(execution.get("reason") or "INELIGIBLE"),
                "execution_eligibility":str(execution.get("reason") or "INELIGIBLE"),"execution_vwap":execution.get("vwap"),
            }
            self.store.record_trade(row)
        # Research-only excursion persistence runs after the live order handoff
        # so it cannot add SQLite latency before executor.enqueue().
        self.store.save_ef_progress(self.ef_post_progress)
        self.chart_revision+=1
        self.ef_monitor={**evidence,"status":f"TRIGGERED {direction} · {execution.get('reason','UNKNOWN')}",
                         "ready":True,"execution_vwap":execution.get("vwap"),"execution_eligible":execution_eligible}

    def live_snapshot(self) -> Dict[str, Any]:
        """Dashboard snapshot without SQLite/network work under Engine.lock."""
        current_ms = now_ms()
        with self.lock:
            candle = dict(self.candle) if self.candle else None
            if candle:
                candle["phase_second"] = clamp(
                    (current_ms - int(candle["time"])) / 1000.0, 0.0, 300.0
                )
                candle["seconds_left"] = max(
                    0.0, (int(candle["time"]) + CANDLE_MS - current_ms) / 1000.0
                )
            error = (
                self.last_error
                if self.last_error and current_ms - self.last_error_ms < 120_000
                else ""
            )
            feature = dict(self.feature)
            main = self.current_main.as_dict() if self.current_main else None
            reversal = self.current_reversal.as_dict() if self.current_reversal else None
            ef = self.current_ef.as_dict() if self.current_ef else None
            ef_monitor = dict(self.ef_monitor)
            reversal_monitor = dict(self.reversal_evidence)
            last_fill_fallback = dict(self.last_fill) if isinstance(self.last_fill, dict) else self.last_fill
            feed = {
                "status": self.feed_status,
                "url": self.feed_url,
                "last_event_age_ms": (
                    current_ms - self.last_event_local_ms
                    if self.last_event_local_ms else None
                ),
                "exchange_latency_ms": self.exchange_latency_ms,
                "events_per_sec": self.event_rate,
                "event_count": self.event_count,
                "streams": self._stream_health(current_ms),
                "clock_skew_ms": self.clock_skew_ms,
            }
            processing = {
                "feature_compute_us": self.feature_compute_us,
                "market_queue_depth": self.market_events.qsize(),
                "market_queue_max_depth": self.market_queue_max_depth,
                "market_queue_dropped": self.market_queue_dropped,
                "feature_age_ms": (
                    current_ms - int(feature.get("ts_ms", 0)) if feature else None
                ),
            }
            main_block = self.main_block
            gated = dict(self.current_gated) if isinstance(self.current_gated, dict) else self.current_gated
            gated_block = self.gated_block
            learning = dict(self.last_learning)
            chart_revision = self.chart_revision
            state_revision = self.state_revision
            model_snapshot = {
                "version": self.model.version,
                "updates": self.model.samples,
                "temperature": self.model.temperature,
                "max_drift": MODEL_WEIGHT_CLAMP,
                "learning_rate": MODEL_LEARNING_RATE,
                "min_samples": MODEL_MIN_SAMPLES,
            }
            uptime_sec = (current_ms - self.started_ms) / 1000.0

        # Independent locks / SQLite / SDK state are read only after Engine.lock
        # is released, so a slow dashboard request cannot stall market processing.
        processing["latency"] = self.latency.snapshot()
        trade_summary = self.store.trade_summary()
        controls_snapshot = self.controls.snapshot(current_ms)
        capital = self.store.capital_state()
        leg_pnl = self.store.leg_pnl()
        open_positions = self.store.venue_open_positions()
        unredeemed = self.store.venue_unredeemed_positions()
        metrics = self.store.metrics()
        book = self.book.snapshot()
        last_fill = self.store.latest_trade() or last_fill_fallback
        execution = self.executor.readiness()
        gated_metrics = self.store.gated_metrics()
        return {
            "version": VERSION,
            "build_revision": BUILD_REVISION,
            "build_number": BUILD_NUMBER,
            "capital": capital,
            "leg_pnl": leg_pnl,
            "open_positions": open_positions,
            "unredeemed": unredeemed,
            "build_sha": BUILD_SHA,
            "built_at": BUILT_AT,
            "server_ms": current_ms,
            "uptime_sec": uptime_sec,
            "feed": feed,
            "processing": processing,
            "candle": candle,
            "feature": feature,
            "main": main,
            "reversal": reversal,
            "ef": ef,
            "ef_monitor": ef_monitor,
            "reversal_monitor": reversal_monitor,
            "metrics": metrics,
            "trades": trade_summary,
            "book": book,
            "last_fill": last_fill,
            "execution": execution,
            "controls": controls_snapshot,
            "main_block": main_block,
            "regime": feature.get("regime", ""),
            "gated": gated,
            "gated_block": gated_block,
            "gated_metrics": gated_metrics,
            "model": model_snapshot,
            "learning": learning,
            "economics": {key: value for key, value in trade_summary.items() if key != "curve"},
            "chart_revision": chart_revision,
            "state_revision": state_revision,
            "error": error,
        }

    def pnl_snapshot(self, range_key: str = "1D") -> Dict[str, Any]:
        summary = self.store.trade_summary(range_key=range_key)
        summary["stake"] = self.controls.next_stake("MAIN")
        with self.lock:
            self.pnl_summary = {
                key: value for key, value in summary.items() if key != "curve"
            }
            self.pnl_summary["curve"] = summary["curve"][-1:]
        return summary

    def weights_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "version": self.model.version,
                "updates": self.model.samples,
                "temperature": self.model.temperature,
                "learning_rate": MODEL_LEARNING_RATE,
                "max_drift": MODEL_WEIGHT_CLAMP,
                "min_samples": MODEL_MIN_SAMPLES,
                "last_candle_id": self.model.last_candle_id,
                "learning": dict(self.last_learning),
                "weights": self.model.weight_table(),
            }

    def chart_snapshot(self) -> Dict[str, Any]:
        # Prediction counters and chart markers must use the same candle IDs.
        # Merge durable settled candles with live/REST candles so a prediction can
        # never count in accuracy while disappearing only because it fell outside
        # the latest bootstrap response or a REST candle was temporarily missing.
        stored = self.store.chart_candles(CHART_CANDLES)
        with self.lock:
            live_candles = [dict(candle) for candle in self.candles]
            revision = self.chart_revision
        merged: Dict[int, Dict[str, Any]] = {
            int(candle["time"]): dict(candle) for candle in stored
        }
        for candle in live_candles:
            merged[int(candle["time"])] = dict(candle)
        candles = [merged[key] for key in sorted(merged)][-CHART_CANDLES:]
        return {
            "revision": revision,
            "candles": candles,
            "markers": self.store.markers(),
            "history": self.store.recent_history(40),
        }


def route_market_message(message: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Accept raw or combined Binance payloads and return the flowchart stream name."""
    if not isinstance(message, dict):
        return None
    if isinstance(message.get("data"), dict):
        stream = str(message.get("stream") or "")
        data = message["data"]
        if stream:
            return stream, data
        message = data

    # Subscription acknowledgements are not market events.
    if "result" in message and "id" in message:
        return None

    event_type = str(message.get("e") or "")
    if event_type == "aggTrade":
        return f"{STREAM_SYMBOL}@aggTrade", message
    if event_type == "kline" and isinstance(message.get("k"), dict):
        return f"{STREAM_SYMBOL}@kline_5m", message
    # Partial book depth has no `e` field; identify it by its documented shape.
    if (
        "lastUpdateId" in message
        and isinstance(message.get("bids"), list)
        and isinstance(message.get("asks"), list)
    ):
        return f"{STREAM_SYMBOL}@depth5@100ms", message
    return None


class FeedThread(threading.Thread):
    """Low-latency Binance feed with endpoint rotation and hard timeouts.

    v14 could sit forever on the first blocked endpoint because the connection
    attempt had no hard timeout. v4 tries combined-stream URLs first, then raw `/ws` subscriptions, rotates
    through all official hosts, bypasses accidental proxy settings, and closes any
    connection that opens without delivering market events.
    """

    def __init__(self, engine: Engine) -> None:
        super().__init__(name="binance-feed", daemon=True)
        self.engine = engine
        self.ws: Any = None
        self._ws_lock = threading.Lock()

    def close(self) -> None:
        with self._ws_lock:
            ws = self.ws
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass

    def run(self) -> None:
        try:
            import websocket  # type: ignore
        except ImportError:
            self.engine.record_error(
                "Missing websocket-client. Run: pip install --upgrade websocket-client"
            )
            self.engine.set_feed_status("dependency missing")
            return

        websocket.enableTrace(False)
        websocket.setdefaulttimeout(WS_CONNECT_TIMEOUT_SEC)
        backoff = 1.0
        endpoint_index = 0

        # REST only keeps the model populated while the WebSocket is unavailable.
        # It uses the same Engine.handle_message path, so features, predictions,
        # latency counters and the dashboard are updated consistently.
        def rest_poller() -> None:
            last_closed_id = 0
            while not self.engine.stop_event.is_set():
                if self.engine.is_ws_live():
                    self.engine.stop_event.wait(5.0)
                    continue
                try:
                    received = now_ms()
                    rows = rest_json(
                        "/api/v3/klines",
                        {"symbol": SYMBOL, "interval": "5m", "limit": 2},
                    )
                    depth = rest_json(
                        "/api/v3/depth", {"symbol": SYMBOL, "limit": 5}
                    )

                    # Populate state and compute features, but do not emit a MAIN
                    # or REVERSAL from the slower fallback. Predictions remain
                    # strictly tied to the low-latency WebSocket flowchart.
                    start_ns = time.perf_counter_ns()
                    with self.engine.lock:
                        # v5.9 closes the in-flight REST race: if the WS became
                        # live while the HTTP requests were running, discard this
                        # fallback snapshot instead of overwriting fresher state.
                        if self.engine.ws_live:
                            continue
                        self.engine.last_event_local_ms = received
                        self.engine.logical_ts_ms = max(
                            self.engine.logical_ts_ms, received
                        )
                        self.engine.event_count += 1 + (1 if rows else 0)
                        self.engine.rate_count += 1 + (1 if rows else 0)
                        elapsed_rate = time.monotonic() - self.engine.rate_started
                        if elapsed_rate >= 1.0:
                            self.engine.event_rate = (
                                self.engine.rate_count / elapsed_rate
                            )
                            self.engine.rate_count = 0
                            self.engine.rate_started = time.monotonic()

                        if rows:
                            # Feed the just-closed candle once so saved predictions
                            # can settle, then update the current candle.
                            for row in rows:
                                open_ms = int(row[0])
                                close_ms = int(row[6])
                                closed = received > close_ms
                                if closed and open_ms == last_closed_id:
                                    continue
                                raw_kline = {
                                    "t": open_ms,
                                    "T": close_ms,
                                    "o": str(row[1]),
                                    "h": str(row[2]),
                                    "l": str(row[3]),
                                    "c": str(row[4]),
                                    "v": str(row[5]),
                                    "x": closed,
                                }
                                self.engine._on_kline(
                                    {"E": received, "k": raw_kline}, received
                                )
                                if closed:
                                    last_closed_id = open_ms
                        self.engine._on_depth(depth, received, received)
                        self.engine._compute_features(received)
                        self.engine.feature_compute_us = max(
                            0, (time.perf_counter_ns() - start_ns) // 1_000
                        )
                        self.engine.state_revision += 1
                        # Keep the status update in the same lock-protected
                        # transaction as the REST snapshot. A first WS event
                        # either happens before this block (so REST is skipped)
                        # or after it (so WS becomes the final visible status).
                        self.engine.set_feed_status(
                            "rest-fallback",
                            "https://api.binance.com (REST fallback)",
                        )
                except Exception as exc:
                    self.engine.record_error(f"REST fallback: {exc}")
                self.engine.stop_event.wait(5.0)

        threading.Thread(
            target=rest_poller, name="rest-fallback", daemon=True
        ).start()

        def set_ws_status(status: str, endpoint: str) -> None:
            # Once REST has populated the dashboard, do not replace that useful
            # state with a misleading permanent "connecting" label. The WebSocket
            # endpoint and errors remain visible, and "live" takes priority.
            with self.engine.lock:
                fallback_active = (
                    self.engine.feed_status == "rest-fallback"
                    and self.engine.candle is not None
                )
                if fallback_active and status != "live":
                    self.engine.feed_url = (
                        "REST fallback active; WebSocket attempt: " + endpoint
                    )
                    self.engine.state_revision += 1
                    return
            self.engine.set_feed_status(status, endpoint)

        while not self.engine.stop_event.is_set():
            endpoint = WS_ENDPOINTS[endpoint_index % len(WS_ENDPOINTS)]
            endpoint_index += 1
            set_ws_status(f"connecting {endpoint}", endpoint)

            opened = threading.Event()
            first_market_event = threading.Event()
            attempt_started = time.monotonic()
            opened_at = [0.0]
            last_market_at = [0.0]
            last_stream_at = {"aggTrade": 0.0, "depth": 0.0, "kline": 0.0}
            close_reason = [""]
            self.engine.market_queue_overflow.clear()

            def on_open(ws_app: Any) -> None:
                opened_at[0] = time.monotonic()
                opened.set()
                self.engine.set_ws_live(False)
                set_ws_status("subscribing", endpoint)
                payload = {
                    "method": "SUBSCRIBE",
                    "params": list(SUBSCRIBE_STREAMS),
                    "id": 1,
                }
                try:
                    ws_app.send(json.dumps(payload, separators=(",", ":")))
                except Exception as exc:
                    close_reason[0] = f"subscribe failed: {exc}"
                    self.engine.record_error(f"{endpoint}: {close_reason[0]}")
                    ws_app.close()

            def on_message(_ws: Any, raw: Any) -> None:
                received = now_ms()
                received_mono_ns = mono_ns()
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    message = json.loads(raw)
                    routed = route_market_message(message)
                    if routed is None:
                        return
                    stream, data = routed
                    arrival_mono = time.monotonic()
                    last_market_at[0] = arrival_mono
                    if "aggTrade" in stream:
                        last_stream_at["aggTrade"] = arrival_mono
                    elif "depth" in stream:
                        last_stream_at["depth"] = arrival_mono
                    elif "kline" in stream:
                        last_stream_at["kline"] = arrival_mono
                    if not first_market_event.is_set():
                        self.engine.set_ws_live(True)
                        first_market_event.set()
                        set_ws_status("live", endpoint)
                    self.engine.handle_message(stream, data, received, received_mono_ns)
                except Exception as exc:
                    self.engine.record_error(f"websocket message: {exc}")

            def on_error(_ws: Any, error: Any) -> None:
                text = str(error or "unknown error")
                close_reason[0] = text
                set_ws_status("connection error", endpoint)
                self.engine.record_error(f"{endpoint}: {text}")

            def on_close(_ws: Any, code: Any, reason: Any) -> None:
                detail = f"{code or 'closed'} {reason or ''}".strip()
                if not close_reason[0]:
                    close_reason[0] = detail
                self.engine.set_ws_live(False)
                set_ws_status(f"reconnecting ({detail})", endpoint)

            def watchdog(ws_app: Any) -> None:
                while not self.engine.stop_event.wait(0.25):
                    now = time.monotonic()
                    if not opened.is_set():
                        if now - attempt_started >= WS_CONNECT_TIMEOUT_SEC + 1.0:
                            close_reason[0] = "connect timeout"
                            self.engine.record_error(f"{endpoint}: connect timeout")
                            try:
                                ws_app.close()
                            except Exception:
                                pass
                            return
                        continue
                    if not first_market_event.is_set():
                        if now - opened_at[0] >= WS_FIRST_EVENT_TIMEOUT_SEC:
                            close_reason[0] = "opened but no market events"
                            self.engine.record_error(
                                f"{endpoint}: opened but no market events within "
                                f"{WS_FIRST_EVENT_TIMEOUT_SEC:.0f}s"
                            )
                            try:
                                ws_app.close()
                            except Exception:
                                pass
                            return
                        continue
                    if self.engine.market_queue_overflow.is_set():
                        close_reason[0] = "engine queue overflow; resync required"
                        self.engine.record_error(f"{endpoint}: {close_reason[0]}")
                        try:
                            ws_app.close()
                        except Exception:
                            pass
                        return
                    # One healthy stream must not mask a dead required stream.
                    # After the normal first-event grace, each subscribed BTC
                    # stream must have produced data recently or the socket is
                    # rebuilt so kline/depth state cannot silently go stale.
                    if now - opened_at[0] >= WS_FIRST_EVENT_TIMEOUT_SEC:
                        stale_streams = [
                            name for name, stamp in last_stream_at.items()
                            if not stamp or now - stamp >= WS_STALE_TIMEOUT_SEC
                        ]
                        if stale_streams:
                            close_reason[0] = "stale stream(s): " + ",".join(stale_streams)
                            self.engine.record_error(f"{endpoint}: {close_reason[0]}")
                            try:
                                ws_app.close()
                            except Exception:
                                pass
                            return
                    if now - last_market_at[0] >= WS_STALE_TIMEOUT_SEC:
                        close_reason[0] = "market feed stale"
                        self.engine.record_error(
                            f"{endpoint}: no market event for "
                            f"{WS_STALE_TIMEOUT_SEC:.0f}s"
                        )
                        try:
                            ws_app.close()
                        except Exception:
                            pass
                        return

            try:
                ws_app = websocket.WebSocketApp(
                    endpoint,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                with self._ws_lock:
                    self.ws = ws_app
                threading.Thread(
                    target=watchdog,
                    args=(ws_app,),
                    name="feed-watchdog",
                    daemon=True,
                ).start()
                ws_app.run_forever(
                    ping_interval=20,
                    ping_timeout=8,
                    skip_utf8_validation=True,
                    sockopt=((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),),
                    http_no_proxy=["*"],
                    suppress_origin=True,
                )
            except Exception as exc:
                close_reason[0] = str(exc)
                self.engine.record_error(f"feed loop {endpoint}: {exc}")
            finally:
                with self._ws_lock:
                    self.ws = None

            if self.engine.stop_event.wait(backoff):
                break
            backoff = (
                1.0 if first_market_event.is_set() else min(8.0, backoff * 1.7)
            )

def rest_json(path: str, params: Dict[str, Any], timeout: float = 8.0) -> Any:
    query = urllib.parse.urlencode(params)
    last_error: Optional[Exception] = None
    for base in REST_BASES:
        request = urllib.request.Request(
            base + path + "?" + query,
            headers={"User-Agent": f"BTC-Model/{VERSION}", "Accept-Encoding": "gzip"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    import gzip

                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"Binance REST unavailable: {last_error}")


def fetch_chart_candles(limit: int = CHART_CANDLES) -> List[Dict[str, Any]]:
    rows = rest_json(
        "/api/v3/klines",
        {"symbol": SYMBOL, "interval": "5m", "limit": int(limit)},
    )
    current = now_ms()
    out = []
    for row in rows:
        open_ms = int(row[0])
        out.append(
            {
                "time": open_ms,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "closed": current > int(row[6]),
                "close_time_ms": int(row[6]),
            }
        )
    return out


CONTROLS_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Trade Controls v__VERSION__</title>
<style>
:root{color-scheme:dark;--bg:#080b10;--panel:#10151d;--panel2:#0b1017;--line:#263142;--muted:#8b98aa;--text:#eaf0f8;--up:#27d17f;--down:#ff5d6c;--main:#60a5fa;--rev:#f7b955;--ef:#9b59ff;--warn:#ffd166;--blue:#8ab4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:13px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.shell{max-width:760px;margin:auto}.top{position:sticky;top:0;z-index:5;background:#080b10f2;border-bottom:1px solid var(--line);padding:10px 12px;display:flex;justify-content:space-between;align-items:center;gap:10px}.brand{font-weight:900;letter-spacing:.5px}.small{font-size:11px;color:var(--muted);line-height:1.5}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:8px;padding:8px}.card{grid-column:span 12;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px}.label{font-size:10px;color:var(--muted);letter-spacing:.7px;text-transform:uppercase}.big{font-size:21px;font-weight:900;margin-top:4px}.row{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.nav{color:var(--blue);text-decoration:none;border:1px solid var(--line);padding:7px 10px;border-radius:8px}.toggle{width:155px;height:56px;border:0;border-radius:14px;background:var(--up);color:#06140d;font:900 18px inherit}.toggle.off{background:#293342;color:#b7c1cf}.stateGrid,.stakeGrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:10px}.cell{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px}.cell b{display:block;margin-top:3px;font-size:15px}.up{color:var(--up)}.down{color:var(--down)}.main{color:var(--main)}.rev{color:var(--rev)}.ef{color:var(--ef)}.warn{color:var(--warn)}.note{margin-top:10px;border-left:3px solid var(--blue);background:#0b1119;padding:8px 10px;color:#aab7c8;line-height:1.5}.formGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:9px}label{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;margin:5px 0 3px}input,select{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--text);padding:8px;border-radius:7px;font:inherit}.btn{border:1px solid var(--line);background:#161d27;color:var(--text);padding:8px 12px;border-radius:8px;font:700 12px inherit}.primary{border-color:var(--blue);color:var(--blue)}.danger{border-color:var(--down);color:var(--down);background:transparent}.rule{display:flex;justify-content:space-between;gap:8px;align-items:center;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:7px}.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}.chip{border:1px solid var(--line);background:var(--panel2);color:var(--muted);padding:5px 8px;border-radius:999px}.chip.on{border-color:var(--blue);color:var(--blue)}.msg{min-height:18px;margin-top:8px;font-weight:700}.readiness{white-space:pre-wrap}.kindLine{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:3px}.miniToggle{min-width:50px;height:27px;padding:0 10px;border:1px solid #2d9b68;border-radius:999px;background:#10291f;color:#71e4a7;font:900 11px inherit;cursor:pointer}.miniToggle.off{border-color:#5b6675;background:#151b24;color:#94a0b2}.miniToggle:disabled{opacity:.5;cursor:wait}.miniToggle:active{transform:translateY(1px)}
.stateXBox{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}.sxActive{color:var(--warn)}
@media(max-width:520px){.stateGrid,.stakeGrid{grid-template-columns:repeat(2,minmax(0,1fr))}.formGrid{grid-template-columns:1fr}.toggle{width:120px;height:50px}}
</style></head><body><div class="shell">
<header class="top"><div><div class="brand">TRADE CONTROLS · v__VERSION__</div><div class="small">build __BUILD__</div><div id="runStamp" class="small">--</div></div><a class="nav" href="/">← Dashboard</a></header>
<div class="grid">
<section class="card"><div class="row"><div><div class="label">Master live-order switch</div><div class="big">MAIN · REVERSAL · EF</div><div id="masterStatus" class="small">loading safe state…</div></div><button id="master" class="toggle off">OFF</button></div>
<div id="kindStates" class="stateGrid"></div><div class="note">Master controls all new real orders; the small MAIN / REVERSAL / EF switches can block each stream individually. Master starts OFF after every terminal launch. Individual choices persist across restarts. Signal generation, settlement and accuracy remain active while trading is OFF or banned.</div>
<div id="ready" class="small readiness" style="margin-top:9px"></div>
<div class="stateXBox"><div class="row"><div><div class="label">State X Protection</div><div id="stateXStatus" class="big" style="font-size:17px">NORMAL</div><div id="stateXDetails" class="small">loading…</div></div><button id="stateXToggle" type="button" class="miniToggle off">OFF</button></div></div></section>

<section class="card"><div class="label">Shared staking · all three signals</div><div class="row"><div><div id="nextStake" class="big">--</div><div class="small">one current stake and one combined streak</div></div><div id="streak" class="small"></div></div>
<div class="formGrid">
<div><label>Mode</label><select id="mode"><option value="fixed">fixed</option><option value="percent">percent</option><option value="streak">streak</option></select></div>
<div><label>Fixed stake $</label><input id="fixed_stake" type="number" min="1" step="0.01"></div>
<div><label>% free capital</label><input id="percent" type="number" min="0.01" step="0.01"></div>
<div><label>Current stake $</label><input id="current_stake" type="number" min="1" step="0.01"></div>
<div><label>Recalc after wins</label><input id="win_trigger" type="number" min="1" step="1"></div>
<div><label>Recalc after losses</label><input id="loss_trigger" type="number" min="1" step="1"></div>
<div><label>Minimum $</label><input id="min_stake" type="number" min="0.01" step="0.01"></div>
<div><label>Maximum $</label><input id="max_stake" type="number" min="0.01" step="0.01"></div>
</div><div style="margin-top:10px"><button id="saveStake" class="btn primary">Review & save shared stake</button></div></section>

<section class="card"><div class="big" style="font-size:17px">BANNED HOURS</div><div class="small">Execution-only bans. Blocked signals are stored as F in Data; the BTC chart never prints F.</div><div id="rules"></div>
<div style="border-top:1px solid var(--line);margin-top:12px;padding-top:10px"><div class="label">Add a ban rule</div><label>Signals</label><div id="kinds" class="chips"></div><label>Days</label><div id="days" class="chips"></div>
<div class="formGrid"><div><label>Start (24h HH:MM)</label><input id="start" type="time" value="15:00"></div><div><label>End exclusive</label><input id="end" type="time" value="19:00"></div></div>
<div style="margin-top:9px"><button id="addRule" class="btn primary">Review & add ban</button></div></div></section>
<section class="card"><div id="msg" class="msg"></div></section>
</div></div>
<script>
(function(){'use strict';
var state=null,KINDS=['MAIN','REVERSAL','EF'],DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
var RUN_UPTIME_BASE=Number('__UPTIME_SEC__')||0;
var RUN_PAGE_BASE=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
function runtimeText(totalSeconds){
  var left=Math.max(0,Math.floor(Number(totalSeconds)||0)),out=[];
  var units=[['y',31536000],['mo',2592000],['d',86400],['h',3600],['m',60],['s',1]];
  units.forEach(function(unit){var n=Math.floor(left/unit[1]);if(n){out.push(n+unit[0]);left-=n*unit[1];}});
  return out.length?out.join(' '):'0s';
}
function countdownText(totalSeconds){var left=Math.max(0,Math.ceil(Number(totalSeconds)||0)),m=Math.floor(left/60),s=left%60;return m+'m '+String(s).padStart(2,'0')+'s'}
function tickRuntime(){
  var node=document.getElementById('runStamp');if(!node)return;
  var now=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
  node.textContent='runtime · '+runtimeText(RUN_UPTIME_BASE+(now-RUN_PAGE_BASE)/1000);
}

function e(id){return document.getElementById(id)}function money(v){return '$'+Number(v||0).toFixed(2)}
function request(method,url,body,done){var x=new XMLHttpRequest();x.open(method,url,true);if(body)x.setRequestHeader('Content-Type','application/json');x.onreadystatechange=function(){if(x.readyState===4){var r={};try{r=JSON.parse(x.responseText)}catch(_){r={ok:false,error:'bad server response'}}done(r)}};x.send(body?JSON.stringify(body):null)}
function show(msg,ok){e('msg').textContent=msg||'';e('msg').className='msg '+(ok?'up':'down')}
function minutes(v){var p=String(v||'').split(':');return Number(p[0])*60+Number(p[1])}
function bindSignalToggles(){
 Array.prototype.forEach.call(document.querySelectorAll('[data-kind-toggle]'),function(b){
  b.onclick=function(){
   var k=b.getAttribute('data-kind-toggle'),s=(state.kinds||{})[k]||{};
   var current=s.manual_enabled!==false,next=!current;
   if(next&&state.master_enabled&&!confirm('Turn '+k+' live execution ON?'))return;
   b.disabled=true;
   request('POST','/api/controls/signal',
     {confirmed:true,kind:k,manual_enabled:next},
     function(r){
       if(!r.ok){b.disabled=false;show(r.error||('Could not change '+k),false);return}
       state=r.state||state;
       show(k+' execution '+(next?'ON':'OFF'),true);
       render();
     });
  };
 });
}
function render(){
 var on=!!state.master_enabled,ready=state.execution||{},stake=state.shared_stake||{},sx=state.state_x||{},sxOn=!!sx.enabled,sxActive=!!sx.active;
 e('master').textContent=on?'ON':'OFF';e('master').className='toggle'+(on?'':' off');
 e('masterStatus').textContent=(on?'LIVE ORDERS ARMED':'SAFE · NEW ORDERS BLOCKED')+' · '+state.clock+' '+state.timezone;
 e('masterStatus').className='small '+(on?'up':'');
 e('ready').textContent=ready.ready?'Execution preflight READY · mainnet websocket fresh':('Execution locked · '+(ready.missing||[]).join(' · '));
 e('ready').className='small readiness '+(ready.ready?'up':'warn');
 e('kindStates').innerHTML=KINDS.map(function(k){var s=state.kinds[k]||{},manual=s.manual_enabled!==false;return '<div class="cell"><div class="label '+(k==='MAIN'?'main':k==='REVERSAL'?'rev':'ef')+'">'+k+'</div>'+'<div class="kindLine"><b class="'+(s.effective_enabled?'up':s.auto_banned?'warn':'down')+'">'+(s.effective_enabled?'TRADING':s.auto_banned?'BANNED':'BLOCKED')+'</b>'+'<button type="button" class="miniToggle'+(manual?'':' off')+'" data-kind-toggle="'+k+'">'+(manual?'ON':'OFF')+'</button></div>'+'<div class="small">'+(s.status||'')+'</div></div>'}).join('');bindSignalToggles();
 e('stateXToggle').textContent=sxOn?'ON':'OFF';e('stateXToggle').className='miniToggle'+(sxOn?'':' off');
 e('stateXStatus').textContent=sxActive?'SX ACTIVE':'NORMAL';e('stateXStatus').className='big '+(sxActive?'sxActive':'up');e('stateXStatus').style.fontSize='17px';
 e('stateXDetails').textContent=sxActive?('current trade veto active · '+(sx.trigger_reason||'--')):('Protection '+(sxOn?'ON':'OFF')+' · per-trade only · OFF has zero veto authority · shadow diagnostics continue');
 e('nextStake').textContent=money(state.shared_next_stake);e('streak').innerHTML='<span class="up">wins '+Number(state.win_streak||0)+'</span> · <span class="down">losses '+Number(state.loss_streak||0)+'</span>';
 Object.keys(stake).forEach(function(k){if(e(k))e(k).value=stake[k]});
 e('rules').innerHTML=(state.rules||[]).map(function(r){return '<div class="rule"><div><b>'+r.describe+'</b><div class="small">'+(r.kinds||[]).join(', ')+'</div></div><button class="btn danger" data-delete="'+r.id+'">Remove</button></div>'}).join('')||'<div class="small" style="margin-top:7px">No ban rules.</div>';
 Array.prototype.forEach.call(document.querySelectorAll('[data-delete]'),function(b){b.onclick=function(){if(!confirm('Remove this execution ban?'))return;request('POST','/api/controls/rule/delete',{confirmed:true,id:b.dataset.delete},finish)}});
}
function load(){request('GET','/api/controls',null,function(r){state=r;render()})}
function finish(r){if(!r.ok){show(r.error||'Change failed.',false);return}show('Applied.',true);load()}
e('master').onclick=function(){var target=!state.master_enabled;var warning=target?'ARM REAL MAINNET ORDERS for MAIN, REVERSAL and EF?':'Turn OFF all new live orders? Existing accepted orders are not cancelled.';if(!confirm(warning))return;request('POST','/api/controls/apply',{confirmed:true,system:{manual_enabled:target}},finish)};
e('stateXToggle').onclick=function(){var sx=state.state_x||{},target=!sx.enabled,warning=target?'Turn State X Protection ON? It may veto only the current qualifying trade when BTC evidence is hostile.':'Turn State X Protection OFF? SX will retain shadow diagnostics but have zero execution authority.';if(!confirm(warning))return;request('POST','/api/controls/state-x',{confirmed:true,manual_enabled:target},finish)};
e('saveStake').onclick=function(){var s={};['fixed_stake','percent','current_stake','win_trigger','loss_trigger','min_stake','max_stake'].forEach(function(k){s[k]=Number(e(k).value)});s.mode=e('mode').value;if(!confirm('Apply this one shared stake to MAIN, REVERSAL and EF?'))return;request('POST','/api/controls/apply',{confirmed:true,system:{stake:s}},finish)};
function chips(id,values,selected){e(id).innerHTML=values.map(function(v,i){return '<button type="button" class="chip '+(selected.indexOf(i)>=0||selected.indexOf(v)>=0?'on':'')+'" data-value="'+i+'">'+v+'</button>'}).join('');Array.prototype.forEach.call(e(id).querySelectorAll('.chip'),function(b){b.onclick=function(){b.classList.toggle('on')}})}
chips('kinds',KINDS,['MAIN']);chips('days',DAYS,[0,1,2,3]);
e('addRule').onclick=function(){var ks=[],ds=[];Array.prototype.forEach.call(e('kinds').querySelectorAll('.chip.on'),function(b){ks.push(KINDS[Number(b.dataset.value)])});Array.prototype.forEach.call(e('days').querySelectorAll('.chip.on'),function(b){ds.push(Number(b.dataset.value))});var rule={kinds:ks,days:ds,start_minute:minutes(e('start').value),end_minute:minutes(e('end').value)};if(!confirm('Add this execution-only ban?'))return;request('POST','/api/controls/rule',{confirmed:true,rule:rule},finish)};
load();setInterval(load,3000);
tickRuntime();setInterval(tickRuntime,1000);
})();
</script></body></html>"""


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>BTC Model v__VERSION__</title>
<style>
:root{color-scheme:dark;--bg:#080b10;--panel:#10151d;--line:#263142;--muted:#8b98aa;--text:#eaf0f8;--up:#27d17f;--down:#ff5d6c;--main:#60a5fa;--rev:#f7b955;--ef:#9b59ff;--warn:#ffd166}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}body{min-height:100vh}.shell{width:100%;max-width:760px;margin:0 auto;min-height:100vh}.top{position:sticky;top:0;z-index:5;background:#080b10f3;backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:10px 12px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:10px;align-items:center}.brand{font-weight:800;letter-spacing:.5px}.status{color:var(--muted);text-align:right;white-space:nowrap}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:8px;padding:8px}.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:11px;min-width:0}.span3{grid-column:span 3}.span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}.span12{grid-column:span 12}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.7px}.big{font-size:25px;font-weight:800;margin-top:5px}.up{color:var(--up)}.down{color:var(--down)}.main{color:var(--main)}.rev{color:var(--rev)}.ef{color:var(--ef)}.forbidden{color:var(--main);font-weight:800}.muted{color:var(--muted)}.navlink{color:var(--text);text-decoration:none;border:1px solid var(--line);background:var(--panel);padding:7px 12px;border-radius:9px;font-weight:700;white-space:nowrap}.navlink:hover{border-color:var(--main)}.warn{color:var(--warn)}.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.metric{font-size:22px;font-weight:800;margin:5px 0}.small{font-size:11px;color:var(--muted);line-height:1.5}.bar{height:7px;border-radius:10px;background:#202a38;overflow:hidden;margin-top:7px}.bar>i{display:block;height:100%;background:currentColor;width:0}.checks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:8px}.check{border:1px solid var(--line);padding:6px;border-radius:6px;color:var(--muted)}.check.ok{border-color:#1c6848;color:var(--up)}.chartBox{height:390px;position:relative}.chartBox canvas{display:block;width:100%;height:100%;touch-action:none;cursor:crosshair}.tip{position:absolute;display:none;pointer-events:none;background:#05070bcc;border:1px solid var(--line);padding:7px;border-radius:7px;white-space:pre;z-index:3}.features{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:9px}.f{border-bottom:1px solid #1b2430;padding:4px 0}.f b{float:right}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:7px 6px;border-bottom:1px solid #202a38;text-align:left;white-space:nowrap}.scroll{overflow:auto}.error{color:#ff9aa4;white-space:pre-wrap}.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 7px}.pager{display:flex;gap:5px;align-items:center;justify-content:center;flex:1}.pageButton{min-width:32px;padding:5px 8px;border:1px solid var(--line);border-radius:5px;background:#161d27;color:var(--text)}.pageButton.active{border-color:#8ab4ff;color:#8ab4ff;background:#17243a}.pageGap{color:var(--muted);padding:0 2px}button:disabled{opacity:.45}a{color:#8ab4ff}.rangeBtn{padding:5px 9px;border:1px solid var(--line);border-radius:6px;background:#161d27;color:var(--muted)}.rangeBtn.active{border-color:#8ab4ff;color:#8ab4ff;background:#17243a}
.bookHeader{display:grid;grid-template-columns:minmax(0,1fr) 175px;gap:12px;align-items:start}.sideTiles{display:grid;grid-template-columns:1fr 1fr;margin-top:9px;background:#0b1017;border:1px solid var(--line);border-radius:9px;overflow:hidden}.sideTile{padding:10px 11px;min-width:0}.sideTile+.sideTile{border-left:1px solid #202a38}.sideTile .px{font-size:22px;font-weight:900;margin:3px 0}.bookFacts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:9px}.fact,.pnlStat{background:#0b1017;border:1px solid #202a38;border-radius:8px;padding:7px}.fact b{display:block;font-size:13px;margin-top:3px}.fillBox{background:#0b1017;border:1px solid var(--line);border-radius:9px;padding:10px;text-align:right}.pnlTop{display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:12px;align-items:start}.pnlHero{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pnlHero>div{text-align:right}.pnlStats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:11px}.pnlStat b{display:block;font-size:17px;margin-top:4px}.chartCard{padding:10px}.chartTitle{line-height:1.2}
.pnlChart{margin-top:15px;padding-top:11px;border-top:1px solid #202a38}.pnlChartHead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:7px}.pnlRange{display:flex;gap:14px;color:var(--muted);font-size:10px;letter-spacing:.35px}.pnlRange b{margin-left:4px;font-size:11px}.pnlCanvasWrap{height:190px;border:1px solid #1d2735;border-radius:8px;background:#0b1017;overflow:hidden}.pnlCanvasWrap canvas{display:block;width:100%;height:190px}
@media(max-width:720px){.span3,.span4{grid-column:span 6}.span6,.span8{grid-column:span 12}.bookFacts,.pnlStats{grid-template-columns:repeat(2,minmax(0,1fr))}.chartBox{height:340px}}
@media(max-width:560px){.top{grid-template-columns:minmax(0,1fr) auto}.top .status{grid-column:2;grid-row:2}.top .navs{grid-column:2;grid-row:1}.grid{gap:6px;padding:6px}.card{padding:9px}.span3,.span4,.span6,.span8,.span12{grid-column:span 12}.big{font-size:22px}.features{grid-template-columns:repeat(2,minmax(0,1fr))}.checks{grid-template-columns:1fr}.bookHeader,.pnlTop{grid-template-columns:1fr}.fillBox{text-align:left}.chartBox{height:315px}}
</style><script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
</head><body><div class="shell">
<header class="top"><div><div class="brand">BTC MODEL v__VERSION__</div><div class="small">build <b id="buildStamp">__BUILD__</b></div><div id="runStamp" class="small">--</div></div><div class="navs" style="display:flex;gap:7px"><a href="/data" class="navlink">Data</a><a href="/controls" class="navlink">Trade Controls</a></div><div id="topStatus" class="status">connecting…</div></header>
<main class="grid">
  <section class="card span3"><div class="label">BTCUSDT</div><div id="price" class="big">--</div><div id="candleInfo" class="small">waiting for kline</div></section>
  <section class="card span4"><div class="label">MAIN prediction</div><div id="mainDirection" class="big main">WAITING</div><div id="mainMeta" class="small">settlement-aware · waits while final-close evidence is weak</div><div id="mainReason" class="small"></div></section>
  <section class="card span4"><div class="label">REVERSAL prediction</div><div id="revDirection" class="big rev">NOT TRIGGERED</div><div id="revMeta" class="small">one maximum per candle</div><div id="revReason" class="small"></div></section>
  <section class="card span4"><div class="label">EF prediction &middot; independent</div><div id="efDirection" class="big ef">WATCHING</div><div id="efMeta" class="small">contrarian exhaustion &middot; one maximum</div><div id="efReason" class="small"></div></section>

  <section class="card span3"><div class="label">Main accuracy</div><div id="mainAcc" class="metric">--</div><div id="mainAccN" class="small">0 / 0</div></section>
  <section class="card span3"><div class="label">Reversal accuracy</div><div id="revAcc" class="metric rev">--</div><div id="revAccN" class="small">0 / 0 triggered</div></section>
  <section class="card span3"><div class="label">EF accuracy</div><div id="efAcc" class="metric ef">--</div><div id="efAccN" class="small">0 / 0 triggered</div></section>
  <section class="card span3"><div class="label">Combined PnL accuracy</div><div id="combinedAcc" class="metric">--</div><div id="combinedAccN" class="small">net MAIN + REV + EF PnL per candle</div></section>

  <section class="card span12"><div class="bookHeader"><div><div class="label">Predict.fun order book &middot; websocket</div><div class="sideTiles"><div class="sideTile"><div class="label">UP &middot; YES ASK</div><div id="bookUp" class="px up">--</div><div id="bookUpSub" class="small">waiting for live snapshot</div></div><div class="sideTile"><div class="label">DOWN &middot; NO ASK</div><div id="bookDown" class="px down">--</div><div id="bookDownSub" class="small">waiting for live snapshot</div></div></div><div class="bookFacts"><div class="fact"><div class="label">Spread</div><b id="bookSpread">--</b></div><div class="fact"><div class="label">Book age</div><b id="bookAge">--</b></div><div class="fact"><div class="label">Environment</div><b id="bookEnvironment">MAINNET</b></div><div class="fact"><div class="label">Requests</div><b id="bookRequests">--</b></div></div><div id="bookMeta" class="small" style="margin-top:8px">connecting</div></div><div class="fillBox"><div class="label">Last live order</div><div id="fillPrice" class="metric">--</div><div id="fillMeta" class="small">--</div></div></div></section>

  <section class="card span12"><div class="pnlTop"><div><div class="label">P&amp;L at real fill prices</div><div id="pnlTotal" class="big">--</div><div id="pnlMeta" class="small">no settled live order yet</div></div><div class="pnlHero"><div><div class="label">Fill rate</div><div id="pnlFill" class="metric">--</div><div class="small">confirmed orders</div></div><div><div class="label">Shared next stake</div><div id="capStake" class="metric">--</div><div class="small">MAIN &middot; REV &middot; EF</div></div></div></div><div class="pnlStats"><div class="pnlStat"><div class="label">Bankroll</div><b id="capBalance">--</b><div id="capSplit" class="small">wallet + unclaimed</div></div><div class="pnlStat"><div class="label">Unclaimed wins</div><b id="capPending">--</b><div class="small">settled, not yet redeemed</div></div><div class="pnlStat"><div class="label">Available</div><b id="capFree">--</b><div class="small">after pending-order reserve</div></div><div class="pnlStat"><div class="label">Average entry</div><b id="pnlAvgEntry">--</b><div id="pnlAvg" class="small">--</div></div></div><div id="openPos"></div><div id="capMeta" class="small" style="margin-top:8px">--</div><div id="capTruth" class="small">--</div><div id="capBan" class="small">--</div><div class="pnlChart"><div class="pnlChartHead"><div><button class="rangeBtn active" data-range="1D">24H</button> <button class="rangeBtn" data-range="1W">1W</button> <button class="rangeBtn" data-range="ALL">ALL</button></div><div class="pnlRange"><span>HIGH <b id="pnlHigh">--</b></span><span>LOW <b id="pnlLow">--</b></span><span>CURRENT <b id="pnlNow">--</b></span></div></div><div class="pnlCanvasWrap"><canvas id="pnlCanvas"></canvas></div></div></section>

  <section class="card span12 chartCard"><div class="label chartTitle">BTCUSDT 5-MINUTE CHART &middot; MAIN / REVERSAL / EF<br>MARKERS</div><div id="lwchart" style="height:46vh"></div><div id="chartFallback" class="chartBox" style="height:46vh;display:none"><canvas id="chart"></canvas><div id="tip" class="tip"></div></div><div id="chartMode" class="small muted" style="display:none">offline chart renderer &middot; drag to pan, pinch to zoom, double-tap to reset</div></section>

  <section class="card span12"><div class="row" style="justify-content:space-between"><div class="label">Settled candle history</div><span><a href="/data">Data</a> &middot; <a href="/export.csv">export CSV</a></span></div><div class="scroll"><table id="history"><thead><tr><th>Candle</th><th>Actual</th><th>MAIN</th><th>Buy</th><th>at</th><th>Result</th><th>REVERSAL</th><th>Buy</th><th>Result</th><th>EF</th><th>Buy</th><th>Result</th><th>Combined PnL</th><th>Stake</th><th>P&amp;L</th></tr></thead><tbody></tbody></table></div><div class="row" style="justify-content:space-between;padding-top:10px"><button id="histPrev">previous</button><div id="histPages" class="pager"></div><button id="histNext">next</button></div></section>
</main></div>
<script>
(function(){
'use strict';
// v4.5 fix: the marker placement below needs the candle length. In v4.0.3 this
// referenced a name that only existed in Python, so drawing the chart threw a
// ReferenceError as soon as any prediction marker was on screen.
var CANDLE_MS=300000;
function el(id){return document.getElementById(id);}
function text(id,value){var node=el(id);if(node)node.textContent=value;}
function cls(id,value){var node=el(id);if(node)node.className=value;}
function esc(value){return String(value == null ? '' : value).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});}
function pct(metric){return metric && metric.accuracy != null ? (100*metric.accuracy).toFixed(1)+'%' : '--';}
// v7.7: delay_ms is now the TOTAL across every replacement of one order.
// The last attempt is shown beside it only when a retry actually happened.
function latency(f){var total=Number((f&&f.delay_ms)||0),last=f?f.last_attempt_ms:null;
  var text=total+'ms total';
  if(last!=null&&Number(last)<total-1)text+=' (last try '+Number(last)+'ms)';
  return text;}
function directionClass(value){return value==='UP'?'up':value==='DOWN'?'down':'';}
function londonParts(ms){
  // Every displayed time is Europe/London. toISOString() is UTC and was the
  // source of the old "UTC" labels; Intl applies GMT/BST correctly including
  // the DST switch, which a fixed offset cannot.
  try{
    var f=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',
      year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
    var o={};f.formatToParts(new Date(ms)).forEach(function(p){o[p.type]=p.value;});
    if(o.hour==='24')o.hour='00';
    return o;
  }catch(_){
    var d=new Date(ms);
    return {year:String(d.getUTCFullYear()),
      month:('0'+(d.getUTCMonth()+1)).slice(-2),day:('0'+d.getUTCDate()).slice(-2),
      hour:('0'+d.getUTCHours()).slice(-2),minute:('0'+d.getUTCMinutes()).slice(-2),
      second:('0'+d.getUTCSeconds()).slice(-2)};
  }
}
function londonZone(ms){
  try{
    var f=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',timeZoneName:'short'});
    var p=f.formatToParts(new Date(ms)).filter(function(x){return x.type==='timeZoneName';});
    return p.length?p[0].value:'GMT';
  }catch(_){return 'GMT';}
}
function londonHM(ms){var p=londonParts(ms);return p.hour+':'+p.minute;}
function londonHMS(ms){var p=londonParts(ms);return p.hour+':'+p.minute+':'+p.second;}
function londonDate(ms){var p=londonParts(ms);return p.year+'-'+p.month+'-'+p.day;}
function londonStamp(ms){return londonDate(ms)+' '+londonHMS(ms);}
function londonShort(ms){return londonDate(ms)+' '+londonHM(ms);}
var RUN_UPTIME_BASE=Number('__UPTIME_SEC__')||0;
var RUN_PAGE_BASE=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
function runtimeText(totalSeconds){
  var left=Math.max(0,Math.floor(Number(totalSeconds)||0)),out=[];
  var units=[['y',31536000],['mo',2592000],['d',86400],['h',3600],['m',60],['s',1]];
  units.forEach(function(unit){var n=Math.floor(left/unit[1]);if(n){out.push(n+unit[0]);left-=n*unit[1];}});
  return out.length?out.join(' '):'0s';
}
function tickRuntime(){
  var node=document.getElementById('runStamp');if(!node)return;
  var now=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
  node.textContent='runtime · '+runtimeText(RUN_UPTIME_BASE+(now-RUN_PAGE_BASE)/1000);
}
function formatTime(ms){try{return londonHMS(ms);}catch(_){return '--';}}
function formatNumber(value,digits){return value == null ? '--' : Number(value).toFixed(digits == null ? 3 : digits);}
function requestJSON(url,callback){
  var xhr=new XMLHttpRequest();
  xhr.open('GET',url+(url.indexOf('?')>=0?'&':'?')+'_='+Date.now(),true);
  xhr.timeout=5000;
  xhr.onreadystatechange=function(){if(xhr.readyState!==4)return;if(xhr.status>=200&&xhr.status<300){try{callback(null,JSON.parse(xhr.responseText));}catch(err){callback(err);}}else{callback(new Error('HTTP '+xhr.status));}};
  xhr.ontimeout=function(){callback(new Error('request timeout'));};
  xhr.onerror=function(){callback(new Error('request failed'));};
  try{xhr.send();}catch(err){callback(err);}
}
var live=null;
var chartData={candles:[],markers:[],history:[]};
var chartRevision=-1;
var chartBusy=false;
function defaultViewCount(){
  var width=(document.documentElement&&document.documentElement.clientWidth)||window.innerWidth||360;
  return Math.max(20,Math.min(60,Math.round(width/9)));
}
var viewCount=defaultViewCount();
var viewEnd=null;
var followLive=true;
var hoverX=null;
var visibleChart=null;
var pointers={};
var dragState=null;
var pinchState=null;
function efMarkerText(marker){var up=marker.direction==='UP';if(marker.correct==null)return up?'EFUP':'EFDOWN';return 'EF'+(up?'U':'D')+(marker.correct?'W':'L');}
function markerText(marker){var shadow=!!marker.financial_is_shadow;if(marker.kind==='EF')return (shadow?'S·':'')+efMarkerText(marker);var result=marker.correct==null?'•':marker.correct?'✓':'✕';return (shadow?'S·':'')+(marker.kind==='MAIN'?'M':'R')+' '+marker.direction+' '+result;}
function renderHistory(){ loadHistory(); }

function updateUI(state){
  live=state||{};
  var candle=live.candle||{},feature=live.feature||{},feed=live.feed||{},processing=live.processing||{},metrics=live.metrics||{};
  text('topStatus',(feed.status||'--')+' · '+(feed.last_event_age_ms==null?'no data':feed.last_event_age_ms+' ms old'));
  text('price',candle.close?Number(candle.close).toFixed(1):'--');
  cls('price','big '+(candle.close>=candle.open?'up':'down'));
  if(candle.time){
    var left=Number(candle.seconds_left||0),minutes=Math.floor(left/60),seconds=String(Math.floor(left%60));if(seconds.length<2)seconds='0'+seconds;
    text('candleInfo',londonHM(candle.time)+' '+londonZone(candle.time)+' · closes in '+minutes+':'+seconds);
  }else text('candleInfo','waiting for kline');
  text('feedLatency',feed.exchange_latency_ms==null?'--':feed.exchange_latency_ms+' ms');
  text('procLatency',processing.feature_compute_us==null?'--':processing.feature_compute_us+' µs');
  text('procInfo','feature age '+(processing.feature_age_ms==null?'--':processing.feature_age_ms)+' ms · every WebSocket event');
  var main=live.main;
  if(main){text('mainDirection',main.direction);cls('mainDirection','big '+directionClass(main.direction));text('mainMeta',formatTime(main.ts_ms)+' '+londonZone(main.ts_ms)+' · P(up) '+(100*main.probability_up).toFixed(1)+'%');text('mainReason',main.reason||'');}
  else{text('mainDirection','WAITING');cls('mainDirection','big main');text('mainMeta',live.main_block||'watching for a sustained alignment');text('mainReason','');}
  var reversal=live.reversal;
  if(reversal){text('revDirection',reversal.direction);cls('revDirection','big '+directionClass(reversal.direction));text('revMeta',formatTime(reversal.ts_ms)+' '+londonZone(reversal.ts_ms)+' · opposite MAIN · P(up) '+(100*reversal.probability_up).toFixed(1)+'%');text('revReason',reversal.reason||'');}
  else{text('revDirection','NOT TRIGGERED');cls('revDirection','big rev');text('revMeta','at most one opposite prediction per candle');text('revReason','');}
  var ef=live.ef,efMonitor=live.ef_monitor||{};
  if(ef){text('efDirection',ef.direction==='UP'?'EFUP':'EFDOWN');cls('efDirection','big ef');text('efMeta',formatTime(ef.ts_ms)+' '+londonZone(ef.ts_ms)+' · live order uses shared stake');text('efReason',ef.reason||'');}
  else{text('efDirection','WATCHING');cls('efDirection','big ef');text('efMeta',efMonitor.status||'watching for contrarian exhaustion');text('efReason','score '+formatNumber(efMonitor.score,2)+' · flow '+formatNumber(efMonitor.opposite_flow,2)+' · book '+formatNumber(efMonitor.opposite_book,2)+' · rejection '+formatNumber(efMonitor.rejection,2)+' · crossing '+formatNumber(efMonitor.crossing_feasibility,2));}
  var gated=live.gated,gm=live.gated_metrics||{};
  var monitor=live.reversal_monitor||{},checks=monitor.checks||{};
  text('persist',monitor.status||'waiting');
  var checkHtml='',key;for(key in checks){if(Object.prototype.hasOwnProperty.call(checks,key)){var okay=!!checks[key];checkHtml+='<div class="check '+(okay?'ok':'')+'">'+(okay?'✓':'·')+' '+esc(key.split('_').join(' '))+'</div>';}}
  var checksNode=el('checks');if(checksNode)checksNode.innerHTML=checkHtml||'<div class="check">monitor starts at 30 seconds</div>';
  text('mainAcc',pct(metrics.main));text('mainAccN',Number(metrics.main&&metrics.main.wins||0)+' W / '+Number(metrics.main&&metrics.main.losses||0)+' L · settled PnL · real '+Number(metrics.main&&metrics.main.real||0)+' · shadow '+Number(metrics.main&&metrics.main.shadow||0));
  text('revAcc',pct(metrics.reversal));text('revAccN',Number(metrics.reversal&&metrics.reversal.wins||0)+' W / '+Number(metrics.reversal&&metrics.reversal.losses||0)+' L · settled PnL · real '+Number(metrics.reversal&&metrics.reversal.real||0)+' · shadow '+Number(metrics.reversal&&metrics.reversal.shadow||0));
  text('efAcc',pct(metrics.ef));text('efAccN',Number(metrics.ef&&metrics.ef.wins||0)+' W / '+Number(metrics.ef&&metrics.ef.losses||0)+' L · settled PnL · real '+Number(metrics.ef&&metrics.ef.real||0)+' · shadow '+Number(metrics.ef&&metrics.ef.shadow||0));
  text('combinedAcc',pct(metrics.combined));text('combinedAccN',Number(metrics.combined&&metrics.combined.wins||0)+' W / '+Number(metrics.combined&&metrics.combined.losses||0)+' L · net MAIN + REV + EF settled PnL per candle · real '+Number(metrics.combined&&metrics.combined.real||0)+' · shadow '+Number(metrics.combined&&metrics.combined.shadow||0)+' · mixed '+Number(metrics.combined&&metrics.combined.mixed||0));
  var cap=live.capital||{},ban=cap.ban||{};
  {
    var bal=Number(cap.balance||0),fresh=!!cap.fresh;
    var wal=Number(cap.wallet||0),pend=Number(cap.pending_payout||0);
    var fund=Number(cap.wallet_free||0);
    var controls=live.controls||{};
    text('capBalance',fresh?'$'+bal.toFixed(2):'UNAVAILABLE');
    cls('capBalance','big '+(fresh?'':'down'));
    text('capSplit',fresh?('$'+wal.toFixed(2)+' USDT + $'+pend.toFixed(2)+' unclaimed'):'no proved wallet read');
    text('capPending','$'+pend.toFixed(2));
    cls('capPending',pend>0?'up':'');
    text('capFree','$'+Number(cap.free||0).toFixed(2));
    var age=cap.balance_age_sec==null?'--':Number(cap.balance_age_sec).toFixed(0)+'s';
    text('capMeta',(fresh?'Predict.fun USDT live':'Predict.fun USDT unavailable')
      +' \u00b7 balance age '+age
      +' \u00b7 settled trade P&L '+(cap.realised>=0?'+':'')+Number(cap.realised||0).toFixed(2)
      +' \u00b7 pending order reserve $'+Number(cap.reserved||0).toFixed(2)
      +' \u00b7 fundable now $'+Number(fund).toFixed(2)
      +' \u00b7 sizing uses wallet + unclaimed, funding uses wallet only'
      +' \u00b7 one shared stake for MAIN / REVERSAL / EF');
    cls('capMeta','small');

    // v7.8: the one addition to the v7.7 panel. Buy, Used, shares and P&L
    // are Predict.fun's own numbers from GET /v1/positions, never the local
    // stake we asked for.
    var pos=live.open_positions||[],posHtml='';
    pos.forEach(function(p){
      var pnl=p.pnl_usd==null?null:Number(p.pnl_usd);
      var buy=p.buy_price==null?'--':'$'+Number(p.buy_price).toFixed(3);
      var used=p.used_usd==null?'--':'$'+Number(p.used_usd).toFixed(2);
      posHtml+='<div class="small" style="margin-top:8px">'
        +'<b>'+esc(p.kind)+' '+esc(p.direction)+'</b>'
        +' \u00b7 Buy '+buy
        +' \u00b7 Used '+used
        +' \u00b7 '+Number(p.shares||0).toFixed(3)+' shares'
        +' \u00b7 Current P&L <b class="'+(pnl>0?'up':(pnl<0?'down':''))+'">'
        +(pnl==null?'--':((pnl>=0?'+':'\u2212')+'$'+Math.abs(pnl).toFixed(2)))
        +'</b></div>';
    });
    var posNode=document.getElementById('openPos');
    if(posNode) posNode.innerHTML=posHtml;

    var truth=cap.truth||{};
    text('capTruth',truth.anchored
      ?('venue moved '+(truth.venue_delta>=0?'+':'')+Number(truth.venue_delta).toFixed(2)
        +' \u00b7 local ledger '+(truth.ledger_delta>=0?'+':'')+Number(truth.ledger_delta).toFixed(2)
        +' \u00b7 unexplained '+(truth.unexplained>=0?'+':'')+Number(truth.unexplained).toFixed(2)
        +' (deposits / withdrawals / gas)')
      :'venue reconciliation waiting for a proved wallet read');
    cls('capTruth','small '+(truth.anchored&&Math.abs(Number(truth.unexplained||0))>0.5?'down':''));
    text('capStake','$'+Number(controls.shared_next_stake||cap.next_stake||0).toFixed(2));
    text('capBan',controls.master_enabled?'LIVE MASTER ON':'SAFE \u00b7 LIVE MASTER OFF');
    cls('capBan','small '+(controls.master_enabled?'up':'down'));
  }
  renderBook(live);
  if(activePnlRange==='1D')renderTradePnl(live);
  liveCandleTick(live);
  var names=['delta_1s','delta_5s','delta_30s','ofi_1s','ofi_5s','spot_imbalance5','return_250ms_bps','return_1s_bps','return_5s_bps','body_usd','above_open_balance_30s','open_cross_count','path_efficiency','body_range_ratio','close_location','aggressive_bid_cluster','aggressive_ask_cluster','volume_profile_delta','probability_up'];
  var featureHtml='';for(var n=0;n<names.length;n++){var name=names[n],digits=(name.indexOf('return')>=0||name==='body_usd')?2:3;featureHtml+='<div class="f"><span>'+name+'</span><b>'+formatNumber(feature[name],digits)+'</b></div>';}
  var featureNode=el('features');if(featureNode)featureNode.innerHTML=featureHtml;
  var economics=live.economics||{};
  var econText=(economics.count?('net '+formatNumber(economics.pnl,2)+' USD over '+economics.count+' settled orders'):'no settled order yet');
  var flowNode=el('flowStatus');if(flowNode)flowNode.innerHTML='1. WebSocket cache: <b>'+esc(feed.status||'--')+'</b><br>2. Features: <b>'+(feature.ts_ms?'LIVE':'WAITING')+'</b><br>3. MAIN: <b>'+(main?esc(main.direction):'WAITING')+'</b> · REVERSAL: <b>'+(reversal?esc(reversal.direction):'not triggered')+'</b> · EF: <b>'+(ef?esc(ef.direction):'watching')+'</b><br>4. Evaluation: <b>Binance candle-close only</b><br>5. Economics: <b>'+esc(econText)+'</b><br>6. Learning: <b>'+esc((live.learning&&live.learning.status)||'idle')+'</b> · model v'+Number((live.model&&live.model.version)||0);
  text('error',live.error||'');
  if(live.chart_revision!==chartRevision)loadChart();else safeDrawChart();
}
// ---- v5/v7 chart -----------------------------------------------------
// Candles plus entry arrows, exactly as v5/v7 drew them: BUY below the bar,
// SELL above, colour by outcome, and the label turns into W/L once settled.
// A reversal leg is prefixed with R and drawn in the v7 amber.
var lwChart=null, lwSeries=null, fallbackChart=false, lwAttempt=0, lwLoading=false;
var LW_SOURCES=['https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js',
  'https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js'];
function ensureLwLibrary(){
  if(typeof LightweightCharts!=='undefined')return true;
  if(lwLoading||lwAttempt>=6)return false;
  var script=document.createElement('script');
  script.src=LW_SOURCES[lwAttempt%LW_SOURCES.length];lwAttempt++;lwLoading=true;script.async=true;
  script.onload=function(){lwLoading=false;initLwChart();if(lwSeries)renderLwChart(chartData);};
  script.onerror=function(){lwLoading=false;window.setTimeout(ensureLwLibrary,1500);};
  document.head.appendChild(script);
  return false;
}
function setChartMode(useFallback){
  fallbackChart=!!useFallback;
  var host=document.getElementById('lwchart'),box=document.getElementById('chartFallback'),note=document.getElementById('chartMode');
  if(host)host.style.display=fallbackChart?'none':'block';
  if(box)box.style.display=fallbackChart?'block':'none';
  if(note)note.style.display=fallbackChart?'block':'none';
}
function activateFallbackChart(){if(!fallbackChart)setChartMode(true);return true;}
function initLwChart(){
  if(lwChart)return;
  // Never latch. A slow CDN must not cost the real chart for the session:
  // show the local canvas meanwhile, then upgrade the moment the library lands.
  if(!ensureLwLibrary()){activateFallbackChart();return;}
  var host=document.getElementById('lwchart'); if(!host)return;
  setChartMode(false);
  try{
    lwChart=LightweightCharts.createChart(host,{
      layout:{background:{color:'#0b0e14'},textColor:'#99a'},
      grid:{vertLines:{color:'#1a2030'},horzLines:{color:'#1a2030'}},
      timeScale:{timeVisible:true,secondsVisible:false}});
    lwSeries=lwChart.addCandlestickSeries({upColor:'#26a69a',downColor:'#ef5350',
      borderVisible:false,wickUpColor:'#26a69a',wickDownColor:'#ef5350'});
  }catch(problem){lwChart=null;lwSeries=null;activateFallbackChart();return;}
  lwChart.applyOptions({width:host.clientWidth});
  window.addEventListener('resize',function(){
    lwChart.applyOptions({width:host.clientWidth});});
}
var lastTradeCurve=[];
function drawTradePnl(curve){
  var c=document.getElementById('pnlCanvas'); if(!c)return;
  var w=Math.max(280,c.clientWidth||600),h=190,dpr=Math.max(1,window.devicePixelRatio||1);
  var pixelW=Math.round(w*dpr),pixelH=Math.round(h*dpr);
  if(c.width!==pixelW||c.height!==pixelH){c.width=pixelW;c.height=pixelH;c.style.width='100%';c.style.height=h+'px';}
  var x=c.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);
  if(!curve||!curve.length){x.fillStyle='#8b98aa';x.font='11px monospace';x.textAlign='center';x.textBaseline='middle';x.fillText('P&L starts after the first settled live order',w/2,h/2);return;}
  var points=[0].concat(curve.map(function(v){return Number(v)||0;}));
  var rawLo=Math.min.apply(null,points),rawHi=Math.max.apply(null,points);
  var rawSpan=Math.max(rawHi-rawLo,1),verticalPad=Math.max(rawSpan*.12,.50);
  var lo=rawLo-verticalPad,hi=rawHi+verticalPad;
  var plot={l:10,r:w-10,t:10,b:h-23},span=hi-lo;
  function py(v){return plot.t+(plot.b-plot.t)*(1-(v-lo)/span);}
  function px(i){return plot.l+(plot.r-plot.l)*(i/Math.max(1,points.length-1));}
  x.lineWidth=1;x.strokeStyle='#17202d';
  for(var gridLine=0;gridLine<4;gridLine++){
    var gridY=plot.t+(plot.b-plot.t)*(gridLine/3);
    x.beginPath();x.moveTo(plot.l,gridY+.5);x.lineTo(plot.r,gridY+.5);x.stroke();
  }
  if(lo<=0&&hi>=0){
    x.save();x.setLineDash([4,4]);x.strokeStyle='#354156';x.lineWidth=1;
    x.beginPath();x.moveTo(plot.l,py(0));x.lineTo(plot.r,py(0));x.stroke();x.restore();
  }
  x.lineWidth=1.5;x.lineCap='butt';x.lineJoin='round';
  function segment(ax,ay,bx,by,color){x.strokeStyle=color;x.beginPath();x.moveTo(ax,ay);x.lineTo(bx,by);x.stroke();}
  for(var i=1;i<points.length;i++){
    var a=points[i-1],b=points[i],x1=px(i-1),x2=px(i),y1=py(a),y2=py(b);
    if((a<0&&b>0)||(a>0&&b<0)){
      var ratio=Math.abs(a)/(Math.abs(a)+Math.abs(b)),crossX=x1+(x2-x1)*ratio,crossY=py(0);
      segment(x1,y1,crossX,crossY,a>=0?'#27d17f':'#ff5d6c');
      segment(crossX,crossY,x2,y2,b>=0?'#27d17f':'#ff5d6c');
    }else segment(x1,y1,x2,y2,b>=0?'#27d17f':'#ff5d6c');
  }
  x.font='9px monospace';x.fillStyle='#66758a';x.textBaseline='bottom';
  x.textAlign='left';x.fillText('START',plot.l,h-4);
  x.textAlign='right';x.fillText(curve.length+' ORDERS',plot.r,h-4);
}
function renderBook(live){
  var b=live.book||{},up=b.up||{},dn=b.down||{};
  var environment=String(b.environment||'mainnet').toUpperCase()+' · LIVE WEBSOCKET';
  var rpm=Number(b.requests_last_minute||0);
  var limit=Number(b.documented_limit_rpm||240);
  var access=b.environment==='testnet'
    ?' \u00b7 separate sandbox, no key \u00b7 '+rpm+'/'+limit+' req/min'
    :(b.api_key_configured?' \u00b7 API key active \u00b7 '+rpm+'/'+limit+' req/min'
      :' \u00b7 API key missing');
  var market=b.market?(' \u00b7 '+b.market):'';
  text('bookEnvironment',environment);
  text('bookRequests',rpm+' / '+limit+' min');
  text('bookAge',b.age_ms==null?'--':Math.round(b.age_ms)+' ms');
  text('bookSpread',up.spread==null?'--':Number(up.spread).toFixed(3));
  if(String(b.status||'').indexOf('live')!==0||up.price==null||dn.price==null){
    text('bookUp','--');text('bookDown','--');
    text('bookUpSub',String(b.status||'').indexOf('live')===0?'no liquid quote':(b.status||'offline'));
    text('bookDownSub',b.error||'waiting for live snapshot');
    text('bookMeta',environment+' \u00b7 '+(b.error||b.status||'connecting')+market+access);
  } else {
    text('bookUp',Number(up.price).toFixed(3));
    text('bookDown',Number(dn.price).toFixed(3));
    text('bookUpSub','break-even '+(100*Number(up.break_even)).toFixed(1)+'% \u00b7 size '+formatNumber(up.size,0));
    text('bookDownSub','break-even '+(100*Number(dn.break_even)).toFixed(1)+'% \u00b7 size '+formatNumber(dn.size,0));
    text('bookMeta',(b.market||'current BTC 5m market')+access+' \u00b7 wallet events '+(b.wallet_ws_ready?'ready':'not ready'));
  }
  var f=live.last_fill;
  if(f){
    var fp=f.fill_price!=null?f.fill_price:f.price,qp=f.quoted_price!=null?f.quoted_price:f.quoted;
    if(f.filled&&fp!=null){
      text('fillPrice',Number(fp).toFixed(3));cls('fillPrice','metric up');
      text('fillMeta',f.kind+' '+f.direction+' \u00b7 bought '+Number(f.shares||0).toFixed(4)
        +' shares for $'+Number(f.stake||0).toFixed(2)
        +' \u00b7 quoted '+Number(qp).toFixed(3)
        +' \u00b7 slip '+(f.slippage>=0?'+':'')+Number(f.slippage).toFixed(3)
        +' \u00b7 '+latency(f)+' \u00b7 '+f.attempts+' attempt'+(f.attempts>1?'s':''));
    }else{
      text('fillPrice',f.order_status||'NOT FILLED');cls('fillPrice','metric down');
      text('fillMeta',f.kind+' '+f.direction+' \u00b7 '+(f.failure_reason||'awaiting live order')
        +' \u00b7 '+latency(f)+' \u00b7 '+Number(f.attempts||0)
        +' attempt'+(Number(f.attempts||0)===1?'':'s'));
    }
  }
}
var activePnlRange='1D';
function renderTradePnl(live){
  var t=live.trades||{};
  lastTradeCurve=t.curve||[];
  if(!t.count){
    text('pnlTotal','--');cls('pnlTotal','big');
    text('pnlMeta','no settled live order in this range · '+Number(t.attempted||0)+' terminal attempts · '+Number(t.failed||0)+' failed');
    text('pnlFill',t.fill_rate==null?'--':(100*Number(t.fill_rate)).toFixed(0)+'%');
    text('pnlAvgEntry',t.avg_price==null?'--':Number(t.avg_price).toFixed(3));
    text('pnlAvg','attempt stats only · first-attempt failures '+(t.first_attempt_failure_rate==null?'--':(100*Number(t.first_attempt_failure_rate)).toFixed(0)+'%'));
    text('pnlHigh','--');text('pnlLow','--');text('pnlNow','--');
    cls('pnlHigh','');cls('pnlLow','');cls('pnlNow','');
    drawTradePnl(lastTradeCurve);return;
  }
  var extrema=[0].concat(lastTradeCurve.map(function(value){return Number(value)||0;}));
  var high=Math.max.apply(null,extrema),low=Math.min.apply(null,extrema);
  text('pnlHigh',(high>0?'+':'')+high.toFixed(2));
  text('pnlLow',(low>0?'+':'')+low.toFixed(2));
  cls('pnlHigh',high>=0?'up':'down');cls('pnlLow',low>=0?'up':'down');
  var current=extrema[extrema.length-1];
  text('pnlNow',(current>0?'+':'')+current.toFixed(2));
  cls('pnlNow',current>=0?'up':'down');
  var v=Number(t.pnl||0),el=document.getElementById('pnlTotal');
  if(el){el.textContent=(v>=0?'+':'')+v.toFixed(2)+' USD';el.className='big '+(v>=0?'up':'down');}
  text('pnlMeta',t.count+' settled orders \u00b7 per 100 orders '+(t.per_100==null?'--':Number(t.per_100).toFixed(2))
    +' \u00b7 return on stake '+(t.return_on_stake==null?'--':(100*t.return_on_stake).toFixed(1)+'%')
    +' \u00b7 MAIN '+Number((t.by_kind||{}).MAIN||0).toFixed(2)
    +' \u00b7 REVERSAL '+Number((t.by_kind||{}).REVERSAL||0).toFixed(2)
    +' \u00b7 EF '+Number((t.by_kind||{}).EF||0).toFixed(2));
  text('pnlFill',t.fill_rate==null?'--':(100*t.fill_rate).toFixed(0)+'%');
  text('pnlAvgEntry',t.avg_price==null?'--':Number(t.avg_price).toFixed(3));
  text('pnlAvg','avg price '+(t.avg_price==null?'--':Number(t.avg_price).toFixed(3))
    +' \u00b7 avg shares '+(t.avg_shares==null?'--':Number(t.avg_shares).toFixed(3))
    +' \u00b7 avg total delay '+(t.avg_delay_ms||0)+'ms \u00b7 first-attempt failures '
    +(t.first_attempt_failure_rate==null?'--':(100*Number(t.first_attempt_failure_rate)).toFixed(0)+'%')
    +' \u00b7 '+(t.retries||0)+' retried');
  drawTradePnl(lastTradeCurve);
}
var histOffset=0,histLimit=10,histTotal=0;
function goHistoryPage(page){
  var pages=Math.max(1,Math.ceil(histTotal/histLimit));
  page=Math.max(1,Math.min(pages,Number(page)||1));
  histOffset=(page-1)*histLimit;loadHistory();
}
function renderHistoryPages(total){
  histTotal=Number(total||0);
  var holder=el('histPages');if(!holder)return;holder.innerHTML='';
  var pages=Math.ceil(histTotal/histLimit),current=Math.floor(histOffset/histLimit)+1;
  if(!pages)return;
  var chosen=[];
  if(pages<=7){for(var p=1;p<=pages;p++)chosen.push(p);}
  else{
    var wanted={1:true};wanted[pages]=true;wanted[current]=true;
    if(current>1)wanted[current-1]=true;if(current<pages)wanted[current+1]=true;
    for(var key in wanted)if(Object.prototype.hasOwnProperty.call(wanted,key))chosen.push(Number(key));
    chosen.sort(function(a,b){return a-b;});
  }
  var previous=0;
  chosen.forEach(function(page){
    if(previous&&page>previous+1){var gap=document.createElement('span');gap.className='pageGap';gap.textContent='…';holder.appendChild(gap);}
    var button=document.createElement('button');button.type='button';button.className='pageButton'+(page===current?' active':'');button.textContent=String(page);
    button.addEventListener('click',function(){goHistoryPage(page);});holder.appendChild(button);previous=page;
  });
}
function loadHistory(){
  requestJSON('/api/history?offset='+histOffset+'&limit='+histLimit,function(err,data){
    if(err||!data)return;
    var body=document.querySelector('#history tbody'); if(!body)return;
    body.innerHTML='';
    (data.rows||[]).forEach(function(r){
      var tr=document.createElement('tr'),m=r.main||{},v=r.reversal||{},e=r.ef||{};
      var net=v.direction?v:m;
      function cell(t,c){var td=document.createElement('td');td.textContent=t;if(c)td.className=c;return td;}
      function mark(o){return o&&o.correct!=null?(o.correct?'win':'loss'):'--';}
      function cls(o){return o&&o.correct!=null?(o.correct?'up':'down'):'';}
      function buy(o){if(!o)return ['--',''];if(o.financial_is_shadow)return ['SHADOW','forbidden'];if(o.forbidden)return ['F','forbidden'];if(o.filled==null)return ['--',''];if(!o.filled)return ['failed','down'];return [o.fill_price==null?'--':Number(o.fill_price).toFixed(3),'up'];}
      var mainBuy=buy(m),reversalBuy=buy(v),efBuy=buy(e);
      tr.appendChild(cell(londonStamp(r.candle_id)));
      tr.appendChild(cell(r.actual||'--',r.actual==='UP'?'up':'down'));
      tr.appendChild(cell(m.direction||'--',m.direction==='UP'?'up':'down'));
      tr.appendChild(cell(mainBuy[0],mainBuy[1]));
      tr.appendChild(cell(m.at!=null?(m.at+'s'):'--'));
      tr.appendChild(cell(mark(m),cls(m)));
      tr.appendChild(cell(v.direction||'--',v.direction?(v.direction==='UP'?'up':'down'):''));
      tr.appendChild(cell(reversalBuy[0],reversalBuy[1]));
      tr.appendChild(cell(v.direction?mark(v):'--',cls(v)));
      tr.appendChild(cell(e.direction?(e.direction==='UP'?'EFUP':'EFDOWN'):'--',e.direction?'ef':''));
      tr.appendChild(cell(efBuy[0],efBuy[1]));
      tr.appendChild(cell(e.direction?mark(e):'--',cls(e)));
      var combinedResult=r.combined_financial_result||null;
      tr.appendChild(cell(combinedResult?combinedResult.toLowerCase():'--',combinedResult==='WIN'?'up':combinedResult==='LOSS'?'down':''));
      var legs=[m,v,e],stake=0,pnl=0,hasMoney=false;
      legs.forEach(function(o){
        var settled=o&&(o.financial_result==='WIN'||o.financial_result==='LOSS'||o.financial_result==='FLAT');
        if(settled&&o.stake!=null&&(o.filled||o.financial_is_shadow)){stake+=Number(o.stake);hasMoney=true;}
        if(settled&&o.pnl!=null){pnl+=Number(o.pnl);hasMoney=true;}
      });
      if(r.combined_financial_pnl!=null){pnl=Number(r.combined_financial_pnl);hasMoney=true;}
      tr.appendChild(cell(hasMoney&&stake>0?'$'+stake.toFixed(2):'--'));
      tr.appendChild(cell(hasMoney?(pnl>=0?'+$':'-$')+Math.abs(pnl).toFixed(2):'--',hasMoney?(pnl>0?'up':pnl<0?'down':''):''));
      body.appendChild(tr);
    });
    var to=(data.offset||0)+(data.rows||[]).length;
    renderHistoryPages(data.total||0);
    var p=document.getElementById('histPrev'),n=document.getElementById('histNext');
    if(p)p.disabled=(data.offset||0)<=0;
    if(n)n.disabled=to>=(data.total||0);
  });
}
function renderLwChart(data){
  initLwChart();
  if(fallbackChart){safeDrawChart();return;}
  if(!lwSeries||!data)return;
  var candles=(data.candles||[]).map(function(c){
    return {time:Math.floor((c.time||c.candle_id||0)/1000),
            open:+c.open,high:+c.high,low:+c.low,close:+c.close};
  }).filter(function(c){return c.time>0;});
  if(candles.length)lwSeries.setData(candles);
  var marks=(data.markers||[]).map(function(m){
    var rev=(m.kind==='REVERSAL'),ef=(m.kind==='EF');
    var buy=(m.direction==='UP');
    var res=(m.correct===null||m.correct===undefined)?'PENDING':(m.correct?'WIN':'LOSS');
    return {time:Math.floor((m.candle_id||0)/1000),
      position:buy?'belowBar':'aboveBar',
      color:(m.signals_off||m.financial_is_shadow)?'#60a5fa':ef?'#9b59ff':res==='LOSS'?(rev?'#7a6a55':'#888')
           :(rev?'#d2a24c':(buy?'#26a69a':'#ef5350')),
      shape:buy?'arrowUp':'arrowDown',
      text:((m.financial_is_shadow?'S·':'')+(ef?efMarkerText(m):res==='PENDING'?(rev?'R'+(buy?'BUY':'SELL'):(buy?'BUY':'SELL'))
          :((rev?'R':'')+(res==='WIN'?'W':'L'))))};
  }).filter(function(m){return m.time>0;});
  marks.sort(function(a,b){return a.time-b.time;});
  lwSeries.setMarkers(marks);
}
function liveCandleTick(state){
  // The chart used to redraw only when a prediction or settlement bumped the
  // revision, so between events it sat still while price moved on. The live
  // candle is now pushed straight from the state feed.
  if(fallbackChart){scheduleFallbackDraw();return;}
  if(!lwSeries||!state||!state.candle)return;
  var c=state.candle;
  var t=Math.floor((c.time||0)/1000);
  if(t<=0)return;
  try{lwSeries.update({time:t,open:+c.open,high:+c.high,low:+c.low,close:+c.close});}catch(e){}
}
function loadChart(){if(chartBusy)return;chartBusy=true;requestJSON('/api/chart',function(err,data){chartBusy=false;if(err){text('error','Dashboard chart: '+err.message);return;}chartData=data||{candles:[],markers:[],history:[]};chartRevision=chartData.revision;renderHistory();renderLwChart(chartData);});}
function copyCandle(source){return {time:Number(source.time),open:Number(source.open),high:Number(source.high),low:Number(source.low),close:Number(source.close)};}
function allCandles(){
  var byTime={},source=chartData.candles||[],i,c;
  for(i=0;i<source.length;i++){c=copyCandle(source[i]);if(isFinite(c.time)&&isFinite(c.open)&&isFinite(c.high)&&isFinite(c.low)&&isFinite(c.close))byTime[String(c.time)]=c;}
  if(live&&live.candle){c=copyCandle(live.candle);if(isFinite(c.time)&&isFinite(c.open)&&isFinite(c.high)&&isFinite(c.low)&&isFinite(c.close))byTime[String(c.time)]=c;}
  var out=[];for(var key in byTime)if(Object.prototype.hasOwnProperty.call(byTime,key))out.push(byTime[key]);out.sort(function(a,b){return a.time-b.time;});return out;
}
function clampView(total){
  if(total<=0){viewEnd=0;return {start:0,end:0};}
  viewCount=Math.max(8,Math.min(viewCount,total));
  if(viewEnd==null||followLive)viewEnd=total;
  viewEnd=Math.max(viewCount,Math.min(total,Math.round(viewEnd)));
  return {start:Math.max(0,viewEnd-viewCount),end:viewEnd};
}
function setChartRange(value){viewCount=Math.max(8,Number(value)||60);followLive=true;viewEnd=null;safeDrawChart();}
function resetChartView(){viewCount=defaultViewCount();followLive=true;viewEnd=null;hoverX=null;safeDrawChart();}
window.setChartRange=setChartRange;window.resetChartView=resetChartView;
function zoomChart(factor,anchorX){
  var all=allCandles(),total=all.length;if(!total)return;
  var view=clampView(total),oldCount=view.end-view.start,newCount=Math.max(8,Math.min(total,Math.round(oldCount*factor)));
  var ratio=visibleChart&&visibleChart.cw>0?Math.max(0,Math.min(1,(anchorX-visibleChart.pad.l)/visibleChart.cw)):0.5;
  var anchorIndex=view.start+ratio*oldCount;
  var newStart=Math.round(anchorIndex-ratio*newCount);
  newStart=Math.max(0,Math.min(total-newCount,newStart));
  viewCount=newCount;viewEnd=newStart+newCount;followLive=viewEnd>=total;safeDrawChart();
}
function safeDrawChart(){try{drawChart();}catch(problem){text('topStatus','dashboard chart error');text('error',String(problem&&problem.stack||problem));}}
var fallbackDrawQueued=false;
function scheduleFallbackDraw(){
  if(fallbackDrawQueued)return;
  fallbackDrawQueued=true;
  var run=function(){fallbackDrawQueued=false;safeDrawChart();};
  if(window.requestAnimationFrame)window.requestAnimationFrame(run);else window.setTimeout(run,32);
}
function drawChart(){
  var canvas=el('chart');if(!canvas)return;var box=canvas.parentElement,dpr=window.devicePixelRatio||1,w=Math.max(300,box.clientWidth),h=Math.max(250,box.clientHeight);
  if(canvas.width!==Math.floor(w*dpr)||canvas.height!==Math.floor(h*dpr)){canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';}
  var ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  var all=allCandles(),view=clampView(all.length),candles=all.slice(view.start,view.end),i;
  if(!candles.length){ctx.fillStyle='#8b98aa';ctx.font='12px monospace';ctx.fillText('Waiting for Binance candles…',20,30);visibleChart=null;return;}
  var pad={l:8,r:67,t:16,b:28},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b,lo=Infinity,hi=-Infinity;
  var indexByTime={};for(i=0;i<candles.length;i++){indexByTime[String(candles[i].time)]=i;lo=Math.min(lo,candles[i].low);hi=Math.max(hi,candles[i].high);}
  var markers=chartData.markers||[],visibleMarkers=[];
  for(i=0;i<markers.length;i++){var mk=markers[i],idx=indexByTime[String(Number(mk.candle_id))];if(idx===undefined)continue;var mp=Number(mk.price);if(isFinite(mp)){lo=Math.min(lo,mp);hi=Math.max(hi,mp);}visibleMarkers.push({marker:mk,index:idx});}
  var margin=Math.max((hi-lo)*0.10,1);lo-=margin;hi+=margin;
  var xStep=cw/candles.length,bodyW=Math.max(2,Math.min(11,xStep*0.58));function y(price){return pad.t+(hi-price)/(hi-lo)*ch;}function x(index){return pad.l+(index+0.5)*xStep;}
  visibleChart={pad:pad,cw:cw,ch:ch,xStep:xStep,start:view.start,end:view.end,total:all.length,candles:candles};
  ctx.strokeStyle='#1c2531';ctx.lineWidth=1;ctx.fillStyle='#8290a2';ctx.font='10px monospace';
  for(var g=0;g<=5;g++){var yy=pad.t+ch*g/5;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(pad.l+cw,yy);ctx.stroke();ctx.fillText((hi-(hi-lo)*g/5).toFixed(1),pad.l+cw+5,yy+3);}
  var ticks=Math.max(2,Math.min(6,Math.floor(cw/68)));
  for(g=0;g<=ticks;g++){var gridIndex=Math.min(candles.length-1,Math.floor((candles.length-1)*g/ticks)),xx=x(gridIndex);ctx.beginPath();ctx.moveTo(xx,pad.t);ctx.lineTo(xx,pad.t+ch);ctx.stroke();ctx.fillText(londonHM(candles[gridIndex].time),Math.max(0,Math.min(cw-24,xx-15)),h-8);}
  for(i=0;i<candles.length;i++){var c=candles[i],up=c.close>=c.open,color=up?'#27d17f':'#ff5d6c',cx=x(i);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(cx,y(c.high));ctx.lineTo(cx,y(c.low));ctx.stroke();var top=Math.min(y(c.open),y(c.close)),bodyHeight=Math.max(1,Math.abs(y(c.open)-y(c.close)));ctx.fillRect(cx-bodyW/2,top,bodyW,bodyHeight);}
  var hoverCandleTime=null;
  if(hoverX!=null&&!dragState&&!pinchState){
    var hoverIdx=Math.max(0,Math.min(candles.length-1,Math.floor((hoverX-pad.l)/xStep)));
    hoverCandleTime=candles[hoverIdx].time;
  }
  var markerSlots={};
  for(i=0;i<visibleMarkers.length;i++){
    var item=visibleMarkers[i],marker=item.marker,slotKey=String(marker.candle_id),slot=markerSlots[slotKey]||0;markerSlots[slotKey]=slot+1;
    var fraction=Math.max(0.05,Math.min(0.92,(Number(marker.ts_ms)-Number(marker.candle_id))/CANDLE_MS));
    var mx=pad.l+(item.index+fraction)*xStep+(slot?Math.min(8,xStep*0.18):0),my=y(Number(marker.price)),isMain=marker.kind==='MAIN',isEf=marker.kind==='EF',isOff=!!marker.signals_off,isShadow=!!marker.financial_is_shadow;
    ctx.fillStyle=(isOff||isShadow)?'#60a5fa':(isEf?'#9b59ff':(isMain?(marker.direction==='UP'?'#26a69a':'#ef5350'):'#f7b955'));ctx.strokeStyle='#071019';ctx.lineWidth=2;ctx.beginPath();
    var glyph=Math.max(3.5,Math.min(7,xStep*0.52)),tip=glyph*1.6;ctx.lineWidth=Math.max(1,glyph/3.5);
    if(marker.direction==='UP'){ctx.moveTo(mx,my-tip);ctx.lineTo(mx-glyph,my+glyph*0.29);ctx.lineTo(mx+glyph,my+glyph*0.29);}else{ctx.moveTo(mx,my+tip);ctx.lineTo(mx-glyph,my-glyph*0.29);ctx.lineTo(mx+glyph,my-glyph*0.29);}ctx.closePath();ctx.fill();ctx.stroke();
    if(!(xStep>=26||(hoverCandleTime!=null&&Number(marker.candle_id)===hoverCandleTime)))continue;
    var label=markerText(marker),labelY=marker.direction==='UP'?my-16:my+27;ctx.font='bold 10px monospace';var labelW=ctx.measureText(label).width+8,labelX=Math.max(2,Math.min(w-labelW-2,mx-labelW/2));
    ctx.fillStyle='rgba(5,7,11,.88)';ctx.fillRect(labelX,labelY-11,labelW,14);ctx.strokeStyle=(isOff||isShadow)?'#60a5fa':(isEf?'#9b59ff':(isMain?(marker.direction==='UP'?'#26a69a':'#ef5350'):'#f7b955'));ctx.strokeRect(labelX,labelY-11,labelW,14);ctx.fillStyle=(isOff||isShadow)?'#a7d2ff':(isEf?'#c7a3ff':(isMain?(marker.direction==='UP'?'#9de8df':'#ffb0b7'):'#ffd98f'));ctx.fillText(label,labelX+4,labelY);
  }
  var tip=el('tip');if(hoverX!=null&&!dragState&&!pinchState){var hoverIndex=Math.max(0,Math.min(candles.length-1,Math.floor((hoverX-pad.l)/xStep))),hc=candles[hoverIndex],hx=x(hoverIndex);ctx.strokeStyle='#7e8b9c';ctx.beginPath();ctx.moveTo(hx,pad.t);ctx.lineTo(hx,pad.t+ch);ctx.stroke();var related=[];for(i=0;i<visibleMarkers.length;i++)if(Number(visibleMarkers[i].marker.candle_id)===hc.time)related.push(markerText(visibleMarkers[i].marker));tip.style.display='block';tip.style.left=Math.min(w-190,Math.max(4,hx+8))+'px';tip.style.top='18px';tip.textContent=londonShort(hc.time)+' '+londonZone(hc.time)+'\nO '+hc.open.toFixed(1)+' H '+hc.high.toFixed(1)+'\nL '+hc.low.toFixed(1)+' C '+hc.close.toFixed(1)+(related.length?'\n'+related.join('\n'):'');}else if(tip)tip.style.display='none';
}
var weightsData=null;
function renderWeights(){
  var table=el('weights');if(!table||!weightsData)return;
  var body=table.getElementsByTagName('tbody')[0];if(!body)return;
  var list=weightsData.weights||[],rows='',i;
  for(i=0;i<list.length;i++){
    var item=list[i],drift=Number(item.drift||0),atLimit=Math.abs(Math.abs(drift)-Number(item.max_drift||0))<1e-9;
    rows+='<tr><td>'+esc(item.name)+'</td><td>'+formatNumber(item.weight,3)+'</td><td class="muted">'+formatNumber(item.anchor,2)+'</td><td class="'+(drift>0?'up':drift<0?'down':'muted')+'">'+(drift>=0?'+':'')+formatNumber(drift,3)+(atLimit?' (clamped)':'')+'</td></tr>';
  }
  body.innerHTML=rows||'<tr><td colspan="4" class="muted">no weights</td></tr>';
  text('weightMeta','version '+Number(weightsData.version||0)+' · '+Number(weightsData.updates||0)+' updates · learning rate '+formatNumber(weightsData.learning_rate,3)+' · max drift '+formatNumber(weightsData.max_drift,2)+' · adapts after '+Number(weightsData.min_samples||0)+' settled MAIN');
  var learning=weightsData.learning||{};
  text('learnStatus',(learning.status||'idle')+(learning.error==null?'':' · last error '+formatNumber(learning.error,3)));
}
function loadWeights(){requestJSON('/api/weights',function(err,data){if(err)return;weightsData=data;renderWeights();});}
function pollState(){requestJSON('/api/state',function(err,state){if(err){text('topStatus','dashboard API error');text('error',String(err.message||err));}else{try{updateUI(state);}catch(problem){text('topStatus','dashboard render error');text('error',String(problem&&problem.stack||problem));}}window.setTimeout(pollState,250);});}
var canvas=el('chart');if(canvas){
  canvas.addEventListener('wheel',function(event){event.preventDefault();var rect=canvas.getBoundingClientRect();zoomChart(Math.exp(event.deltaY*0.0018),event.clientX-rect.left);},{passive:false});
  canvas.addEventListener('pointerdown',function(event){event.preventDefault();canvas.setPointerCapture(event.pointerId);var rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left;pointers[event.pointerId]={x:x,y:event.clientY-rect.top};hoverX=x;if(Object.keys(pointers).length===1){dragState={x:x,end:viewEnd};pinchState=null;}else if(Object.keys(pointers).length===2){var ids=Object.keys(pointers),a=pointers[ids[0]],b=pointers[ids[1]];pinchState={distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),count:viewCount,center:(a.x+b.x)/2};dragState=null;}safeDrawChart();});
  canvas.addEventListener('pointermove',function(event){var rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;if(pointers[event.pointerId]){pointers[event.pointerId]={x:x,y:y};var ids=Object.keys(pointers);if(ids.length>=2){var a=pointers[ids[0]],b=pointers[ids[1]],distance=Math.max(1,Math.hypot(a.x-b.x,a.y-b.y));if(!pinchState)pinchState={distance:distance,count:viewCount,center:(a.x+b.x)/2};var factor=pinchState.distance/distance,desired=Math.max(8,Math.round(pinchState.count/factor));zoomChart(desired/viewCount,(a.x+b.x)/2);pinchState.distance=distance;pinchState.count=viewCount;pinchState.center=(a.x+b.x)/2;}else if(dragState&&visibleChart){var shift=Math.round((dragState.x-x)/Math.max(1,visibleChart.xStep)),total=visibleChart.total;viewEnd=Math.max(viewCount,Math.min(total,(dragState.end==null?total:dragState.end)+shift));followLive=viewEnd>=total;hoverX=x;safeDrawChart();}}else{hoverX=x;safeDrawChart();}});
  function endPointer(event){delete pointers[event.pointerId];if(Object.keys(pointers).length===0){dragState=null;pinchState=null;}else if(Object.keys(pointers).length===1){var id=Object.keys(pointers)[0];dragState={x:pointers[id].x,end:viewEnd};pinchState=null;}safeDrawChart();}
  canvas.addEventListener('pointerup',endPointer);canvas.addEventListener('pointercancel',endPointer);
  canvas.addEventListener('pointerleave',function(event){if(!pointers[event.pointerId]){hoverX=null;safeDrawChart();}});
  canvas.addEventListener('dblclick',function(){resetChartView();});
}
window.addEventListener('resize',function(){safeDrawChart();drawTradePnl(lastTradeCurve);});
var pollingStarted=false;
function startPolling(){if(pollingStarted)return;pollingStarted=true;pollState();}
function startStream(){
  if(!window.EventSource){startPolling();return;}
  var source;
  try{source=new EventSource('/events');}catch(err){startPolling();return;}
  source.onmessage=function(event){
    try{updateUI(JSON.parse(event.data));}
    catch(problem){text('topStatus','dashboard render error');text('error',String(problem&&problem.stack||problem));}
  };
  source.onerror=function(){try{source.close();}catch(err){}startPolling();};
}
var previousButton=el('histPrev'),nextButton=el('histNext');
if(previousButton)previousButton.addEventListener('click',function(){goHistoryPage(Math.floor(histOffset/histLimit));});
if(nextButton)nextButton.addEventListener('click',function(){goHistoryPage(Math.floor(histOffset/histLimit)+2);});
Array.prototype.forEach.call(document.querySelectorAll('.rangeBtn'),function(button){
  button.addEventListener('click',function(){
    activePnlRange=button.getAttribute('data-range')||'1D';
    Array.prototype.forEach.call(document.querySelectorAll('.rangeBtn'),function(b){b.classList.toggle('active',b===button);});
    requestJSON('/api/pnl?range='+encodeURIComponent(activePnlRange),function(err,data){if(!err&&data)renderTradePnl({trades:data});});
  });
});
loadChart();loadWeights();startStream();
window.setInterval(loadWeights,5000);
tickRuntime();window.setInterval(tickRuntime,1000);
})();
</script></body></html>"""


DATA_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>BTC Model v__VERSION__ Data</title><style>
:root{color-scheme:dark;--bg:#080b10;--panel:#10151d;--line:#263142;--muted:#8b98aa;--text:#eaf0f8;--up:#27d17f;--down:#ff5d6c;--main:#60a5fa;--rev:#f7b955;--ef:#9b59ff;--blue:#8ab4ff;--warn:#ffd166}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.shell{max-width:760px;margin:auto}.top{position:sticky;top:0;z-index:5;background:#080b10f2;border-bottom:1px solid var(--line);padding:10px 12px;display:flex;justify-content:space-between;align-items:center}.brand{font-size:15px;font-weight:900}.small{font-size:11px;color:var(--muted);line-height:1.5}.nav,.btn{color:var(--blue);text-decoration:none;border:1px solid var(--line);background:#161d27;padding:7px 10px;border-radius:7px;font:700 11px inherit}.grid{display:grid;gap:8px;padding:8px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px}.title{font-size:16px;font-weight:900}.main{color:var(--main)}.rev{color:var(--rev)}.ef{color:var(--ef)}.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn);font-weight:900}.forbidden{color:var(--main);font-weight:900}.scroll{overflow:auto;margin-top:7px}table{width:100%;border-collapse:collapse;font-size:11px}th,td{padding:7px 5px;border-bottom:1px solid #202a38;text-align:left;white-space:nowrap}.pager{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:9px}.money{font-weight:900}.export{border-color:#3978d7;background:#2e6bc6;color:white}
</style></head><body><div class="shell"><header class="top"><div><div class="brand">DATA · LIVE ORDERS · v__VERSION__</div><div class="small">build __BUILD__ · 10 rows per query</div><div id="runStamp" class="small">--</div></div><a class="nav" href="/">← Dashboard</a></header><div class="grid">
<section id="MAIN" class="card"></section><section id="REVERSAL" class="card"></section><section id="EF" class="card"></section>
<section class="card"><div class="small">Full prediction and execution export. Stake is immediately next to P&amp;L.</div><a class="btn export" style="display:inline-block;margin-top:8px" href="/export.csv">export now</a></section>
</div></div><script>(function(){'use strict';var states={MAIN:0,REVERSAL:0,EF:0},size=10;
function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}function n(v,d){return v==null?'--':Number(v).toFixed(d)}function money(v){if(v==null)return'--';v=Number(v);return(v>=0?'+$':'-$')+Math.abs(v).toFixed(2)}function fee(r){var c=r.fee_collateral,s=r.fee_shares;if(c!=null||s!=null){var bits=[];if(Number(c||0))bits.push('$'+Number(c).toFixed(4));if(Number(s||0))bits.push(Number(s).toFixed(4)+' sh');return bits.join(' + ')||'$0.0000'}return r.fee_rate==null?'--':(100*Number(r.fee_rate)).toFixed(2)+'%'}
function load(k){var x=new XMLHttpRequest();x.open('GET','/api/orders?kind='+k+'&offset='+states[k]+'&limit='+size,true);x.onreadystatechange=function(){if(x.readyState===4){try{render(k,JSON.parse(x.responseText))}catch(err){document.getElementById(k).innerHTML='<span class="down">'+esc(err)+'</span>'}}};x.send()}
function londonParts(ms){try{var f=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});var o={};f.formatToParts(new Date(ms)).forEach(function(p){o[p.type]=p.value;});if(o.hour==='24')o.hour='00';return o;}catch(_){var d=new Date(ms);return {year:String(d.getUTCFullYear()),month:('0'+(d.getUTCMonth()+1)).slice(-2),day:('0'+d.getUTCDate()).slice(-2),hour:('0'+d.getUTCHours()).slice(-2),minute:('0'+d.getUTCMinutes()).slice(-2),second:('0'+d.getUTCSeconds()).slice(-2)};}}
function londonHM(ms){var p=londonParts(ms);return p.hour+':'+p.minute;}
var RUN_UPTIME_BASE=Number('__UPTIME_SEC__')||0;
var RUN_PAGE_BASE=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
function runtimeText(totalSeconds){
  var left=Math.max(0,Math.floor(Number(totalSeconds)||0)),out=[];
  var units=[['y',31536000],['mo',2592000],['d',86400],['h',3600],['m',60],['s',1]];
  units.forEach(function(unit){var n=Math.floor(left/unit[1]);if(n){out.push(n+unit[0]);left-=n*unit[1];}});
  return out.length?out.join(' '):'0s';
}
function tickRuntime(){
  var node=document.getElementById('runStamp');if(!node)return;
  var now=(window.performance&&typeof window.performance.now==='function')?window.performance.now():Date.now();
  node.textContent='runtime · '+runtimeText(RUN_UPTIME_BASE+(now-RUN_PAGE_BASE)/1000);
}
function render(k,d){var rows=d.rows||[],page=Math.floor(Number(d.offset||0)/size)+1,pages=Math.max(1,Math.ceil(Number(d.total||0)/size));var color=k==='MAIN'?'main':k==='REVERSAL'?'rev':'ef';var html='<div class="title '+color+'">'+k+' · RECENT ORDERS</div><div class="small">real execution data · same shared stake · newest first</div><div class="scroll"><table><thead><tr><th>UTC</th><th>Candle</th><th>sec</th><th>Side</th><th>Attempt</th><th>Signal px</th><th>Quote</th><th>Fill</th><th>Shares</th><th>Total delay</th><th>Last try</th><th>Book age</th><th>Fee</th><th>Market ID</th><th>Order</th><th>Status</th><th>Result</th><th>Stake</th><th>P&amp;L</th></tr></thead><tbody>';
rows.forEach(function(r){var sx=r.state_x==='SX',status=r.forbidden?(sx?'F+SX':'F'):(sx?'SX':(r.status||'--')),sc=r.forbidden?'forbidden':sx?'warn':r.filled?'up':(status==='QUEUED'||status==='ACCEPTED'||status==='UNKNOWN'?'':'down'),result=r.correct==null?'--':r.correct?'WIN':'LOSS',detail=[r.failure_reason||'',r.sx_trigger_reason?('SX '+r.sx_trigger_reason):''].filter(Boolean).join(' · ');html+='<tr><td>'+esc(String(r.utc||'').replace('T',' ').replace('Z',''))+'</td><td>'+londonHM(r.candle_id)+'</td><td>'+n(r.seconds_into_candle,1)+'</td><td>'+esc(r.direction)+'</td><td>'+(r.ef_attempt_seq==null?'--':'#'+Number(r.ef_attempt_seq))+'</td><td>'+n(r.signal_price,1)+'</td><td>'+n(r.quoted_price,3)+'</td><td>'+n(r.fill_price,3)+'</td><td>'+n(r.shares,3)+'</td><td>'+n(r.delay_ms,0)+'ms</td><td>'+n(r.last_attempt_ms,0)+'ms</td><td>'+n(r.book_age_ms,0)+'ms</td><td>'+fee(r)+'</td><td>'+esc(r.market_id||'--')+'</td><td>'+esc(r.order_id||'--')+'</td><td class="'+sc+'" title="'+esc(detail)+'">'+esc(status)+'</td><td class="'+(r.correct==null?'':r.correct?'up':'down')+'">'+result+'</td><td>$'+n(r.stake,2)+'</td><td class="money '+(Number(r.pnl||0)>=0?'up':'down')+'">'+money(r.pnl)+'</td></tr>'});html+='</tbody></table></div><div class="pager"><button class="btn" data-prev="'+k+'">previous</button><span class="small">page '+page+' / '+pages+' · '+Number(d.total||0)+' rows</span><button class="btn" data-next="'+k+'">next</button></div>';document.getElementById(k).innerHTML=html;var p=document.querySelector('[data-prev="'+k+'"]'),q=document.querySelector('[data-next="'+k+'"]');p.disabled=states[k]===0;q.disabled=states[k]+size>=Number(d.total||0);p.onclick=function(){states[k]=Math.max(0,states[k]-size);load(k)};q.onclick=function(){states[k]+=size;load(k)}}
['MAIN','REVERSAL','EF'].forEach(load)})();
tickRuntime();setInterval(tickRuntime,1000);
</script></body></html>"""


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], engine: Engine, store: Store) -> None:
        self.engine = engine
        self.store = store
        super().__init__(address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args: Any) -> None:
        return

    # ---- access control -----------------------------------------------
    # The controls page can flip the master switch and resize stakes, and the
    # wallet key lives on the same box, so once this socket is reachable from
    # anywhere it must not be open. Every route is gated, including the JSON
    # endpoints and every POST - an unauthenticated /api/controls POST would be
    # just as damaging as the HTML page.
    def _authorised(self) -> bool:
        secret = DASHBOARD_PASSWORD
        if not secret:
            return True                     # loopback-only, nothing to guard
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:].strip()).decode("utf-8")
        except Exception:
            return False
        _, _, supplied = raw.partition(":")
        # Constant time: a naive == leaks the password one character at a time
        # to anyone who can measure response latency.
        return hmac.compare_digest(supplied, secret)

    def _demand_auth(self) -> None:
        body = b"authentication required"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="btc-model"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._send_bytes(200, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:
        if not self._authorised():
            self._demand_auth()
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            page = (DASHBOARD_HTML
                    .replace("__VERSION__", VERSION)
                    .replace("__BUILD__", f"{BUILD_REVISION} · b{BUILD_NUMBER} · {BUILD_SHA}")
                    .replace("__UPTIME_SEC__", str(max(
                        0.0, (now_ms() - self.server.engine.started_ms) / 1000.0)))
                    )
            self._send_bytes(200, "text/html; charset=utf-8", page.encode("utf-8"))
        elif path == "/api/state":
            self._send_json(self.server.engine.live_snapshot())
        elif path == "/api/chart":
            self._send_json(self.server.engine.chart_snapshot())
        elif path == "/api/history":
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = urllib.parse.parse_qs(query)
            try:
                offset = max(0, int(params.get("offset", ["0"])[0]))
                limit = max(1, min(50, int(params.get("limit", ["10"])[0])))
            except (TypeError, ValueError):
                offset, limit = 0, 10
            self._send_json(self.server.store.settled_history(offset, limit))
        elif path == "/api/pnl":
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = urllib.parse.parse_qs(query)
            range_key = str(params.get("range", ["1D"])[0]).upper()
            self._send_json(self.server.engine.pnl_snapshot(range_key))
        elif path == "/api/orders":
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = urllib.parse.parse_qs(query)
            kind = str(params.get("kind", ["MAIN"])[0]).upper()
            try:
                offset = max(0, int(params.get("offset", ["0"])[0]))
                limit = max(1, min(50, int(params.get("limit", ["10"])[0])))
                self._send_json(
                    self.server.store.recent_orders(kind, offset, limit)
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)})
        elif path == "/api/weights":
            self._send_json(self.server.engine.weights_snapshot())
        elif path == "/export.csv":
            body = self.server.store.export_csv()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="BTC_MODEL_V8_predictions.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/data":
            page = (DATA_HTML
                    .replace("__VERSION__", VERSION)
                    .replace("__BUILD__", f"{BUILD_REVISION} · b{BUILD_NUMBER} · {BUILD_SHA}")
                    .replace("__UPTIME_SEC__", str(max(
                        0.0, (now_ms() - self.server.engine.started_ms) / 1000.0))))
            self._send_bytes(200, "text/html; charset=utf-8", page.encode("utf-8"))
        elif path == "/controls":
            page = (CONTROLS_HTML
                    .replace("__VERSION__", VERSION)
                    .replace("__BUILD__", f"{BUILD_REVISION} · b{BUILD_NUMBER} · {BUILD_SHA}")
                    .replace("__UPTIME_SEC__", str(max(
                        0.0, (now_ms() - self.server.engine.started_ms) / 1000.0)))
                    )
            self._send_bytes(200, "text/html; charset=utf-8", page.encode("utf-8"))
        elif path == "/api/controls":
            self._send_json({
                **self.server.engine.controls.snapshot(),
                "capital": self.server.store.capital_state(),
                "execution": self.server.engine.executor.readiness(),
                "version": VERSION,
            })
        elif path == "/events":
            self._events()
        else:
            self._send_bytes(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self) -> None:
        if not self._authorised():
            self._demand_auth()
            return
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "Malformed request body."})
            return
        controls = self.server.engine.controls
        store = self.server.store
        try:
            if path == "/api/controls/apply":
                # Two-step confirmation lives in the UI; the server only ever
                # sees an explicitly confirmed change.
                if payload.get("confirmed") is not True:
                    self._send_json({
                        "ok": False,
                        "error": "Changes must be confirmed before applying."})
                    return
                change = payload.get("system") or {}
                manual_value = change.get("manual_enabled")
                if manual_value is not None and not isinstance(manual_value, bool):
                    self._send_json({
                        "ok": False,
                        "error": "Master switch must be true or false.",
                    })
                    return
                proposed_stake = change.get("stake")
                if proposed_stake is not None:
                    if not isinstance(proposed_stake, dict):
                        self._send_json({
                            "ok": False,
                            "error": "Stake configuration must be an object.",
                        })
                        return
                    stake_error = validate_stake_config(proposed_stake)
                    if stake_error:
                        self._send_json({"ok": False, "error": stake_error})
                        return
                requested_on = change.get("manual_enabled") is True
                arming_version: Optional[int] = None
                if requested_on:
                    arming_version = controls.manual_version()
                    capital = store.capital_state()
                    stake_config = (
                        proposed_stake
                        if proposed_stake is not None
                        else store.control_row(SYSTEM_CONTROL_KIND)["stake"]
                    )
                    required_stake = configured_stake(
                        stake_config, float(capital["balance"])
                    )
                    # Arming is deliberate and may wait for fresh, read-only
                    # account/approval/balance checks. It never sends an
                    # approval transaction or an order.
                    readiness = self.server.engine.executor.refresh_live_readiness(
                        force=True, required_stake=required_stake
                    )
                    if not readiness.get("ready"):
                        self._send_json({
                            "ok": False,
                            "error": "Cannot turn live trading ON: "
                                     + ", ".join(readiness.get("missing") or []),
                        })
                        return
                outcome = controls.apply_change(
                    SYSTEM_CONTROL_KIND,
                    manual_enabled=change.get("manual_enabled"),
                    stake=change.get("stake"),
                    expected_manual_version=arming_version,
                )
                if not outcome.get("ok"):
                    self._send_json(outcome)
                    return
                self._send_json({"ok": True, "result": outcome,
                                 "state": controls.snapshot()})
            elif path == "/api/controls/signal":
                if payload.get("confirmed") is not True:
                    self._send_json({
                        "ok": False,
                        "error": "Changes must be confirmed before applying.",
                    })
                    return
                kind = str(payload.get("kind") or "").upper()
                manual_value = payload.get("manual_enabled")
                outcome = controls.apply_signal_toggle(kind, manual_value)
                if not outcome.get("ok"):
                    self._send_json(outcome)
                    return
                self._send_json({
                    "ok": True,
                    "result": outcome,
                    "state": controls.snapshot(),
                })
            elif path == "/api/controls/state-x":
                if payload.get("confirmed") is not True:
                    self._send_json({
                        "ok": False,
                        "error": "Changes must be confirmed before applying.",
                    })
                    return
                outcome = controls.apply_state_x_toggle(
                    payload.get("manual_enabled")
                )
                if not outcome.get("ok"):
                    self._send_json(outcome)
                    return
                self._send_json({
                    "ok": True,
                    "result": outcome,
                    "state": controls.snapshot(),
                })
            elif path == "/api/controls/rule":
                if payload.get("confirmed") is not True:
                    self._send_json({
                        "ok": False,
                        "error": "Changes must be confirmed before applying."})
                    return
                rule = payload.get("rule") or {}
                rule = {
                    "id": str(rule.get("id") or f"rule-{now_ms()}"),
                    "kinds": [str(k).upper() for k in (rule.get("kinds") or [])],
                    "days": [int(d) for d in (rule.get("days") or [])],
                    "start_minute": int(rule.get("start_minute", -1)),
                    "end_minute": int(rule.get("end_minute", -1)),
                }
                rule["label"] = describe_rule(rule)
                with controls.submit_gate:
                    error = validate_ban_rule(rule, store.ban_rules())
                    if error:
                        self._send_json({"ok": False, "error": error})
                        return
                    store.save_ban_rule(rule)
                self._send_json({"ok": True, "state": controls.snapshot()})
            elif path == "/api/controls/rule/delete":
                if payload.get("confirmed") is not True:
                    self._send_json({
                        "ok": False,
                        "error": "Changes must be confirmed before applying."})
                    return
                with controls.submit_gate:
                    store.delete_ban_rule(str(payload.get("id") or ""))
                self._send_json({"ok": True, "state": controls.snapshot()})
            else:
                self._send_bytes(404, "text/plain; charset=utf-8", b"not found")
        except Exception as problem:
            self._send_json({"ok": False, "error": str(problem)})

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while not self.server.engine.stop_event.is_set():
                payload = json.dumps(
                    self.server.engine.live_snapshot(),
                    separators=(",", ":"),
                    allow_nan=False,
                )
                self.wfile.write(("data:" + payload + "\n\n").encode("utf-8"))
                self.wfile.flush()
                if self.server.engine.stop_event.wait(SSE_INTERVAL_SEC):
                    break
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return


class App:
    def __init__(self, db_path: Path, port: int,
                 host: str = "127.0.0.1") -> None:
        self.store = Store(db_path)
        # Keep historical feature rows and core learned model weights while the
        # v7 signal epoch gives the live-order dashboard a clean visible start.
        current_candle = candle_id_from_ms(now_ms())
        latest_signal = self.store.latest_candle_id()
        # If v5.4 already recorded this live candle, start on the next one so
        # the old row does not leak into the fresh view. Otherwise include the
        # current candle, allowing the first v5.4.x call to appear immediately.
        fresh_from = (
            current_candle + CANDLE_MS
            if latest_signal >= current_candle else current_candle
        )
        self.signal_epoch = self.store.ensure_signal_epoch(fresh_from)
        self.engine = Engine(self.store)
        self.feed = FeedThread(self.engine)
        self.server = DashboardServer(
            (host, port), self.engine, self.store)
        self.host = host
        self.port = port
        self.stopped = False

    def bootstrap(self) -> None:
        try:
            candles = fetch_chart_candles(CHART_CANDLES)
            self.engine.load_history(candles)
        except Exception as exc:
            self.engine.record_error(str(exc))

    def run(self) -> None:
        # The dashboard and WebSocket start immediately. REST chart history loads
        # in the background and is never allowed to delay or overwrite live data.
        threading.Thread(target=self.bootstrap, name="chart-bootstrap", daemon=True).start()
        self._book_stop = threading.Event()
        self.predict_ws = PredictWebSocket(
            self.engine.book, self._book_stop,
            self.engine.executor.on_wallet_event,
            self.engine.executor.auth,
        )
        self.engine.start_processor()
        self.engine.executor.start()
        self.predict_ws.start()
        threading.Thread(target=book_worker,
                         args=(self.engine, self.predict_ws, self._book_stop),
                         name="predict-book", daemon=True).start()
        self.feed.start()

        def stop_handler(_signum: int, _frame: Any) -> None:
            self.stop()

        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)
        print(f"BTC Model v{VERSION}")
        print("  build     : %s (%s)" % (BUILD_SHA, BUILT_AT))
        print("  file      : %s" % Path(__file__).resolve())
        print("  mode      : MAIN + REVERSAL + EF with LIVE Predict.fun orders")
        print("  safety    : master switch starts OFF on every launch")
        print("  state x   : per-trade veto only; OFF remains shadow diagnostics")
        print("  feed      : aggTrade + depth5@100ms + kline_5m")
        print("  model     : v%d, %d online updates, adapts after %d settled MAIN"
              % (self.engine.model.version, self.engine.model.samples,
                 MODEL_MIN_SAMPLES))
        print("  database  : %s" % self.store.path)
        print("  orderbook : Predict.fun %s websocket"
              % self.engine.book.environment)
        print("  book scope: %s" % self.engine.book.book_scope)
        print("  auth      : automatic JWT renewal + account verification")
        print("  preflight : read-only BUY approvals + smart-account USDT")
        shown = "127.0.0.1" if is_loopback_host(self.host) else self.host
        print("  dashboard : http://%s:%d%s" % (
            shown, self.port,
            "  (password protected)" if DASHBOARD_PASSWORD else ""))
        print("  stop      : Ctrl+C")
        try:
            self.server.serve_forever(poll_interval=0.25)
        finally:
            self.stop()

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.engine.stop_event.set()
        try:
            self._book_stop.set()
            self.predict_ws.close()
        except Exception:
            pass
        self.feed.close()
        try:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            self.server.server_close()
        except Exception:
            pass
        self.feed.join(timeout=2.0)
        try:
            self.engine.executor.join(timeout=2.0)
            self.predict_ws.join(timeout=2.0)
        except Exception:
            pass
        self.store.close()


def synthetic_trade(ts_ms: int, price: float, aggressive_buy: bool, qty: float = 1.0) -> Dict[str, Any]:
    return {
        "E": ts_ms,
        "p": str(price),
        "q": str(qty),
        "m": not aggressive_buy,
    }


def synthetic_depth(
    ts_ms: int, bid: float, bid_qty: float, ask: float, ask_qty: float
) -> Dict[str, Any]:
    return {
        "E": ts_ms,
        "bids": [[str(bid), str(bid_qty)] for _ in range(5)],
        "asks": [[str(ask), str(ask_qty)] for _ in range(5)],
    }


def synthetic_kline(
    candle_id: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    closed: bool,
    event_ms: int,
) -> Dict[str, Any]:
    return {
        "E": event_ms,
        "k": {
            "t": candle_id,
            "T": candle_id + CANDLE_MS - 1,
            "o": str(open_price),
            "h": str(high),
            "l": str(low),
            "c": str(close),
            "v": "100",
            "x": closed,
        },
    }



class V81AdaptationTests(unittest.TestCase):
    """v8.1 GPT regime adaptation.

    The property under test throughout is that adaptation is a *superset* of
    v8: every path that is not a confidently measured regime change must
    return the multiplier 1.0, at which point every downstream number is the
    v8 number. Downgrade is prevented structurally rather than by tuning.
    """

    def _engine(self):
        eng = Engine.__new__(Engine)
        eng._adapt_returns = deque(maxlen=ADAPT_SLOW_SEC + 600)
        eng._adapt_bucket = None
        eng._adapt_bucket_close = 0.0
        eng._adapt_completed_bucket = None
        eng._adapt_completed_close = 0.0
        eng._adapt_ratio_raw = 1.0
        eng._adapt_ratio_cache = 1.0
        return eng

    def _feed(self, eng, n, start_ms=0, price=64000.0, step=0.0, seed=1):
        """n one-second samples; `step` is the per-second log move."""
        rng = random.Random(seed)
        p = price
        for i in range(n):
            p *= math.exp(step * (1.0 if rng.random() < 0.5 else -1.0))
            eng._adapt_sample(start_ms + i * 1000, p)
        return p

    # -- identity guarantees -------------------------------------------
    def test_ratio_is_one_before_any_data(self):
        self.assertEqual(self._engine().adapt_ratio(), 1.0)

    def test_ratio_is_one_during_warmup(self):
        eng = self._engine()
        self._feed(eng, ADAPT_MIN_SLOW - 1, step=0.0002)
        self.assertEqual(eng.adapt_ratio(), 1.0)

    def test_ratio_is_one_on_a_steady_tape(self):
        eng = self._engine()
        self._feed(eng, ADAPT_SLOW_SEC + 100, step=0.0002)
        self.assertEqual(eng.adapt_ratio(), 1.0)

    def test_master_switch_off_forces_identity(self):
        eng = self._engine()
        self._feed(eng, ADAPT_SLOW_SEC + 100, step=0.0002)
        global ADAPT_ENABLED
        prev = ADAPT_ENABLED
        try:
            globals()["ADAPT_ENABLED"] = False
            self.assertEqual(eng.adapt_ratio(), 1.0)
        finally:
            globals()["ADAPT_ENABLED"] = prev

    def test_identity_band_is_exact_and_engagement_is_continuous(self):
        self.assertEqual(Engine._engaged_adapt_ratio(ADAPT_IDENTITY_LO), 1.0)
        self.assertEqual(Engine._engaged_adapt_ratio(1.0), 1.0)
        self.assertEqual(Engine._engaged_adapt_ratio(ADAPT_IDENTITY_HI), 1.0)
        just_high = Engine._engaged_adapt_ratio(ADAPT_IDENTITY_HI + 1e-8)
        just_low = Engine._engaged_adapt_ratio(ADAPT_IDENTITY_LO - 1e-8)
        self.assertAlmostEqual(just_high, 1.0, places=7)
        self.assertAlmostEqual(just_low, 1.0, places=7)
        self.assertAlmostEqual(
            Engine._engaged_adapt_ratio(ADAPT_FULL_HI), ADAPT_FULL_HI,
            places=12,
        )
        self.assertAlmostEqual(
            Engine._engaged_adapt_ratio(ADAPT_FULL_LO), ADAPT_FULL_LO,
            places=12,
        )

    # -- adaptation actually engages -----------------------------------
    def test_ratio_rises_when_volatility_expands(self):
        eng = self._engine()
        self._feed(eng, ADAPT_SLOW_SEC, step=0.00005)
        base = eng.adapt_ratio()
        self._feed(eng, ADAPT_FAST_SEC, start_ms=ADAPT_SLOW_SEC * 1000,
                   step=0.0008, seed=7)
        self.assertGreater(eng.adapt_ratio(), base * 2.0)

    def test_ratio_is_bounded_both_ways(self):
        eng = self._engine()
        self._feed(eng, ADAPT_SLOW_SEC, step=0.00001)
        self._feed(eng, ADAPT_FAST_SEC, start_ms=ADAPT_SLOW_SEC * 1000,
                   step=0.05, seed=3)
        self.assertLessEqual(eng.adapt_ratio(), ADAPT_RATIO_HI)
        self.assertGreaterEqual(eng.adapt_ratio(), ADAPT_RATIO_LO)

    def test_one_bad_print_cannot_create_a_regime(self):
        eng = self._engine()
        for bucket in range(ADAPT_SLOW_SEC + 1):
            value = 0.20 if bucket == ADAPT_SLOW_SEC else (
                0.0001 if bucket % 2 else -0.0001
            )
            eng._adapt_returns.append((bucket, value))
        eng._refresh_adapt_ratio()
        self.assertEqual(eng.adapt_ratio(), 1.0)

    # -- sampler correctness -------------------------------------------
    def test_message_rate_does_not_change_the_estimate(self):
        """The defect this release exists to remove.

        Same price path, same wall-clock span, one sampled once per second
        and one sampled fifty times per second. A ring appended per feature
        rebuild would report different dispersion for these two. A
        wall-clock bucketed sampler must not.
        """
        slow, fast = self._engine(), self._engine()
        rng = random.Random(11)
        p = 64000.0
        for sec in range(1200):
            p *= math.exp(0.0003 * (1.0 if rng.random() < 0.5 else -1.0))
            slow._adapt_sample(sec * 1000, p)
            for k in range(50):          # same second, fifty messages
                fast._adapt_sample(sec * 1000 + k * 20, p)
        self.assertAlmostEqual(slow._adapt_rms(600, 10),
                               fast._adapt_rms(600, 10), places=9)

    def test_sampler_uses_completed_close_to_close_returns(self):
        """Movement inside each second must not disappear at its boundary."""
        eng = self._engine()
        price = 64_000.0
        closes = []
        for sec in range(40):
            eng._adapt_sample(sec * 1000, price)
            price *= 1.01
            eng._adapt_sample(sec * 1000 + 999, price)
            closes.append(price)
        eng._adapt_sample(40_000, price)
        expected = abs(math.log(closes[1] / closes[0]))
        self.assertAlmostEqual(eng._adapt_rms(60, 10), expected, places=12)

    def test_intrasecond_path_cannot_change_completed_return_series(self):
        """Only completed second closes belong in the volatility estimate."""
        first, second = self._engine(), self._engine()
        price = 64_000.0
        for sec in range(80):
            close = price * math.exp(0.0004 * (1 if sec % 2 else -1))
            first._adapt_sample(sec * 1000, price)
            first._adapt_sample(sec * 1000 + 999, close)

            # Same close, deliberately different first tick and message path.
            second._adapt_sample(sec * 1000, price * (1.01 if sec % 3 else 0.99))
            for offset, weight in ((200, 0.2), (600, 0.8), (999, 1.0)):
                mid = price + (close - price) * weight
                second._adapt_sample(sec * 1000 + offset, mid)
            price = close
        first._adapt_sample(80_000, price)
        second._adapt_sample(80_000, price * 1.03)
        self.assertEqual(list(first._adapt_returns), list(second._adapt_returns))

    def test_gap_longer_than_stale_limit_breaks_the_chain(self):
        eng = self._engine()
        eng._adapt_ratio_raw = 4.0
        eng._adapt_ratio_cache = 4.0
        eng._adapt_sample(0, 64000.0)
        eng._adapt_sample((ADAPT_STALE_BUCKETS + 50) * 1000, 78000.0)
        self.assertEqual(len(eng._adapt_returns), 0)
        self.assertEqual(eng.adapt_ratio(), 1.0)

    def test_out_of_order_and_bad_prints_are_ignored(self):
        eng = self._engine()
        eng._adapt_sample(10_000, 64000.0)
        eng._adapt_sample(11_000, 64010.0)
        n = len(eng._adapt_returns)
        eng._adapt_sample(5_000, 64020.0)          # out of order
        eng._adapt_sample(12_000, 0.0)             # bad print
        eng._adapt_sample(12_000, float("nan"))    # bad print
        self.assertEqual(len(eng._adapt_returns), n)

    def test_estimator_is_causal(self):
        """Future prices cannot alter an already completed estimate."""
        base, extended = self._engine(), self._engine()
        self._feed(base, 800, step=0.0003)
        self._feed(extended, 800, step=0.0003)
        cutoff = base._adapt_returns[-1][0]
        frozen = list(base._adapt_returns)
        before = base._adapt_rms(600, 10)
        self._feed(extended, 300, start_ms=800_000, step=0.02, seed=99)
        historical = [(b, r) for b, r in extended._adapt_returns if b <= cutoff]
        self.assertEqual(historical, frozen)
        self.assertEqual(before, base._adapt_rms(600, 10))

    def test_cached_ratio_does_not_rescan_windows_per_read(self):
        eng = self._engine()
        self._feed(eng, ADAPT_SLOW_SEC + 100, step=0.0002)
        cached = eng.adapt_ratio()
        with mock.patch.object(eng, "_adapt_rms", side_effect=AssertionError):
            for _ in range(100):
                self.assertEqual(eng.adapt_ratio(), cached)

    def test_legacy_tick_sigma_is_not_double_scaled(self):
        eng = self._engine()
        eng.pressure_history = deque(
            [(float(i), 64_000.0 + i * 2.0) for i in range(120)],
            maxlen=PRESSURE_HISTORY,
        )
        eng._adapt_ratio_cache = 4.0
        global ADAPT_ENABLED
        previous = ADAPT_ENABLED
        try:
            globals()["ADAPT_ENABLED"] = True
            enabled = eng._sigma_per_root_second()
            globals()["ADAPT_ENABLED"] = False
            disabled = eng._sigma_per_root_second()
        finally:
            globals()["ADAPT_ENABLED"] = previous
        self.assertEqual(enabled, disabled)

    def test_master_switch_off_restores_legacy_fair_odds_bit_for_bit(self):
        eng = self._engine()
        eng.candle = {"time": 0}
        eng.candles = deque([
            {
                "open": 64_000.0,
                "close": 64_000.0 + float(i + 1),
                "closed": True,
            }
            for i in range(24)
        ])
        eng._adapt_ratio_cache = 4.0
        ts_ms, price, open_price = 60_000, 64_035.0, 64_000.0
        moves = sorted(float(i + 1) for i in range(24))
        typical = moves[len(moves) // 2]
        seconds_left = 240.0
        per_second = max(typical / math.sqrt(300.0), price * 1e-6)
        sigma = per_second * math.sqrt(seconds_left)
        expected = clamp(
            0.5 * (1.0 + math.erf(
                (price - open_price) / (sigma * math.sqrt(2.0))
            )),
            0.01, 0.99,
        )
        global ADAPT_ENABLED
        previous = ADAPT_ENABLED
        try:
            globals()["ADAPT_ENABLED"] = False
            actual, actual_left = eng._fair_odds(ts_ms, price, open_price)
        finally:
            globals()["ADAPT_ENABLED"] = previous
        self.assertEqual(actual, expected)
        self.assertEqual(actual_left, seconds_left)

    # -- hold gate ------------------------------------------------------
    # -- constants sane -------------------------------------------------
    def test_clamp_ceiling_clears_the_observed_squeeze(self):
        # measured reach of the 96-candle RMS ratio in the Aug 2026 squeeze
        self.assertGreater(ADAPT_RATIO_HI, 4.66)

    def test_fast_window_is_shorter_than_slow(self):
        self.assertLess(ADAPT_FAST_SEC, ADAPT_SLOW_SEC)
        self.assertLessEqual(ADAPT_MIN_FAST, ADAPT_FAST_SEC)
        self.assertLessEqual(ADAPT_MIN_SLOW, ADAPT_SLOW_SEC)
        self.assertLess(ADAPT_RATIO_LO, ADAPT_FULL_LO)
        self.assertLess(ADAPT_FULL_LO, ADAPT_IDENTITY_LO)
        self.assertLess(ADAPT_IDENTITY_LO, 1.0)
        self.assertLess(1.0, ADAPT_IDENTITY_HI)
        self.assertLess(ADAPT_IDENTITY_HI, ADAPT_FULL_HI)
        self.assertLess(ADAPT_FULL_HI, ADAPT_RATIO_HI)


class V7SafetyTests(unittest.TestCase):
    """Adversarial checks for the v7 live-order boundary and shared controls."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "v7.sqlite3"
        self.store = Store(self.path)
        self.controls = TradeControls(self.store)
        self.cid = candle_id_from_ms(now_ms())

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass
        self.temporary.cleanup()

    def _prediction(
        self, kind: str, candle_id: Optional[int] = None,
        direction: str = "UP",
    ) -> Prediction:
        candle_id = int(self.cid if candle_id is None else candle_id)
        prediction = Prediction(
            candle_id=candle_id, kind=kind, direction=direction,
            ts_ms=candle_id + 1_000, price=100.0,
            probability_up=0.65 if direction == "UP" else 0.35,
            reason="v7 safety test", features={},
        )
        if kind == "EF":
            self.store.add_ef_prediction(prediction)
        else:
            self.store.add_prediction(prediction)
        return prediction

    def _trade(
        self, kind: str, candle_id: Optional[int] = None,
        direction: str = "UP", filled: bool = False,
        status: str = "QUEUED", stake: float = 10.0,
        fill_price: float = 0.40, shares: float = 25.0,
        order_hash: Optional[str] = None,
    ) -> Prediction:
        prediction = self._prediction(kind, candle_id, direction)
        self.store.record_trade({
            "candle_id": prediction.candle_id,
            "kind": kind,
            "direction": direction,
            "ts_ms": prediction.ts_ms,
            "seconds_into_candle": 1.0,
            "quoted_price": fill_price,
            "fill_price": fill_price if filled else None,
            "slippage": 0.0 if filled else None,
            "delay_ms": 30,
            "attempts": 1 if order_hash else 0,
            "filled": filled,
            "stake": stake,
            "shares": shares if filled else None,
            "fee_rate": 0.0,
            "market_id": "77",
            "market_title": "BTC 5m test",
            "book_age_ms": 20,
            "attempt_log": [],
            "forbidden": False,
            "execution_mode": "LIVE",
            "order_hash": order_hash,
            "order_status": status,
            "filled_value": stake if filled else None,
        })
        return prediction

    @staticmethod
    def _closed(candle_id: int, up: bool = True) -> Dict[str, Any]:
        return {
            "time": candle_id, "open": 100.0, "high": 102.0,
            "low": 98.0, "close": 101.0 if up else 99.0,
            "volume": 10.0, "close_time_ms": candle_id + CANDLE_MS - 1,
        }

    @staticmethod
    def _fresh_wallet(executor: LiveExecutor, amount: float = 1_000.0) -> None:
        with executor._readiness_lock:
            executor._wallet_balance_usd = float(amount)
            executor._balance_checked_ms = now_ms()
            executor._balance_error = ""

    @staticmethod
    def _sx_feature(
        direction: str = "UP",
        phase_second: float = 250.0,
        aligned_return_1s: float = 2.0,
        aligned_delta_30s: float = 1.2,
        rejection_pass: bool = True,
    ) -> Dict[str, Any]:
        sign = 1.0 if direction == "UP" else -1.0
        if direction == "UP":
            reject_up, reject_down = ((0.2, 0.4) if rejection_pass else (0.6, 0.2))
        else:
            reject_down, reject_up = ((0.2, 0.4) if rejection_pass else (0.6, 0.2))
        return {
            "phase_second": phase_second,
            "return_1s_bps": sign * aligned_return_1s,
            "delta_30s": sign * aligned_delta_30s,
            "reject_up": reject_up,
            "reject_down": reject_down,
        }

    @staticmethod
    def _seed_sx_baseline(store: Store, first_candidate_ms: int) -> None:
        start = int(first_candidate_ms) - STATE_X_BASELINE_MS
        for index in range(6):
            stamp = start + index * 60 * 60_000
            store.add_state_x_observation({
                "candle_id": candle_id_from_ms(stamp),
                "kind": "MAIN",
                "direction": "UP",
                "ts_ms": stamp,
                "seconds_into_candle": 10.0,
                "aligned_return_1s_bps": 0.1,
                "aligned_delta_30s": 0.1,
                "late_metric_15m": 10.0,
                "aligned_1s_metric_15m": 0.1,
                "aligned_delta30_median_15m": 0.1,
                "late_p80_6h": None,
                "aligned_1s_p80_6h": None,
                "original_candidate": False,
                "original_confirmed": False,
                "rejection_balance": 1.0,
                "refined_trigger": False,
                "trigger_reason": "",
                "inputs_ready": True,
            })

    def _activate_state_x(
        self,
        controls: Optional[TradeControls] = None,
        store: Optional[Store] = None,
        rejection_pass: bool = True,
        aligned_delta_30s: float = 1.2,
    ) -> Tuple[int, Dict[str, Any]]:
        controls = controls or self.controls
        store = store or self.store
        trigger_candle = self.cid - CANDLE_MS
        first_candle = trigger_candle - CANDLE_MS
        first_ts = first_candle + 250_000
        trigger_ts = trigger_candle + 250_000
        self._seed_sx_baseline(store, first_ts)
        self.assertTrue(
            controls.apply_state_x_toggle(True, first_ts).get("ok")
        )
        first = Prediction(
            candle_id=first_candle,
            kind="MAIN",
            direction="UP",
            ts_ms=first_ts,
            price=100.0,
            probability_up=0.7,
            reason="SX first distinct candle",
        )
        first_result = controls.state_x.observe_signal(
            first,
            self._sx_feature(
                "UP",
                rejection_pass=rejection_pass,
                aligned_delta_30s=aligned_delta_30s,
            ),
        )
        self.assertTrue(first_result["observation"]["original_candidate"])
        self.assertFalse(first_result["observation"]["original_confirmed"])
        confirming = Prediction(
            candle_id=trigger_candle,
            kind="MAIN",
            direction="UP",
            ts_ms=trigger_ts,
            price=100.0,
            probability_up=0.7,
            reason="SX second distinct candle",
        )
        result = controls.state_x.observe_signal(
            confirming,
            self._sx_feature(
                "UP",
                rejection_pass=rejection_pass,
                aligned_delta_30s=aligned_delta_30s,
            ),
        )
        self.assertTrue(result["observation"]["original_confirmed"])
        self.assertTrue(result["blocked"])
        return trigger_ts, result

    def test_state_x_a_off_parity_is_execution_inert(self) -> None:
        """A: OFF adds diagnostics only; the legacy queued-order path wins."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        self.assertFalse(engine.controls.snapshot()["state_x"]["enabled"])
        self.assertTrue(engine.controls.apply_change(manual_enabled=True)["ok"])
        prediction = self._prediction("EF", direction="DOWN")
        engine.feature = self._sx_feature("DOWN")
        before = self.store.control_row(SYSTEM_CONTROL_KIND)
        expected_stake = engine.controls.next_stake("EF")
        quote = {
            "price": 0.44, "spread": 0.02, "size": 400.0,
            "break_even": 0.4488, "fee_rate": 0.02, "age_ms": 25,
            "market_id": "sx-off", "market_title": "BTC 5m SX OFF",
        }
        with mock.patch.object(engine.book, "quote", return_value=quote), \
             mock.patch.object(engine.executor, "enqueue") as enqueue:
            engine._record_trade(prediction, "EF")
        row = self.store.trade_row(prediction.candle_id, "EF")
        self.assertIsNotNone(row)
        self.assertEqual(row["order_status"], "QUEUED")
        self.assertEqual(row["state_x"] or "", "")
        self.assertFalse(bool(row["state_x_active"] or 0))
        self.assertFalse(bool(row["forbidden"] or 0))
        self.assertAlmostEqual(float(row["stake"]), expected_stake)
        enqueue.assert_called_once_with(prediction, "EF")
        stored = self.store.get_ef_prediction(prediction.candle_id)
        self.assertEqual((stored.ts_ms, stored.direction),
                         (prediction.ts_ms, prediction.direction))
        after = self.store.control_row(SYSTEM_CONTROL_KIND)
        self.assertEqual(before["stake"], after["stake"])
        self.assertEqual(
            (before["win_streak"], before["loss_streak"]),
            (after["win_streak"], after["loss_streak"]),
        )

    def test_state_x_b_signals_keep_identity_while_orders_are_blocked(self) -> None:
        """B: MAIN / REVERSAL / EF still fire identically during SX."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        self._activate_state_x(engine.controls, self.store)
        self.assertTrue(engine.controls.apply_change(manual_enabled=True)["ok"])
        for rule in list(self.store.ban_rules()):
            self.store.delete_ban_rule(rule["id"])
        quote = {
            "price": 0.43, "spread": 0.01, "size": 500.0,
            "break_even": 0.4386, "fee_rate": 0.02, "age_ms": 20,
            "market_id": "sx", "market_title": "BTC 5m SX",
        }
        expected: Dict[str, Tuple[int, str]] = {}
        with mock.patch.object(engine.book, "quote", return_value=quote), \
             mock.patch.object(engine.executor, "enqueue") as enqueue:
            for index, (kind, direction) in enumerate((
                ("MAIN", "UP"), ("REVERSAL", "DOWN"), ("EF", "UP")
            ), start=1):
                prediction = Prediction(
                    candle_id=self.cid,
                    kind=kind,
                    direction=direction,
                    ts_ms=self.cid + index * 1_000,
                    price=100.0 + index,
                    probability_up=0.7 if direction == "UP" else 0.3,
                    reason=f"unchanged {kind}",
                    features=self._sx_feature(direction),
                )
                inserted = (
                    self.store.add_ef_prediction(prediction)
                    if kind == "EF" else self.store.add_prediction(prediction)
                )
                self.assertTrue(inserted)
                engine.feature = self._sx_feature(direction)
                engine._record_trade(prediction, kind)
                expected[kind] = (prediction.ts_ms, direction)
        enqueue.assert_not_called()
        for kind, identity in expected.items():
            prediction = (
                self.store.get_ef_prediction(self.cid)
                if kind == "EF" else self.store.get_prediction(self.cid, kind)
            )
            row = self.store.trade_row(self.cid, kind)
            self.assertEqual((prediction.ts_ms, prediction.direction), identity)
            self.assertEqual(row["state_x"], "SX")
            self.assertEqual(row["order_status"], "STATE_X")
            self.assertFalse(bool(row["filled"] or 0))

    def test_state_x_c_timer_is_exact_and_old_submissions_are_exempt(self) -> None:
        """C/G race: [T,T+35m) blocks; T+35m does not."""
        self.controls.state_x.set_notification_sink(lambda _message: None)
        trigger_ms, _ = self._activate_state_x()
        end_ms = trigger_ms + STATE_X_DURATION_MS
        self.assertTrue(self.controls.state_x.execution_block(end_ms - 1)[0])
        self.assertEqual(
            self.controls.state_x.snapshot(end_ms - 1)["remaining_ms"], 1
        )
        # A real POST already begun before activation keeps its existing order
        # lifecycle; a merely queued order does not receive this exemption.
        self.assertFalse(
            self.controls.state_x.execution_block(
                trigger_ms + 1_000, trigger_ms - 1
            )[0]
        )
        self.assertTrue(
            self.controls.state_x.execution_block(trigger_ms + 1_000, None)[0]
        )
        self.assertFalse(self.controls.state_x.execution_block(end_ms)[0])
        self.assertEqual(self.controls.state_x.snapshot(end_ms)["status"], "NORMAL")
        self.controls.apply_change(manual_enabled=True)
        self.assertTrue(self.controls.may_execute("EF", end_ms)[0])

    def test_state_x_formula_is_causal_direction_aligned_and_distinct(self) -> None:
        first_candle = self.cid - 2 * CANDLE_MS
        second_candle = self.cid - CANDLE_MS
        first_ts = first_candle + 250_000
        second_ts = second_candle + 250_000
        self._seed_sx_baseline(self.store, first_ts)
        self.controls.state_x.set_notification_sink(lambda _message: None)
        self.controls.apply_state_x_toggle(True, first_ts)
        first = self.controls.state_x.observe_signal(
            Prediction(first_candle, "MAIN", "UP", first_ts, 100.0, 0.7, "one"),
            self._sx_feature("UP"),
        )
        same_candle = self.controls.state_x.observe_signal(
            Prediction(first_candle, "EF", "UP", first_ts + 1, 100.0, 0.7, "same"),
            self._sx_feature("UP"),
        )
        self.assertTrue(first["observation"]["original_candidate"])
        self.assertFalse(first["observation"]["original_confirmed"])
        self.assertFalse(same_candle["observation"]["original_confirmed"])
        confirming = self.controls.state_x.observe_signal(
            Prediction(second_candle, "MAIN", "DOWN", second_ts, 99.0, 0.3, "two"),
            self._sx_feature("DOWN"),
        )
        observation = confirming["observation"]
        self.assertTrue(observation["original_confirmed"])
        self.assertAlmostEqual(
            observation["late_p80_6h"],
            percentile_linear([10.0] * 5 + [250.0, 250.0], 0.80),
        )
        self.assertAlmostEqual(
            observation["aligned_1s_p80_6h"],
            percentile_linear([0.1] * 5 + [2.0, 2.0], 0.80),
        )
        self.assertGreater(observation["late_metric_15m"],
                           observation["late_p80_6h"])
        self.assertGreater(observation["aligned_1s_metric_15m"],
                           observation["aligned_1s_p80_6h"])
        self.assertEqual(observation["trigger_reason"], "REJECTION+DELTA30")

    def test_state_x_trigger_reason_variants_are_exact(self) -> None:
        cases = (
            (True, 0.2, "REJECTION"),
            (False, 1.2, "DELTA30"),
            (True, 1.2, "REJECTION+DELTA30"),
        )
        for index, (rejection_pass, delta30, expected) in enumerate(cases):
            path = Path(self.temporary.name) / f"sx-reason-{index}.sqlite3"
            store = Store(path)
            controls = TradeControls(store)
            controls.state_x.set_notification_sink(lambda _message: None)
            try:
                _, result = self._activate_state_x(
                    controls, store,
                    rejection_pass=rejection_pass,
                    aligned_delta_30s=delta30,
                )
                self.assertEqual(result["observation"]["trigger_reason"], expected)
                self.assertEqual(controls.state_x.snapshot()["trigger_reason"],
                                 expected)
            finally:
                store.close()

    def test_state_x_d_csv_grades_all_three_without_real_pnl(self) -> None:
        """D: all streams survive in CSV and settle as research-only rows."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        self._activate_state_x(engine.controls, self.store)
        engine.controls.apply_change(manual_enabled=True)
        for rule in list(self.store.ban_rules()):
            self.store.delete_ban_rule(rule["id"])
        quote = {
            "price": 0.40, "spread": 0.01, "size": 300.0,
            "break_even": 0.408, "fee_rate": 0.02, "age_ms": 10,
            "market_id": "sx-csv", "market_title": "BTC 5m SX CSV",
        }
        directions = {"MAIN": "UP", "REVERSAL": "DOWN", "EF": "UP"}
        with mock.patch.object(engine.book, "quote", return_value=quote):
            for index, kind in enumerate(TRADE_KINDS, start=1):
                direction = directions[kind]
                prediction = Prediction(
                    self.cid, kind, direction, self.cid + index * 1_000,
                    100.0, 0.7 if direction == "UP" else 0.3,
                    f"CSV {kind}", features=self._sx_feature(direction),
                )
                if kind == "EF":
                    self.store.add_ef_prediction(prediction)
                else:
                    self.store.add_prediction(prediction)
                engine.feature = self._sx_feature(direction)
                engine._record_trade(prediction, kind)
        self.store.settle_candle(self._closed(self.cid, up=True))
        self.store.settle_trades(self.cid, "UP")
        records = [
            row for row in csv.DictReader(
                io.StringIO(self.store.export_csv().decode("utf-8"))
            ) if int(row["candle_id"]) == self.cid
        ]
        self.assertEqual({row["kind"] for row in records}, set(TRADE_KINDS))
        for row in records:
            self.assertEqual(row["state_x"], "SX")
            self.assertEqual(row["state_x_active"], "1")
            self.assertEqual(row["filled"], "0")
            self.assertEqual(float(row["pnl"]), 0.0)
            self.assertEqual(row["stake"], "")
            self.assertIn(row["correct"], {"0", "1"})
            self.assertEqual(row["sx_trigger_reason"], "REJECTION+DELTA30")
        self.assertEqual(self.store.trade_summary()["count"], 0)
        self.assertTrue(all(v["settled"] == 0 for v in self.store.leg_pnl().values()))

    def test_state_x_e_staking_and_capital_are_isolated(self) -> None:
        """E: a blocked win/loss cannot advance the shared real stake chain."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        trigger_ms, _ = self._activate_state_x(engine.controls, self.store)
        engine.controls.apply_change(manual_enabled=True)
        for rule in list(self.store.ban_rules()):
            self.store.delete_ban_rule(rule["id"])
        before_control = self.store.control_row(SYSTEM_CONTROL_KIND)
        before_capital = self.store.capital_state()
        prediction = Prediction(
            self.cid, "MAIN", "UP", self.cid + 1_000, 100.0, 0.7,
            "SX staking isolation", features=self._sx_feature("UP"),
        )
        self.store.add_prediction(prediction)
        engine.feature = self._sx_feature("UP")
        with mock.patch.object(engine.book, "quote", return_value={"price": 0.4}):
            engine._record_trade(prediction, "MAIN")
        self.store.settle_candle(self._closed(self.cid, up=True))
        emitted = self.store.settle_trades_and_report(self.cid, "UP")
        self.assertEqual(emitted, [])
        after_control = self.store.control_row(SYSTEM_CONTROL_KIND)
        after_capital = self.store.capital_state()
        self.assertEqual(
            (after_control["win_streak"], after_control["loss_streak"],
             after_control["stake"]),
            (before_control["win_streak"], before_control["loss_streak"],
             before_control["stake"]),
        )
        self.assertEqual(after_capital["balance"], before_capital["balance"])
        self.assertEqual(after_capital["free"], before_capital["free"])
        self.assertEqual(after_capital["settled_trades"],
                         before_capital["settled_trades"])

        engine.controls.state_x.snapshot(trigger_ms + STATE_X_DURATION_MS)
        real_cid = self.cid + CANDLE_MS
        self._trade("EF", real_cid, "UP", filled=True, status="FILLED")
        self.store.settle_candle(self._closed(real_cid, up=True))
        real_events = self.store.settle_trades_and_report(real_cid, "UP")
        self.assertEqual(real_events, [("EF", True)])
        for source, won in real_events:
            engine.controls.record_result(source, won)
        final_control = self.store.control_row(SYSTEM_CONTROL_KIND)
        self.assertEqual(final_control["win_streak"],
                         before_control["win_streak"] + 1)
        self.assertEqual(final_control["loss_streak"], 0)

    def test_state_x_f_forbidden_collision_preserves_f_and_sx(self) -> None:
        """F: forbidden and State X are orthogonal facts."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        self._activate_state_x(engine.controls, self.store)
        engine.controls.apply_change(manual_enabled=True)
        engine.controls.apply_signal_toggle("EF", False)
        prediction = Prediction(
            self.cid, "EF", "UP", self.cid + 1_000, 100.0, 0.7,
            "F plus SX", features=self._sx_feature("UP"),
        )
        self.store.add_ef_prediction(prediction)
        engine.feature = self._sx_feature("UP")
        with mock.patch.object(engine.book, "quote", return_value={"price": 0.4}):
            engine._record_trade(prediction, "EF")
        row = self.store.trade_row(self.cid, "EF")
        self.assertTrue(bool(row["forbidden"]))
        self.assertEqual(row["state_x"], "SX")
        self.assertEqual(self.store.recent_orders("EF")["rows"][0]["status"],
                         "F+SX")
        self.store.settle_candle(self._closed(self.cid, up=True))
        self.store.settle_trades(self.cid, "UP")
        settled = self.store.trade_row(self.cid, "EF")
        self.assertEqual((settled["filled"], settled["correct"], settled["pnl"]),
                         (0, 1, 0.0))

    def test_state_x_g_existing_position_is_never_mutated(self) -> None:
        """G: activation cannot cancel, resize or reinterpret an open fill."""
        existing_cid = self.cid - 3 * CANDLE_MS
        self._trade(
            "MAIN", existing_cid, "UP", filled=True, status="FILLED",
            stake=10.0, fill_price=0.40, shares=25.0, order_hash="existing",
        )
        before = self.store.trade_row(existing_cid, "MAIN")
        self.controls.state_x.set_notification_sink(lambda _message: None)
        self._activate_state_x()
        after_activation = self.store.trade_row(existing_cid, "MAIN")
        protected = (
            "direction", "fill_price", "filled", "stake", "shares",
            "order_hash", "order_status", "submitted_ms", "confirmed_ms",
        )
        self.assertEqual(
            tuple(before[name] for name in protected),
            tuple(after_activation[name] for name in protected),
        )
        self.store.settle_candle(self._closed(existing_cid, up=True))
        events = self.store.settle_trades_and_report(existing_cid, "UP")
        self.assertEqual(events, [("MAIN_REV", True)])
        for source, won in events:
            self.controls.record_result(source, won)
        settled = self.store.trade_row(existing_cid, "MAIN")
        self.assertEqual(settled["order_status"], "FILLED")
        self.assertTrue(bool(settled["filled"]))
        self.assertGreater(float(settled["pnl"]), 0.0)

    def test_state_x_g_worker_catches_an_older_queued_order(self) -> None:
        """The final worker boundary blocks a queue item not yet submitted."""
        engine = Engine(self.store)
        engine.controls.state_x.set_notification_sink(lambda _message: None)
        engine.controls.apply_change(manual_enabled=True)
        prediction = self._prediction("EF", direction="UP")
        engine.feature = self._sx_feature("UP")
        quote = {
            "price": 0.40, "spread": 0.01, "size": 100.0,
            "break_even": 0.408, "fee_rate": 0.02, "age_ms": 10,
            "market_id": "queued", "market_title": "queued before SX",
        }
        with mock.patch.object(engine.book, "quote", return_value=quote), \
             mock.patch.object(engine.executor, "enqueue"):
            engine._record_trade(prediction, "EF")
        self.assertEqual(
            self.store.trade_row(self.cid, "EF")["order_status"], "QUEUED"
        )
        self._activate_state_x(engine.controls, self.store)
        engine.executor._execute(prediction, "EF")
        row = self.store.trade_row(self.cid, "EF")
        self.assertEqual(row["order_status"], "STATE_X")
        self.assertEqual(row["state_x"], "SX")
        self.assertIsNone(row["stake"])
        self.assertFalse(bool(row["filled"] or 0))

    def test_state_x_h_active_timer_survives_restart(self) -> None:
        """H: persisted toggle and the original absolute expiry are restored."""
        path = Path(self.temporary.name) / "sx-restart.sqlite3"
        first_store = Store(path)
        first_controls = TradeControls(first_store)
        first_controls.state_x.set_notification_sink(lambda _message: None)
        try:
            trigger_ms, _ = self._activate_state_x(first_controls, first_store)
            original_end = trigger_ms + STATE_X_DURATION_MS
        finally:
            first_store.close()
        second_store = Store(path)
        second_controls = TradeControls(second_store)
        second_controls.state_x.set_notification_sink(lambda _message: None)
        try:
            restored = second_controls.state_x.snapshot(trigger_ms + 60_000)
            self.assertTrue(restored["enabled"])
            self.assertTrue(restored["active"])
            self.assertEqual(restored["end_time_ms"], original_end)
            self.assertTrue(
                second_controls.state_x.execution_block(original_end - 1)[0]
            )
            self.assertFalse(
                second_controls.state_x.execution_block(original_end)[0]
            )
            self.assertFalse(
                second_store.control_row(SYSTEM_CONTROL_KIND)["manual_enabled"],
                "restart still forces only the master switch OFF",
            )
        finally:
            second_store.close()

    def test_state_x_i_notifications_fire_once_per_boundary(self) -> None:
        """I: one activation, no active-window spam, one timer-clear notice."""
        messages: List[str] = []
        self.controls.state_x.set_notification_sink(messages.append)
        trigger_ms, _ = self._activate_state_x()
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("STATE X ACTIVE"))
        later_candle = self.cid
        self.controls.state_x.observe_signal(
            Prediction(
                later_candle, "EF", "UP", later_candle + 2_000,
                100.0, 0.7, "active-window observation",
            ),
            self._sx_feature("UP"),
        )
        self.controls.state_x.snapshot(trigger_ms + STATE_X_DURATION_MS - 1)
        self.assertEqual(len(messages), 1)
        self.controls.state_x.snapshot(trigger_ms + STATE_X_DURATION_MS)
        self.controls.state_x.snapshot(trigger_ms + STATE_X_DURATION_MS + 1)
        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[1].startswith("STATE X CLEARED"))

    def test_state_x_manual_off_is_immediate_and_ui_is_native(self) -> None:
        self.controls.state_x.set_notification_sink(lambda _message: None)
        trigger_ms, _ = self._activate_state_x()
        self.assertTrue(self.controls.state_x.execution_block(trigger_ms + 1)[0])
        result = self.controls.apply_state_x_toggle(False, trigger_ms + 2)
        self.assertTrue(result["ok"])
        self.assertFalse(self.controls.state_x.execution_block(trigger_ms + 3)[0])
        self.assertFalse(
            self.store.control_row(STATE_X_CONTROL_KIND)["manual_enabled"]
        )
        self.assertIn('id="stateXToggle"', CONTROLS_HTML)
        self.assertIn('id="stateXStatus"', CONTROLS_HTML)
        self.assertIn("/api/controls/state-x", CONTROLS_HTML)
        self.assertNotIn("stateX", DASHBOARD_HTML)

    def test_master_starts_off_controls_all_kinds_and_applies_bans(self) -> None:
        self.assertFalse(self.controls.snapshot()["master_enabled"])
        friday = int(datetime(2026, 8, 14, 12, tzinfo=timezone.utc).timestamp() * 1000)
        monday_ban = int(datetime(2026, 8, 17, 15, 30, tzinfo=timezone.utc).timestamp() * 1000)
        self.controls.apply_change(manual_enabled=True)
        with mock.patch(f"{__name__}.BAN_TIMEZONE", "utc"):
            self.assertTrue(all(
                self.controls.may_execute(kind, friday)[0]
                for kind in TRADE_KINDS
            ))
            self.assertFalse(self.controls.may_execute("MAIN", monday_ban)[0])
            self.assertTrue(self.controls.may_execute("REVERSAL", monday_ban)[0])
            self.assertTrue(self.controls.may_execute("EF", monday_ban)[0])
        self.controls.apply_change(manual_enabled=False)
        self.assertTrue(all(
            not self.controls.may_execute(kind, friday)[0]
            for kind in TRADE_KINDS
        ))
        malformed = self.controls.apply_change(
            manual_enabled="false"  # type: ignore[arg-type]
        )
        self.assertFalse(malformed["ok"])
        self.assertFalse(self.controls.snapshot()["master_enabled"])

    def test_master_is_forced_off_again_on_process_restart(self) -> None:
        other = Path(self.temporary.name) / "restart.sqlite3"
        first = Store(other)
        TradeControls(first).apply_change(manual_enabled=True)
        self.assertTrue(first.control_row(SYSTEM_CONTROL_KIND)["manual_enabled"])
        first.close()
        second = Store(other)
        try:
            self.assertFalse(
                second.control_row(SYSTEM_CONTROL_KIND)["manual_enabled"]
            )
        finally:
            second.close()

    def test_late_on_preflight_cannot_overtake_newer_off_intent(self) -> None:
        arming_version = self.controls.manual_version()
        off = self.controls.apply_change(manual_enabled=False)
        self.assertTrue(off["ok"])
        stale_on = self.controls.apply_change(
            manual_enabled=True,
            expected_manual_version=arming_version,
        )
        self.assertFalse(stale_on["ok"])
        self.assertTrue(stale_on["stale"])
        self.assertFalse(self.controls.snapshot()["master_enabled"])

    def test_one_shared_stake_is_identical_even_with_open_reservations(self) -> None:
        config = dict(DEFAULT_STAKE_CONFIG)
        config.update({"mode": STAKE_MODE_PERCENT, "percent": 10.0})
        self.assertTrue(self.controls.apply_change(stake=config)["ok"])
        self.assertEqual(
            [self.controls.next_stake(kind) for kind in TRADE_KINDS],
            [10.0, 10.0, 10.0],
        )
        self._trade("MAIN", status="UNKNOWN", order_hash="0xreserve")
        self.assertEqual(self.store.capital_state()["reserved"], 10.0)
        self.assertEqual(
            [self.controls.next_stake(kind) for kind in TRADE_KINDS],
            [10.0, 10.0, 10.0],
        )

    def test_reserved_full_wallet_stake_does_not_starve_its_own_order(self) -> None:
        config = dict(DEFAULT_STAKE_CONFIG)
        config.update({
            "mode": STAKE_MODE_FIXED,
            "fixed_stake": 100.0,
            "max_stake": 100.0,
        })
        self.assertTrue(self.controls.apply_change(stake=config)["ok"])
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade(
            "MAIN", candle_id=future, status="QUEUED", stake=100.0
        )
        self.assertEqual(self.store.capital_state()["free"], 0.0)
        self.assertEqual(self.controls.next_stake("EF"), 0.0)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        self._fresh_wallet(executor)
        executor.book.market_candle_id = future
        executor.book._current_market = {
            "id": 9001,
            "title": "Bitcoin Up or Down - 5 minutes",
            "startsAt": iso_utc(future),
            "endsAt": iso_utc(future + CANDLE_MS),
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
        }
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(
            executor.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(
            executor, "_attempt", return_value="BLOCKED"
        ) as attempt:
            executor._execute(prediction, "MAIN")
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(attempt.call_args.args[2], 100.0)

    def test_duplicate_signal_callback_cannot_enqueue_a_second_order(self) -> None:
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            engine = Engine(self.store)
        prediction = self._prediction("MAIN")
        with mock.patch.object(
            engine.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            engine.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(engine.executor, "enqueue") as enqueue:
            engine._record_trade(prediction, "MAIN")
            engine._record_trade(prediction, "MAIN")
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(
            self.store.db.execute(
                "SELECT COUNT(*) FROM trades WHERE candle_id=? AND kind='MAIN'",
                (self.cid,),
            ).fetchone()[0],
            1,
        )

    def test_signal_stake_allocation_is_linearized_with_on_change(self) -> None:
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            engine = Engine(self.store)
        prediction = self._prediction("MAIN")
        config = dict(DEFAULT_STAKE_CONFIG)
        config.update({"mode": STAKE_MODE_FIXED, "fixed_stake": 20.0})
        started = threading.Event()

        def record() -> None:
            started.set()
            engine._record_trade(prediction, "MAIN")

        with engine.controls.submit_gate:
            worker = threading.Thread(target=record)
            worker.start()
            self.assertTrue(started.wait(1.0))
            self.assertIsNone(self.store.trade_row(self.cid, "MAIN"))
            changed = engine.controls.apply_change(
                manual_enabled=True, stake=config
            )
            self.assertTrue(changed["ok"])
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        row = self.store.trade_row(self.cid, "MAIN")
        self.assertIsNotNone(row)
        self.assertEqual(row["order_status"], "QUEUED")
        self.assertEqual(row["stake"], 20.0)

    def test_master_off_acknowledgement_is_linearized_with_submission(self) -> None:
        self.controls.apply_change(manual_enabled=True)
        prediction = self._trade("MAIN", status="QUEUED", order_hash=None)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        post_started = threading.Event()
        release_post = threading.Event()
        off_finished = threading.Event()
        results: List[str] = []

        def request(_method: str, _path: str, _payload: Any) -> Tuple[int, Any]:
            post_started.set()
            if not release_post.wait(2.0):
                raise TimeoutError("test POST gate timed out")
            return 201, {}

        def submit() -> None:
            results.append(executor._attempt(prediction, "MAIN", 10.0, 1, []))

        def turn_off() -> None:
            self.controls.apply_change(manual_enabled=False)
            off_finished.set()

        with mock.patch.object(
            executor, "_build_payload",
            return_value=("0xgate", {"data": {}}, {"price": 0.4}),
        ), mock.patch.object(
            executor, "_request", side_effect=request
        ), mock.patch.object(
            executor, "_wait_for_state", return_value="UNKNOWN"
        ):
            submit_thread = threading.Thread(target=submit)
            submit_thread.start()
            self.assertTrue(post_started.wait(1.0))
            off_thread = threading.Thread(target=turn_off)
            off_thread.start()
            self.assertFalse(off_finished.wait(0.05))
            release_post.set()
            submit_thread.join(timeout=2.0)
            off_thread.join(timeout=2.0)
        self.assertFalse(submit_thread.is_alive())
        self.assertFalse(off_thread.is_alive())
        self.assertTrue(off_finished.is_set())
        self.assertFalse(self.controls.snapshot()["master_enabled"])
        self.assertEqual(results, ["UNKNOWN"])

    def test_signed_unknown_stays_reserved_after_candle_close(self) -> None:
        old_candle = candle_id_from_ms(now_ms() - 2 * CANDLE_MS)
        self._trade(
            "MAIN", candle_id=old_candle, status="UNKNOWN",
            order_hash="0xstill-ambiguous",
        )
        self.assertEqual(self.store.capital_state()["reserved"], 10.0)
        self.assertIn("MAIN", self.store.open_position_kinds())
        self.store.update_trade_execution(
            old_candle, "MAIN", order_status="FAILED"
        )
        self.assertEqual(self.store.capital_state()["reserved"], 0.0)
        self.assertNotIn("MAIN", self.store.open_position_kinds())

    def test_ban_overlap_checks_every_minute_and_validates_boundaries(self) -> None:
        narrow = {
            "id": "narrow", "kinds": ["EF"], "days": [0],
            "start_minute": 1, "end_minute": 4,
        }
        overlap = {
            "id": "overlap", "kinds": ["EF"], "days": [0],
            "start_minute": 2, "end_minute": 3,
        }
        self.assertTrue(rules_overlap(narrow, overlap))
        self.assertIn("overlaps", validate_ban_rule(overlap, [narrow]))
        invalid_start = dict(overlap, id="bad", start_minute=24 * 60)
        self.assertIn("Start time", validate_ban_rule(invalid_start, []))

    def test_pending_stake_waits_but_master_off_is_immediate(self) -> None:
        self.controls.apply_change(manual_enabled=True)
        self._trade("MAIN", status="UNKNOWN", order_hash="0xpending")
        config = dict(DEFAULT_STAKE_CONFIG)
        config["current_stake"] = 12.0
        outcome = self.controls.apply_change(stake=config)
        self.assertTrue(outcome["pending"])
        self.controls.apply_change(manual_enabled=False)
        self.assertFalse(self.controls.snapshot()["master_enabled"])
        self.store.update_trade_execution(
            self.cid, "MAIN", order_status="FAILED"
        )
        self.controls.state("MAIN")
        self.assertEqual(
            self.store.control_row(SYSTEM_CONTROL_KIND)["stake"]["current_stake"],
            12.0,
        )

    def test_forbidden_rows_are_f_in_data_but_never_chart_text(self) -> None:
        engine = Engine(self.store)
        prediction = self._prediction("MAIN")
        engine._record_trade(prediction, "MAIN")
        self.store.settle_candle(self._closed(self.cid))
        self.store.settle_trades(self.cid, "UP")
        row = self.store.recent_orders("MAIN")["rows"][0]
        marker = self.store.markers()[0]
        self.assertTrue(row["forbidden"])
        self.assertEqual(row["status"], "F")
        self.assertTrue(marker["signals_off"])
        self.assertNotIn("'F'", re.search(
            r"function markerText\(marker\)\{[^\n]+", DASHBOARD_HTML
        ).group(0))
        self.assertIn("m.signals_off?'#60a5fa'", DASHBOARD_HTML)

        banned_cid = int(
            datetime(2026, 8, 17, 15, 30, tzinfo=timezone.utc).timestamp() * 1000
        )
        self.controls.apply_change(manual_enabled=True)
        banned = self._prediction("MAIN", banned_cid)
        with mock.patch(f"{__name__}.BAN_TIMEZONE", "utc"):
            engine._record_trade(banned, "MAIN")
        banned_marker = [
            item for item in self.store.markers()
            if item["candle_id"] == banned_cid
        ][0]
        self.assertTrue(banned_marker["forbidden"])
        self.assertFalse(banned_marker["signals_off"])

    def test_shared_streak_counts_ef_and_is_idempotent(self) -> None:
        self._trade("MAIN", direction="UP", filled=True, status="FILLED")
        self._trade(
            "REVERSAL", direction="DOWN", filled=True, status="FILLED"
        )
        self._trade("EF", direction="UP", filled=True, status="FILLED")
        emitted = self.store.settle_trades_and_report(self.cid, "UP")
        self.assertEqual(emitted, [("MAIN_REV", False), ("EF", True)])
        for source, won in emitted:
            self.controls.record_result(source, won)
        shared = self.store.control_row(SYSTEM_CONTROL_KIND)
        self.assertEqual((shared["win_streak"], shared["loss_streak"]), (1, 0))
        self.assertEqual(self.store.settle_trades_and_report(self.cid, "UP"), [])
        sources = {
            row[0] for row in self.store.db.execute(
                "SELECT source FROM streak_events WHERE candle_id=?", (self.cid,)
            )
        }
        self.assertEqual(sources, {"MAIN_REV", "EF"})

    def test_shared_streak_updates_are_atomic_across_threads(self) -> None:
        config = dict(self.store.control_row(SYSTEM_CONTROL_KIND)["stake"])
        config["win_trigger"] = 100
        self.store.write_control(SYSTEM_CONTROL_KIND, stake=config)
        gate = threading.Barrier(12)

        def advance() -> None:
            gate.wait()
            self.controls.record_result("EF", True)

        workers = [threading.Thread(target=advance) for _ in range(12)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3.0)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        shared = self.store.control_row(SYSTEM_CONTROL_KIND)
        self.assertEqual(shared["win_streak"], 12)
        self.assertEqual(shared["loss_streak"], 0)

    def test_reversal_precedence_waits_for_unresolved_live_order(self) -> None:
        self._trade("MAIN", direction="UP", filled=True, status="FILLED")
        self._trade(
            "REVERSAL", direction="DOWN", filled=False,
            status="UNKNOWN", order_hash="0xlate-reversal",
        )
        self.assertEqual(self.store.settle_trades_and_report(self.cid, "UP"), [])
        self.store.update_trade_execution(
            self.cid, "REVERSAL", order_status="FAILED"
        )
        self.assertEqual(
            self.store.settle_trades_and_report(self.cid, "UP"),
            [("MAIN_REV", True)],
        )

    def test_rate_guard_adapts_to_server_limit_and_honours_cooldown(self) -> None:
        book = PredictBook(testnet=False)
        book._capture_rate_headers({
            "RateLimit-Limit": "40",
            "RateLimit-Remaining": "0",
            "RateLimit-Reset": "2",
        })
        self.assertEqual(book.effective_local_limit(), 30)
        self.assertGreaterEqual(book.rate_cooldown_seconds(), 1)
        with self.assertRaisesRegex(RuntimeError, "cooldown"):
            book._reserve_request("/v1/markets")
        with book._lock:
            book.rate_block_until = 0.0
            current = time.monotonic()
            book._request_times = deque([current] * 30)
        with self.assertRaisesRegex(RuntimeError, "30/min"):
            book._reserve_request("/v1/markets")

    def test_websocket_subscriptions_heartbeat_and_live_book(self) -> None:
        class FakeAuth:
            def token_and_generation(self) -> Tuple[str, int]:
                return "jwt-test", 1

            def invalidate(self, _reason: str) -> None:
                return

        class FakeSocket:
            def __init__(self) -> None:
                self.sent: List[str] = []
                self.closed = False

            def send(self, payload: str) -> None:
                self.sent.append(payload)

            def close(self) -> None:
                self.closed = True

        wallet_events: List[Dict[str, Any]] = []
        book = PredictBook(testnet=False)
        book.market_id = 77
        fake = FakeSocket()
        socket_thread = PredictWebSocket(
            book, threading.Event(), wallet_events.append,
            FakeAuth(),  # type: ignore[arg-type]
        )
        socket_thread._app = fake
        socket_thread._on_open(fake)
        subscriptions = [json.loads(item) for item in fake.sent]
        topics = {item["params"][0] for item in subscriptions}
        self.assertEqual(
            topics,
            {"predictOrderbook/77", "predictWalletEvents/jwt-test"},
        )
        for request in subscriptions:
            socket_thread._on_message(fake, json.dumps({
                "type": "R", "requestId": request["requestId"],
                "success": True,
            }))
        self.assertTrue(book.wallet_ws_ready)
        stamp = now_ms()
        socket_thread._on_message(fake, json.dumps({
            "type": "M", "topic": "predictOrderbook/77",
            "data": {
                "marketId": 77, "updateTimestampMs": stamp,
                "asks": [[0.60, 100.0]], "bids": [[0.59, 90.0]],
            },
        }))
        self.assertEqual(book.status, "live websocket")
        self.assertAlmostEqual(book.quote("UP")["price"], 0.60)
        with book._lock:
            book.book_ms = now_ms() - 60_000
            book.ws_last_message_ms = now_ms()
        self.assertAlmostEqual(book.quote("UP")["price"], 0.60)
        with book._lock:
            book.ws_last_message_ms = now_ms() - PREDICT_WS_STALE_MS - 1
        self.assertIsNone(book.quote("UP")["price"])
        with book._lock:
            book.ws_last_message_ms = now_ms()
        before = len(fake.sent)
        socket_thread._on_message(fake, json.dumps({
            "type": "M", "topic": "heartbeat", "data": "echo-me",
        }))
        self.assertEqual(
            json.loads(fake.sent[before]),
            {"method": "heartbeat", "data": "echo-me"},
        )
        socket_thread._on_message(fake, json.dumps({
            "type": "M", "topic": "predictWalletEvents/jwt-test",
            "data": {"type": "orderAccepted", "orderHash": "0x1"},
        }))
        self.assertEqual(wallet_events[-1]["orderHash"], "0x1")
        with book._lock:
            book.ws_last_message_ms = now_ms() - PREDICT_WS_RECONNECT_MS - 1
        socket_thread._opened_ms = book.ws_last_message_ms
        with mock.patch.object(
            socket_thread.stop_event, "wait", return_value=False
        ):
            socket_thread._watch_stale_session(fake)
        self.assertTrue(fake.closed)
        self.assertFalse(book.ws_connected)
        socket_thread._on_close(fake)
        self.assertFalse(book.wallet_ws_ready)

    def test_automatic_jwt_renewal_verifies_configured_account(self) -> None:
        address = "0x" + "11" * 20
        issued = int(time.time())
        claims = base64.urlsafe_b64encode(json.dumps({
            "iat": issued, "exp": issued + 3600,
        }).encode()).decode().rstrip("=")
        secret_token = f"header.{claims}.signature"

        class Builder:
            def __init__(self) -> None:
                self.messages: List[str] = []

            def sign_predict_account_message(self, message: str) -> str:
                self.messages.append(message)
                return "0x" + "ab" * 65

        builder = Builder()
        book = PredictBook(testnet=False)
        with mock.patch.dict(os.environ, {"PREDICT_JWT": ""}):
            auth = PredictAuthSession(book, "api-key", address, builder)
        responses = [
            (200, {"data": {"message": "dynamic venue message"}}),
            (200, {"data": {"token": secret_token}}),
            (200, {"data": {"address": address.upper()}}),
        ]
        with mock.patch.object(auth, "_http", side_effect=responses) as http:
            self.assertTrue(auth.ensure_token())
            self.assertTrue(auth.ensure_token())
        self.assertEqual(http.call_count, 3)
        self.assertEqual(builder.messages, ["dynamic venue message"])
        post_payload = http.call_args_list[1].args[2]
        self.assertEqual(post_payload["signer"], address)
        self.assertEqual(post_payload["message"], "dynamic venue message")
        token, generation = auth.token_and_generation()
        self.assertEqual(token, secret_token)
        self.assertEqual(generation, 1)
        state_text = json.dumps(auth.snapshot(), sort_keys=True)
        self.assertNotIn(secret_token, state_text)
        self.assertTrue(auth.snapshot()["verified"])

    def test_wallet_websocket_reconnects_on_jwt_generation_change(self) -> None:
        class FakeAuth:
            def __init__(self) -> None:
                self.token = "jwt-one"
                self.generation = 1

            def token_and_generation(self) -> Tuple[str, int]:
                return self.token, self.generation

            def invalidate(self, _reason: str) -> None:
                self.token = ""

        class FakeSocket:
            def __init__(self) -> None:
                self.sent: List[str] = []
                self.closed = False

            def send(self, payload: str) -> None:
                self.sent.append(payload)

            def close(self) -> None:
                self.closed = True

        auth = FakeAuth()
        book = PredictBook(testnet=False)
        book.market_id = 77
        fake = FakeSocket()
        socket_thread = PredictWebSocket(
            book, threading.Event(), auth=auth  # type: ignore[arg-type]
        )
        socket_thread._app = fake
        socket_thread._on_open(fake)
        self.assertTrue(any(
            "predictWalletEvents/jwt-one" in item for item in fake.sent
        ))
        socket_thread._wallet_subscribed = True
        book.wallet_ws_ready = True
        auth.token = "jwt-two"
        auth.generation = 2
        socket_thread.ensure_subscriptions()
        self.assertTrue(fake.closed)
        self.assertFalse(book.wallet_ws_ready)
        self.assertNotIn("jwt-one", book.error)
        self.assertNotIn("jwt-two", book.error)

    def test_onchain_preflight_checks_buy_approval_and_wallet_balance(self) -> None:
        address = "0x" + "33" * 20

        class Scope:
            def __init__(self, **values: Any) -> None:
                self.__dict__.update(values)

        class Side:
            BUY = 0

        class Struct:
            def __init__(self, **values: Any) -> None:
                self.__dict__.update(values)

        class PreflightBuilder:
            def __init__(self) -> None:
                self.satisfied = True
                self.scope: Any = None

            def get_approval_steps(self, scope: Any) -> List[Any]:
                self.scope = scope
                return [Struct(id="ERC20_ALLOWANCE:CTF_EXCHANGE")]

            def check_approvals(self, steps: List[Any]) -> List[Any]:
                return [Struct(step=steps[0], satisfied=self.satisfied)]

            def balance_of(self, token: str) -> int:
                self_token = token
                self.assert_token = self_token
                return 25 * 10**18

        env = {
            "PREDICT_API_KEY": "api-key",
            "PREDICT_PRIVATE_KEY": "0x" + "22" * 32,
            "PREDICT_ACCOUNT_ADDRESS": address,
            "PREDICT_JWT": "",
        }
        with mock.patch.dict(os.environ, env), mock.patch.object(
            LiveExecutor, "_load_sdk", lambda _self: None
        ):
            book = PredictBook(testnet=False)
            executor = LiveExecutor(
                self.store, self.controls, book, threading.Event()
            )
        book.market_id = 77
        book.market_candle_id = self.cid
        book._current_market = {
            "id": 77, "isNegRisk": False, "isYieldBearing": False,
        }
        book.set_ws_state(True)
        self.assertTrue(book.apply_ws_book({
            "marketId": 77, "updateTimestampMs": now_ms(),
            "asks": [[0.51, 100.0]], "bids": [[0.49, 100.0]],
        }))
        book.wallet_ws_ready = True
        auth = mock.Mock()
        auth.ensure_token.return_value = True
        auth.snapshot.return_value = {
            "ready": True, "status": "authenticated", "error": "",
            "generation": 1, "verified": True,
            "last_verified_ms": now_ms(), "last_refresh_ms": now_ms(),
            "expires_in_sec": 3600,
        }
        auth.token_and_generation.return_value = ("jwt", 1)
        executor.auth = auth
        executor._builder = object()
        builder = PreflightBuilder()
        executor._preflight_builder = builder
        executor._sdk = {"ApprovalScope": Scope, "Side": Side}
        ready = executor.refresh_live_readiness(
            force=True, required_stake=10.0
        )
        self.assertTrue(ready["ready"], ready["missing"])
        self.assertEqual(ready["wallet_balance_usd"], 25.0)
        self.assertEqual(builder.scope.operation, "TRADE")
        self.assertEqual(builder.scope.side, Side.BUY)
        builder.satisfied = False
        blocked = executor.refresh_live_readiness(
            force=True, required_stake=30.0
        )
        self.assertFalse(blocked["ready"])
        self.assertTrue(any(
            "BUY approval" in item for item in blocked["missing"]
        ))
        self.assertTrue(any(
            "below shared stake" in item for item in blocked["missing"]
        ))

    def test_restart_reconciles_a_stored_partial_fill_exactly_once(self) -> None:
        self._trade(
            "MAIN", filled=True, status="FILLED", order_hash="0xpartial"
        )
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        context = executor._contexts["0xpartial"]
        context["next_check"] = 0.0
        with mock.patch.object(
            executor, "_rest_state", return_value=("FILLED", {})
        ) as rest_state:
            executor._last_reconcile = 0.0
            executor._reconcile_unknowns()
            executor._last_reconcile = 0.0
            executor._reconcile_unknowns()
        self.assertEqual(rest_state.call_count, 1)
        self.assertFalse(context["restored"])

    def test_ambiguous_submission_is_unknown_and_never_blindly_retried(self) -> None:
        prediction = self._trade("MAIN", order_hash=None)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        logs: List[Dict[str, Any]] = []
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "_build_payload",
            return_value=("0xambiguous", {"data": {}}, {"price": 0.4}),
        ), mock.patch.object(
            executor, "_request", side_effect=socket.timeout("late response")
        ) as request:
            result = executor._attempt(prediction, "MAIN", 10.0, 1, logs)
        self.assertEqual(result, "UNKNOWN")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(
            self.store.trade_row(self.cid, "MAIN")["order_status"], "UNKNOWN"
        )

    def test_connection_reset_after_post_is_also_ambiguous(self) -> None:
        prediction = self._trade("MAIN", order_hash=None)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "_build_payload",
            return_value=("0xreset", {"data": {}}, {"price": 0.4}),
        ), mock.patch.object(
            executor, "_request", side_effect=ConnectionResetError("reset")
        ) as request:
            outcome = executor._attempt(
                prediction, "MAIN", 10.0, 1, []
            )
        self.assertEqual(outcome, "UNKNOWN")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(
            self.store.trade_row(self.cid, "MAIN")["order_status"], "UNKNOWN"
        )

    def test_local_presubmit_failure_never_strands_a_signed_hash(self) -> None:
        prediction = self._trade("MAIN", order_hash=None)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "_build_payload",
            return_value=("0xlocal", {"data": {}}, {"price": 0.4}),
        ), mock.patch.object(
            executor, "_request",
            side_effect=PredictRequestNotSent("local rate guard"),
        ):
            outcome = executor._attempt(prediction, "MAIN", 10.0, 1, [])
        self.assertEqual(outcome, "BLOCKED")
        row = self.store.trade_row(self.cid, "MAIN")
        self.assertEqual(row["order_status"], "NOT_SENT")
        self.assertIsNone(row["order_hash"])
        self.assertNotIn("0xlocal", executor._contexts)

    def test_http_auth_and_server_failures_never_blindly_retry(self) -> None:
        blocked = self._trade("MAIN", order_hash=None)
        unknown = self._trade(
            "MAIN", candle_id=self.cid + CANDLE_MS, order_hash=None
        )
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        self._fresh_wallet(executor)
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "_build_payload",
            side_effect=[
                ("0xauth", {"data": {}}, {"price": 0.4}),
                ("0xserver", {"data": {}}, {"price": 0.4}),
            ],
        ), mock.patch.object(
            executor, "_request",
            side_effect=[(401, {"error": "expired"}),
                         (503, {"error": "unavailable"})],
        ) as request:
            first = executor._attempt(blocked, "MAIN", 10.0, 1, [])
            second = executor._attempt(unknown, "MAIN", 10.0, 1, [])
        self.assertEqual((first, second), ("BLOCKED", "UNKNOWN"))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            self.store.trade_row(self.cid, "MAIN")["order_status"], "HTTP_401"
        )
        self.assertIsNone(
            self.store.trade_row(self.cid, "MAIN")["order_hash"]
        )
        self.assertNotIn("0xauth", executor._contexts)
        self.assertEqual(
            self.store.trade_row(
                self.cid + CANDLE_MS, "MAIN"
            )["order_status"],
            "HTTP_503",
        )
        self.assertLessEqual(
            executor._contexts["0xserver"]["next_check"], time.monotonic()
        )

    def test_only_terminal_proof_allows_one_retry(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        first = self._trade("MAIN", future, status="QUEUED")
        second = self._trade("MAIN", future + CANDLE_MS, status="QUEUED")
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        self._fresh_wallet(executor)
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(
            executor.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(
            executor, "_attempt", side_effect=["TERMINAL", "FILLED"]
        ) as attempt:
            executor.book.market_candle_id = future
            executor.book._current_market = {
                "id": 9002,
                "title": "Bitcoin Up or Down - 5 minutes",
                "startsAt": iso_utc(future),
                "endsAt": iso_utc(future + CANDLE_MS),
                "tradingStatus": "OPEN",
                "status": "REGISTERED",
                "isVisible": True,
                "variantData": {
                    "type": "CRYPTO_UP_DOWN",
                    "priceFeedSymbol": "BTCUSDT",
                },
            }
            executor._execute(first, "MAIN")
            self.assertEqual(attempt.call_count, 2)
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(
            executor.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(
            executor, "_attempt", return_value="UNKNOWN"
        ) as attempt:
            executor.book.market_candle_id = future + CANDLE_MS
            executor.book._current_market = {
                "id": 9003,
                "title": "Bitcoin Up or Down - 5 minutes",
                "startsAt": iso_utc(future + CANDLE_MS),
                "endsAt": iso_utc(future + 2 * CANDLE_MS),
                "tradingStatus": "OPEN",
                "status": "REGISTERED",
                "isVisible": True,
                "variantData": {
                    "type": "CRYPTO_UP_DOWN",
                    "priceFeedSymbol": "BTCUSDT",
                },
            }
            executor._execute(second, "MAIN")
            self.assertEqual(attempt.call_count, 1)

    def test_late_wallet_fill_is_deduplicated_repriced_and_graded(self) -> None:
        self._trade(
            "MAIN", filled=False, status="UNKNOWN", order_hash="0xlate"
        )
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        event = {
            "type": "orderTransactionSuccess", "orderHash": "0xlate",
            "orderId": "venue-1", "settlementId": "settlement-1",
            "timestamp": now_ms(),
            "fill": {
                "executedPriceWei": str(4 * 10**17),
                "executedSizeWei": str(25 * 10**18),
                "executedValueWei": str(10 * 10**18),
            },
            "fee": {
                "amountWei": str(1 * 10**18), "type": "SHARES",
            },
        }
        executor.on_wallet_event(event)
        executor.on_wallet_event(event)
        # A new process restores the aggregate and the persisted settlement
        # id, so replaying the wallet event still cannot duplicate the fill.
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            restarted = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        restarted.on_wallet_event(event)
        row = self.store.trade_row(self.cid, "MAIN")
        self.assertTrue(row["filled"])
        self.assertEqual(row["stake"], 10.0)
        self.assertEqual(row["shares"], 25.0)
        self.assertEqual(row["fee_shares"], 1.0)
        self.assertEqual(
            self.store.db.execute(
                "SELECT COUNT(*) FROM order_fills WHERE order_hash='0xlate'"
            ).fetchone()[0],
            1,
        )
        self.store.settle_candle(self._closed(self.cid))
        restarted.on_wallet_event(event)
        row = self.store.trade_row(self.cid, "MAIN")
        self.assertEqual(row["pnl"], 14.0)
        self.assertEqual(
            self.store.db.execute(
                "SELECT COUNT(*) FROM streak_events WHERE candle_id=?",
                (self.cid,),
            ).fetchone()[0],
            1,
        )

    def test_rest_recovery_uses_exact_signed_hash_match(self) -> None:
        self._trade(
            "MAIN", filled=False, status="UNKNOWN", order_hash="0xrecover"
        )
        with mock.patch.dict(os.environ, {"PREDICT_ACCOUNT_ADDRESS": "0xaccount"}), \
                mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        responses = [
            (200, {"data": {"status": "FILLED", "amountFilled": "25"}}),
            (200, {"data": [{
                "taker": {
                    "hash": "0xrecover", "amount": "25", "price": "0.4"
                },
                "amountFilled": "25", "priceExecuted": "0.4",
                "transactionHash": "0xtx",
            }]}),
        ]
        with mock.patch.object(executor, "_request", side_effect=responses) as request:
            state, _ = executor._rest_state("0xrecover")
        self.assertEqual(state, "FILLED")
        self.assertEqual(request.call_count, 2)
        row = self.store.trade_row(self.cid, "MAIN")
        self.assertTrue(row["filled"])
        self.assertEqual((row["stake"], row["shares"]), (10.0, 25.0))

    def test_official_sdk_payload_keeps_wei_and_journal_uses_decimal_price(self) -> None:
        class Struct:
            def __init__(self, **values: Any) -> None:
                self.__dict__.update(values)

        class Side:
            BUY = 0

        class Builder:
            def __init__(self) -> None:
                self.market_input: Any = None
                self.book: Any = None
                self.order_input: Any = None

            def get_market_order_amounts(self, market_input: Any, book: Any) -> Any:
                self.market_input, self.book = market_input, book
                return Struct(
                    maker_amount=10 * 10**18,
                    taker_amount=24 * 10**18,
                    amount=25 * 10**18,
                    price_per_share=4 * 10**17,
                    slippage_bps=PREDICT_ORDER_SLIPPAGE_BPS,
                    is_min_amount_out=True,
                )

            def build_order(self, strategy: str, order_input: Any) -> Any:
                self.order_input = order_input
                return {"strategy": strategy}

            def build_typed_data(self, order: Any, **options: Any) -> Any:
                return {"order": order, **options}

            def sign_typed_data_order(self, _typed: Any) -> Any:
                return Struct(
                    salt="1", maker="0xmaker", signer="0xsigner",
                    taker="0x0", token_id="222", maker_amount="10",
                    taker_amount="24", expiration="0", nonce="0",
                    fee_rate_bps="200", side=0, signature_type=0,
                    signature="0xsig",
                )

            def build_typed_data_hash(self, _typed: Any) -> str:
                return "0xABC"

        book = PredictBook(testnet=False)
        book.market_id = 77
        book.market_candle_id = self.cid
        book._current_market = {
            "id": 77,
            "outcomes": [
                {"name": "UP", "onChainId": "111"},
                {"name": "DOWN", "onChainId": "222"},
            ],
            "isNegRisk": False,
            "isYieldBearing": False,
        }
        book.set_ws_state(True)
        self.assertTrue(book.apply_ws_book({
            "marketId": 77, "updateTimestampMs": now_ms(),
            "asks": [[0.61, 20.0]], "bids": [[0.60, 25.0]],
        }))
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, book, threading.Event()
            )
        builder = Builder()
        executor._builder = builder
        executor._sdk = {
            "Book": Struct, "BuildOrderInput": Struct,
            "MarketHelperValueInput": Struct, "Side": Side,
        }
        prediction = self._prediction("MAIN", direction="DOWN")
        order_hash, payload, meta = executor._build_payload(prediction, 10.0)
        data = payload["data"]
        self.assertEqual(order_hash, "0xabc")
        self.assertEqual(meta["price"], 0.4)
        self.assertEqual(meta["planned_stake"], 10.0)
        self.assertAlmostEqual(meta["max_price"], 10.0 / 24.0)
        self.assertEqual(data["pricePerShare"], str(4 * 10**17))
        self.assertEqual(data["amount"], str(25 * 10**18))
        self.assertTrue(data["isMinAmountOut"])
        self.assertTrue(data["isFillOrKill"])
        self.assertEqual(data["slippageBps"], str(PREDICT_ORDER_SLIPPAGE_BPS))
        self.assertEqual(data["order"]["hash"], "0xabc")
        self.assertEqual(builder.market_input.value_wei, 10 * 10**18)
        self.assertEqual(builder.order_input.token_id, "222")
        self.assertEqual(builder.book.asks, [(0.4, 25.0)])

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_executor_refuses_partial_stake_and_ef_depth_beyond_cap(self) -> None:
        main = self._trade("MAIN", order_hash=None)
        ef_cid = self.cid + CANDLE_MS
        ef = self._trade("EF", candle_id=ef_cid, order_hash=None)
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "_build_payload",
            side_effect=[
                (
                    "0xthin", {"data": {}},
                    {"price": 0.40, "planned_stake": 6.0, "max_price": 0.40},
                ),
                (
                    "0xefcap", {"data": {}},
                    {"price": 0.49, "planned_stake": 10.0, "max_price": 0.51},
                ),
            ],
        ), mock.patch.object(executor, "_request") as request:
            main_result = executor._attempt(main, "MAIN", 10.0, 1, [])
            ef_result = executor._attempt(ef, "EF", 10.0, 1, [])
        self.assertEqual((main_result, ef_result), ("BLOCKED", "BLOCKED"))
        request.assert_not_called()
        main_row = self.store.trade_row(self.cid, "MAIN")
        ef_row = self.store.trade_row(ef_cid, "EF")
        self.assertEqual(main_row["order_status"], "NO_LIQUIDITY")
        self.assertEqual(ef_row["order_status"], "PRICE_LIMIT")
        self.assertIsNone(main_row["order_hash"])
        self.assertIsNone(ef_row["order_hash"])
        self.assertNotIn("0xthin", executor._contexts)
        self.assertNotIn("0xefcap", executor._contexts)

    def test_control_endpoint_refuses_to_arm_without_full_preflight(self) -> None:
        # This test proves the HTTP control path refuses arming when full
        # preflight is not ready. Never let inherited operator credentials turn
        # that unit test into a live Predict.fun/RPC network timing test.
        engine = Engine(self.store)
        not_ready = {"ready": False, "missing": ["preflight stubbed by test"]}
        with mock.patch.object(
            engine.executor, "refresh_live_readiness",
            return_value=not_ready,
        ) as preflight:
            server = DashboardServer(("127.0.0.1", 0), engine, self.store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/api/state", timeout=3.0
                ) as response:
                    snapshot = json.loads(response.read().decode())
                self.assertFalse(snapshot["controls"]["master_enabled"])
                self.assertEqual(set(snapshot["controls"]["kinds"]), set(TRADE_KINDS))
                body = json.dumps({
                    "confirmed": True, "system": {"manual_enabled": True}
                }).encode()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/controls/apply",
                    data=body, headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    result = json.loads(response.read().decode())
                self.assertFalse(result["ok"])
                self.assertIn("Cannot turn live trading ON", result["error"])
                self.assertIn("preflight stubbed by test", result["error"])
                self.assertFalse(self.controls.snapshot()["master_enabled"])
                preflight.assert_called_once()
                self.assertTrue(preflight.call_args.kwargs["force"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)

    def test_arming_preflights_the_proposed_shared_stake(self) -> None:
        engine = Engine(self.store)
        server = DashboardServer(("127.0.0.1", 0), engine, self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = dict(DEFAULT_STAKE_CONFIG)
        config.update({
            "mode": STAKE_MODE_FIXED,
            "fixed_stake": 50.0,
            "max_stake": 50.0,
        })
        try:
            with mock.patch.object(
                engine.executor, "refresh_live_readiness",
                return_value={"ready": True, "missing": []},
            ) as preflight:
                body = json.dumps({
                    "confirmed": True,
                    "system": {"manual_enabled": True, "stake": config},
                }).encode()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/controls/apply",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    result = json.loads(response.read().decode())
            self.assertTrue(result["ok"])
            self.assertTrue(self.controls.snapshot()["master_enabled"])
            self.assertEqual(
                preflight.call_args.kwargs["required_stake"], 50.0
            )
            self.assertTrue(preflight.call_args.kwargs["force"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_http_off_overtakes_an_older_slow_on_preflight(self) -> None:
        engine = Engine(self.store)
        server = DashboardServer(("127.0.0.1", 0), engine, self.store)
        server_thread = threading.Thread(
            target=server.serve_forever, daemon=True
        )
        server_thread.start()
        preflight_started = threading.Event()
        release_preflight = threading.Event()
        on_result: List[Dict[str, Any]] = []
        on_errors: List[Exception] = []

        def slow_preflight(**_kwargs: Any) -> Dict[str, Any]:
            preflight_started.set()
            release_preflight.wait(3.0)
            return {"ready": True, "missing": []}

        def post(enabled: bool) -> Dict[str, Any]:
            body = json.dumps({
                "confirmed": True,
                "system": {"manual_enabled": enabled},
            }).encode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/controls/apply",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=4.0) as response:
                return json.loads(response.read().decode())

        def arm() -> None:
            try:
                on_result.append(post(True))
            except Exception as exc:
                on_errors.append(exc)

        try:
            with mock.patch.object(
                engine.executor, "refresh_live_readiness",
                side_effect=slow_preflight,
            ):
                arm_thread = threading.Thread(target=arm)
                arm_thread.start()
                self.assertTrue(preflight_started.wait(2.0))
                off_result = post(False)
                self.assertTrue(off_result["ok"])
                release_preflight.set()
                arm_thread.join(timeout=4.0)
            self.assertFalse(arm_thread.is_alive())
            self.assertFalse(on_errors)
            self.assertEqual(len(on_result), 1)
            self.assertFalse(on_result[0]["ok"])
            self.assertTrue(on_result[0].get("stale"))
            self.assertFalse(engine.controls.snapshot()["master_enabled"])
        finally:
            release_preflight.set()
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2.0)

    def test_additive_migration_preserves_data_and_shared_stake(self) -> None:
        legacy = Path(self.temporary.name) / "legacy.sqlite3"
        db = sqlite3.connect(str(legacy))
        db.executescript(
            "CREATE TABLE sentinel(value TEXT);"
            "INSERT INTO sentinel VALUES('keep-me');"
            "CREATE TABLE trade_controls("
            "kind TEXT PRIMARY KEY,manual_enabled INTEGER NOT NULL DEFAULT 1,"
            "stake_config TEXT NOT NULL,win_streak INTEGER NOT NULL DEFAULT 0,"
            "loss_streak INTEGER NOT NULL DEFAULT 0,pending TEXT,"
            "updated_ms INTEGER NOT NULL DEFAULT 0);"
        )
        config = dict(DEFAULT_STAKE_CONFIG)
        config["current_stake"] = 17.0
        db.execute(
            "INSERT INTO trade_controls VALUES('MAIN',1,?,2,1,NULL,1)",
            (json.dumps(config),),
        )
        db.commit()
        db.close()
        migrated = Store(legacy)
        try:
            shared = migrated.control_row(SYSTEM_CONTROL_KIND)
            self.assertFalse(shared["manual_enabled"])
            self.assertEqual(shared["stake"]["current_stake"], 17.0)
            self.assertEqual((shared["win_streak"], shared["loss_streak"]), (2, 1))
            self.assertEqual(
                migrated.db.execute("SELECT value FROM sentinel").fetchone()[0],
                "keep-me",
            )
            columns = {
                row[1] for row in migrated.db.execute("PRAGMA table_info(trades)")
            }
            self.assertTrue({
                "order_hash", "order_status", "filled_value", "retry_count",
                "state_x", "state_x_active", "state_x_trigger_time",
                "state_x_end_time", "sx_trigger_reason",
            }.issubset(columns))
            self.assertFalse(
                migrated.control_row(STATE_X_CONTROL_KIND)["manual_enabled"]
            )
            self.assertIsNotNone(migrated.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='state_x_observations'"
            ).fetchone())
        finally:
            migrated.close()

    def test_no_shadow_or_external_ml_mode_and_new_ui_contract(self) -> None:
        tables = {
            row[0] for row in self.store.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertFalse(any("shadow" in name.lower() for name in tables))
        self.assertFalse(hasattr(Store, "record_shadow"))
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertFalse(any(
            name == "xgboost" or name.startswith("xgboost.")
            or name == "sklearn" or name.startswith("sklearn.")
            for name in imported
        ))
        self.assertEqual(CONTROLS_HTML.count('id="master"'), 1)
        self.assertIn('class="rangeBtn active" data-range="1D">24H', DASHBOARD_HTML)
        self.assertNotIn('data-range="ALL"', DASHBOARD_HTML)
        self.assertIn("var activePnlRange='1D'", DASHBOARD_HTML)
        self.assertIn("bookHeader", DASHBOARD_HTML)
        self.assertIn("sideTiles", DASHBOARD_HTML)
        self.assertIn("pnlStats", DASHBOARD_HTML)
        self.assertIn('id="lwchart"', DASHBOARD_HTML)
        self.assertIn('id="chartFallback"', DASHBOARD_HTML)
        self.assertEqual(DASHBOARD_HTML.count("function drawChart"), 1)
        self.assertIn("<th>Stake</th><th>P&amp;L</th>", DATA_HTML)
        header = self.store.export_csv().decode().splitlines()[0].split(",")
        self.assertEqual(header[-13:-11], ["stake", "pnl"])
        self.assertEqual(header[-11:], [
            "state_x", "state_x_active", "state_x_trigger_time",
            "state_x_end_time", "sx_late_metric_15m", "sx_late_p80_6h",
            "sx_aligned_1s_metric_15m", "sx_aligned_1s_p80_6h",
            "sx_rejection_balance", "sx_aligned_delta30_median_15m",
            "sx_trigger_reason",
        ])
        self.assertEqual(self.store.trade_summary()["range"], "1D")

    def test_protected_main_and_reversal_signal_sources_are_locked(self) -> None:
        expected = {
            "pressure_score": "4a0204f0c5c5ca945b39119e3d375d4331568b210a483f427e6855fb09f48f95",
            "pressure_text": "1b2ff2cbf2d276821e776905940d3699446c0383d892dfac822244c04544b5ee",
            "make_call": "e1d2dea70eccc01246239e386b8430724d8bff11942924e651b9701b6abe0bd5",
            "volume_factor": "ae53e59330aa7829950f3c8d9663b4e499cbd648adc7d8b5e2f2fb19212119b0",
            "rejection_factor": "17e55f535a39b1f7d6375a5ac19110c620448bf763ede9479dd4d90510267d9b",
            "runway_factor": "2e50d56d3d826802f349ad5486a2065bbcc382256c0651c4e2dc652313cdb62c",
            "feasibility_factor": "673be92b5ba50177072f1d496f17f2ac3d7589fa0fa83505eb3b917cec3c0fb9",
            # v8.1 GPT: this is the intended adaptive decision surface. The
            # cached multiplier changes only the legacy typical body supplied
            # to fair odds; the erf form, probability clamp, price floor and
            # sqrt(t) scaling remain unchanged. ADAPT_ENABLED=False and every
            # unproven/neutral regime return the v8 value bit for bit.
            "Engine._fair_odds": "fff7bb174ded6a70e1de5e18904090b12d1c2b96d4b702a982bc53f28f0549d9",
            # v8.1 GPT: the sampler call occurs immediately before fair odds
            # so the last completed second is available without a wait. It
            # only updates adaptive state. Every other locked signal method
            # below remains byte-identical to v8.
            "Engine._compute_features": "977452158e8e2ddbe01392e422bef978b401e18ba601ad8d47c7a8ecd533e5cf",
            "Engine._prediction_logic": "614fffc8e7419bc77e3a0cc26949821c3649861cf056000ca1a77f4f9ba3455c",
            # R5 restores the exact protected v8.1 GPT MAIN integration source.
            # MAIN/REV signal behavior is immutable here; R5 changes are isolated
            # to EF/execution/clock infrastructure.
            "Engine._try_main": "edcb7bd6dbdb4120f7cbfe904787edebaf709c586f40f326a4616eed526e7828",
            "Engine._emit_main": "8cd5c121d7106c155f364c93607476111332b6e59652968bdc87bf82820517d0",
            "Engine._watch_reversal": "a5315c77cbb2cf2668211611a61ece30ed09d0187b4f9ce87cdf5108bbf57736",
            "Engine._emit_reversal": "8642dfd49233b08c4d3f4b46301229cf4d7ca3c730ea640927accf6d3c00c131",
        }
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        found: Dict[str, Any] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[node.name] = node
            elif isinstance(node, ast.ClassDef) and node.name == "Engine":
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        found[f"Engine.{member.name}"] = member
        actual = {
            name: hashlib.sha256(
                (ast.get_source_segment(source, found[name]) or "").encode()
            ).hexdigest()
            for name in expected
        }
        self.assertEqual(actual, expected)

    def test_v72_individual_toggle_blocks_only_selected_stream(self) -> None:
        self.assertTrue(self.controls.apply_change(manual_enabled=True)["ok"])
        result = self.controls.apply_signal_toggle("REVERSAL", False)
        self.assertTrue(result["ok"])
        allowed, why = self.controls.may_execute("REVERSAL")
        self.assertFalse(allowed)
        self.assertIn("manually OFF", why)
        self.assertTrue(self.controls.may_execute("EF")[0])
        # MAIN may be inside its configured clock ban, so assert the persistent
        # individual preference directly rather than depending on wall clock.
        self.assertTrue(self.controls.state("MAIN")["manual_enabled"])
        self.assertFalse(self.controls.state("REVERSAL")["manual_enabled"])

    def test_v72_individual_off_is_forbidden_blue_f_and_still_grades(self) -> None:
        engine = Engine(self.store)
        self.assertTrue(engine.controls.apply_change(manual_enabled=True)["ok"])
        self.assertTrue(engine.controls.apply_signal_toggle("EF", False)["ok"])
        prediction = self._prediction("EF", direction="DOWN")
        with mock.patch.object(engine.book, "quote", return_value={
            "price": 0.44, "spread": 0.02, "size": 400.0,
            "break_even": 0.4488, "fee_rate": 0.02, "age_ms": 120,
            "market_id": "m", "market_title": "t",
        }):
            engine._record_trade(prediction, "EF")
        before = self.store.recent_orders("EF")["rows"][0]
        self.assertTrue(before["forbidden"])
        self.assertEqual(before["status"], "F")
        self.assertIn("manually OFF", before["failure_reason"])
        # Prediction settlement remains independent from execution permission.
        self.store.settle_candle(self._closed(self.cid, up=False))
        self.store.settle_trades(self.cid, "DOWN")
        after = self.store.recent_orders("EF")["rows"][0]
        marker = [m for m in self.store.markers() if m["kind"] == "EF"][0]
        self.assertTrue(after["forbidden"])
        self.assertEqual(after["status"], "F")
        self.assertTrue(after["correct"])
        self.assertTrue(marker["signals_off"])
        self.assertNotIn("'F'", re.search(
            r"function markerText\(marker\)\{[^\n]+", DASHBOARD_HTML
        ).group(0))
        self.assertIn("m.signals_off?'#60a5fa'", DASHBOARD_HTML)

    def test_v72_signal_off_linearizes_against_live_submit_gate(self) -> None:
        self.controls.apply_change(manual_enabled=True)
        finished = threading.Event()
        results: List[Dict[str, Any]] = []

        def turn_off() -> None:
            results.append(self.controls.apply_signal_toggle("EF", False))
            finished.set()

        with self.controls.submit_gate:
            worker = threading.Thread(target=turn_off)
            worker.start()
            self.assertFalse(
                finished.wait(0.05),
                "OFF must not acknowledge while a live submission owns submit_gate",
            )
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        self.assertTrue(finished.is_set())
        self.assertTrue(results and results[0]["ok"])
        self.assertFalse(self.controls.state("EF")["manual_enabled"])
        self.assertFalse(self.controls.may_execute("EF")[0])

    def test_v72_individual_choices_persist_but_master_restarts_off(self) -> None:
        other = Path(self.temporary.name) / "v72-toggle-persist.sqlite3"
        first = Store(other)
        first_controls = TradeControls(first)
        try:
            self.assertTrue(all(
                first.control_row(kind)["manual_enabled"] for kind in TRADE_KINDS
            ))
            first_controls.apply_change(manual_enabled=True)
            first_controls.apply_signal_toggle("EF", False)
            self.assertTrue(first.control_row(SYSTEM_CONTROL_KIND)["manual_enabled"])
            self.assertFalse(first.control_row("EF")["manual_enabled"])
        finally:
            first.close()

        second = Store(other)
        try:
            self.assertFalse(
                second.control_row(SYSTEM_CONTROL_KIND)["manual_enabled"],
                "MASTER must still fail safe OFF on every process launch",
            )
            self.assertTrue(second.control_row("MAIN")["manual_enabled"])
            self.assertTrue(second.control_row("REVERSAL")["manual_enabled"])
            self.assertFalse(
                second.control_row("EF")["manual_enabled"],
                "individual user choice must survive restart",
            )
        finally:
            second.close()

    def test_v72_controls_ui_has_small_individual_toggles(self) -> None:
        self.assertIn("miniToggle", CONTROLS_HTML)
        self.assertIn("data-kind-toggle", CONTROLS_HTML)
        self.assertIn("bindSignalToggles", CONTROLS_HTML)
        self.assertIn("/api/controls/signal", CONTROLS_HTML)
        self.assertIn("Master controls all new real orders", CONTROLS_HTML)

    def test_v73_subcent_sdk_quantization_is_not_no_liquidity(self) -> None:
        # The exact regression family: a $2.57 cent-precision stake may become
        # microscopically/sub-cent smaller after SDK integer amount math.
        self.assertTrue(_full_shared_stake_available(2.57, 2.5700000000))
        self.assertTrue(_full_shared_stake_available(2.57, 2.5699999990))
        self.assertTrue(_full_shared_stake_available(2.57, 2.5660000000))
        self.assertTrue(_full_shared_stake_available(2.57, 2.5650000000))

        # Anything beyond half a cent is a genuine stake shortage and still
        # fails closed. The old thin-book $10 -> $6 case must stay blocked.
        self.assertFalse(_full_shared_stake_available(2.57, 2.5649000000))
        self.assertFalse(_full_shared_stake_available(2.57, 2.5600000000))
        self.assertFalse(_full_shared_stake_available(10.00, 6.00))
        self.assertFalse(_full_shared_stake_available(2.57, float("nan")))

    def test_v74_predict_intenum_order_fields_serialize_as_ints(self) -> None:
        from dataclasses import dataclass
        from enum import IntEnum

        class SideWire(IntEnum):
            BUY = 0
            SELL = 1

        class SignatureWire(IntEnum):
            EOA = 0

        @dataclass
        class SignedOrderWire:
            salt: str
            maker: str
            signer: str
            taker: str
            token_id: str
            maker_amount: str
            taker_amount: str
            expiration: str
            nonce: str
            fee_rate_bps: str
            side: SideWire
            signature_type: SignatureWire
            signature: str
            hash: str

        wire = _plain_json(SignedOrderWire(
            salt="1",
            maker="0x1111111111111111111111111111111111111111",
            signer="0x1111111111111111111111111111111111111111",
            taker="0x0000000000000000000000000000000000000000",
            token_id="123",
            maker_amount="2570000000000000000",
            taker_amount="4000000000000000000",
            expiration="0",
            nonce="0",
            fee_rate_bps="0",
            side=SideWire.BUY,
            signature_type=SignatureWire.EOA,
            signature="0xabc",
            hash="0xdef",
        ))

        self.assertEqual(wire["side"], 0)
        self.assertEqual(wire["signatureType"], 0)
        self.assertIs(type(wire["side"]), int)
        self.assertIs(type(wire["signatureType"]), int)
        self.assertEqual(wire["makerAmount"], "2570000000000000000")
        self.assertEqual(wire["tokenId"], "123")
        self.assertNotEqual(wire["side"], {})
        self.assertNotEqual(wire["signatureType"], {})

        encoded = json.dumps({"data": {"order": wire}}, separators=(",", ":"))
        decoded = json.loads(encoded)
        self.assertEqual(decoded["data"]["order"]["side"], 0)
        self.assertEqual(decoded["data"]["order"]["signatureType"], 0)

    def test_v74_plain_json_keeps_nested_camel_case(self) -> None:
        from enum import IntEnum

        class E(IntEnum):
            ZERO = 0
            ONE = 1

        payload = _plain_json({
            "outer_key": {
                "side": E.ZERO,
                "signature_type": E.ONE,
                "maker_amount": "10",
            }
        })
        self.assertEqual(payload, {
            "outerKey": {
                "side": 0,
                "signatureType": 1,
                "makerAmount": "10",
            }
        })

    def test_v75_rejects_15m_child_even_if_parent_is_5m(self) -> None:
        common = {
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "marketVariant": "CRYPTO_UP_DOWN",
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
            "_category_title": "Bitcoin Up or Down",
            "_category_slug": f"btc-updown-{self.cid // 1000}",
            "_category_starts_at": iso_utc(self.cid),
            "_category_ends_at": iso_utc(self.cid + CANDLE_MS),
        }
        fifteen = dict(
            common,
            id=150,
            title="Bitcoin Up or Down - August 15, 12AM-12:15AM ET",
        )
        five = dict(
            common,
            id=5,
            title="Bitcoin Up or Down - August 15, 12AM-12:05AM ET",
        )
        ranked = PredictBook._rank_markets([fifteen, five], self.cid)
        self.assertEqual([row["id"] for row in ranked], [5])

    def test_v75_accepts_cross_midnight_5m_title(self) -> None:
        item = {
            "id": 55,
            "title": "Bitcoin Up or Down - August 14, 11:55PM-12AM ET",
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "marketVariant": "CRYPTO_UP_DOWN",
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
            "_category_title": "Bitcoin Up or Down",
            "_category_slug": f"btc-updown-{self.cid // 1000}",
            "_category_starts_at": iso_utc(self.cid),
            "_category_ends_at": iso_utc(self.cid + CANDLE_MS),
        }
        ranked = PredictBook._rank_markets([item], self.cid)
        self.assertEqual([row["id"] for row in ranked], [55])

    def test_v75_own_15m_times_override_misleading_5m_text(self) -> None:
        item = {
            "id": 15,
            "title": "Bitcoin Up or Down - 5 minutes",
            "categorySlug": f"btc-updown-5m-{self.cid // 1000}",
            "startsAt": iso_utc(self.cid),
            "endsAt": iso_utc(self.cid + 3 * CANDLE_MS),
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "marketVariant": "CRYPTO_UP_DOWN",
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
        }
        self.assertEqual(PredictBook._rank_markets([item], self.cid), [])

    def test_v76_three_retries_means_four_total_terminal_attempts(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade("MAIN", future, status="QUEUED")
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        self._fresh_wallet(executor)
        executor.book.market_candle_id = future
        executor.book._current_market = {
            "id": 7600,
            "title": "Bitcoin Up or Down - 5 minutes",
            "startsAt": iso_utc(future),
            "endsAt": iso_utc(future + CANDLE_MS),
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "marketVariant": "CRYPTO_UP_DOWN",
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
        }
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(
            executor.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(
            executor, "_attempt",
            side_effect=["TERMINAL", "TERMINAL", "TERMINAL", "TERMINAL"],
        ) as attempt:
            executor._execute(prediction, "MAIN")

        self.assertEqual(PREDICT_ORDER_MAX_RETRIES, 3)
        self.assertEqual(attempt.call_count, 4)
        self.assertEqual(
            [call.args[3] for call in attempt.call_args_list],
            [1, 2, 3, 4],
        )

    # ---- v7.7: unredeemed winnings ------------------------------------
    def test_v77_settled_win_is_capital_before_the_claim_lands(self) -> None:
        """The core v7.7 bug: auto-claim lag made the bankroll look smaller."""
        self.store.set_live_wallet_balance(100.0)
        self.assertEqual(self.store.capital_state()["balance"], 100.0)

        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")

        # The wallet has not been re-read, so it still shows the pre-payout
        # figure. v7.6 sized from 100.00 here; v7.7 sizes from 125.00.
        capital = self.store.capital_state()
        self.assertEqual(capital["wallet"], 100.0)
        self.assertEqual(capital["pending_payout"], 25.0)
        self.assertEqual(capital["balance"], 125.0)
        # Funding authority is untouched: shares cannot pay for an order.
        self.assertEqual(capital["wallet_free"], 100.0)

    def test_v77_claim_is_retired_when_the_usdt_actually_arrives(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        self.assertEqual(self.store.pending_payout_usd(), 25.0)

        # Auto-claim completes; the same money must not be counted twice.
        self.store.set_live_wallet_balance(125.0)
        capital = self.store.capital_state()
        self.assertEqual(capital["pending_payout"], 0.0)
        self.assertEqual(capital["wallet"], 125.0)
        self.assertEqual(capital["balance"], 125.0)

    def test_v77_partial_credit_leaves_only_the_remainder_pending(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        self.store.set_live_wallet_balance(110.0)
        self.assertAlmostEqual(self.store.pending_payout_usd(), 15.0, places=6)
        self.assertEqual(self.store.capital_state()["balance"], 125.0)

    def test_v77_a_loss_never_creates_a_claim(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, direction="DOWN", filled=True,
                    stake=10.0, fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        self.assertEqual(self.store.pending_payout_usd(), 0.0)
        self.assertEqual(self.store.capital_state()["balance"], 100.0)

    def test_v77_unfilled_win_creates_no_claim(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=False, status="NOT_SENT")
        self.store.settle_trades(self.cid, "UP")
        self.assertEqual(self.store.pending_payout_usd(), 0.0)

    def test_v77_stale_claim_expires_and_cannot_inflate_capital(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        self.assertEqual(self.store.pending_payout_usd(), 25.0)
        stale = now_ms() - int(PREDICT_CLAIM_TTL_SEC * 1000.0) - 1_000
        with self.store.lock:
            self.store.db.execute(
                "UPDATE payout_claims SET settled_ms=?", (stale,)
            )
            self.store.db.commit()
        self.assertEqual(self.store.pending_payout_usd(), 0.0)
        self.assertEqual(self.store.capital_state()["balance"], 100.0)

    def test_v77_streak_recalculation_compounds_from_unclaimed_winnings(
        self,
    ) -> None:
        config = dict(DEFAULT_STAKE_CONFIG)
        config.update({
            "mode": STAKE_MODE_STREAK, "percent": 10.0,
            "win_trigger": 1, "loss_trigger": 2,
            "current_stake": 10.0, "min_stake": 1.0, "max_stake": 50.0,
        })
        self.assertTrue(self.controls.apply_change(stake=config)["ok"])
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")

        result = self.controls.record_result("MAIN_REV", True)
        self.assertTrue(result["recalculated"])
        # 10% of 125.00, not 10% of the stale 100.00 wallet reading.
        self.assertEqual(result["current_stake"], 12.5)

    def test_v77_ledger_and_venue_agree_when_nothing_is_unexplained(
        self,
    ) -> None:
        self.store.set_live_wallet_balance(100.0)
        self.assertTrue(self.store.capital_state()["truth"]["anchored"])
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        # Collateral has left the wallet and become an open position.
        self.store.set_live_wallet_balance(90.0)
        self.store.settle_trades(self.cid, "UP")
        self.store.set_live_wallet_balance(115.0)
        truth = self.store.capital_state()["truth"]
        self.assertEqual(truth["ledger_delta"], 15.0)
        self.assertEqual(truth["venue_delta"], 15.0)
        self.assertEqual(truth["unexplained"], 0.0)

    # ---- v7.7: retry latency is a total, not the last attempt ----------
    def _latency_executor(self) -> LiveExecutor:
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            return LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )

    @staticmethod
    def _accepting_response() -> Dict[str, Any]:
        return {"data": {"orderId": "1", "orderHash": "0xlatency"}}

    def test_v77_delay_ms_is_the_total_not_the_last_retry(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade("MAIN", future, status="QUEUED")
        executor = self._latency_executor()
        # This order first went out 900ms ago; only the replacement succeeds.
        origin = now_ms() - 900
        with mock.patch.object(
            executor, "_build_payload",
            return_value=("0xlatency", {}, {"price": 0.40}),
        ), mock.patch.object(
            executor, "_submit_signed_order",
            return_value=(
                "RESPONSE", 200,
                {"data": {"orderId": "1", "orderHash": "0xlatency"}},
            ),
        ), mock.patch.object(
            executor, "_wait_for_state", return_value="FILLED"
        ):
            executor._attempt(prediction, "MAIN", 10.0, 2, [], origin)

        row = self.store.trade_row(future, "MAIN") or {}
        self.assertGreaterEqual(int(row["delay_ms"]), 900)
        # v7.6 reported only this figure and called it the order's latency.
        self.assertLess(int(row["last_attempt_ms"]), 500)
        self.assertLess(int(row["last_attempt_ms"]), int(row["delay_ms"]))

    def test_v77_reconciler_retry_recovers_the_journalled_origin(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade("MAIN", future, status="QUEUED")
        origin = now_ms() - 1_400
        self.store.update_trade_execution(
            future, "MAIN", first_submit_ms=origin
        )
        executor = self._latency_executor()
        with mock.patch.object(
            executor, "_build_payload",
            return_value=("0xlate", {}, {"price": 0.40}),
        ), mock.patch.object(
            executor, "_submit_signed_order",
            return_value=(
                "RESPONSE", 200,
                {"data": {"orderId": "2", "orderHash": "0xlate"}},
            ),
        ), mock.patch.object(
            executor, "_wait_for_state", return_value="FILLED"
        ):
            # No caller-supplied origin: this is the _reconcile_unknowns path.
            executor._attempt(prediction, "MAIN", 10.0, 3, [])

        row = self.store.trade_row(future, "MAIN") or {}
        self.assertGreaterEqual(int(row["delay_ms"]), 1_400)

    def test_v77_first_submit_ms_survives_every_replacement(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade("MAIN", future, status="QUEUED")
        executor = self._latency_executor()
        origin = now_ms() - 600
        seen: List[int] = []

        def capture(*args: Any, **_kwargs: Any) -> Tuple[str, None, None]:
            seen.append(int(args[9]))
            self.store.update_trade_execution(
                future, "MAIN", first_submit_ms=int(args[9])
            )
            return "BLOCKED", None, None

        with mock.patch.object(
            executor, "_build_payload",
            return_value=("0xkeep", {}, {"price": 0.40}),
        ), mock.patch.object(
            executor, "_submit_signed_order", side_effect=capture
        ):
            executor._attempt(prediction, "MAIN", 10.0, 1, [], origin)
            executor._attempt(prediction, "MAIN", 10.0, 2, [], origin)
            executor._attempt(prediction, "MAIN", 10.0, 3, [])

        self.assertEqual(seen, [origin, origin, origin])

    def test_v77_schema_and_dashboard_expose_the_new_figures(self) -> None:
        with self.store.lock:
            columns = {
                row["name"] for row in
                self.store.db.execute("PRAGMA table_info(trades)").fetchall()
            }
            tables = {
                row[0] for row in self.store.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertIn("first_submit_ms", columns)
        self.assertIn("last_attempt_ms", columns)
        self.assertIn("payout_claims", tables)
        for marker in ("capBalance", "capPending", "openPos", "capTruth", "Last try"):
            self.assertIn(marker, DASHBOARD_HTML + DATA_HTML)
        # v7.8: `el` is the global element-lookup helper. A local named `el`
        # inside updateUI hoists and shadows it for the whole function, which
        # broke every text()/cls() call and blanked the dashboard.
        body = DASHBOARD_HTML[DASHBOARD_HTML.find("function updateUI"):]
        self.assertNotIn("var el=", body)
        self.assertIn("var controls=live.controls", DASHBOARD_HTML)

    # ---- v7.8: venue positions ----------------------------------------
    @staticmethod
    def _venue_position(shares_wei, price, value, pnl, status=None,
                        outcome="Yes", market_id="4242"):
        """A GET /v1/positions entry in the documented response shape."""
        return {
            "id": f"pos-{outcome}-{market_id}",
            "amount": str(shares_wei),
            "valueUsd": str(value),
            "averageBuyPriceUsd": str(price),
            "pnlUsd": str(pnl),
            "market": {"id": int(market_id), "title": "Bitcoin Up or Down",
                       "conditionId": "0xcond", "status": "REGISTERED"},
            "outcome": {"name": outcome, "indexSet": 1, "onChainId": "9",
                        "status": status,
                        "bestBid": {"price": 0.44, "size": 120.0},
                        "bestAsk": {"price": 0.46, "size": 90.0}},
        }

    def _executor(self) -> LiveExecutor:
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            ex = LiveExecutor(self.store, self.controls,
                              PredictBook(testnet=False), threading.Event())
        ex.predict_account = "0x" + "ab" * 20
        return ex

    def test_v78_positions_parse_the_documented_response_shape(self) -> None:
        executor = self._executor()
        page = {"success": True, "data": [
            self._venue_position(25 * 10**18, 0.40, 11.25, 1.25)
        ]}
        with mock.patch.object(executor, "_request", return_value=(200, page)):
            ok, error = executor.refresh_positions()
        self.assertTrue(ok, error)
        open_positions = self.store.venue_open_positions()
        self.assertEqual(len(open_positions), 1)
        row = open_positions[0]
        # amount is a bigint string in base units, not a share count
        self.assertAlmostEqual(row["shares"], 25.0, places=6)
        self.assertEqual(row["buy_price"], 0.40)
        self.assertEqual(row["used_usd"], 10.0)
        self.assertEqual(row["pnl_usd"], 1.25)

    def test_v78_won_position_is_venue_backed_unredeemed_money(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        executor = self._executor()
        page = {"success": True, "data": [
            self._venue_position(25 * 10**18, 0.40, 25.0, 15.0, status="WON")
        ]}
        with mock.patch.object(executor, "_request", return_value=(200, page)):
            self.assertTrue(executor.refresh_positions()[0])

        capital = self.store.capital_state()
        self.assertEqual(capital["pending_source"], "PREDICT_FUN_POSITIONS")
        self.assertEqual(capital["pending_payout"], 25.0)
        self.assertEqual(capital["wallet"], 100.0)
        self.assertEqual(capital["balance"], 125.0)
        # A resolved position is no longer marked to a book.
        self.assertEqual(capital["open_position_value"], 0.0)
        self.assertEqual(self.store.venue_open_positions(), [])

    def test_v78_venue_view_overrides_the_inferred_claim_ledger(self) -> None:
        """The v7.7 inference must not be a second opinion once truth exists."""
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        self.assertEqual(self.store.capital_state()["pending_payout"], 25.0)

        executor = self._executor()
        # The venue says the payout has already been redeemed: nothing held.
        with mock.patch.object(
            executor, "_request", return_value=(200, {"success": True, "data": []})
        ):
            self.assertTrue(executor.refresh_positions()[0])
        capital = self.store.capital_state()
        self.assertEqual(capital["pending_source"], "PREDICT_FUN_POSITIONS")
        self.assertEqual(capital["pending_payout"], 0.0)
        self.assertEqual(capital["balance"], 100.0)

    def test_v78_stale_positions_fall_back_to_the_inferred_ledger(self) -> None:
        self.store.set_live_wallet_balance(100.0)
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        executor = self._executor()
        with mock.patch.object(
            executor, "_request", return_value=(200, {"success": True, "data": []})
        ):
            executor.refresh_positions()
        stale = now_ms() - int(PREDICT_POSITIONS_STALE_SEC * 1000.0) - 5_000
        with self.store.lock:
            self.store.db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                ("v78_positions_checked_ms", str(stale)),
            )
            self.store.db.commit()
        capital = self.store.capital_state()
        self.assertEqual(capital["pending_source"], "INFERRED_CLAIM_LEDGER")
        self.assertEqual(capital["pending_payout"], 25.0)

    def test_v78_equity_never_becomes_fundable_capital(self) -> None:
        """Item 19: an open position cannot pay for the next order."""
        self.store.set_live_wallet_balance(50.0)
        executor = self._executor()
        page = {"success": True, "data": [
            self._venue_position(30 * 10**18, 0.50, 18.0, 3.0)
        ]}
        with mock.patch.object(executor, "_request", return_value=(200, page)):
            self.assertTrue(executor.refresh_positions()[0])
        capital = self.store.capital_state()
        self.assertEqual(capital["open_position_value"], 18.0)
        self.assertEqual(capital["equity"], 68.0)
        # Sizing and funding both exclude the live mark of an open position.
        self.assertEqual(capital["balance"], 50.0)
        self.assertEqual(capital["wallet_free"], 50.0)

    def test_v78_partial_page_set_never_deletes_real_positions(self) -> None:
        executor = self._executor()
        page = {"success": True, "data": [
            self._venue_position(25 * 10**18, 0.40, 11.0, 1.0)
        ]}
        with mock.patch.object(executor, "_request", return_value=(200, page)):
            self.assertTrue(executor.refresh_positions()[0])
        self.assertEqual(len(self.store.venue_open_positions()), 1)
        with mock.patch.object(executor, "_request", return_value=(500, {})):
            ok, error = executor.refresh_positions()
        self.assertFalse(ok)
        self.assertIn("500", error)
        # A failed refresh leaves the last good view in place.
        self.assertEqual(len(self.store.venue_open_positions()), 1)

    def test_v78_position_is_matched_to_its_signal(self) -> None:
        self._trade("MAIN", self.cid, direction="UP", filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        with self.store.lock:
            self.store.db.execute(
                "UPDATE trades SET market_id='4242' WHERE candle_id=?",
                (self.cid,),
            )
            self.store.db.commit()
        executor = self._executor()
        page = {"success": True, "data": [
            self._venue_position(25 * 10**18, 0.40, 11.0, 1.0)
        ]}
        with mock.patch.object(executor, "_request", return_value=(200, page)):
            self.assertTrue(executor.refresh_positions()[0])
        row = self.store.venue_open_positions()[0]
        self.assertEqual(row["kind"], "MAIN")
        self.assertEqual(row["direction"], "UP")

    def test_v78_leg_pnl_splits_by_signal(self) -> None:
        self._trade("MAIN", self.cid, filled=True, stake=10.0,
                    fill_price=0.40, shares=25.0)
        self.store.settle_trades(self.cid, "UP")
        legs = self.store.leg_pnl()
        self.assertEqual(legs["MAIN"]["settled"], 1)
        self.assertEqual(legs["MAIN"]["wins"], 1)
        self.assertEqual(legs["REVERSAL"]["settled"], 0)

    def test_v78_fresh_database_seeds_the_first_stake_from_the_venue(
        self,
    ) -> None:
        """A clean run must size stake 1 from Predict.fun, not a stored value."""
        fresh_path = Path(self.temporary.name) / "fresh-start.sqlite3"
        store = Store(fresh_path)
        try:
            controls = TradeControls(store)
            config = dict(DEFAULT_STAKE_CONFIG)
            config.update({"mode": STAKE_MODE_STREAK, "percent": 10.0,
                           "min_stake": 1.0, "max_stake": 50.0})
            self.assertTrue(controls.apply_change(stake=config)["ok"])
            # Nothing has been traded, so no stake has been earned yet.
            store.set_live_wallet_balance(35.12)
            seeded = store.control_row(SYSTEM_CONTROL_KIND)["stake"]
            self.assertEqual(seeded["current_stake"], 3.51)
            self.assertEqual(store.capital_state()["wallet"], 35.12)
        finally:
            store.close()

    def test_v78_reset_archives_rather_than_deletes(self) -> None:
        base = Path(self.temporary.name) / "archive-me.sqlite3"
        store = Store(base)
        store.close()
        (base.parent / "orders_v13.csv").write_text("utc,key\n")
        lines = archive_run_data(base)
        self.assertFalse(base.exists())
        backups = list(base.parent.glob("archive-me.sqlite3.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(list(base.parent.glob("orders_v13.csv.*.bak")))
        self.assertTrue(any("seeded from the live" in ln for ln in lines))

    def test_v78_reset_then_reseeds_against_a_new_balance(self) -> None:
        base = Path(self.temporary.name) / "reseed.sqlite3"
        first = Store(base)
        TradeControls(first).apply_change(stake=dict(
            DEFAULT_STAKE_CONFIG, mode=STAKE_MODE_STREAK, percent=10.0,
            min_stake=1.0, max_stake=50.0))
        first.set_live_wallet_balance(200.0)
        self.assertEqual(
            first.control_row(SYSTEM_CONTROL_KIND)["stake"]["current_stake"],
            20.0)
        first.close()

        archive_run_data(base)
        second = Store(base)
        try:
            TradeControls(second).apply_change(stake=dict(
                DEFAULT_STAKE_CONFIG, mode=STAKE_MODE_STREAK, percent=10.0,
                min_stake=1.0, max_stake=50.0))
            # The old $20 stake must not survive the reset.
            second.set_live_wallet_balance(35.12)
            self.assertEqual(
                second.control_row(SYSTEM_CONTROL_KIND)["stake"]["current_stake"],
                3.51)
        finally:
            second.close()

    # ---- London wall clock --------------------------------------------
    def test_london_display_is_independent_of_the_host_clock(self) -> None:
        """A VPS set to any timezone must render the same London time."""
        winter = int(datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
                     .timestamp() * 1000)
        summer = int(datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
                     .timestamp() * 1000)
        # GMT in winter, BST in summer - a fixed offset would be wrong for
        # half the year.
        self.assertEqual(london_stamp(winter), "2026-01-15 12:00:00.000")
        self.assertEqual(london_stamp(summer), "2026-08-15 13:00:00.000")
        self.assertEqual(london_label(winter), "GMT")
        self.assertEqual(london_label(summer), "BST")

    def test_london_runtime_format_is_mm_dd_hh_mm_ss(self) -> None:
        summer = int(datetime(2026, 8, 15, 23, 30, tzinfo=timezone.utc)
                     .timestamp() * 1000)
        # BST pushes this past midnight, so the date must roll too.
        self.assertEqual(london_runtime(summer), "08/16/00/30/00")

    def test_builtin_uk_clock_matches_tzdata_including_both_switches(
        self,
    ) -> None:
        """The no-tzdata fallback must not be an approximation.

        Termux ships without the IANA database, so this path is what actually
        runs there. It is validated against zoneinfo when zoneinfo is usable,
        and skipped rather than silently passing when it is not.
        """
        try:
            from zoneinfo import ZoneInfo

            real = ZoneInfo("Europe/London")
            probe = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
            if probe.astimezone(real).utcoffset() != timedelta(hours=1):
                self.skipTest("tzdata unavailable, nothing to compare against")
        except Exception:
            self.skipTest("tzdata unavailable, nothing to compare against")

        clock = _UKClock()
        checks = [
            datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
            datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
            # Both sides of each switch, including the repeated autumn hour.
            datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 25, 1, 59, tzinfo=timezone.utc),
        ]
        for moment in checks:
            self.assertEqual(
                moment.astimezone(clock).strftime("%Y-%m-%d %H:%M %Z"),
                moment.astimezone(real).strftime("%Y-%m-%d %H:%M %Z"),
                f"built-in UK clock disagrees with tzdata at {moment}",
            )

    # ---- remote dashboard access ---------------------------------------
    def test_app_actually_binds_the_requested_host(self) -> None:
        """main() passes --host to App, so App must accept and use it.

        Nothing else in the suite constructs App, which is how a signature
        mismatch here reached a live VPS and crash-looped the service.
        """
        import inspect

        signature = inspect.signature(App.__init__)
        self.assertIn("host", signature.parameters)
        source = inspect.getsource(App.__init__)
        self.assertIn("DashboardServer(\n            (host, port)", source)
        self.assertNotIn('DashboardServer(("127.0.0.1", port)', source)

        database = Path(self.temporary.name) / "bind-check.sqlite3"
        app = App(database, 0, "127.0.0.1")
        try:
            self.assertEqual(app.host, "127.0.0.1")
            self.assertEqual(app.server.server_address[0], "127.0.0.1")
        finally:
            app.server.server_close()
            app.store.close()

    def test_public_bind_is_refused_without_a_password(self) -> None:
        """Item: reachable from anywhere, but never unguarded."""
        self.assertIn("BTC_MODEL_PASSWORD", check_exposure("0.0.0.0", ""))
        self.assertIn("too short", check_exposure("0.0.0.0", "short"))
        # A real password is accepted, and loopback never needs one.
        self.assertEqual(check_exposure("0.0.0.0", "x" * 24), "")
        self.assertEqual(check_exposure("127.0.0.1", ""), "")
        self.assertEqual(check_exposure("localhost", ""), "")

    def test_every_route_requires_the_password_when_set(self) -> None:
        engine = Engine(self.store)
        secret = "correct-horse-battery"
        with mock.patch(f"{__name__}.DASHBOARD_PASSWORD", secret):
            server = DashboardServer(("127.0.0.1", 0), engine, self.store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                good = base64.b64encode(f"x:{secret}".encode()).decode()
                bad = base64.b64encode(b"x:wrong").decode()
                # A POST is as dangerous as the page: it can flip the master
                # switch, so it must be gated too.
                for path, data in (("/", None), ("/controls", None),
                                   ("/api/state", None), ("/data", None),
                                   ("/api/controls", b"{}")):
                    for header, expect in ((None, 401), (bad, 401), (good, 200)):
                        request = urllib.request.Request(base + path, data=data)
                        if header:
                            request.add_header("Authorization", "Basic " + header)
                        try:
                            with urllib.request.urlopen(request, timeout=5) as r:
                                status = r.status
                        except urllib.error.HTTPError as exc:
                            status = exc.code
                        if expect == 401:
                            self.assertEqual(
                                status, 401,
                                f"{path} was reachable without the password")
                        else:
                            self.assertNotEqual(
                                status, 401,
                                f"{path} rejected the correct password")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)

    def test_loopback_default_needs_no_password(self) -> None:
        engine = Engine(self.store)
        with mock.patch(f"{__name__}.DASHBOARD_PASSWORD", ""):
            server = DashboardServer(("127.0.0.1", 0), engine, self.store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/api/state"
                with urllib.request.urlopen(url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)

    def test_iso_utc_stays_utc_because_it_is_a_wire_format(self) -> None:
        """Predict.fun startsAt/endsAt are UTC and are parsed back as UTC."""
        summer = int(datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
                     .timestamp() * 1000)
        self.assertEqual(iso_utc(summer), "2026-08-15 12:00:00.000")
        self.assertNotEqual(iso_utc(summer), london_stamp(summer))

    def test_ban_rules_follow_london_not_the_machine(self) -> None:
        # 15:30 UTC in August is 16:30 in London.
        summer = int(datetime(2026, 8, 17, 15, 30, tzinfo=timezone.utc)
                     .timestamp() * 1000)
        moment, label = local_moment(summer)
        self.assertEqual(moment.strftime("%H:%M"), "16:30")
        self.assertEqual(label, "BST")
        self.assertEqual(BAN_TIMEZONE, "london")

    def test_every_page_renders_compact_elapsed_runtime(self) -> None:
        for page in (DASHBOARD_HTML, DATA_HTML, CONTROLS_HTML):
            self.assertIn('id="runStamp"', page)
            self.assertIn("__UPTIME_SEC__", page)
            self.assertIn("function runtimeText", page)
            self.assertIn("runtime · ", page)
            self.assertIn("['y',31536000]", page)
            self.assertIn("['mo',2592000]", page)
            self.assertIn("['d',86400]", page)
            self.assertIn("['h',3600]", page)
            self.assertIn("['m',60]", page)
            self.assertIn("['s',1]", page)
            self.assertIn("tickRuntime();", page)
        self.assertNotIn("__BUILT_AT__", DASHBOARD_HTML)
        self.assertNotIn("__BUILT_AT__", DATA_HTML)
        self.assertNotIn("__BUILT_AT__", CONTROLS_HTML)

    def test_v76_unknown_still_never_creates_a_retry(self) -> None:
        future = candle_id_from_ms(now_ms() + CANDLE_MS)
        prediction = self._trade("EF", future, status="QUEUED")
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, self.controls, PredictBook(testnet=False),
                threading.Event(),
            )
        self._fresh_wallet(executor)
        executor.book.market_candle_id = future
        executor.book._current_market = {
            "id": 7601,
            "title": "Bitcoin Up or Down - 5 minutes",
            "startsAt": iso_utc(future),
            "endsAt": iso_utc(future + CANDLE_MS),
            "tradingStatus": "OPEN",
            "status": "REGISTERED",
            "isVisible": True,
            "marketVariant": "CRYPTO_UP_DOWN",
            "variantData": {
                "type": "CRYPTO_UP_DOWN",
                "priceFeedSymbol": "BTCUSDT",
            },
        }
        with mock.patch.object(
            self.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            executor, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(
            executor.book, "quote", return_value={"price": 0.4}
        ), mock.patch.object(
            executor, "_attempt", return_value="UNKNOWN"
        ) as attempt:
            executor._execute(prediction, "EF")

        self.assertEqual(attempt.call_count, 1)



class V911Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "v911.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_ef_adaptive_zero_evidence_control_transfer_is_exact_zero(self) -> None:
        row = ef_runway_v2(10, 0, 200, 2.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100)
        self.assertEqual(row["control_transfer"], 0.0)

    def test_ef_adaptive_floors_only_ratchet_up(self) -> None:
        certain = ef_adaptive_settlement(0, 0, 200, 2.0, 1.0, 100)
        uncertain = ef_adaptive_settlement(0, 0, 200, 2.0, 0.0, 0)
        self.assertEqual(certain["consensus_floor"], EF_CONS_BASE)
        self.assertEqual(certain["edge_floor"], EF_EDGE_BASE)
        self.assertGreaterEqual(uncertain["consensus_floor"], certain["consensus_floor"])
        self.assertGreaterEqual(uncertain["edge_floor"], certain["edge_floor"])
        # Actual probability floor is price-relative and therefore tested after
        # executable VWAP is known. With zero uncertainty it is exact break-even.
        g0 = ef_adaptive_price_gate(certain, 0.34)
        g1 = ef_adaptive_price_gate(uncertain, 0.34)
        self.assertAlmostEqual(g0["probability_floor"], 0.34 * (1.0 + PREDICT_FEE_RATE))
        self.assertGreaterEqual(g1["probability_floor"], g0["probability_floor"])

    def test_ef_adaptive_consensus_collapses_if_either_input_is_weak(self) -> None:
        weak_probability = math.sqrt(0.01 * 1.0)
        weak_control = math.sqrt(0.50 * 0.01)
        self.assertLess(weak_probability, EF_CONS_BASE)
        self.assertLess(weak_control, EF_CONS_BASE)

    def test_ef_adaptive_uncertainty_never_raises_quality(self) -> None:
        certain = ef_adaptive_settlement(0, 0, 200, 2.0, 0.60, 100)
        uncertain = ef_adaptive_settlement(0, 0, 200, 2.0, 0.60, 0)
        self.assertLessEqual(uncertain["quality"], certain["quality"])

    def test_ef_adaptive_consensus_uses_untilted_probability_once(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "ef_adaptive_settlement")
        segment = ast.get_source_segment(source, fn) or ""
        self.assertIn("settlement_probability_base * control", segment)
        self.assertNotIn("settlement_probability * control", segment)
        self.assertEqual(segment.count("settlement_probability_base * control"), 1)

    def test_ef_adaptive_four_quiet_regimes_all_abstain(self) -> None:
        regimes = [(0.6, 2.0, 0.48), (1.2, 4.0, 0.48),
                   (2.5, 9.0, 0.49), (6.0, 21.0, 0.49)]
        for sigma, move, price in regimes:
            row = ef_runway_v2(
                move, move, 200, sigma, 1.0, 0.3,
                0.52, 0.329, 0.50, 0.50, 0.20, 0.60, 0.40, 100
            )
            # Reachability is saturated and the tiny apparent edge can be
            # positive, but weak BTC evidence quality must still abstain.
            self.assertEqual(row["reachability"], 1.0)
            self.assertGreaterEqual(row["control_transfer"], 0.54)
            self.assertGreaterEqual(row["settlement_feasibility"], 0.56)
            gate = ef_adaptive_price_gate(row, price)
            self.assertFalse(gate["eligible"])
            self.assertLess(row["quality"], 0.59)

    def test_ef_adaptive_phase150_positive_edge_is_not_killed_by_max_price_floor(self) -> None:
        # Reproduces the audited failure shape: p=0.446, base=0.320, control~0.80,
        # $0.34 entry. Edge is +0.0992, so a max-price 0.51 belief floor must not
        # block an otherwise strong setup.
        evidence = {
            "settlement_probability": 0.446,
            "settlement_probability_base": 0.320,
            "ef_consensus": math.sqrt(0.320 * 0.80),
            "consensus_floor": EF_CONS_BASE,
            "edge_floor": EF_EDGE_BASE,
            "ef_uncertainty": 0.0,
            "runway_v2_score": 0.70,
        }
        gate = ef_adaptive_price_gate(evidence, 0.34)
        self.assertAlmostEqual(gate["expected_edge"], 0.446 - 0.34 * 1.02, places=9)
        self.assertLess(gate["probability_floor"], 0.446)
        self.assertTrue(gate["eligible"], gate["abstain_reason"])

    def test_ef_adaptive_negative_prediction_edge_cannot_veto_strong_btc(self) -> None:
        # Predict.fun economics are execution diagnostics only. A negative
        # diagnostic edge must not turn a BTC-qualified EF into an abstention.
        for probability, p_base in ((0.328, 0.219), (0.142, 0.080)):
            evidence = {
                "settlement_probability": probability,
                "settlement_probability_base": p_base,
                "ef_consensus": max(EF_CONS_BASE + 0.05, math.sqrt(p_base * 0.80)),
                "consensus_floor": EF_CONS_BASE,
                "edge_floor": EF_EDGE_BASE,
                "ef_uncertainty": 0.0,
                "runway_v2_score": 0.70,
            }
            gate = ef_adaptive_price_gate(evidence, 0.50)
            self.assertLess(gate["expected_edge"], 0.0)
            self.assertTrue(gate["eligible"], gate["abstain_reason"])
            self.assertNotIn("expected edge", gate["abstain_reason"])

    def test_ef_adaptive_cheap_positive_mispricing_is_not_rejected_at_051(self) -> None:
        evidence = {
            "settlement_probability": 0.45,
            "settlement_probability_base": 0.35,
            "ef_consensus": math.sqrt(0.35 * 0.80),
            "consensus_floor": EF_CONS_BASE,
            "edge_floor": EF_EDGE_BASE,
            "ef_uncertainty": 0.0,
            "runway_v2_score": 0.70,
        }
        gate = ef_adaptive_price_gate(evidence, 0.25)
        self.assertGreater(gate["expected_edge"], 0.19)
        self.assertLess(gate["probability_floor"], 0.30)
        self.assertTrue(gate["eligible"], gate["abstain_reason"])

    def test_predict_price_never_changes_btc_adaptive_eligibility(self) -> None:
        strong = {
            "settlement_probability": 0.56,
            "ef_consensus": EF_CONS_BASE + 0.08,
            "consensus_floor": EF_CONS_BASE,
            "edge_floor": EF_EDGE_BASE,
            "ef_uncertainty": 0.0,
            "runway_v2_score": 0.70,
        }
        weak = dict(strong, runway_v2_score=0.50)
        for price in (None, 0.01, 0.20, 0.50, 0.99):
            self.assertTrue(
                ef_adaptive_price_gate(strong, price)["eligible"],
                f"strong BTC setup was vetoed by Predict.fun price {price}",
            )
            self.assertFalse(
                ef_adaptive_price_gate(weak, price)["eligible"],
                f"weak BTC setup was rescued by Predict.fun price {price}",
            )

    def test_ef_watch_never_touches_predict_book_before_fire(self) -> None:
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        stamp = cid + 90_000
        engine.candle = {
            "time": cid, "open": 100000.0, "high": 100010.0,
            "low": 99990.0, "close": 100001.0, "volume": 1.0,
        }
        engine.feature = {"price": 100001.0}
        engine.ef_metrics = {
            "candidate_eligible": False, "inputs_ready": True, "direction": "UP",
            "reachability": 0.70, "control_transfer": 0.68,
            "settlement_feasibility": 0.66, "runway_v2_score": 0.64,
            "chop": 0.30, "delta_250ms": 0.70, "delta_1s": 0.40,
            "delta_2s": 0.30, "settlement_probability": 0.56,
            "ef_consensus": EF_CONS_BASE + 0.08, "consensus_floor": EF_CONS_BASE,
            "edge_floor": EF_EDGE_BASE, "ef_uncertainty": 0.0,
        }
        with mock.patch.object(
            engine.book, "executable_vwap",
            side_effect=AssertionError("Predict.fun book reached before EF fire"),
        ) as book_walk, mock.patch.object(
            engine.book, "quote",
            side_effect=AssertionError("Predict.fun quote reached before EF fire"),
        ) as quote_call, mock.patch.object(
            engine, "_emit_ef"
        ) as emit, mock.patch.object(
            self.store, "upsert_ef_candidate", return_value=None
        ):
            engine._watch_ef(stamp)
        book_walk.assert_not_called()
        quote_call.assert_not_called()
        emit.assert_called_once()
        args = emit.call_args.args
        self.assertEqual(args[1], "UP")
        self.assertEqual(args[3]["reason"], "EXECUTOR_PENDING")
        self.assertTrue(args[4])

    def test_ef_watch_has_no_fixed_ten_dollar_predict_gate(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        engine_class = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Engine"
        )
        method = next(
            n for n in engine_class.body
            if isinstance(n, ast.FunctionDef) and n.name == "_watch_ef"
        )
        segment = ast.get_source_segment(source, method) or ""
        self.assertNotIn("executable_vwap(direction, 10.0)", segment)
        self.assertNotIn("ef_adaptive_btc_gate(evidence)", segment)
        self.assertIn("EF_EARLY_SCORE_MIN", segment)
        self.assertIn("flow_acceleration", segment)
        self.assertEqual(segment.count("self.book.executable_vwap"), 0)
        self.assertNotIn("self.book.quote", segment)

    def test_over_50_predict_price_cannot_delay_or_veto_btc_ef_fire(self) -> None:
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        stamp = cid + 40_000
        engine.candle = {
            "time": cid, "open": 100000.0, "high": 100010.0,
            "low": 99990.0, "close": 100001.0, "volume": 1.0,
        }
        engine.feature = {"price": 100001.0}
        engine.ef_metrics = {
            "candidate_eligible": False, "inputs_ready": True, "direction": "DOWN",
            "reachability": 0.70, "control_transfer": 0.68,
            "settlement_feasibility": 0.66, "runway_v2_score": 0.64,
            "chop": 0.30, "delta_250ms": -0.70, "delta_1s": -0.40,
            "delta_2s": -0.30, "settlement_probability": 0.56,
            "ef_consensus": EF_CONS_BASE + 0.08, "consensus_floor": EF_CONS_BASE,
            "edge_floor": EF_EDGE_BASE, "ef_uncertainty": 0.0,
        }
        with mock.patch.object(
            engine.book, "executable_vwap",
            side_effect=AssertionError("price must be executor-only"),
        ), mock.patch.object(
            engine, "_emit_ef"
        ) as emit, mock.patch.object(
            self.store, "upsert_ef_candidate", return_value=None
        ):
            engine._watch_ef(stamp)
        emit.assert_called_once()
        self.assertEqual(emit.call_args.args[1], "DOWN")

    def test_ef_candidate_db_and_csv_include_declined_outcome(self) -> None:
        cid = candle_id_from_ms(now_ms()) - CANDLE_MS
        evidence = ef_adaptive_settlement(5, 5, 200, 1.2, 0.54, 100)
        gate = ef_adaptive_price_gate(evidence, 0.48)
        evidence.update(gate)
        features = {
            "ef_settlement_probability": evidence["settlement_probability"],
            "ef_settlement_probability_base": evidence["settlement_probability_base"],
            "ef_consensus": evidence["ef_consensus"],
            "ef_expected_edge": evidence["expected_edge"],
            "ef_probability_floor": evidence["probability_floor"],
            "ef_consensus_floor": evidence["consensus_floor"],
            "ef_edge_floor": evidence["edge_floor"],
            "ef_reference_vwap_10": 0.48,
            "ef_abstain_reason": gate["abstain_reason"],
        }
        self.store.upsert_ef_candidate(
            candle_id=cid, direction="UP", candidate_ts_ms=cid+1000,
            decision_ts_ms=cid+1000, price=100000.0, probability_up=0.515,
            fired=False, abstain_reason=gate["abstain_reason"],
            reference_vwap_10=0.48, evidence=evidence, features=features,
        )
        self.store.settle_candle({
            "time":cid,"open":100000.0,"high":100010.0,"low":99990.0,
            "close":99995.0,"volume":1.0,"close_time_ms":cid+CANDLE_MS-1,
        })
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT * FROM ef_candidates WHERE candle_id=?", (cid,)
            ).fetchone()
        self.assertEqual(row["actual"], "DOWN")
        self.assertEqual(int(row["fired"]), 0)
        csv_text = self.store.export_csv().decode("utf-8")
        self.assertIn("EF_CANDIDATE", csv_text)
        header = csv_text.splitlines()[0]
        for field in ("ef_settlement_probability", "ef_settlement_probability_base",
                      "ef_consensus", "ef_expected_edge", "ef_probability_floor",
                      "ef_consensus_floor", "ef_edge_floor",
                      "ef_reference_vwap_10", "ef_abstain_reason"):
            self.assertIn(field, header)

    def test_runway_v2_early_is_not_hard_blocked(self) -> None:
        weak = ef_runway_v2(20, 2, 275, 2.0, 1, 0.3, 0.05, 0.02, 0.2, 0.2, 0.4, 0.25, 0.65, 20)
        strong = ef_runway_v2(20, 8, 275, 2.0, 5, 2.0, 0.7, 0.6, 0.9, 0.8, 0.1, 0.95, 0.05, 20)
        self.assertGreater(strong["settlement_feasibility"], weak["settlement_feasibility"])
        self.assertGreater(strong["quality"], 0.59)

    def test_predict_price_is_execution_only_and_one_cent_is_valid(self) -> None:
        book = PredictBook(testnet=False)
        now = now_ms()
        with book._lock:
            book.ws_connected=True; book.ws_last_message_ms=now; book.status="live websocket"; book.book_ms=now
            book.book={"asks":[[0.01,2000.0]],"bids":[[0.98,2000.0]]}
        q=book.executable_vwap("UP",5.0)
        self.assertTrue(q["ok"])
        self.assertAlmostEqual(q["vwap"],0.01,places=9)
        self.assertLessEqual(q["vwap"],EF_MAX_SHARE_PRICE)

    def test_over_50c_is_financially_ineligible(self) -> None:
        book=PredictBook(testnet=False); now=now_ms()
        with book._lock:
            book.ws_connected=True; book.ws_last_message_ms=now; book.status="live websocket"; book.book_ms=now
            book.book={"asks":[[0.51,1000.0]],"bids":[[0.48,1000.0]]}
        q=book.executable_vwap("UP",5.0)
        self.assertTrue(q["ok"])
        self.assertGreater(q["vwap"],EF_MAX_SHARE_PRICE)

    def test_failed_unfilled_does_not_enter_financial_accuracy(self) -> None:
        cid=candle_id_from_ms(now_ms())-CANDLE_MS
        self.store.record_trade({"candle_id":cid,"kind":"EF","direction":"UP","ts_ms":cid+1000,
            "seconds_into_candle":1.0,"quoted_price":0.3,"filled":False,"attempts":1,
            "failure_reason":"failed","attempt_log":[],"forbidden":False,"execution_mode":"LIVE","order_status":"FAILED"})
        self.store.settle_trades(cid,"UP")
        self.assertEqual(self.store.metrics()["ef"]["total"],0)

    def test_financial_accuracy_uses_pnl_sign_not_directional_correctness(self) -> None:
        cid=candle_id_from_ms(now_ms())-CANDLE_MS
        self.store.record_trade({"candle_id":cid,"kind":"MAIN","direction":"UP","ts_ms":cid+1000,
            "seconds_into_candle":1.0,"quoted_price":0.8,"fill_price":0.8,"filled":True,"attempts":1,
            "stake":10.0,"shares":9.0,"fee_rate":0.0,"failure_reason":None,"attempt_log":[],
            "forbidden":False,"execution_mode":"LIVE","order_status":"FILLED"})
        # Direction is UP, but malformed economics deliberately make PnL negative; metric must follow PnL.
        self.store.settle_trades(cid,"UP")
        row=self.store.trade_row(cid,"MAIN")
        self.assertEqual(row["correct"],1)
        self.assertEqual(row["financial_result"],"LOSS")
        self.assertEqual(self.store.metrics()["main"]["wins"],0)

    def test_master_off_shadow_never_advances_streak(self) -> None:
        cid=candle_id_from_ms(now_ms())-CANDLE_MS
        self.store.record_trade({"candle_id":cid,"kind":"EF","direction":"UP","ts_ms":cid+1000,
            "seconds_into_candle":1.0,"quoted_price":0.2,"filled":False,"attempts":0,"stake":5.0,"shares":25.0,
            "fee_rate":0.02,"failure_reason":"SHADOW: master trading switch is manually OFF","attempt_log":[],
            "forbidden":False,"execution_mode":"SHADOW","order_status":"SHADOW","financial_is_shadow":True})
        emitted=self.store.settle_trades_and_report(cid,"UP")
        self.assertEqual(emitted,[])
        self.assertEqual(self.store.metrics()["ef"]["shadow"],1)

    def test_confirmed_fill_settles_even_if_lifecycle_label_lags(self) -> None:
        """Wallet-confirmed fill truth must outrank a stale QUEUED status label."""
        cid = candle_id_from_ms(now_ms()) - CANDLE_MS
        self.store.set_live_wallet_balance(100.0)
        self.store.record_trade({
            "candle_id": cid, "kind": "MAIN", "direction": "UP",
            "ts_ms": cid + 1000, "seconds_into_candle": 1.0,
            "quoted_price": 0.40, "fill_price": 0.40, "filled": True,
            "attempts": 1, "stake": 10.0, "shares": 25.0, "fee_rate": 0.0,
            "failure_reason": None, "attempt_log": [], "forbidden": False,
            "execution_mode": "LIVE", "order_status": "QUEUED",
        })
        self.store.settle_trades(cid, "UP")
        row = self.store.trade_row(cid, "MAIN")
        self.assertEqual(row["financial_result"], "WIN")
        self.assertEqual(self.store.metrics()["main"]["wins"], 1)
        self.assertAlmostEqual(self.store.pending_payout_usd(), 25.0)

    def test_history_result_is_financial_not_directional(self) -> None:
        cid = candle_id_from_ms(now_ms()) - CANDLE_MS
        pred = Prediction(cid, "MAIN", "UP", cid + 1000, 100000.0, 0.7, "audit", features={})
        self.store.add_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "MAIN", "direction": "UP",
            "ts_ms": cid + 1000, "seconds_into_candle": 1.0,
            "quoted_price": 0.80, "fill_price": 0.80, "filled": True,
            "attempts": 1, "stake": 10.0, "shares": 9.0, "fee_rate": 0.0,
            "failure_reason": None, "attempt_log": [], "forbidden": False,
            "execution_mode": "LIVE", "order_status": "FILLED",
        })
        self.store.settle_candle({
            "time": cid, "open": 100000.0, "high": 100010.0,
            "low": 99990.0, "close": 100005.0, "volume": 1.0,
            "close_time_ms": cid + CANDLE_MS - 1,
        })
        self.store.settle_trades(cid, "UP")
        history = self.store.settled_history(0, 10)["rows"]
        row = next(item for item in history if item["candle_id"] == cid)
        self.assertEqual(row["main"]["directional_correct"], 1)
        self.assertEqual(row["main"]["financial_result"], "LOSS")
        self.assertEqual(row["main"]["correct"], 0)

    def test_state_x_off_has_zero_execution_authority(self) -> None:
        sx=StateXProtection(self.store)
        sx.apply_toggle(False)
        p=Prediction(candle_id_from_ms(now_ms()),"EF","UP",now_ms(),100000,0.7,"sx")
        result=sx.observe_signal(p,{"return_1s_bps":-2,"return_250ms_bps":-1,"delta_1s":-1,"delta_5s":-1,"ofi_1s":-1000,"spot_imbalance5":-1})
        self.assertTrue(result["would_block"])
        self.assertFalse(result["blocked"])
        self.assertFalse(sx.execution_block()[0])

    def test_predict_fun_is_never_read_before_btc_ef_qualification(self) -> None:
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        engine.candle = {"time": cid, "open": 100000.0, "high": 100001.0,
                         "low": 99999.0, "close": 100000.0, "volume": 1.0}
        engine.feature = {"price": 100000.0}
        engine.ef_metrics = {
            "eligible": False, "direction": "UP",
            "blockers": ["BTC control transfer not strong enough"],
        }
        with mock.patch.object(
            engine.book, "executable_vwap", side_effect=AssertionError(
                "Predict.fun was consulted before BTC qualification"
            )
        ) as executable:
            engine._watch_ef(cid + 30_000)
        executable.assert_not_called()

        # Structural guard: the BTC evidence builder itself has no Predict.fun
        # book or execution-control dependency.
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Engine":
                method = next(
                    (m for m in node.body if isinstance(m, ast.FunctionDef)
                     and m.name == "_compute_ef_metrics"), None
                )
                break
        segment = ast.get_source_segment(source, method) if method else ""
        self.assertNotIn("self.book", segment)
        self.assertNotIn("self.controls", segment)

    def test_combined_accuracy_uses_net_main_rev_ef_pnl(self) -> None:
        cid1 = candle_id_from_ms(now_ms()) - 2 * CANDLE_MS
        cid2 = cid1 + CANDLE_MS
        with self.store.lock:
            # User-required semantics: -10 MAIN +8 REV +1 EF = -1 => one LOSS.
            self.store.db.executemany(
                "INSERT INTO trades(candle_id,kind,direction,ts_ms,filled,financial_pnl,"
                "financial_result,financial_is_shadow,forbidden,execution_mode,order_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (cid1,"MAIN","DOWN",cid1+1000,1,-10.0,"LOSS",0,0,"LIVE","FILLED"),
                    (cid1,"REVERSAL","UP",cid1+2000,1,8.0,"WIN",0,0,"LIVE","FILLED"),
                    (cid1,"EF","UP",cid1+3000,1,1.0,"WIN",0,0,"LIVE","FILLED"),
                    (cid2,"MAIN","UP",cid2+1000,1,4.0,"WIN",0,0,"LIVE","FILLED"),
                ],
            )
            self.store.db.commit()
        metrics = self.store.metrics()
        self.assertEqual(metrics["main"]["wins"], 1)
        self.assertEqual(metrics["main"]["losses"], 1)
        self.assertEqual(metrics["reversal"]["wins"], 1)
        self.assertEqual(metrics["ef"]["wins"], 1)
        self.assertEqual(metrics["combined"]["total"], 2)
        self.assertEqual(metrics["combined"]["wins"], 1)
        self.assertEqual(metrics["combined"]["losses"], 1)
        self.assertAlmostEqual(metrics["combined"]["accuracy"], 0.5)
        self.assertEqual(metrics["combined"]["basis"], "NET_MAIN_REV_EF_PNL_SIGN_PER_CANDLE")

    def test_master_off_shadow_marker_is_blue_without_becoming_forbidden(self) -> None:
        self.assertIn("m.signals_off||m.financial_is_shadow", DASHBOARD_HTML)
        self.assertIn("isShadow=!!marker.financial_is_shadow", DASHBOARD_HTML)

    def test_all_pnl_range_keeps_more_than_600_points(self) -> None:
        start = candle_id_from_ms(now_ms()) - 700 * CANDLE_MS
        rows = []
        for i in range(650):
            cid = start + i * CANDLE_MS
            rows.append((cid, "EF", "UP", cid + 1000, 0.4, 1, 2.5,
                         "WIN", 0, 0, "", 5.0, 2.5))
        with self.store.lock:
            self.store.db.executemany(
                "INSERT INTO trades(candle_id,kind,direction,ts_ms,fill_price,filled,"
                "financial_pnl,financial_result,financial_is_shadow,forbidden,state_x,"
                "stake,pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
            )
            self.store.db.commit()
        summary = self.store.trade_summary(range_key="ALL")
        self.assertEqual(summary["count"], 650)
        self.assertEqual(len(summary["curve_points"]), 650)

    def test_post_ef_progress_classification_and_persistence(self) -> None:
        self.assertEqual(
            classify_ef_post_progress(0.1, False, "UP", "UP"), "REVERSAL_FAKE"
        )
        self.assertEqual(
            classify_ef_post_progress(0.5, False, "UP", "UP"),
            "REVERSAL_REAL_TOO_WEAK"
        )
        self.assertEqual(
            classify_ef_post_progress(0.9, False, "UP", "UP"),
            "APPROACHED_OPEN_STALLED"
        )
        self.assertEqual(
            classify_ef_post_progress(1.0, True, "DOWN", "UP"),
            "CROSSED_OPEN_THEN_REVERTED"
        )
        self.assertEqual(
            classify_ef_post_progress(1.0, True, "UP", "UP"),
            "CROSSED_AND_SETTLED_EF_SIDE"
        )
        cid = candle_id_from_ms(now_ms())
        self.store.save_ef_progress({
            "candle_id": cid, "direction": "UP", "fire_ts_ms": cid + 10_000,
            "fire_price": 99990.0, "candle_open": 100000.0,
            "initial_distance": 10.0, "closest_distance": 1.0,
            "progress_fraction": 0.9, "crossed_open": False,
            "best_side_distance": 0.0, "fire_features": {"ef_runway_v2_score": 0.7},
        })
        row = self.store.ef_progress_row(cid)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(float(row["progress_fraction"]), 0.9)

    def test_disabled_signal_keeps_directional_diagnostic_but_no_financial_win_loss(self) -> None:
        cid = candle_id_from_ms(now_ms()) - CANDLE_MS
        pred = Prediction(cid, "MAIN", "UP", cid + 1000, 100000.0, 0.7, "diag", features={})
        self.store.add_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "MAIN", "direction": "UP", "ts_ms": cid + 1000,
            "seconds_into_candle": 1.0, "quoted_price": 0.4, "filled": False,
            "attempts": 0, "failure_reason": "FORBIDDEN: MAIN trading is manually OFF",
            "attempt_log": [], "forbidden": True, "execution_mode": "LIVE",
            "order_status": "FORBIDDEN",
        })
        self.store.settle_candle({
            "time": cid, "open": 100000.0, "high": 100010.0, "low": 99990.0,
            "close": 100005.0, "volume": 1.0, "close_time_ms": cid + CANDLE_MS - 1,
        })
        self.store.settle_trades(cid, "UP")
        trade = self.store.trade_row(cid, "MAIN")
        self.assertIsNone(trade["financial_result"])
        prediction = self.store.get_prediction(cid, "MAIN")
        self.assertTrue(prediction.correct)
        marker = next(x for x in self.store.markers() if x["candle_id"] == cid and x["kind"] == "MAIN")
        self.assertIsNone(marker["correct"])
        self.assertTrue(marker["directional_correct"])
        self.assertTrue(marker["forbidden"])

    def test_market_callback_queue_is_bounded_and_nonblocking(self) -> None:
        engine=Engine(self.store)
        self.assertGreater(engine.market_events.maxsize,0)
        start=mono_ns()
        ok=engine.handle_message("btcusdt@aggTrade",{"E":now_ms(),"p":"100000","q":"0.001","m":False},now_ms(),mono_ns())
        self.assertTrue(ok)
        self.assertLess((mono_ns()-start)/1_000_000.0,10.0)


    def test_main_settlement_guard_defers_marginal_early_candidate(self) -> None:
        feature = {
            "fair_p_up": 0.605, "seconds_left": 260.0, "phase_second": 40.0,
            "above_open_balance_30s": 0.55, "delta_1s": 0.08, "delta_5s": 0.08,
            "delta_30s": 0.04, "spot_imbalance5": 0.05, "ofi_1s": 10.0,
            "ofi_5s": 12.0, "return_1s_bps": 0.05, "return_5s_bps": 0.10,
            "reject_up": 0.1, "reject_down": 0.1, "body_range_ratio": 0.20,
            "close_location": 0.60, "path_efficiency": 0.35, "open_cross_count": 1,
        }
        q = main_settlement_quality(feature, "UP", 100000.0, 100004.0, 2.0)
        self.assertFalse(q["pass"])
        self.assertGreater(q["horizon_uncertainty"], 0.5)

    def test_main_settlement_guard_allows_exceptional_early_candidate(self) -> None:
        feature = {
            "fair_p_up": 0.86, "seconds_left": 260.0, "phase_second": 40.0,
            "above_open_balance_30s": 0.96, "delta_1s": 0.75, "delta_5s": 0.72,
            "delta_30s": 0.62, "spot_imbalance5": 0.55, "ofi_1s": 300.0,
            "ofi_5s": 350.0, "return_1s_bps": 2.4, "return_5s_bps": 5.2,
            "reject_up": 0.0, "reject_down": 3.0, "body_range_ratio": 0.88,
            "close_location": 0.95, "path_efficiency": 0.88, "open_cross_count": 0,
        }
        q = main_settlement_quality(feature, "UP", 100000.0, 100055.0, 2.0)
        self.assertTrue(q["pass"])
        self.assertGreater(q["score"], q["required"])

    def test_fired_opposite_ef_can_veto_main_settlement(self) -> None:
        feature = {
            "fair_p_up": 0.78, "seconds_left": 120.0, "phase_second": 180.0,
            "above_open_balance_30s": 0.90, "delta_1s": 0.45, "delta_5s": 0.40,
            "delta_30s": 0.35, "spot_imbalance5": 0.30, "ofi_1s": 120.0,
            "ofi_5s": 140.0, "return_1s_bps": 1.2, "return_5s_bps": 2.0,
            "reject_up": 0.0, "reject_down": 2.0, "body_range_ratio": 0.75,
            "close_location": 0.90, "path_efficiency": 0.80, "open_cross_count": 0,
        }
        q = main_settlement_quality(
            feature, "UP", 100000.0, 100035.0, 2.0,
            ef_direction="DOWN", ef_settlement_score=0.80, ef_fired=True,
        )
        self.assertTrue(q["ef_opposition_veto"])
        self.assertFalse(q["pass"])

    def test_avg_move_linear_optimization_is_legacy_exact(self) -> None:
        def legacy(hist, secs=10.0):
            moves=[]
            for i in range(len(hist)):
                for j in range(i+1,len(hist)):
                    if hist[j][0]-hist[i][0]>=secs:
                        moves.append(abs(hist[j][1]-hist[i][1])); break
            moves.sort()
            return moves[len(moves)//2] if moves else 0.0
        hist=[(i*0.37,100000.0+math.sin(i/7.0)*20+i*0.03) for i in range(300)]
        self.assertEqual(avg_move(hist,10.0),legacy(hist,10.0))

    def test_shadow_history_is_labelled_not_failed(self) -> None:
        self.assertIn("if(o.financial_is_shadow)return ['SHADOW','forbidden']", DASHBOARD_HTML)
        self.assertIn("m.financial_is_shadow?'S·':'')", DASHBOARD_HTML)

    def test_main_final_hold_guard_rejects_flow_only_early_call(self) -> None:
        feature = {
            "fair_p_up": 0.61, "seconds_left": 265.0, "phase_second": 35.0,
            "above_open_balance_30s": 0.58, "delta_1s": 0.95, "delta_5s": 0.90,
            "delta_30s": 0.80, "spot_imbalance5": 0.85, "ofi_1s": 500.0,
            "ofi_5s": 600.0, "return_1s_bps": 2.5, "return_5s_bps": 5.0,
            "reject_up": 0.0, "reject_down": 2.0, "body_range_ratio": 0.4,
            "close_location": 0.62, "path_efficiency": 0.65, "open_cross_count": 0,
        }
        q = main_settlement_quality(feature, "UP", 100000.0, 100003.0, 2.0)
        self.assertFalse(q["pass"])
        self.assertFalse(q["hold_ok"])

    def test_partial_fill_is_excluded_until_financial_lifecycle_is_stable(self) -> None:
        cid = candle_id_from_ms(now_ms()) - CANDLE_MS
        self.store.record_trade({
            "candle_id":cid,"kind":"MAIN","direction":"UP","ts_ms":cid+1000,
            "seconds_into_candle":1.0,"quoted_price":0.4,"fill_price":0.4,
            "filled":True,"attempts":1,"stake":10.0,"shares":20.0,"fee_rate":0.0,
            "failure_reason":None,"attempt_log":[],"forbidden":False,
            "execution_mode":"LIVE","order_status":"PARTIALLYFILLED"})
        self.store.settle_trades(cid,"UP")
        row=self.store.trade_row(cid,"MAIN")
        self.assertIsNone(row["financial_result"])
        self.assertEqual(self.store.metrics()["main"]["total"],0)
        self.assertEqual(self.store.leg_pnl()["MAIN"]["settled"],0)
        self.store.update_trade_execution(cid,"MAIN",order_status="FILLED")
        self.store.settle_trades(cid,"UP")
        self.assertEqual(self.store.trade_row(cid,"MAIN")["financial_result"],"WIN")

    def test_fallback_chart_uses_blue_only_for_shadow_or_off_main(self) -> None:
        self.assertIn("(isOff||isShadow)?'#60a5fa'", DASHBOARD_HTML)
        self.assertIn("isMain?(marker.direction==='UP'?'#26a69a':'#ef5350')", DASHBOARD_HTML)

    def test_r63_early_ef_fires_on_first_qualifying_read_without_legacy_gate(self) -> None:
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        engine.candle = {"time": cid, "open": 100000.0, "high": 100010.0,
                         "low": 99990.0, "close": 100001.0, "volume": 1.0}
        engine.feature = {"price": 100001.0}
        engine.ef_metrics = {
            "candidate_eligible": False, "inputs_ready": True, "direction": "UP",
            "reachability": 0.70, "control_transfer": 0.68,
            "settlement_feasibility": 0.66, "runway_v2_score": 0.64,
            "chop": 0.30, "delta_250ms": 0.70, "delta_1s": 0.40,
            "delta_2s": 0.30, "settlement_probability": 0.56,
        }
        with mock.patch.object(engine, "_emit_ef") as emit, \
             mock.patch.object(self.store, "upsert_ef_candidate", return_value=None):
            engine._watch_ef(cid + 25_000)
        emit.assert_called_once()
        self.assertEqual(engine.ef_candidate_reads, 1)
        evidence = emit.call_args.args[2]
        self.assertGreaterEqual(evidence["early_prep_score"], EF_EARLY_SCORE_MIN)

    def test_r63_early_ef_blocks_weak_prep_even_if_legacy_candidate_is_true(self) -> None:
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        engine.candle = {"time": cid, "open": 100000.0, "high": 100010.0,
                         "low": 99990.0, "close": 100001.0, "volume": 1.0}
        engine.feature = {"price": 100001.0}
        engine.ef_metrics = {
            "candidate_eligible": True, "inputs_ready": True, "direction": "DOWN",
            "reachability": 0.20, "control_transfer": 0.30,
            "settlement_feasibility": 0.35, "runway_v2_score": 0.40,
            "chop": 0.95, "delta_250ms": -0.05, "delta_1s": -0.02,
            "delta_2s": -0.01, "settlement_probability": 0.52,
        }
        with mock.patch.object(engine, "_emit_ef") as emit, \
             mock.patch.object(self.store, "upsert_ef_candidate", return_value=None):
            engine._watch_ef(cid + 25_000)
        emit.assert_not_called()
        self.assertFalse(engine.ef_monitor["ready"])
        self.assertIn("reach", engine.ef_monitor["status"])

    def test_r63_early_formula_matches_last_night_ab_arm(self) -> None:
        reach, control, settle, quality, chop = 0.70, 0.68, 0.66, 0.64, 0.30
        d250, d1, d2 = 0.70, 0.40, 0.30
        slow = 0.60 * d1 + 0.40 * d2
        acceleration = d250 - slow
        accel_support = clamp((acceleration + 0.18) / 0.42, 0.0, 1.0)
        fast_support = clamp((d250 + 0.12) / 0.52, 0.0, 1.0)
        expected = clamp(
            0.27 * reach + 0.27 * control + 0.22 * settle
            + 0.12 * quality + 0.07 * accel_support + 0.05 * fast_support,
            0.0, 1.0,
        )
        engine = Engine(self.store)
        cid = candle_id_from_ms(now_ms())
        engine.candle = {"time": cid, "open": 100000.0, "high": 100010.0,
                         "low": 99990.0, "close": 100001.0, "volume": 1.0}
        engine.feature = {"price": 100001.0}
        engine.ef_metrics = {
            "inputs_ready": True, "direction": "UP", "reachability": reach,
            "control_transfer": control, "settlement_feasibility": settle,
            "runway_v2_score": quality, "chop": chop,
            "delta_250ms": d250, "delta_1s": d1, "delta_2s": d2,
            "settlement_probability": 0.56,
        }
        with mock.patch.object(engine, "_emit_ef") as emit, \
             mock.patch.object(self.store, "upsert_ef_candidate", return_value=None):
            engine._watch_ef(cid + 30_000)
        emit.assert_called_once()
        actual = emit.call_args.args[2]["early_prep_score"]
        self.assertAlmostEqual(actual, expected, places=12)

    def test_build_revision_is_r63_early_ef_production_and_visible(self) -> None:
        self.assertEqual(VERSION, "9.1.1")
        self.assertEqual(BUILD_REVISION, "9.1.1-r6.4-true-hot-ef")
        self.assertEqual(BUILD_NUMBER, 11)
        self.assertEqual(EF_PRICE_LIMIT_COOLDOWN_MS, 0)
        self.assertEqual(EF_EARLY_SCORE_MIN, 0.535)
        self.assertEqual(EF_EARLY_REACH_MIN, 0.38)
        self.assertEqual(EF_EARLY_CONTROL_MIN, 0.44)
        self.assertEqual(EF_EARLY_SETTLEMENT_MIN, 0.48)
        self.assertEqual(EF_EARLY_QUALITY_MIN, 0.51)
        self.assertEqual(EF_EARLY_CHOP_MAX, 0.88)
        self.assertGreater(EF_SLIPPAGE_FALLBACK_BPS, PREDICT_ORDER_SLIPPAGE_BPS)
        self.assertEqual([bps for _, bps in EF_SLIPPAGE_BANDS], [5000, 4118, 3333, 1667])

    def test_queue_overflow_sets_resync_flag(self) -> None:
        engine=Engine(self.store)
        engine.market_events=queue.Queue(maxsize=1)
        engine.market_events.put(("x",{},now_ms(),mono_ns()))
        ok=engine.handle_message("btcusdt@aggTrade",{"E":now_ms(),"p":"100000","q":"0.001","m":False},now_ms(),mono_ns())
        self.assertFalse(ok)
        self.assertTrue(engine.market_queue_overflow.is_set())

    def test_combined_accounting_excludes_failed_even_when_other_legs_settle(self) -> None:
        cid=candle_id_from_ms(now_ms())-CANDLE_MS
        with self.store.lock:
            self.store.db.executemany(
                "INSERT INTO trades(candle_id,kind,direction,ts_ms,filled,financial_pnl,financial_result,financial_is_shadow,forbidden,execution_mode,order_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (cid,"MAIN","UP",cid+1000,0,None,None,0,0,"LIVE","FAILED"),
                    (cid,"REVERSAL","DOWN",cid+2000,1,3.0,"WIN",0,0,"LIVE","FILLED"),
                    (cid,"EF","DOWN",cid+3000,1,-1.0,"LOSS",0,0,"LIVE","FILLED"),
                ],
            ); self.store.db.commit()
        m=self.store.metrics()
        self.assertEqual(m["main"]["total"],0)
        self.assertEqual(m["combined"]["total"],1)
        self.assertEqual(m["combined"]["wins"],1)
        self.assertAlmostEqual(m["combined"]["net_pnl"],2.0)



    def test_export_csv_exposes_financial_truth_and_shadow_flag(self) -> None:
        header = self.store.export_csv().decode().splitlines()[0].split(",")
        for name in ("financial_result", "financial_pnl", "financial_source",
                     "financial_is_shadow", "execution_eligibility",
                     "execution_vwap", "directional_correct"):
            self.assertIn(name, header)
        self.assertEqual(header[-13:-11], ["stake", "pnl"])
        self.assertEqual(header[-11:], [
            "state_x", "state_x_active", "state_x_trigger_time",
            "state_x_end_time", "sx_late_metric_15m", "sx_late_p80_6h",
            "sx_aligned_1s_metric_15m", "sx_aligned_1s_p80_6h",
            "sx_rejection_balance", "sx_aligned_delta30_median_15m",
            "sx_trigger_reason",
        ])



    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r51_price_limit_archive_is_attempt_numbered_and_pending_until_ack(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 60_000
        pred = Prediction(cid, "EF", "DOWN", ts, 100000.0, 0.30, "test", features={})
        self.assertTrue(self.store.add_ef_prediction(pred))
        self.assertTrue(self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts,
            "seconds_into_candle": 60.0, "quoted_price": 0.49, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "test price limit",
        }))
        row = self.store.trade_row(cid, "EF")
        self.assertEqual(row["ef_attempt_seq"], 1)
        self.assertTrue(self.store.r5_release_failed_ef(cid, ts, "DOWN", "test price limit"))
        self.assertIsNone(self.store.trade_row(cid, "EF"))
        failed = self.store.latest_ef_failed_attempt(cid)
        self.assertEqual(failed["attempt_seq"], 1)
        self.assertEqual(failed["order_status"], "PRICE_LIMIT")
        self.assertGreater(int(failed["cooldown_until_ms"] or 0), int(failed["archived_ms"]))
        pending = self.store.r5_pending_ef_rearm_notices()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["attempt_seq"], 1)

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r51_engine_clears_exact_price_limit_and_enters_cooldown(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 70_000
        pred = Prediction(cid, "EF", "UP", ts, 100000.0, 0.70, "test", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "UP", "ts_ms": ts,
            "seconds_into_candle": 70.0, "quoted_price": 0.49, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "test price limit",
        })
        self.assertTrue(self.store.r5_release_failed_ef(cid, ts, "UP", "test price limit"))
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        engine.current_ef = pred
        handled_at = now_ms()
        self.assertTrue(engine._r5_rearm_failed_ef(handled_at))
        self.assertIsNone(engine.current_ef)
        self.assertEqual(engine.ef_monitor["status"], "COOLDOWN")
        self.assertGreater(engine.ef_rearm_cooldown_until_ms, handled_at)
        self.assertEqual(self.store.r5_pending_ef_rearm_notices(), [])

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r52_live_price_limit_callback_clears_dashboard_immediately(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 75_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        pred = Prediction(cid, "EF", "DOWN", ts, 100001.0, 0.30, "live callback", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts,
            "seconds_into_candle": 75.0, "quoted_price": 0.65, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "live cap",
        })
        engine.current_ef = pred
        engine.ef_monitor = {"status": "TRIGGERED DOWN", "ready": True}
        self.assertTrue(self.store.r5_release_failed_ef(cid, ts, "DOWN", "live cap"))
        self.assertIsNone(engine.current_ef)
        self.assertEqual(engine.ef_monitor["status"], "COOLDOWN")
        self.assertGreater(engine.ef_rearm_cooldown_until_ms, now_ms())
        # Direct callback ACKs the durable notice only after Engine state changed.
        self.assertEqual(self.store.r5_pending_ef_rearm_notices(), [])

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r51_price_limit_cooldown_blocks_immediate_ef_recheck(self) -> None:
        cid = candle_id_from_ms(now_ms())
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        engine.ef_metrics = {"candidate_eligible": True, "direction": "DOWN"}
        stamp = cid + 120_000
        engine.ef_rearm_cooldown_until_ms = stamp + 2_000
        engine.ef_rearm_cooldown_reason = "PRICE_LIMIT"
        engine.ef_rearm_attempt_seq = 1
        with mock.patch.object(engine.book, "executable_vwap") as book_call:
            engine._watch_ef(stamp)
        book_call.assert_not_called()
        self.assertEqual(engine.ef_monitor["status"], "COOLDOWN")
        self.assertFalse(engine.ef_monitor["ready"])

    def test_r51_data_shows_archived_attempt_one_and_active_attempt_two(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts1 = cid + 80_000
        p1 = Prediction(cid, "EF", "DOWN", ts1, 100000.0, 0.30, "first", features={})
        self.store.add_ef_prediction(p1)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts1,
            "seconds_into_candle": 80.0, "quoted_price": 0.49, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "first cap",
        })
        self.store.r5_release_failed_ef(cid, ts1, "DOWN", "first cap")
        self.store.r5_ack_ef_rearm_notice(cid, ts1, "DOWN")
        ts2 = ts1 + 10_000
        p2 = Prediction(cid, "EF", "DOWN", ts2, 99990.0, 0.31, "second", features={})
        self.store.add_ef_prediction(p2)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts2,
            "seconds_into_candle": 90.0, "quoted_price": 0.30, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "QUEUED",
        })
        rows = self.store.recent_orders("EF", 0, 10)["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ef_attempt_seq"], 2)
        self.assertFalse(rows[0]["archived_failed_attempt"])
        self.assertEqual(rows[1]["ef_attempt_seq"], 1)
        self.assertTrue(rows[1]["archived_failed_attempt"])
        self.assertIn("REARMED", rows[1]["status"])


    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r51_pending_price_limit_tombstone_clears_older_same_candle_memory(self) -> None:
        cid = candle_id_from_ms(now_ms())
        old_ts = cid + 60_000
        failed_ts = old_ts + 1_000
        failed = Prediction(cid, "EF", "DOWN", failed_ts, 100000.0, 0.30, "failed", features={})
        self.store.add_ef_prediction(failed)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": failed_ts,
            "seconds_into_candle": 61.0, "quoted_price": 0.65, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "test price limit",
        })
        self.assertTrue(self.store.r5_release_failed_ef(cid, failed_ts, "DOWN", "test price limit"))
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        engine.current_ef = Prediction(cid, "EF", "DOWN", old_ts, 100001.0, 0.31, "stale memory", features={})
        self.assertTrue(engine._r5_rearm_failed_ef(now_ms()))
        self.assertIsNone(engine.current_ef)
        self.assertIn(engine.ef_monitor["status"], {"COOLDOWN", "WATCHING"})

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r51_executor_sweep_releases_orphaned_hashless_price_limit(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 80_000
        pred = Prediction(cid, "EF", "UP", ts, 100000.0, 0.70, "test", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "UP", "ts_ms": ts,
            "seconds_into_candle": 80.0, "quoted_price": 0.65, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "orphaned price limit",
        })
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            executor = LiveExecutor(
                self.store, TradeControls(self.store), PredictBook(testnet=False),
                threading.Event(),
            )
        self.assertEqual(executor._r5_sweep_hashless_price_limits(), 1)
        self.assertIsNone(self.store.trade_row(cid, "EF"))
        failed = self.store.latest_ef_failed_attempt(cid)
        self.assertIsNotNone(failed)
        self.assertEqual(str(failed["order_status"]), "PRICE_LIMIT")
        self.assertEqual(len(self.store.r5_pending_ef_rearm_notices()), 1)


    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r55_system_price_limit_forgets_ef_immediately_and_sets_5s(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 165_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        pred = Prediction(cid, "EF", "DOWN", ts, 100000.0, 0.30, "system cap", features={})
        engine.current_ef = pred
        engine.ef_monitor = {"status": "TRIGGERED DOWN", "ready": True}
        before = now_ms()
        engine.executor._notify_ef_price_limit(pred, 0.5354)
        self.assertIsNone(engine.current_ef)
        self.assertEqual(engine.ef_monitor["status"], "COOLDOWN")
        remaining = int(engine.ef_rearm_cooldown_until_ms) - before
        self.assertGreaterEqual(remaining, 4900)
        self.assertLessEqual(remaining, 5200)
        self.assertEqual(EF_PRICE_LIMIT_COOLDOWN_MS, 5000)

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r55_price_limit_cooldown_expires_to_watching_without_market_event(self) -> None:
        cid = candle_id_from_ms(now_ms())
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        engine.current_ef = None
        engine.ef_rearm_cooldown_until_ms = now_ms() - 1
        engine.ef_rearm_cooldown_reason = "PRICE_LIMIT"
        engine.ef_monitor = {"status": "COOLDOWN", "ready": False}
        self.assertTrue(engine._r5_reconcile_ef_lifecycle_once())
        self.assertEqual(engine.ef_monitor["status"], "WATCHING")
        self.assertEqual(engine.ef_rearm_cooldown_until_ms, 0)

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r55_old_price_limit_cannot_clear_newer_same_candle_ef(self) -> None:
        cid = candle_id_from_ms(now_ms())
        old_ts = cid + 170_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        old = Prediction(cid, "EF", "DOWN", old_ts, 100000.0, 0.30, "old", features={})
        newer = Prediction(cid, "EF", "DOWN", old_ts + 1000, 99999.0, 0.30, "new", features={})
        engine.current_ef = newer
        engine.executor._notify_ef_price_limit(old, 0.60)
        self.assertIs(engine.current_ef, newer)

    def test_r53_queue_full_rearms_only_after_executor_capacity_returns(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 160_000
        pred = Prediction(cid, "EF", "DOWN", ts, 100000.0, 0.30, "queue full", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts,
            "seconds_into_candle": 160.0, "quoted_price": 0.30, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "QUEUE_FULL",
            "failure_reason": "execution intent queue full; no order posted",
        })
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            ex = LiveExecutor(
                self.store, TradeControls(self.store), PredictBook(testnet=False),
                threading.Event(),
            )
        # Fill the queue to prove cleanup waits rather than hot-looping.
        while not ex.jobs.full():
            ex.jobs.put_nowait((pred, "EF"))
        ex.defer_ef_release_when_queue_available(pred, "queue full")
        self.assertFalse(ex._r5_process_deferred_ef_release())
        self.assertIsNotNone(self.store.trade_row(cid, "EF"))
        ex.jobs.get_nowait()
        self.assertTrue(ex._r5_process_deferred_ef_release())
        self.assertIsNone(self.store.trade_row(cid, "EF"))
        failed = self.store.latest_ef_failed_attempt(cid)
        self.assertIsNotNone(failed)
        self.assertEqual(str(failed["order_status"]), "QUEUE_FULL")


    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r54_watchdog_releases_active_price_limit_without_sink_delivery(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 110_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        pred = Prediction(cid, "EF", "DOWN", ts, 100001.0, 0.30, "watchdog", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": ts,
            "seconds_into_candle": 110.0, "quoted_price": 0.54, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "signed cap",
        })
        engine.current_ef = pred
        # Simulate the exact live failure mode: direct Store->Engine push is absent.
        self.store.r5_set_ef_rearm_sink(None)
        self.assertTrue(engine._r5_reconcile_ef_lifecycle_once())
        self.assertIsNone(engine.current_ef)
        self.assertIsNone(self.store.trade_row(cid, "EF"))
        failed = self.store.latest_ef_failed_attempt(cid)
        self.assertIsNotNone(failed)
        self.assertEqual(str(failed["order_status"]), "PRICE_LIMIT")
        self.assertIn(engine.ef_monitor["status"], {"COOLDOWN", "WATCHING"})

    @unittest.skip("R6 retired PRICE_LIMIT/cooldown lifecycle")
    def test_r54_watchdog_repairs_archived_price_limit_after_notice_is_lost(self) -> None:
        cid = candle_id_from_ms(now_ms())
        ts = cid + 115_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        pred = Prediction(cid, "EF", "UP", ts, 99999.0, 0.70, "lost notice", features={})
        self.store.add_ef_prediction(pred)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "UP", "ts_ms": ts,
            "seconds_into_candle": 115.0, "quoted_price": 0.53, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "lost notice cap",
        })
        engine.current_ef = pred
        self.store.r5_set_ef_rearm_sink(None)
        self.assertTrue(self.store.r5_release_failed_ef(cid, ts, "UP", "lost notice cap"))
        # Simulate a bad/lost acknowledgement from the old lifecycle design.
        self.store.r5_ack_ef_rearm_notice(cid, ts, "UP")
        self.assertIsNotNone(engine.current_ef)
        self.assertEqual(self.store.r5_pending_ef_rearm_notices(), [])
        self.assertTrue(engine._r5_reconcile_ef_lifecycle_once())
        self.assertIsNone(engine.current_ef)
        self.assertIn(engine.ef_monitor["status"], {"COOLDOWN", "WATCHING"})

    # ---- R6: dedicated EF hot execution ---------------------------------
    def _r6_hot_executor(self) -> LiveExecutor:
        with mock.patch.object(LiveExecutor, "_load_sdk", lambda _self: None):
            return LiveExecutor(
                self.store, TradeControls(self.store), PredictBook(testnet=False),
                threading.Event(),
            )

    def _r6_waiting_ef(self, direction: str = "UP") -> Prediction:
        cid = candle_id_from_ms(now_ms() + CANDLE_MS)
        ts = cid + 1_000
        pred = Prediction(
            cid, "EF", direction, ts, 100000.0,
            0.70 if direction == "UP" else 0.30, "R6 hot test", features={},
        )
        self.assertTrue(self.store.add_ef_prediction(pred))
        self.assertTrue(self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": direction,
            "ts_ms": ts, "seconds_into_candle": 1.0,
            "quoted_price": None, "filled": False, "stake": 10.0,
            "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "WAIT_VWAP",
            "execution_eligibility": "WAIT_VWAP",
        }))
        return pred

    def test_r6_ef_vwap_is_the_only_half_dollar_price_gate(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("UP")
        active = {"prediction": pred, "stake": 10.0, "attempt": 1,
                  "first_submit_ms": 0, "min_book_version": 0}
        # The prepared order can carry a price/slippage ceiling ABOVE $0.50.
        # R6 must not apply a second EF $0.50 decision after the authoritative
        # full-stake VWAP itself has passed.
        state = {
            "vwap": 0.49, "execution_ok": True, "book_ms": now_ms(),
            "book_version": 7, "max_price": 0.90, "order_hash": "0xr6",
            "payload": {"already": "hot"},
            "amounts": {"price": 0.90, "max_price": 0.90,
                        "planned_stake": 10.0, "book_version": 7},
            "stake": 10.0,
        }
        with mock.patch.object(
            ex, "_ef_hot_viability", return_value={
                "ok": True, "live_vwap": 0.49, "live_shares": 21.0,
                "min_out_shares": 10.0, "book_age_ms": 5,
            }
        ), mock.patch.object(
            ex, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(ex, "_attempt", return_value="UNKNOWN") as attempt:
            ex._ef_hot_execute_ready(active, state)
        attempt.assert_called_once()
        args, kwargs = attempt.call_args
        self.assertEqual(args[1], "EF")
        self.assertIsNotNone(kwargs.get("prepared"))
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(row.get("execution_eligibility"), "VWAP_CONFIRMED")
        self.assertNotEqual(str(row.get("order_status") or ""), "PRICE_LIMIT")

    def test_r6_ef_at_or_above_half_dollar_stays_waiting(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("DOWN")
        active = {"prediction": pred, "stake": 10.0, "attempt": 1,
                  "first_submit_ms": 0, "min_book_version": 0}
        base = {
            "execution_ok": True, "book_ms": now_ms(), "book_version": 3,
            "order_hash": "0xwait", "payload": {},
            "amounts": {"price": 0.90, "planned_stake": 10.0}, "stake": 10.0,
        }
        viability = [
            {"ok": True, "live_vwap": value, "live_shares": 20.0,
             "min_out_shares": 10.0, "book_age_ms": 5}
            for value in (0.50, 0.51, 0.90)
        ]
        with mock.patch.object(
            ex, "_ef_hot_viability", side_effect=viability
        ), mock.patch.object(
            ex, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(ex, "_attempt", return_value="UNKNOWN") as attempt:
            for value in (0.50, 0.51, 0.90):
                ex._ef_hot_execute_ready(active, dict(base, vwap=value))
        attempt.assert_not_called()
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(str(row.get("order_status") or ""), "WAIT_VWAP")

    def test_r61_confirmed_failure_stays_in_same_vwap_qualified_batch(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("UP")
        used = {"book_version": 11, "stake": 10.0, "order_hash": "0xdead1"}
        ex._ef_hot_transition_after_terminal(
            pred, used, 1, now_ms() - 40, "ORDERNOTACCEPTED"
        )
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(str(row.get("order_status") or ""), "HOT_RETRY")
        self.assertEqual(row.get("execution_eligibility"), "VWAP_CONFIRMED_RETRY")
        self.assertNotIn("WAIT_VWAP", str(row.get("order_status") or ""))
        with ex._ef_hot_lock:
            active = dict(ex._ef_hot_active or {})
        self.assertIs(active.get("prediction"), pred)
        self.assertEqual(int(active.get("attempt") or 0), 2)
        self.assertTrue(bool(active.get("vwap_confirmed")))
        self.assertEqual(active.get("previous_order_hash"), "0xdead1")

    def test_r61_retry_does_not_recheck_half_dollar_vwap(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("DOWN")
        active = {
            "prediction": pred, "stake": 10.0, "attempt": 2,
            "first_submit_ms": now_ms() - 20, "min_book_version": 0,
            "vwap_confirmed": True, "previous_order_hash": "0xold",
        }
        state = {
            "vwap": 0.82, "execution_ok": True, "book_ms": now_ms(),
            "book_version": 9, "order_hash": "0xretry2", "payload": {},
            "amounts": {"price": 0.84, "planned_stake": 10.0, "book_version": 9},
            "stake": 10.0,
        }
        with mock.patch.object(
            ex, "_ef_hot_viability", return_value={
                "ok": True, "live_vwap": 0.82, "live_shares": 12.5,
                "min_out_shares": 10.0, "book_age_ms": 5,
            }
        ), mock.patch.object(
            ex, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(ex, "_attempt", return_value="UNKNOWN") as attempt:
            ex._ef_hot_execute_ready(active, state)
        attempt.assert_called_once()
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(row.get("execution_eligibility"), "VWAP_CONFIRMED_RETRY")
        self.assertEqual(str(row.get("order_status") or ""), "HOT_RETRY_POST")

    def test_r61_retry_readiness_wait_never_regresses_to_wait_vwap(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("UP")
        active = {
            "prediction": pred, "stake": 10.0, "attempt": 3,
            "first_submit_ms": now_ms() - 30, "min_book_version": 0,
            "vwap_confirmed": True, "previous_order_hash": "0xold2",
        }
        state = {
            "vwap": 0.77, "execution_ok": True, "book_ms": now_ms(),
            "book_version": 10, "order_hash": "0xretry3", "payload": {},
            "amounts": {"price": 0.79, "planned_stake": 10.0, "book_version": 10},
            "stake": 10.0,
        }
        with mock.patch.object(
            ex, "_ef_hot_viability", return_value={
                "ok": True, "live_vwap": 0.77, "live_shares": 12.5,
                "min_out_shares": 10.0, "book_age_ms": 5,
            }
        ), mock.patch.object(
            ex, "readiness", return_value={"ready": False, "missing": ["auth"]}
        ), mock.patch.object(ex, "_attempt") as attempt:
            ex._ef_hot_execute_ready(active, state)
        attempt.assert_not_called()
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(str(row.get("order_status") or ""), "HOT_RETRY_WAIT")
        self.assertEqual(row.get("execution_eligibility"), "WAIT_READINESS_RETRY")

    def test_r61_fourth_terminal_failure_closes_signal_no_wait_vwap(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("UP")
        used = {"book_version": 21, "stake": 10.0, "order_hash": "0xdead4"}
        ex.arm_ef_hot(pred, 10.0, attempt=4, vwap_confirmed=True)
        ex._ef_hot_transition_after_terminal(
            pred, used, 4, now_ms() - 300, "ORDERNOTACCEPTED"
        )
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertEqual(str(row.get("order_status") or ""), "ORDERNOTACCEPTED")
        self.assertEqual(row.get("execution_eligibility"), "RETRY_EXHAUSTED")
        self.assertIn("failed after 4 attempts", str(row.get("failure_reason") or ""))
        self.assertNotIn("WAIT_VWAP", str(row.get("failure_reason") or ""))
        with ex._ef_hot_lock:
            self.assertIsNone(ex._ef_hot_active)

    def test_r6_waiting_ef_freezes_stake_config_but_not_wallet_capital(self) -> None:
        pred = self._r6_waiting_ef("UP")
        self.assertIn("EF", self.store.open_position_kinds())
        # WAIT_VWAP is only an execution intent: no venue order exists yet, so
        # it must not reserve spendable capital.
        self.assertEqual(float(self.store.capital_state()["reserved"]), 0.0)
        controls = TradeControls(self.store)
        cfg = dict(self.store.control_row(SYSTEM_CONTROL_KIND)["stake"])
        cfg["current_stake"] = 12.0
        result = controls.apply_change(
            SYSTEM_CONTROL_KIND, stake=cfg, ts_ms=pred.ts_ms
        )
        self.assertTrue(result.get("pending"))
        self.assertNotEqual(
            float(self.store.control_row(SYSTEM_CONTROL_KIND)["stake"]["current_stake"]),
            12.0,
        )

    def test_r6_hot_loop_never_double_posts_an_unresolved_hash(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("DOWN")
        self.store.update_trade_execution(
            pred.candle_id, "EF", order_hash="0xstilllive",
            order_status="UNKNOWN", submitted_ms=now_ms(),
        )
        active = {"prediction": pred, "stake": 10.0, "attempt": 2,
                  "first_submit_ms": now_ms() - 30, "min_book_version": 0}
        state = {
            "vwap": 0.20, "execution_ok": True, "book_ms": now_ms(),
            "book_version": 9, "order_hash": "0xnew", "payload": {},
            "amounts": {"price": 0.22, "planned_stake": 10.0}, "stake": 10.0,
        }
        with mock.patch.object(
            ex, "readiness", return_value={"ready": True, "missing": []}
        ), mock.patch.object(ex, "_attempt", return_value="UNKNOWN") as attempt:
            ex._ef_hot_execute_ready(active, state)
        attempt.assert_not_called()

    def test_r631_dynamic_ef_slippage_tiers_and_main_rev_keep_default(self) -> None:
        expected = {
            0.01: 5000,
            0.099999: 5000,
            0.10: 4118,
            0.199999: 4118,
            0.20: 3333,
            0.299999: 3333,
            0.30: 1667,
            0.399999: 1667,
            0.40: 909,
            0.48: 909,
            0.73: 909,
        }
        for vwap, bps in expected.items():
            self.assertEqual(ef_slippage_bps(vwap), bps, vwap)
        self.assertEqual(ef_slippage_bps(None), 5000)
        self.assertEqual(ef_slippage_bps(0.0), 5000)
        self.assertGreater(ef_slippage_bps(0.48), PREDICT_ORDER_SLIPPAGE_BPS)
        ex = self._r6_hot_executor()
        ex._ef_builders["UP"] = object()
        amounts = {
            "price": 0.40, "execution_vwap": 0.39, "execution_max_price": 0.41,
            "execution_shares": 25.0, "book_ms": now_ms(), "book_version": 1,
            "slippage_bps": 1667, "execution_ok": True,
        }
        with mock.patch.object(
            ex, "_build_payload", return_value=("0xhot", {}, amounts)
        ) as build:
            ex._ef_hot_build_side("UP", candle_id_from_ms(now_ms()), 10.0)
        self.assertTrue(build.call_args.kwargs["dynamic_ef_slippage"])
        self.assertNotIn("slippage_bps", build.call_args.kwargs)
        self.assertIs(build.call_args.kwargs["builder"], ex._ef_builders["UP"])

    def test_r631_price_rise_preferences_convert_to_predict_min_out(self) -> None:
        # If min shares are (1-s) of the snapshot expectation, the maximum
        # equivalent average-price multiple is 1/(1-s). These bands should
        # reproduce the requested ~2.0x, 1.7x, 1.5x, 1.2x and 1.1x limits.
        cases = [
            (5000, 2.0),
            (4118, 1.70),
            (3333, 1.50),
            (1667, 1.20),
            (909, 1.10),
        ]
        for bps, target in cases:
            min_fraction = 1.0 - bps / 10000.0
            multiple = 1.0 / min_fraction
            self.assertAlmostEqual(multiple, target, delta=0.002)


    def test_r62_first_attempt_acceptance_reads_attempt_journal_not_final_fill(self) -> None:
        self.assertEqual(
            first_attempt_http_status(json.dumps([
                {"attempt": 1, "status": "ACCEPTED"},
                {"attempt": 2, "status": "ORDERNOTACCEPTED"},
            ])),
            "ACCEPTED",
        )
        self.assertEqual(
            first_attempt_http_status(json.dumps([
                {"attempt": 1, "status": "ORDERNOTACCEPTED"},
                {"attempt": 2, "status": "ACCEPTED"},
            ])),
            "ORDERNOTACCEPTED",
        )
        self.assertIsNone(first_attempt_http_status("[]"))

    def test_r62_dynamic_slippage_never_adds_a_second_share_price_gate(self) -> None:
        # 0.48 with 10% isMinAmountOut room may mathematically tolerate an
        # implied fill above $0.50. That is intentional: the earlier full-stake
        # VWAP qualification is the only EF price decision; signing adds no
        # second share-price gate or signed-price cap.
        self.assertEqual(ef_slippage_bps(0.48), 909)
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "LiveExecutor")
        build = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                     and n.name == "_build_payload")
        build_source = ast.get_source_segment(source, build) or ""
        self.assertNotIn("EF_MAX_SHARE_PRICE", build_source)
        self.assertIn("is_min_amount_out=True", build_source)

    def test_r6_executor_has_no_second_ef_price_limit(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "LiveExecutor")
        for method_name in ("_submit_signed_order", "_execute_r4", "_ef_hot_try_fire"):
            fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                      and n.name == method_name)
            segment = ast.get_source_segment(source, fn) or ""
            self.assertNotIn("EF_MAX_SHARE_PRICE", segment)
            self.assertNotIn("PRICE_LIMIT", segment)
        decision = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_ef_hot_execute_ready")
        decision_source = ast.get_source_segment(source, decision) or ""
        self.assertIn("live_vwap >= EF_MAX_SHARE_PRICE", decision_source)
        self.assertNotIn("max_price >= EF_MAX_SHARE_PRICE", decision_source)
        self.assertNotIn("signed_effective_max_price", decision_source)

    def test_r64_newer_book_version_is_not_itself_a_rejection(self) -> None:
        ex = self._r6_hot_executor()
        state = {"direction": "UP", "min_out_shares": 100.0, "book_version": 1}
        with mock.patch.object(
            ex.book, "executable_vwap",
            return_value={"ok": True, "vwap": 0.081, "shares": 101.0,
                          "reason": "ELIGIBLE", "book_age_ms": 4},
        ):
            result = ex._ef_hot_viability(state, 10.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "VIABLE")

    def test_r64_live_ladder_below_signed_min_out_rebuilds_locally(self) -> None:
        ex = self._r6_hot_executor()
        state = {"direction": "DOWN", "min_out_shares": 100.0, "book_version": 1}
        with mock.patch.object(
            ex.book, "executable_vwap",
            return_value={"ok": True, "vwap": 0.09, "shares": 99.0,
                          "reason": "ELIGIBLE", "book_age_ms": 3},
        ):
            result = ex._ef_hot_viability(state, 10.0)
        self.assertFalse(result["ok"])
        self.assertIn("BOOK_BEYOND_SIGNED_MIN_OUT", result["reason"])

    def test_r64_startup_uses_two_direction_owned_hot_threads(self) -> None:
        names = set(LiveExecutor.run.__code__.co_names)
        self.assertIn("_ef_hot_loop_side", names)
        self.assertIn("_ef_hot_threads", names)
        self.assertNotIn("_ef_hot_loop", names)
        self.assertNotIn("_ef_hot_thread", names)

    def test_r64_hot_loop_is_event_driven_not_timeout_resigning(self) -> None:
        code = LiveExecutor._ef_hot_loop_side.__code__
        names = set(code.co_names)
        self.assertIn("wait", names)
        self.assertIn("clear", names)
        self.assertIn("_ef_hot_refresh_side", names)
        self.assertIn(0.25, code.co_consts)

    def test_r64_arm_wake_tries_prebuilt_before_any_resign(self) -> None:
        ex = self._r6_hot_executor()
        calls = []

        class OneWake:
            def wait(self, _timeout):
                return True
            def clear(self):
                calls.append("clear")
            def set(self):
                pass

        ex._ef_hot_wake["UP"] = OneWake()

        def fire():
            calls.append("fire")
            if calls.count("fire") >= 2:
                ex.stop_event.set()

        def refresh(side):
            calls.append(f"refresh:{side}")

        with mock.patch.object(ex, "_ef_hot_try_fire", side_effect=fire), \
             mock.patch.object(ex, "_ef_hot_refresh_side", side_effect=refresh):
            ex._ef_hot_loop_side("UP")

        self.assertEqual(calls[:4], ["clear", "fire", "refresh:UP", "fire"])

    def test_r64_final_stale_min_out_sends_zero_http_posts_and_zero_attempts(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("UP")
        start = now_ms()
        amounts = {
            "price": 0.08, "planned_stake": 10.0, "book_version": 7,
            "market_id": "m", "taker_amount_wei": int(100 * 10**18),
        }
        with mock.patch.object(
            ex.controls.state_x, "execution_block", return_value=(False, {})
        ), mock.patch.object(
            ex.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            ex, "_ef_hot_viability", return_value={
                "ok": False, "reason": "BOOK_BEYOND_SIGNED_MIN_OUT",
                "live_vwap": 0.09, "live_shares": 99.0,
                "min_out_shares": 100.0, "book_age_ms": 2,
            }
        ), mock.patch.object(ex, "_request") as request:
            phase, code, response = ex._submit_signed_order(
                pred, "EF", 10.0, 1, [], start, "0xstale",
                {"data": {}}, amounts, start,
            )
        self.assertEqual((phase, code, response), ("LOCAL_REBUILD", None, None))
        request.assert_not_called()
        row = self.store.trade_row(pred.candle_id, "EF") or {}
        self.assertIsNone(row.get("order_hash"))
        self.assertEqual(int(row.get("attempts") or 0), 0)
        self.assertEqual(str(row.get("order_status") or ""), "HOT_REBUILD")

    def test_r64_final_viable_newer_ladder_reaches_exactly_one_http_post(self) -> None:
        ex = self._r6_hot_executor()
        pred = self._r6_waiting_ef("DOWN")
        start = now_ms()
        amounts = {
            "price": 0.08, "planned_stake": 10.0, "book_version": 3,
            "market_id": "m", "taker_amount_wei": int(100 * 10**18),
        }
        with mock.patch.object(
            ex.controls.state_x, "execution_block", return_value=(False, {})
        ), mock.patch.object(
            ex.controls, "may_execute", return_value=(True, "")
        ), mock.patch.object(
            ex, "_ef_hot_viability", return_value={
                "ok": True, "reason": "VIABLE", "live_vwap": 0.081,
                "live_shares": 101.0, "min_out_shares": 100.0,
                "book_age_ms": 2,
            }
        ), mock.patch.object(
            ex, "_request", return_value=(201, {"data": {"orderId": "1", "orderHash": "0xviable"}})
        ) as request:
            phase, code, response = ex._submit_signed_order(
                pred, "EF", 10.0, 1, [], start, "0xviable",
                {"data": {}}, amounts, start,
            )
        self.assertEqual(phase, "RESPONSE")
        self.assertEqual(code, 201)
        request.assert_called_once_with("POST", "/v1/orders", {"data": {}})

    def test_r64_dynamic_signing_uses_one_copied_book_not_second_live_vwap(self) -> None:
        # _build_payload must derive the EF tier from its copied SDK ladder.
        # A second PredictBook.executable_vwap read here would break the atomic
        # quote/tolerance/signature contract on a fast websocket book.
        names = set(LiveExecutor._build_payload.__code__.co_names)
        self.assertIn("_vwap_from_sdk_book_data", names)
        self.assertIn("ef_slippage_bps", names)
        self.assertNotIn("executable_vwap", names)

    def test_r6_public_hot_quote_never_exposes_signed_material(self) -> None:
        ex = self._r6_hot_executor()
        with ex._ef_hot_lock:
            ex._ef_hot_orders["UP"] = {
                "direction": "UP", "vwap": 0.31, "quote": 0.32,
                "payload": {"secret": 1}, "order_hash": "0xsecret",
                "amounts": {"signed": True}, "book_version": 4,
            }
        public = ex.ef_hot_quote("UP")
        self.assertEqual(public.get("vwap"), 0.31)
        for private in ("payload", "order_hash", "amounts"):
            self.assertNotIn(private, public)

    def test_r54_watchdog_never_clears_newer_same_candle_attempt(self) -> None:
        cid = candle_id_from_ms(now_ms())
        old_ts = cid + 90_000
        new_ts = cid + 100_000
        engine = Engine(self.store)
        engine.candle = {"time": cid, "open": 100000.0}
        old = Prediction(cid, "EF", "DOWN", old_ts, 100001.0, 0.30, "old", features={})
        self.store.add_ef_prediction(old)
        self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "DOWN", "ts_ms": old_ts,
            "seconds_into_candle": 90.0, "quoted_price": 0.55, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "PRICE_LIMIT",
            "failure_reason": "old cap",
        })
        self.store.r5_set_ef_rearm_sink(None)
        self.assertTrue(self.store.r5_release_failed_ef(cid, old_ts, "DOWN", "old cap"))
        self.store.r5_ack_ef_rearm_notice(cid, old_ts, "DOWN")
        newer = Prediction(cid, "EF", "UP", new_ts, 100002.0, 0.70, "newer", features={})
        self.assertTrue(self.store.add_ef_prediction(newer))
        self.assertTrue(self.store.record_trade({
            "candle_id": cid, "kind": "EF", "direction": "UP", "ts_ms": new_ts,
            "seconds_into_candle": 100.0, "quoted_price": 0.35, "filled": False,
            "stake": 10.0, "fee_rate": PREDICT_FEE_RATE, "attempt_log": [],
            "execution_mode": "LIVE", "order_status": "QUEUED",
        }))
        engine.current_ef = newer
        engine._r5_reconcile_ef_lifecycle_once()
        self.assertIsNotNone(engine.current_ef)
        self.assertEqual(int(engine.current_ef.ts_ms), new_ts)
        self.assertEqual(engine.current_ef.direction, "UP")

def run_unittest_suite(verbosity: int = 2) -> bool:
    loader = unittest.TestLoader()
    retired_prefixes = ("test_state_x_",)
    retired_exact = {
        "test_no_shadow_or_external_ml_mode_and_new_ui_contract",
        "test_forbidden_rows_are_f_in_data_but_never_chart_text",
        "test_v72_individual_off_is_forbidden_blue_f_and_still_grades",
    }
    names = [name for name in loader.getTestCaseNames(V7SafetyTests)
             if not name.startswith(retired_prefixes) and name not in retired_exact]
    suite = unittest.TestSuite()
    for name in names:
        suite.addTest(V7SafetyTests(name))
    suite.addTests(loader.loadTestsFromTestCase(V81AdaptationTests))
    suite.addTests(loader.loadTestsFromTestCase(V911Tests))
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    if result.wasSuccessful():
        print(f"self-test passed: {result.testsRun} v9.1.1 checks; retired legacy State X timer/no-shadow tests are replaced by per-trade/shadow tests")
    return result.wasSuccessful()

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Single-file BTC v8.1 GPT core + BTC-only EF Runway v2 + PnL-truth accounting"
        )
    )
    parser.add_argument("--port", type=int, default=PORT_DEFAULT)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().with_name("btc_model_v7.sqlite3"),
        help="accuracy database path",
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--host",
        default=os.getenv("BTC_MODEL_HOST", "127.0.0.1"),
        help=(
            "address to bind the dashboard to. Default 127.0.0.1 (this "
            "machine only). Use 0.0.0.0 to reach it from any device - "
            "this requires BTC_MODEL_PASSWORD to be set."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "start a fresh run: archive the existing database and CSV logs "
            "so the first stake is seeded from the live Predict.fun balance"
        ),
    )
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if run_unittest_suite() else 1)
    database = args.db.resolve()
    if args.reset:
        for line in archive_run_data(database):
            print(line)
    problem = check_exposure(args.host, DASHBOARD_PASSWORD)
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(2)
    app = App(database, args.port, args.host)
    app.run()


def check_exposure(host: str, password: str) -> str:
    """Refuse to listen beyond loopback without a real password.

    Anyone who reaches this port can turn live trading on, resize the stake and
    read the order history, and the wallet key sits on the same machine.
    Binding publicly is allowed, but never silently and never unguarded.
    """
    if is_loopback_host(host):
        return ""
    if not password:
        return (
            f"refusing to bind {host}: set BTC_MODEL_PASSWORD first.\n"
            "The dashboard can enable live trading and change stake sizing, "
            "so it must not be left open.\n"
            '  export BTC_MODEL_PASSWORD="$(openssl rand -base64 24)"'
        )
    if len(password) < DASHBOARD_MIN_PASSWORD_LEN:
        return (
            f"refusing to bind {host}: BTC_MODEL_PASSWORD is too short "
            f"({len(password)} chars, need {DASHBOARD_MIN_PASSWORD_LEN}+).\n"
            "This port gets scanned within minutes of opening."
        )
    return ""


def archive_run_data(database: Path) -> List[str]:
    """Move a previous run aside instead of deleting it.

    A stale `trade_controls.stake_config` is what keeps an old stake alive
    across restarts: the live-balance seed is guarded by a one-time meta key,
    so it never re-runs while the old database is in place. Renaming the file
    both clears that flag and preserves the history, which is worth keeping
    given how few settled trades exist so far.
    """
    stamp = london_dt().strftime("%Y%m%d-%H%M%S")
    moved: List[str] = []
    targets = [database]
    targets.extend(
        database.parent / f"{database.name}{suffix}"
        for suffix in ("-wal", "-shm")
    )
    targets.extend(sorted(database.parent.glob("*.csv")))
    for path in targets:
        if not path.exists():
            continue
        archived = path.with_name(f"{path.name}.{stamp}.bak")
        try:
            path.rename(archived)
            moved.append(f"archived {path.name} -> {archived.name}")
        except OSError as exc:
            moved.append(f"could NOT archive {path.name}: {exc}")
    if not moved:
        return ["reset: nothing to archive, starting clean"]
    moved.append(
        "reset complete: first stake will be seeded from the live "
        "Predict.fun USDT balance"
    )
    return moved


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        sys.exit(1)
