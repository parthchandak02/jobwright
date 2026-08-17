#!/usr/bin/env bash
# Digest delivery: reads the digest file written by the background morning
# pipeline and delivers it. Runs as a no_agent cron later.
# Multi-profile: APPLYPILOT_USER / APPLYPILOT_DIR.
set -euo pipefail

if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
fi

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

TODAY="$(date +%Y%m%d)"
DIGEST_FILE="${APPLYPILOT_DIR}/DIGEST_${TODAY}"
STATUS_FILE="${APPLYPILOT_DIR}/MORNING_STATUS_${TODAY}"
DELIVERED_MARKER="${APPLYPILOT_DIR}/DIGEST_DELIVERED_${TODAY}"
MORNING_PID_FILE="${APPLYPILOT_DIR}/MORNING_PID_${TODAY}"

# If no run today or already delivered → silent
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

# Pipeline finished successfully and digest exists → deliver
if grep -q "digest_written" "${STATUS_FILE}" 2>/dev/null && [ -f "${DIGEST_FILE}" ]; then
  cat "${DIGEST_FILE}"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

# Pipeline finished (done) but digest missing → error (do not mark delivered if still running)
if grep -q "done" "${STATUS_FILE}" 2>/dev/null; then
  if pipeline_running; then
    exit 0
  fi
  if [ ! -f "${DIGEST_FILE}" ]; then
    echo "Job digest unavailable. The morning pipeline finished with an error."
    echo "Check: ${APPLYPILOT_DIR}/logs/morning_${TODAY}.log"
    touch "${DELIVERED_MARKER}"
    exit 0
  fi
fi

# Still running or not finished → silent
exit 0
