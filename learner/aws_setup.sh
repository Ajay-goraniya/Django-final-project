#!/bin/bash
# One-shot setup of v11 (Polymarket signal, Predict.fun execution) on an Ubuntu/Debian server.
# Run as root:  sudo bash aws_setup.sh <PUBLIC_IP> <DASHBOARD_PASSWORD>
# What it does: installs python deps + caddy, copies the v11 file set from this checkout to /opt/v11,
# asks for the two Predict.fun credentials (stored root-only in /opt/v11/secrets.env), starts v11 as a
# systemd service on 127.0.0.1:8794 with a relaunch loop, and exposes the dashboard over HTTPS on
# https://<ip-with-dashes>.sslip.io (Let's Encrypt via Caddy) behind basic auth (user: ajay).
# Master switch starts OFF; it is armed from Trade Controls or the API afterwards.
set -euo pipefail
IP="${1:?public ip}"; PASS="${2:?dashboard password}"
SRC="$(cd "$(dirname "$0")" && pwd)"
HOST="$(echo "$IP" | tr . -).sslip.io"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv sqlite3 curl debian-keyring debian-archive-keyring apt-transport-https >/dev/null
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
mkdir -p /opt/v11/db
cp "$SRC"/btc_model_build11.py "$SRC"/btc_model_v10.py "$SRC"/btc_model_v11.py "$SRC"/model_v10.json "$SRC"/v11_calibration.json "$SRC"/run_v11.sh /opt/v11/
chmod +x /opt/v11/run_v11.sh
python3 -m venv /opt/v11/venv
/opt/v11/venv/bin/pip install -q --upgrade pip numpy websocket-client 'predict-sdk>=0.0.22'
if [ ! -f /opt/v11/secrets.env ]; then
  read -r -p "Predict.fun data API key: " APIKEY
  read -r -s -p "Predict.fun private key (Privy wallet, hidden): " PK; echo
  read -r -p "Predict.fun account address (0x...): " ADDR
  umask 077; printf 'PREDICT_API_KEY=%s\nPREDICT_PRIVATE_KEY=%s\nPREDICT_ACCOUNT_ADDRESS=%s\nV11_MODE=pnl\n' "$APIKEY" "$PK" "$ADDR" > /opt/v11/secrets.env
fi
chmod 600 /opt/v11/secrets.env
cat > /etc/systemd/system/v11.service <<UNIT
[Unit]
Description=v11 BTC 5-minute model (Predict.fun execution)
After=network-online.target
Wants=network-online.target
[Service]
WorkingDirectory=/opt/v11
EnvironmentFile=/opt/v11/secrets.env
Environment=PATH=/opt/v11/venv/bin:/usr/bin:/bin
ExecStart=/opt/v11/run_v11.sh --port 8794 --db /opt/v11/db/v11.sqlite3
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
HASH="$(caddy hash-password --plaintext "$PASS")"
cat > /etc/caddy/Caddyfile <<CADDY
$HOST {
  basicauth {
    ajay $HASH
  }
  reverse_proxy 127.0.0.1:8794
}
CADDY
systemctl daemon-reload
systemctl enable --now v11
systemctl restart caddy
sleep 20
systemctl --no-pager --lines=3 status v11 | tail -5
echo
echo "v11 dashboard: https://$HOST  (user ajay)   master switch is OFF until armed"
echo "logs: journalctl -u v11 -f"
