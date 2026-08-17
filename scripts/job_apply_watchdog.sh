#!/usr/bin/env bash
# Watchdog: alert if morning pipeline finished without delivering digest.
# Multi-profile: APPLYPILOT_USER / APPLYPILOT_DIR. Uses per-user PID only (no global pgrep).
set -euo pipefail

if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
fi

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${APPLYPILOT_DIR}/MORNING_STATUS_${TODAY}"
DELIVERED_MARKER="${APPLYPILOT_DIR}/DIGEST_DELIVERED_${TODAY}"
DIGEST_FILE="${APPLYPILOT_DIR}/DIGEST_${TODAY}"
MORNING_PID_FILE="${APPLYPILOT_DIR}/MORNING_PID_${TODAY}"

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
  echo "Check: ${APPLYPILOT_DIR}/logs/morning_${TODAY}.log"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

if pipeline_running; then
  echo "Morning pipeline still running for ${APPLYPILOT_USER:-legacy}."
  echo "Check: ${APPLYPILOT_DIR}/logs/morning_${TODAY}.log"
  # Do not mark delivered while still running
  exit 0
fi
