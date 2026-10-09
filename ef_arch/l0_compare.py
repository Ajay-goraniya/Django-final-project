#!/usr/bin/env python3
"""
l0_compare.py -- which zero/one-parameter prior is best calibrated? (Sol Q16)

Compares on a fixed 1-second grid of Build36's OWN live feature state
(dumped by replay_build36.py --grid-dump, harness-side, no model change):

  L0-A  fair_p_up                  Build36's causal terminal prior:
                                   Phi(lead / (typical_24c_median/sqrt(300)
                                   * adapt_ratio * sqrt(tau)))
  L0-B  Phi(z)                     z = ln(p/O)/(sig*sqrt(tau)), sig = trailing
                                   600 s RMS of 1 s log-returns (shifted)
  L0-C  settlement_probability_base mapped to P_UP via the EF direction
  L0-S  shrunk L0-A:               P = 0.5 + kappa*(fair_p_up - 0.5), kappa
                                   fitted PREQUENTIALLY (hour h uses hours<h),
                                   one parameter -- tests whether the prior is
                                   merely overconfident

Label: candle closes above open (one coherent binary). Rows weighted 1/N per
candle (Sol section 33). Reports Brier / log-loss / ECE(10), Brier by
seconds-left band, the body-hold rate by band (the explanatory diagnostic),
and candle-clustered bootstrap CIs on Brier differences.

Build36's spot sigma_per_root_second is NOT used: it is a tick-ring
dispersion (~0.14 $/sqrt-s on this day, i.e. ~$2.4 over 300 s) and is not a
5-minute terminal sigma. The perp one (ef_perp_sigma_per_root_second) is the
right scale but was not in this dump.
"""
import csv, math, pathlib, sys
import numpy as np
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent
DUMP = ROOT.parent / "ef_replay" / "work" / "grid_dump_b36.csv"
KL = ROOT.parent / "btc_replay_2026-08-01_24h" / "normalized" / "spot_klines_5m.parquet"
BANDS = ((200, 301, "300-200s left"), (100, 200, "200-100s"), (60, 100, "100-60s"), (0, 60, "last 60s"))

def NORM(x): return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))
def fl(s):
    try: return float(s)
    except Exception: return np.nan

