#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${DAFUWENG_APP_DIR:-${SCRIPT_DIR}}"
SYNC_HOUR="${DAFUWENG_SYNC_HOUR:-20}"
SYNC_MINUTE="${DAFUWENG_SYNC_MINUTE:-30}"
REPAIR_HOUR="${DAFUWENG_REPAIR_HOUR:-3}"
REPAIR_MINUTE="${DAFUWENG_REPAIR_MINUTE:-0}"
REPAIR_LOOKBACK_DAYS="${DAFUWENG_REPAIR_LOOKBACK_DAYS:-10}"
MARKER_START="# dafu-weng daily-sync start"
MARKER_END="# dafu-weng daily-sync end"

mkdir -p "${APP_DIR}/logs"

tmp_cron="$(mktemp)"
trap 'rm -f "${tmp_cron}"' EXIT

crontab -l > "${tmp_cron}" 2>/dev/null || true
sed -i "/${MARKER_START}/,/${MARKER_END}/d" "${tmp_cron}"

cat >> "${tmp_cron}" <<EOF
${MARKER_START}
${SYNC_MINUTE} ${SYNC_HOUR} * * 1-5 cd ${APP_DIR} && { echo "[\$(date '+\\%F \\%T \\%Z')] daily sync start"; . .venv/bin/activate && set -a && . ./.env && set +a && python -m stock_server.jobs sync-tushare --start-date \$(date +\\%F) --end-date \$(date +\\%F) && python -m stock_server.jobs run-daily-selection --date \$(date +\\%F); status=\$?; echo "[\$(date '+\\%F \\%T \\%Z')] daily sync finished status=\${status}"; exit \${status}; } >> logs/cron.log 2>&1
${REPAIR_MINUTE} ${REPAIR_HOUR} * * 2-6 cd ${APP_DIR} && { echo "[\$(date '+\\%F \\%T \\%Z')] volume ratio repair start"; . .venv/bin/activate && set -a && . ./.env && set +a && python -m stock_server.jobs repair-volume-ratio --lookback-days ${REPAIR_LOOKBACK_DAYS}; status=\$?; echo "[\$(date '+\\%F \\%T \\%Z')] volume ratio repair finished status=\${status}"; exit \${status}; } >> logs/cron.log 2>&1
${MARKER_END}
EOF

crontab "${tmp_cron}"

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl enable --now cron 2>/dev/null || sudo systemctl enable --now crond 2>/dev/null || true
fi

echo "Installed daily sync cron:"
crontab -l | sed -n "/${MARKER_START}/,/${MARKER_END}/p"
echo
echo "Log file: ${APP_DIR}/logs/cron.log"
