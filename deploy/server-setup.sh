#!/usr/bin/env bash
# Runs on the server (called by deploy.sh). Ubuntu 24.04 or 26.04. Installs Python 3.12 (via uv, the
# version the app is tested on, whatever the system Python is) + Caddy, then runs:
#   - the API as one uvicorn process (one process on purpose: plans and payment mandates live in memory)
#   - Caddy on 80/443: automatic HTTPS (needed for the microphone), the built frontend, /api -> the API
set -euo pipefail

APP=/opt/pointifly
DOMAIN="${DOMAIN:?DOMAIN not set}"

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq curl ufw gpg >/dev/null

# Caddy: Ubuntu's package, else Caddy's official apt repository.
if ! command -v caddy >/dev/null; then
  if ! apt-get install -y -qq caddy >/dev/null 2>&1; then
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  fi
fi

# uv (Astral's official installer) provides Python 3.12 for the app.
if ! command -v uv >/dev/null && [ ! -x /root/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh >/dev/null
fi
UV="$(command -v uv || echo /root/.local/bin/uv)"

id pointifly >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin pointifly

cd "$APP/backend"
export UV_PYTHON_INSTALL_DIR=/opt/uv-python  # outside /root, so the service user can run it
[ -x .venv/bin/python ] || "$UV" venv --python 3.12 .venv
"$UV" pip install --python .venv/bin/python -q -r requirements.txt
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

# The API takes a few seconds to load on a small server: wait up to 30s for it.
for _ in $(seq 30); do curl -fsS http://127.0.0.1:8000/api/dataset >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:8000/api/dataset >/dev/null && echo "API is up" || { echo "API failed to start:"; journalctl -u pointifly -n 30 --no-pager; exit 1; }
