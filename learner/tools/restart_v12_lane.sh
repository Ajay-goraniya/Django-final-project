#!/bin/bash
# Relaunch the v12 Polymarket observation lane on port 8790, on its EXISTING database.
# Same role as restart_all.sh, which does not cover this lane. Never --reset.
cd /tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/engine || exit 1
setsid nohup python3 btc_model_v12_polymarket.py --execution paper --mode pnl \
  --fixed-stake 10 --port 8790 --db ../results/v12_poly_weekend.sqlite3 \
  > /tmp/v12poly.log 2>&1 < /dev/null &
echo "launched v12 lane on 8790"
