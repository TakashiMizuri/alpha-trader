#!/usr/bin/env bash
# Install alpha-trader (PM Spot Fair) on Ubuntu/Debian VPS.
set -euo pipefail

APP_USER="${APP_USER:-alpha-trader}"
APP_DIR="${APP_DIR:-/opt/alpha-trader}"
PYTHON="${PYTHON:-python3}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install.sh"
  exit 1
fi

echo "==> Creating user ${APP_USER}"
id -u "${APP_USER}" &>/dev/null || useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"

echo "==> Syncing application to ${APP_DIR}"
mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude '.venv' --exclude 'output' --exclude '.git' --exclude '__pycache__' \
  ./ "${APP_DIR}/"

echo "==> Python venv + dependencies"
"${PYTHON}" -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}[dev]"

echo "==> Directories"
mkdir -p "${APP_DIR}/output/logs" "${APP_DIR}/output/health" "${APP_DIR}/output/reports"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Edit ${APP_DIR}/.env (PM_MARKET_SLUG or PM_YES_TOKEN_ID)"
fi

echo "==> systemd"
install -m 644 "${APP_DIR}/deploy/systemd/alpha-trader-logger.service" \
  /etc/systemd/system/alpha-trader-logger.service
systemctl daemon-reload

echo "==> logrotate"
install -m 644 "${APP_DIR}/deploy/logrotate/alpha-trader" /etc/logrotate.d/alpha-trader

echo "==> Done"
echo "  sudo systemctl enable --now alpha-trader-logger"
echo "  sudo systemctl status alpha-trader-logger"
echo "  tail -f ${APP_DIR}/output/logs/market_*.jsonl"
