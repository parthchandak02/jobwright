#!/usr/bin/env bash
# Digest delivery: reads the digest file written by the background morning
# pipeline and delivers it. Runs as a no_agent cron later.
# Multi-profile: JOBWRIGHT_USER / JOBWRIGHT_DIR.
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

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
# API keys live in one global .env (repo root); per-user dir may add non-secret overrides.
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

TODAY="$(date +%Y%m%d)"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
STATUS_FILE="${JOBWRIGHT_DIR}/MORNING_STATUS_${TODAY}"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"
MORNING_PID_FILE="${JOBWRIGHT_DIR}/MORNING_PID_${TODAY}"

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
    echo "Check: ${JOBWRIGHT_DIR}/logs/morning_${TODAY}.log"
    touch "${DELIVERED_MARKER}"
    exit 0
  fi
fi

# Still running or not finished → silent
exit 0
