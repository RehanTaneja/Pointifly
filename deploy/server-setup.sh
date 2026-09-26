#!/usr/bin/env bash
# Runs on the server (called by deploy.sh). Installs Python + Caddy, then runs:
#   - the API as one uvicorn process (one process on purpose: plans and payment mandates live in memory)
#   - Caddy on 80/443: automatic HTTPS (needed for the microphone), the built frontend, /api -> the API
set -euo pipefail

APP=/opt/pointifly
DOMAIN="${DOMAIN:?DOMAIN not set}"

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq python3 python3-venv python3-pip caddy ufw >/dev/null

id pointifly >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin pointifly

cd "$APP/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
chown -R pointifly:pointifly "$APP"
chmod 600 .env secrets/* 2>/dev/null || true

cat >/etc/systemd/system/pointifly.service <<EOF
[Unit]
Description=Pointifly API
After=network-online.target

[Service]
User=pointifly
WorkingDirectory=$APP/backend
Environment=PRESENTATION_MODE=1
ExecStart=$APP/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

AUTH=""
if [ -n "${ACCESS_PASSWORD:-}" ]; then
  HASH="$(caddy hash-password --plaintext "$ACCESS_PASSWORD")"
  AUTH="basicauth {
		demo $HASH
	}"
fi

cat >/etc/caddy/Caddyfile <<EOF
$DOMAIN {
	encode gzip
	$AUTH
	handle /api/* {
		reverse_proxy 127.0.0.1:8000
	}
	handle {
		root * $APP/frontend/dist
		try_files {path} /index.html
		file_server
	}
}
EOF

ufw allow OpenSSH >/dev/null
ufw allow 80,443/tcp >/dev/null
ufw --force enable >/dev/null

systemctl daemon-reload
systemctl enable --now pointifly >/dev/null 2>&1
systemctl restart pointifly
systemctl reload caddy 2>/dev/null || systemctl restart caddy

sleep 3
curl -fsS http://127.0.0.1:8000/api/dataset >/dev/null && echo "API is up" || { echo "API failed to start:"; journalctl -u pointifly -n 30 --no-pager; exit 1; }
