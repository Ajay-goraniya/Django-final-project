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
exit 0
