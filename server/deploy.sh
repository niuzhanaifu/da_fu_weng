#!/usr/bin/env bash
set -euo pipefail

APP_NAME="dafuweng-stock"
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
HOST="${DAFUWENG_HOST:-0.0.0.0}"
PORT="${DAFUWENG_PORT:-8000}"
DB_PATH="${DAFUWENG_DB_PATH:-${APP_DIR}/data/dafuweng.sqlite3}"
INPUT_ADMIN_TOKEN="${DAFUWENG_ADMIN_TOKEN:-}"
INPUT_TUSHARE_TOKEN="${TUSHARE_TOKEN:-}"
INPUT_TUSHARE_FETCH_MINUTES="${TUSHARE_FETCH_MINUTES:-}"
INPUT_TUSHARE_TIMEOUT_SECONDS="${TUSHARE_TIMEOUT_SECONDS:-}"
ADMIN_TOKEN="${INPUT_ADMIN_TOKEN}"
TUSHARE_TOKEN="${INPUT_TUSHARE_TOKEN}"
TUSHARE_FETCH_MINUTES="${TUSHARE_FETCH_MINUTES:-0}"
TUSHARE_TIMEOUT_SECONDS="${TUSHARE_TIMEOUT_SECONDS:-30}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
AUTO_PULL="${AUTO_PULL:-1}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This deploy script must run on Linux."
    exit 1
  fi
}

ensure_admin_token() {
  if [[ -f "${APP_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${APP_DIR}/.env"
    DB_PATH="${DAFUWENG_DB_PATH:-${DB_PATH}}"
    HOST="${DAFUWENG_HOST:-${HOST}}"
    PORT="${DAFUWENG_PORT:-${PORT}}"
    ADMIN_TOKEN="${INPUT_ADMIN_TOKEN:-${DAFUWENG_ADMIN_TOKEN:-${ADMIN_TOKEN}}}"
    TUSHARE_TOKEN="${INPUT_TUSHARE_TOKEN:-${TUSHARE_TOKEN:-}}"
    TUSHARE_FETCH_MINUTES="${INPUT_TUSHARE_FETCH_MINUTES:-${TUSHARE_FETCH_MINUTES:-0}}"
    TUSHARE_TIMEOUT_SECONDS="${INPUT_TUSHARE_TIMEOUT_SECONDS:-${TUSHARE_TIMEOUT_SECONDS:-30}}"
  fi

  if [[ -z "${ADMIN_TOKEN}" ]]; then
    if command -v openssl >/dev/null 2>&1; then
      ADMIN_TOKEN="$(openssl rand -hex 24)"
    else
      ADMIN_TOKEN="$(date +%s%N)-change-this-token"
    fi
  fi
}

pull_latest_code() {
  if [[ "${AUTO_PULL}" == "0" ]]; then
    log "AUTO_PULL=0, skipping git pull."
    return
  fi

  local repo_dir
  if [[ -d "$(cd "${APP_DIR}/.." && pwd)/.git" ]]; then
    repo_dir="$(cd "${APP_DIR}/.." && pwd)"
  elif [[ -d "${APP_DIR}/.git" ]]; then
    repo_dir="${APP_DIR}"
  else
    log "No git repository found for ${APP_DIR}. Skipping git pull."
    return
  fi

  log "Pulling latest code in ${repo_dir}"
  git -C "${repo_dir}" pull --ff-only
}

install_system_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing system packages with apt-get"
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip curl git cron
  elif command -v dnf >/dev/null 2>&1; then
    log "Installing system packages with dnf"
    sudo dnf install -y python3 python3-pip curl git cronie
  elif command -v yum >/dev/null 2>&1; then
    log "Installing system packages with yum"
    sudo yum install -y python3 python3-pip curl git cronie
  else
    log "No supported package manager found. Assuming python3, venv, pip and curl are installed."
  fi
}

write_env_file() {
  log "Writing ${APP_DIR}/.env"
  mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs"
  cat > "${APP_DIR}/.env" <<EOF
DAFUWENG_DB_PATH=${DB_PATH}
DAFUWENG_ADMIN_TOKEN=${ADMIN_TOKEN}
DAFUWENG_HOST=${HOST}
DAFUWENG_PORT=${PORT}
TUSHARE_TOKEN=${TUSHARE_TOKEN}
TUSHARE_FETCH_MINUTES=${TUSHARE_FETCH_MINUTES}
TUSHARE_TIMEOUT_SECONDS=${TUSHARE_TIMEOUT_SECONDS}
EOF
  chmod 600 "${APP_DIR}/.env"
}

install_python_dependencies() {
  log "Creating virtualenv and installing Python dependencies"
  cd "${APP_DIR}"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
}

initialize_database() {
  log "Initializing database"
  cd "${APP_DIR}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  set -a
  # shellcheck disable=SC1091
  source "${APP_DIR}/.env"
  set +a
  python -m stock_server.jobs init-db

  if [[ "${SEED_SAMPLE:-0}" == "1" ]]; then
    log "Seeding sample data and running sample selection"
    python -m stock_server.jobs seed-sample
    python -m stock_server.jobs run-daily-selection --date 2026-05-14
  fi
}

write_systemd_service() {
  log "Writing systemd service ${SERVICE_FILE}"
  sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Da Fu Weng Stock Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn stock_server.main:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable "${APP_NAME}"
  sudo systemctl restart "${APP_NAME}"
}

install_daily_sync_cron() {
  log "Installing daily Tushare sync cron at 17:30"
  mkdir -p "${APP_DIR}/logs"

  local marker_start="# dafu-weng daily-sync start"
  local marker_end="# dafu-weng daily-sync end"
  local cron_line="30 17 * * 1-5 cd ${APP_DIR} && { echo \"[\$(date '+\\%F \\%T \\%Z')] daily sync start\"; . .venv/bin/activate && set -a && . ./.env && set +a && python -m stock_server.jobs sync-tushare --start-date \$(date +\\%F) --end-date \$(date +\\%F) && python -m stock_server.jobs run-daily-selection --date \$(date +\\%F); status=\$?; echo \"[\$(date '+\\%F \\%T \\%Z')] daily sync finished status=\${status}\"; exit \${status}; } >> logs/cron.log 2>&1"
  local current_cron

  current_cron="$(mktemp)"
  crontab -l > "${current_cron}" 2>/dev/null || true
  sed -i "/${marker_start}/,/${marker_end}/d" "${current_cron}"
  {
    cat "${current_cron}"
    echo "${marker_start}"
    echo "${cron_line}"
    echo "${marker_end}"
  } | crontab -
  rm -f "${current_cron}"

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now cron 2>/dev/null || sudo systemctl enable --now crond 2>/dev/null || true
  fi
}

health_check() {
  log "Checking service health"
  sleep 2
  if curl -fsS "http://127.0.0.1:${PORT}/health"; then
    printf '\n'
    log "Deploy complete. Public URL: http://14.103.183.47:${PORT}"
    log "Admin token: ${ADMIN_TOKEN}"
    log "Keep this token safe. It is stored in ${APP_DIR}/.env"
  else
    log "Health check failed. Inspect logs with:"
    echo "sudo journalctl -u ${APP_NAME} -n 100 --no-pager"
    exit 1
  fi
}

main() {
  require_linux
  install_system_packages
  pull_latest_code
  ensure_admin_token
  write_env_file
  install_python_dependencies
  initialize_database
  write_systemd_service
  install_daily_sync_cron
  health_check
}

main "$@"
