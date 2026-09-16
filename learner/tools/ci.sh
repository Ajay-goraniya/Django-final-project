#!/bin/bash
# one-shot check-in bundle: fair table, twin rows, EF2 shadow, books, paired, snapshots, process count
cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live
date -u; echo "real python procs: $(ps -eo args | grep -c '^python3 ')"
python3 fair.py 2>&1 | grep -A5 "FAIR STATES"
bash checkin.sh 2>&1 | grep -E "^  [ABC] "
python3 - <<'PY'
import sqlite3
con=sqlite3.connect("ef2_shadow.sqlite3")
rows=con.execute("SELECT ask, correct FROM ef2 WHERE correct IS NOT NULL AND ask IS NOT NULL ORDER BY candle_id").fetchall()
print("EF2 shadow graded",len(rows))
for cap in (None,0.60,0.50):
    r=[(a,c) for a,c in rows if cap is None or a<=cap]
    if not r: continue
    p=[((1/(a*1.02)-1) if c else -1.0) for a,c in r]; h=len(p)//2
    print(f"  cap {cap}: n={len(r)} hit {sum(c for _,c in r)/len(r)*100:.0f}% per-fire {sum(p)/len(p):+.3f} halves {sum(p[:h]):+.2f}/{sum(p[h:]):+.2f}")
PY
python3 - <<'PY'
import sqlite3,numpy as np
o=sqlite3.connect("dm_shadow.sqlite3"); r=o.execute("select pnl,sec from dm where pnl is not null order by candle_id").fetchall()
print("11.2 live shadow: fires",o.execute("select count(*) from dm").fetchone()[0],"graded",len(r), (f"hit {np.mean([x[0]>0 for x in r])*100:.0f}% per-fire {np.mean([x[0] for x in r]):+.3f} halves {sum(x[0] for x in r[:len(r)//2]):+.2f}/{sum(x[0] for x in r[len(r)//2:]):+.2f}" if r else ""))
PY
for p in 8794 8795 8796 8798; do python3 -c "import json,urllib.request;s=json.load(urllib.request.urlopen('http://127.0.0.1:$p/api/state',timeout=5));b=s.get('book') or {};print($p,'book',(b.get('up') or {}).get('price'),(b.get('down') or {}).get('price'))" 2>&1 | tail -1; done
python3 paired.py v11/launch/b11.sqlite3 v11/tests/c_thr1.sqlite3 2>&1 | tail -1
L=/home/user/Django-final-project/learner/live_backup
for pair in "v11/launch/b11.sqlite3:build11" "v11/tests/b_guard.sqlite3:twin_b_guard" "v11/tests/e_combo.sqlite3:twin_e_combo" "v11/tests/c_thr1.sqlite3:twin_c_thr1" "venues.sqlite3:venues" "ef2_shadow.sqlite3:ef2_shadow" "book1s.sqlite3:book1s" "dm_shadow.sqlite3:dm_shadow" "polybook.sqlite3:polybook" "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/results/v12_poly_weekend.sqlite3:v12_poly_lane"; do src=${pair%%:*}; dst=${pair##*:}; python3 -c "import sqlite3;s=sqlite3.connect('$src');d=sqlite3.connect('/tmp/snap.sqlite3');s.backup(d);d.close()" && gzip -c /tmp/snap.sqlite3 > $L/$dst.sqlite3.gz && rm -f /tmp/snap.sqlite3; done; echo snapshots ok
