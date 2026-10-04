#!/usr/bin/env python3
"""London's exact TWAP60 z, in ONE place. numpy + math only, so anything can import it.

Lives in its own leaf module deliberately: ef3_shadow needs it and so does ef14, and ef14 -> ef10 ->
ef3_shadow is a cycle. Two copies of a formula this fiddly is exactly how EF-12 got the wrong answer -
five small differences from this definition flipped the sign of a conclusion.

  line  = mean REF[E-61 .. E-2]                    (a TWAP60 ending BEFORE the epoch, >= 45 points)
  P     = latest REF in [t-5, t-1]
  sigma = sqrt(mean(dlog REF over [t-121, t-1])^2) * P     RMS, NO mean subtraction, in $/s, >= 60 pts
  start = E + 239
  t-1 >= start:  kn = t-start, m = 60-kn, mean = (avg(REF[start..t-1])*kn + m*P)/60
                 var = sigma^2 * m(m+1)(2m+1)/6
  else:          d = start-(t-1), mean = P, var = sigma^2 * (3600*d + S2), S2 = sum_{i,j<60} min(i,j)
  sd = sqrt(var)/60        z = (mean - line)/sd, UP-signed; negate for DOWN.
"""
import math
import numpy as np

S2 = int(sum(min(i, j) for i in range(60) for j in range(60)))


def london_z_at(ref, E, t):
    """UP-signed z for candle E at signal second t. `ref` maps unix second -> Chainlink price."""
    pre = [ref[E - k] for k in range(2, 62) if (E - k) in ref]
    if len(pre) < 45: return None
    line = float(np.mean(pre))
    start = E + 239
    win5 = [ref[u] for u in range(t - 5, t) if u in ref]
    if not win5: return None
    P = float(win5[-1])
    hist = [ref[u] for u in range(t - 121, t) if u in ref]
    if len(hist) < 60: return None
    dl = np.diff(np.log(np.array(hist, float)))
    sigma = float(math.sqrt(float(np.mean(dl ** 2)))) * P
    if sigma <= 0: return None
    if t - 1 >= start:
        kn = t - start
        m = 60 - kn
        if m <= 0: return None
        seg = [ref[u] for u in range(start, t) if u in ref]
        if not seg: return None
        mean = (float(np.mean(seg)) * kn + m * P) / 60.0
        var = sigma ** 2 * m * (m + 1) * (2 * m + 1) / 6.0
    else:
        d = start - (t - 1)
        mean = P
        var = sigma ** 2 * (3600.0 * d + S2)
    sd = math.sqrt(var) / 60.0
    if sd <= 0: return None
    return (mean - line) / sd
