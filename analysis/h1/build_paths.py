"""Build 5-minute candles with per-second close paths from Binance 1s klines."""
import glob, io, os, sys, zipfile
import numpy as np

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KL = os.path.join(SCRATCH, "klines")
OUT = os.path.join(SCRATCH, "build", "paths.npz")
SEC = 300  # seconds per 5-min candle

def day_seconds(path):
    """Return (t0_ms, closes[86400]) for one daily 1s kline zip, gaps forward-filled."""
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0]).decode()
    ts, cl = [], []
    for line in raw.splitlines():
        if not line or line[0] not in "0123456789":
            continue          # skip a header row if present
        f = line.split(",")
        ts.append(int(f[0])); cl.append(float(f[4]))
    ts = np.array(ts, dtype=np.int64); cl = np.array(cl, dtype=np.float64)
    if ts[0] > 1e15:          # microseconds -> milliseconds
        ts //= 1000
    t0 = ts[0] - (ts[0] % 86400000)
    idx = (ts - t0) // 1000
    out = np.full(86400, np.nan)
    keep = (idx >= 0) & (idx < 86400)
    out[idx[keep]] = cl[keep]
    # forward-fill, then back-fill any leading gap
    m = np.isnan(out)
    if m.all():
        return t0, None
    i = np.where(~m, np.arange(86400), 0)
    np.maximum.accumulate(i, out=i)
    out = out[i]
    first = np.argmax(~m)
    out[:first] = out[first]
    return t0, out

def main():
    files = sorted(glob.glob(os.path.join(KL, "BTCUSDT-1s-*.zip")))
    print(f"{len(files)} daily files")
    ids, paths = [], []
    for n, f in enumerate(files, 1):
        t0, s = day_seconds(f)
        if s is None:
            print("  skip (empty)", f); continue
        day = s.reshape(288, SEC)            # 288 five-minute candles
        ids.append(t0 + np.arange(288) * 300_000)
        paths.append(day)
        if n % 10 == 0 or n == len(files):
            print(f"  {n}/{len(files)} {os.path.basename(f)[-14:-4]}")
    cid = np.concatenate(ids)
    P = np.concatenate(paths).astype(np.float32)
    np.savez_compressed(OUT, cid=cid, paths=P)
    print(f"saved {OUT}: {P.shape[0]} candles x {P.shape[1]} s")
    o, c = P[:, 0], P[:, -1]
    print(f"  up {np.mean(c > o)*100:.2f}%  flat {np.mean(c == o)*100:.3f}%")

if __name__ == "__main__":
    main()
