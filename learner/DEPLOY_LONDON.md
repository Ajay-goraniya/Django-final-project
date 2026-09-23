# London box (eu-west-2, 13.40.72.11) - keep the engine and the bridge up 24/7

Owner, 09-22 21:3x: "Make sure london session is 24/7". Two things must survive an SSH drop, a crash and a reboot:
the engine (systemd) and the Claude remote-control bridge the "London" session rides on (tmux).

## 1. Engine as a systemd service (replaces the nohup start)

`deploy.env` in `/home/ubuntu/pm_london` already holds `DASHBOARD_PASSWORD` (12+ chars) and, since 12.23.1,
`VENUE_GEO_WHITELIST=1` (owner-supplied venue whitelist; the geoblock answer is still logged). Never print it.

`/etc/systemd/system/pm-london.service`:

    [Unit]
    Description=Polymarket v12.2 London
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    WorkingDirectory=/home/ubuntu/pm_london
    EnvironmentFile=/home/ubuntu/pm_london/deploy.env
    ExecStart=/home/ubuntu/pm_london/.venv/bin/python -u btc_model_v12_polymarket.py \
      --mode pnl --capital 50 --host 0.0.0.0 --port 8787 \
      --db polymarket_v12_london_1.sqlite3 --quote-age-ms 2000 --live
    Restart=always
    RestartSec=10
    StandardOutput=append:/home/ubuntu/pm_london/london.log
    StandardError=append:/home/ubuntu/pm_london/london.log

    [Install]
    WantedBy=multi-user.target

Switch over (the meta table keeps master, stake, ef_engine and the EF flag across the restart, so nothing is re-armed):

    pkill -f btc_model_v12_polymarket.py
    sudo systemctl daemon-reload && sudo systemctl enable --now pm-london
    systemctl is-active pm-london && ss -ltnp | grep 8787 && tail -3 london.log

`journalctl -u pm-london -f` or `tail -f london.log` to watch. Every restart is visible in `london.log` as a fresh
startup print and, if the process crashed, as the `TASK_CRASH` / traceback before it.

## 2. The "London" Claude session survives SSH drops only inside tmux

The session is a remote-control bridge: it lives exactly as long as the `claude` process on the box. Closing the
SSH window killed it once (archived 21:32 UTC). Run it detached:

    sudo apt-get install -y tmux
    tmux new -d -s claude
    tmux send-keys -t claude 'cd /home/ubuntu/pm_london && claude' Enter
    # then in that claude: /remote-control  (or however the bridge was started the first time)
    tmux attach -t claude        # to look; Ctrl-b d to leave it running

A reboot kills tmux too; the engine comes back by itself (systemd), the bridge does not - re-run the three tmux lines.

## 3. Checks

- `systemctl is-active pm-london` -> active
- `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8787/` -> 401 (auth wall up)
- dashboard header shows build 12.23.1 and the lane label (SHADOW while master is OFF, LIVE when ON)

## 3. Fast-path packages (13.0.2, owner 09-23: "all the fast requirements installed including coincurve")

Into the engine's own venv, before restarting on 13.0.2 (all three ship prebuilt manylinux wheels; if pip ever
falls back to a source build: `sudo apt-get install -y build-essential autoconf automake libtool pkg-config`):

    cd /home/ubuntu/pm_london && .venv/bin/pip install -r requirements-live.txt
    .venv/bin/python -c "import btc_model_v12_polymarket as m; print(m.fast_report())"

Expected, and printed again as the `[fast]` line at every boot, followed by `[loop] uvloop ...`:

    uvloop=0.2x.x sign=inline(coincurve=2x.x.x) http2=h2 4.x.x

Any `MISSING` or `sign=thread` = not deployed; fix it before the restart. `latency_stats` then reports
`loop`, `sign_mode`, `keepalive_ms` (order transport), `keepalive_book_ms` (book transport) and `fire_to_wire_attempt1`.
