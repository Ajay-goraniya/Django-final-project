#!/bin/bash
# Relaunch any of the live processes (Predict.fun pnl 8789, Polymarket pnl 8788, collector, Build 11 8794; accuracy runs retired 20:43 UTC 09-09) that is not running. NEVER resets a database.
D=/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live
cd /home/user/Django-final-project/learner
alive() { ps -eo args | grep -cE "^python3 .*$1" ; }
[ "$(alive 'btc_model_build10.py --port 8789')" -eq 0 ] && { setsid nohup $D/launch.sh >> $D/b10.log 2>&1 < /dev/null & echo "launched pnl engine"; }
[ "$(alive 'btc_model_v10_runner.py --port 8788')" -eq 0 ] && { setsid nohup python3 btc_model_v10_runner.py --port 8788 --db /tmp/v10_long4.sqlite3 --mode pnl >> /tmp/runner_long4.log 2>&1 < /dev/null & echo "launched pnl runner"; }
[ "$(alive 'venue_collect.py')" -eq 0 ] && { setsid nohup python3 $D/venue_collect.py >> $D/venue_collect.log 2>&1 < /dev/null & echo "launched collector"; }
[ "$(alive 'btc_model_build11.py --port 8794')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live/v11/launch && setsid nohup ./launch.sh >> b11.log 2>&1 < /dev/null & echo "launched build11"; }
[ "$(alive 'btc_model_build11.py --port 8795')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live/v11/tests && setsid nohup ./launch_b_guard.sh >> b_guard.log 2>&1 < /dev/null & echo "launched test b_guard"; }
[ "$(alive 'btc_model_build11.py --port 8796')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live/v11/tests && setsid nohup ./launch_c_thr1.sh >> c_thr1.log 2>&1 < /dev/null & echo "launched test c_thr1"; }
[ "$(alive 'btc_model_build11.py --port 8798')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live/v11/tests && setsid nohup ./launch_e_combo.sh >> e_combo.log 2>&1 < /dev/null & echo "launched test e_combo"; }
[ "$(alive 'ef2_shadow.py')" -eq 0 ] && { setsid nohup python3 $D/ef2_shadow.py >> $D/ef2_shadow.log 2>&1 < /dev/null & echo "launched ef2 shadow"; }
# 1 Hz loggers and the 11.2 live shadow (conditional; added 09-11)
[ "$(alive 'book1s.py')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live && setsid nohup python3 book1s.py >> book1s.log 2>&1 < /dev/null & echo "launched book1s"; }
[ "$(alive 'dm_shadow.py')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live && setsid nohup python3 dm_shadow.py >> dm_shadow.log 2>&1 < /dev/null & echo "launched dm_shadow"; }
[ "$(alive 'poly1s.py')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live && setsid nohup python3 poly1s.py >> poly1s.log 2>&1 < /dev/null & echo "launched poly1s"; }
# The v12 Polymarket observation lane (port 8790). Added 09-13 12:24 after a
# container restart killed all 12 processes: restart_all.sh brought back 11 and
# this one was missed, because it lived only in restart_v12_lane.sh. One script
# has to restore everything or the gap is found by noticing a stale number.
[ "$(alive 'btc_model_v12_polymarket.py')" -eq 0 ] && { cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/engine && setsid nohup python3 btc_model_v12_polymarket.py --execution paper --mode pnl --fixed-stake 10 --port 8790 --db ../results/v12_poly_weekend.sqlite3 >> /tmp/v12poly.log 2>&1 < /dev/null & echo "launched v12 lane"; }
# 12.8.6-vs-12.8.7 paper twins (added 09-14 02:3x after a container restart killed both). Safe-start
# forces master off, so re-seed master/next_stake after launch - the twins are paper, capital 50, stake 3.
T=/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/twins
for L in ctrl:8791 cand:8792; do d=${L%%:*}; p=${L##*:}
  [ "$(alive "btc_model_v12_polymarket.py --port $p")" -eq 0 ] && { (cd $T/$d && setsid nohup python3 btc_model_v12_polymarket.py --port $p --db twin.sqlite3 --capital 50 >> twin.log 2>&1 < /dev/null &); sleep 12; python3 -c "import sqlite3;c=sqlite3.connect('$T/$d/twin.sqlite3',timeout=10);c.execute(\"INSERT OR REPLACE INTO meta VALUES('master','true')\");c.execute(\"INSERT OR REPLACE INTO meta VALUES('next_stake','3.0')\");c.execute(\"INSERT OR REPLACE INTO meta VALUES('stake_settings','{\\\"mode\\\": \\\"fixed\\\", \\\"fixed_stake\\\": 3.0, \\\"percent\\\": 10.0, \\\"current_stake\\\": 3.0, \\\"win_trigger\\\": 3, \\\"loss_trigger\\\": 2, \\\"min_stake\\\": 1.0, \\\"max_stake\\\": 50.0}')\");c.commit()"; echo "launched twin $d"; }
done
exit 0
