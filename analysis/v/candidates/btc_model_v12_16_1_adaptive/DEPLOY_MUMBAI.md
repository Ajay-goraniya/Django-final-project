# Deploying v12.2

Written for a fresh Ubuntu host. Your current box is running build 12.0 live, so
the upgrade path is at the end.

## 1. Install

    sudo apt update && sudo apt install -y python3-venv python3-pip
    mkdir -p ~/polymarket && cd ~/polymarket
    unzip Polymarket_v12_2.zip && cd polymarket_v12
    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements-live.txt     # requirements-paper.txt for paper only

## 2. Check the host before trusting it

    python3 poly_selftest.py

It checks the Binance REST mirrors and websockets, measures the lag on each,
reports your clock offset against the exchange, confirms the SDK version and
credentials, and asks Polymarket whether this host may trade. Read any FAIL line
before going further. Paper mode runs regardless of the credential and geoblock
results.

The clock check matters more than it looks. If your clock is off the book feed
degrades, so make sure NTP is running:

    timedatectl set-ntp true && timedatectl status

## 3. Credentials

    cp deploy.env.example deploy.env
    chmod 600 deploy.env
    # fill in the four POLYMARKET_/RELAYER_ values, then:
    set -a && . ./deploy.env && set +a

Never commit `deploy.env`. The engine reads these from the environment only and
redacts them from any error it logs.

## 4. Run paper first

    python3 btc_model_v12_polymarket.py --mode pnl --capital 50 \
      --db paper.sqlite3 --port 8787

Leave it a full day. Before going live, confirm on the dashboard that the feed
block shows both `arrival_age_s` and `event_lag_s` small, that the latency block
has a p95 you are willing to trade on, and that MAIN and REVERSAL have produced
signals you have actually looked at.

## 5. Go live

    python3 btc_model_v12_polymarket.py --live --mode pnl \
      --db live.sqlite3 --port 8787 \
      --execution-budget-ms 3000 --post-timeout-ms 1500

The budget defaults suit a host beside the venue. From Mumbai the round trip is
longer, so start at 3000/1500 and then set them from the measured
`network_roundtrip_ms` p95 in the dashboard latency block rather than guessing.

Live starts with the master switch OFF. Turn it on from Trade Controls when you
have read the state.

## 6. Do not expose the dashboard

Your screenshot shows `3.7.253.12:8787` open in a browser, which means the
dashboard is reachable from the internet. It has no authentication and it can
move real money. Bind it to localhost and reach it over SSH instead:

    # on the server: keep the default --host 127.0.0.1
    # from your phone or laptop:
    ssh -L 8787:127.0.0.1:8787 user@3.7.253.12
    # then open http://127.0.0.1:8787

If you need it exposed, put it behind a reverse proxy with a password and TLS,
and restrict the source address.

## 7. systemd

`/etc/systemd/system/polymarket.service`:

    [Unit]
    Description=Polymarket v12.2
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    WorkingDirectory=/home/ubuntu/polymarket/polymarket_v12
    EnvironmentFile=/home/ubuntu/polymarket/polymarket_v12/deploy.env
    ExecStart=/home/ubuntu/polymarket/polymarket_v12/.venv/bin/python \
      btc_model_v12_polymarket.py --live --mode pnl --db live.sqlite3 --port 8787 \
      --execution-budget-ms 3000 --post-timeout-ms 1500
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

    sudo systemctl daemon-reload && sudo systemctl enable --now polymarket
    journalctl -u polymarket -f

A restart brings the engine back with the master switch off and reconciles
against the venue twice before the dashboard opens, so a crash mid-order cannot
leave a stale local reservation deciding what you can spend.

## 8. Upgrading the box that is already live on 12.0

1. Turn the master switch off in Trade Controls and wait for anything open to
   settle. Check the dashboard shows no pending orders.
2. Stop the service.
3. **Back up the database first**: `cp live.sqlite3 live.sqlite3.bak-$(date +%F)`.
4. Unzip v12.2 alongside and point it at the same database. The schema migration
   is additive: `signals` is rebuilt with a lane column, every existing row is
   stamped `EF`, and nothing is dropped. The backup is there in case you want to
   go back.
5. Start it, read the state, then turn the master switch back on.

MAIN and REVERSAL default to enabled in the controls, but the master switch is
off after a restart, so nothing fires until you say so. Given neither lane has a
live record, consider leaving them off on the live box and running a second
paper instance on a different port and database to watch them first.
