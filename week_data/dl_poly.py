import json, pathlib, urllib.request, concurrent.futures as cf
files = [l for l in open("/tmp/poly_files.txt").read().split("\n") if l]
OUT = pathlib.Path("predictfun/polymarket_l2")
B = "https://huggingface.co/datasets/predict-quant/poly-btc-orderbook/resolve/main/"
def get(f):
    p = OUT / f.replace("/", "_")
    if p.exists() and p.stat().st_size > 0: return (f, p.stat().st_size, "cached")
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(B + f, headers={"User-Agent": "curl/8.5.0"}), timeout=120) as r:
                d = r.read()
            p.write_bytes(d); return (f, len(d), "ok")
        except Exception as e:
            if a == 3: return (f, 0, f"ERR {e}")
print("files to fetch:", len(files))
ok = 0; tot = 0
with cf.ThreadPoolExecutor(8) as ex:
    for i, (f, n, s) in enumerate(ex.map(get, files)):
        if s in ("ok", "cached"): ok += 1; tot += n
        if i % 50 == 0: print(f"  {i}/{len(files)} ok={ok} bytes={tot/1e6:.0f}MB", flush=True)
print(f"DONE {ok}/{len(files)} files, {tot/1e6:.1f} MB")