rows = list(csv.DictReader(open(DUMP)))
kl = pq.read_table(KL).to_pandas()
close = {int(r.open_time // 1000): float(r.close) for r in kl.itertuples()}
opn = {int(r.open_time // 1000): float(r.open) for r in kl.itertuples()}

cid_all = np.array([int(r["candle_open_ms"]) for r in rows])
keep = np.array([c in close for c in cid_all])
rows = [r for r, k in zip(rows, keep) if k]
ts = np.array([int(r["ts_ms"]) for r in rows]); cid = cid_all[keep]
spot = np.array([fl(r["spot"]) for r in rows]); left = np.array([fl(r["seconds_left"]) for r in rows])
fpu = np.array([fl(r["fair_p_up"]) for r in rows]); spb = np.array([fl(r["settlement_probability_base"]) for r in rows])
ed = np.array([r["ef_direction"] for r in rows])
y = np.array([1.0 if close[c] > opn[c] else 0.0 for c in cid]); O = np.array([opn[c] for c in cid])
hour = ((ts - ts.min()) // 3_600_000).astype(int)

# L0-B sigma: trailing 600-row RMS of 1 s log returns, shifted (strictly past)
lr = np.zeros(len(spot)); lr[1:] = np.diff(np.log(np.maximum(spot, 1e-9)))
lr[~np.concatenate([[False], np.diff(ts) < 5000])] = 0.0
lr = np.nan_to_num(lr, nan=0.0, posinf=0.0, neginf=0.0)
c_ = np.concatenate([[0.0], np.cumsum(lr ** 2)]); idx = np.arange(len(lr)); lo = np.maximum(0, idx - 599)
sigB = np.sqrt(np.maximum((c_[idx + 1] - c_[lo]) / np.maximum(idx + 1 - lo, 1), 1e-18))
sigB = np.concatenate([[sigB[0]], sigB[:-1]])
d = np.log(np.maximum(spot, 1e-9) / np.maximum(O, 1e-9)); tau = np.maximum(left, 1.0)
pB = np.clip(NORM(d / np.maximum(sigB * np.sqrt(tau), 1e-12)), 0.02, 0.98)
pC = np.where(ed == "UP", spb, np.where(ed == "DOWN", 1 - spb, np.nan))

# L0-S: prequential shrinkage of fair_p_up. kappa for hour h minimises
# weighted Brier on hours < h (closed form: weighted least squares on x=fpu-0.5).
pS = np.full(len(y), np.nan); kappas = []
w = np.zeros(len(cid))
for c in np.unique(cid):
    m = cid == c; w[m] = 1.0 / m.sum()
x = fpu - 0.5; t = y - 0.5
for h in range(int(hour.max()) + 1):
    tr = (hour < h) & ~np.isnan(fpu); te = (hour == h) & ~np.isnan(fpu)
    if tr.sum() < 600:
        kappa = 1.0                                   # no history: trust the prior
    else:
        kappa = float(np.clip(np.sum(w[tr] * x[tr] * t[tr]) / max(np.sum(w[tr] * x[tr] ** 2), 1e-12), 0.0, 1.5))
    kappas.append((h, kappa)); pS[te] = np.clip(0.5 + kappa * x[te], 0.01, 0.99)

def brier(p, y, w): return float(np.sum(w * (p - y) ** 2) / np.sum(w))
def logloss(p, y, w):
    p = np.clip(p, 1e-6, 1 - 1e-6); return float(-np.sum(w * (y * np.log(p) + (1 - y) * np.log(1 - p))) / np.sum(w))
def ece(p, y, w, bins=10):
    e = 0.0; edges = np.linspace(0, 1, bins + 1)
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] + (1e-9 if i == bins - 1 else 0))
        if w[m].sum() > 0: e += w[m].sum() / w.sum() * abs(np.average(p[m], weights=w[m]) - np.average(y[m], weights=w[m]))
    return float(e)
def clustered_diff(pa, pb, y, w, cid, n=600, seed=2):
    rs = np.random.default_rng(seed); cands = np.unique(cid); idx_by = {c: np.where(cid == c)[0] for c in cands}; out = []
    for _ in range(n):
        sel = np.concatenate([idx_by[c] for c in rs.choice(cands, len(cands), replace=True)])
        out.append(brier(pa[sel], y[sel], w[sel]) - brier(pb[sel], y[sel], w[sel]))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))

valid = ~np.isnan(spot) & ~np.isnan(O) & (left >= 0) & (left <= 300)
print(f"grid rows {len(rows):,}   valid {int(valid.sum()):,}   candles {len(np.unique(cid[valid]))}   P(close>open) = {np.average(y[valid], weights=w[valid]):.3f}")

print("\nWHY: does the current body predict the close?  (rate at which sign(spot-open) == final outcome)")
for lo_, hi_, name in BANDS:
    m = valid & (left >= lo_) & (left < hi_)
    hold = np.average(((spot[m] - O[m]) > 0) == (y[m] == 1), weights=w[m])
    conf = np.average(np.abs(fpu[m] - 0.5), weights=w[m])
    print(f"   {name:<14} n={int(m.sum()):>6}   body holds {100*hold:5.1f}%   fair_p_up mean |p-0.5| = {conf:.3f}")
print("   -> a driftless prior assumes the lead persists; on this day it mostly did not until the last minute.")

P = {"L0-A fair_p_up (Build36)": fpu, "L0-B Phi(z), 600s RMS sigma": pB,
     "L0-C settlement_prob_base->P_UP": pC, "L0-S shrunk fair_p_up (prequential)": pS,
     "constant 0.5": np.full(len(y), 0.5)}
print(f"\n{'prior':<38}{'n':>8}{'Brier':>9}{'logloss':>9}{'ECE10':>8}   cover")
for name, p in P.items():
    m = valid & ~np.isnan(p)
    if m.sum() == 0: continue
    print(f"{name:<38}{int(m.sum()):>8}{brier(p[m],y[m],w[m]):>9.4f}{logloss(p[m],y[m],w[m]):>9.4f}{ece(p[m],y[m],w[m]):>8.4f}   {100*m.sum()/valid.sum():5.1f}%")

print("\nBrier by seconds-left band (lower is better; constant 0.5 = 0.2500):")
print(f"{'prior':<38}" + "".join(f"{b[2]:>14}" for b in BANDS))
for name, p in P.items():
    m0 = valid & ~np.isnan(p); parts = []
    for lo_, hi_, _ in BANDS:
        m = m0 & (left >= lo_) & (left < hi_); parts.append(brier(p[m], y[m], w[m]) if m.sum() else np.nan)
    print(f"{name:<38}" + "".join(f"{v:>14.4f}" if not np.isnan(v) else f"{'-':>14}" for v in parts))

print("\nprequential kappa by hour (L0-S):", " ".join(f"h{h}:{k:.2f}" for h, k in kappas))

m = valid & ~np.isnan(fpu) & ~np.isnan(pB) & ~np.isnan(pS)
for a, b, label in (("L0-A fair_p_up (Build36)", "L0-B Phi(z), 600s RMS sigma", "A - B"),
                    ("L0-S shrunk fair_p_up (prequential)", "L0-A fair_p_up (Build36)", "S - A"),
                    ("L0-S shrunk fair_p_up (prequential)", "constant 0.5", "S - 0.5")):
    lo_, hi_ = clustered_diff(P[a][m], P[b][m], y[m], w[m], cid[m])
    print(f"Brier({label}) candle-clustered 95% CI: [{lo_:+.4f}, {hi_:+.4f}]  "
          f"{'first better' if hi_ < 0 else ('second better' if lo_ > 0 else 'not separable on one day')}")
