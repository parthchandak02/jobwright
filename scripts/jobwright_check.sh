#!/usr/bin/env bash
# Watchdog: alert if daily brief finished without delivering digest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_jobwright_repo.sh"
else
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh"
fi

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
BRIEF_PID_FILE="${JOBWRIGHT_DIR}/BRIEF_PID_${TODAY}"

[ -f "${STATUS_FILE}" ] || exit 0
[ -f "${DELIVERED_MARKER}" ] && exit 0

pipeline_running() {
  if [ -f "${BRIEF_PID_FILE}" ]; then
    pid="$(cat "${BRIEF_PID_FILE}" 2>/dev/null || true)"
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

if [ -f "${DIGEST_FILE}" ]; then
  cat "${DIGEST_FILE}"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

if grep -q "done" "${STATUS_FILE}" 2>/dev/null; then
  if pipeline_running; then
    exit 0
  fi
  echo "Job digest unavailable. Daily brief pipeline finished with an error."
  echo "Check: ${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

if pipeline_running; then
  echo "Daily brief still running for ${JOBWRIGHT_USER:-legacy}."
  echo "Check: ${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"
  exit 0
fi

exit 0
