#!/usr/bin/env bash
# Deploy Pointifly to a fresh Ubuntu 24.04 server (e.g. Vultr). Run from the repo root on your laptop:
#
#   ./deploy/deploy.sh root@203.0.113.7
#   ACCESS_PASSWORD=choose-one ./deploy/deploy.sh root@203.0.113.7   # optional: password-protect the site
#
# Safe to re-run: it rebuilds the frontend, syncs the code and restarts the services.
# Copies backend/.env, backend/secrets/ and the data caches over SSH; nothing secret goes through git.
set -euo pipefail

TARGET="${1:?usage: deploy/deploy.sh root@SERVER_IP}"
IP="${TARGET#*@}"
DOMAIN="${DOMAIN:-$IP.sslip.io}" # free hostname that resolves to the IP, so Caddy can get an HTTPS certificate
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/pointifly

[ -f "$ROOT/backend/.env" ] || { echo "backend/.env is missing"; exit 1; }

echo "==> Building the frontend"
(cd "$ROOT/frontend" && npm run build)

echo "==> Preparing the server"
ssh "$TARGET" "apt-get update -qq && apt-get install -y -qq rsync >/dev/null && mkdir -p $APP/backend $APP/frontend"

echo "==> Syncing code, .env, secrets and caches"
rsync -az --delete \
  --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude tests --exclude app/data/raw \
  "$ROOT/backend/" "$TARGET:$APP/backend/"
# Caches and API usage counters: seeded from the laptop once, then the server's own copies are kept.
rsync -az --ignore-existing "$ROOT/backend/app/data/raw/" "$TARGET:$APP/backend/app/data/raw/"
rsync -az --delete "$ROOT/frontend/dist/" "$TARGET:$APP/frontend/dist/"
rsync -az "$ROOT/deploy/server-setup.sh" "$TARGET:$APP/server-setup.sh"

echo "==> Installing and starting services"
ssh "$TARGET" "DOMAIN='$DOMAIN' ACCESS_PASSWORD='${ACCESS_PASSWORD:-}' bash $APP/server-setup.sh"

echo
echo "Pointifly is live at https://$DOMAIN"
