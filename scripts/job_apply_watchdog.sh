#!/usr/bin/env bash
# Watchdog: alert if morning pipeline finished without delivering digest.
# Multi-profile: JOBWRIGHT_USER / JOBWRIGHT_DIR. Uses per-user PID only (no global pgrep).
set -euo pipefail

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright-users/${JOBWRIGHT_USER}}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${JOBWRIGHT_DIR}/MORNING_STATUS_${TODAY}"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
MORNING_PID_FILE="${JOBWRIGHT_DIR}/MORNING_PID_${TODAY}"

[ -f "${STATUS_FILE}" ] || exit 0
[ -f "${DELIVERED_MARKER}" ] && exit 0

pipeline_running() {
  if [ -f "${MORNING_PID_FILE}" ]; then
    pid="$(cat "${MORNING_PID_FILE}" 2>/dev/null || true)"
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
  echo "Job digest unavailable. Morning pipeline finished with an error."
  echo "Check: ${JOBWRIGHT_DIR}/logs/morning_${TODAY}.log"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

if pipeline_running; then
  echo "Morning pipeline still running for ${JOBWRIGHT_USER:-legacy}."
  echo "Check: ${JOBWRIGHT_DIR}/logs/morning_${TODAY}.log"
  # Do not mark delivered while still running
  exit 0
fi
