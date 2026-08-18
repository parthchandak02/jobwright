#!/usr/bin/env bash
# Digest delivery: reads DIGEST_YYYYMMDD from the daily brief pipeline.
# Multi-profile: JOBWRIGHT_USER / JOBWRIGHT_DIR.
# Prefer AUTO_DELIVER_CHAT from run_daily_brief.sh; this script is for manual
# "send digest" and the optional staggered cron fallback.
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
REPO_ROOT="$(_jobwright_resolve_repo)" || REPO_ROOT=""
GLOBAL_ENV="${JOBWRIGHT_ENV:-}"
if [[ -z "${GLOBAL_ENV}" && -n "${REPO_ROOT}" ]]; then
  GLOBAL_ENV="${REPO_ROOT}/${DOTENV}"
fi
[[ -n "${GLOBAL_ENV}" && -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

TODAY="$(date +%Y%m%d)"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"
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

if grep -q "digest_written" "${STATUS_FILE}" 2>/dev/null && [ -f "${DIGEST_FILE}" ]; then
  cat "${DIGEST_FILE}"
  touch "${DELIVERED_MARKER}"
  exit 0
fi

if grep -q "done" "${STATUS_FILE}" 2>/dev/null; then
  if pipeline_running; then
    echo "Your daily brief is still running. I will send the digest when it finishes."
    exit 0
  fi
  if [ ! -f "${DIGEST_FILE}" ]; then
    echo "Your daily brief did not complete successfully today."
    echo 'Reply "find jobs now" to retry, or ask for job status.'
    touch "${DELIVERED_MARKER}"
    exit 0
  fi
fi

exit 0
