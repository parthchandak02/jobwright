#!/usr/bin/env bash
# Morning prep: discover → cover letter. Does NOT apply.
# Launches run_morning_pipeline.sh detached so cron exits instantly (300s limit).
# Multi-profile: set JOBWRIGHT_USER + JOBWRIGHT_DIR (wrappers do this).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer installed helper next to this script (Hermes), else repo scripts/
if [[ -f "${SCRIPT_DIR}/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_jobwright_repo.sh"
else
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh"
fi
REPO_ROOT="$(_jobwright_resolve_repo)"
PIPELINE="${REPO_ROOT}/scripts/run_morning_pipeline.sh"
if [[ ! -f "${PIPELINE}" ]]; then
  PIPELINE="${SCRIPT_DIR}/run_morning_pipeline.sh"
fi

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright-users/${JOBWRIGHT_USER}}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
# API keys live in one global .env (repo root); per-user dir may add non-secret overrides.
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

export LLM_MODEL="${LLM_MODEL:-gemini-2.5-flash}"
export APPLY_DRY_RUN=true
unset APPLY_LIVE 2>/dev/null || true

TODAY="$(date +%Y%m%d)"
LOG="${JOBWRIGHT_DIR}/logs/morning_${TODAY}.log"
STATUS_FILE="${JOBWRIGHT_DIR}/MORNING_STATUS_${TODAY}"
mkdir -p "${JOBWRIGHT_DIR}/logs"

rm -f "${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"

CONFIRM_FILE="${JOBWRIGHT_DIR}/APPLY_CONFIRMED"
if [[ -f "${CONFIRM_FILE}" ]]; then
  CONFIRM_DAY="$(date -r "${CONFIRM_FILE}" +%Y%m%d 2>/dev/null || stat -f %Sm -t %Y%m%d "${CONFIRM_FILE}" 2>/dev/null || echo "")"
  [[ "${CONFIRM_DAY}" != "${TODAY}" ]] && rm -f "${CONFIRM_FILE}"
fi

if [[ ! -f "${CONFIRM_FILE}" ]]; then
  rm -f "${JOBWRIGHT_DIR}/APPLY_MANIFEST_${TODAY}"
  rm -f "${JOBWRIGHT_DIR}/APPLY_CONFIRMED_DONE_${TODAY}"
fi

if [ -f "${JOBWRIGHT_DIR}/MORNING_PID" ]; then
  OLD_PID=$(cat "${JOBWRIGHT_DIR}/MORNING_PID" 2>/dev/null || echo "")
  if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
    # Kill process group if possible (pipeline uses start_new_session)
    kill -- "-${OLD_PID}" 2>/dev/null || kill "${OLD_PID}" 2>/dev/null || true
  fi
fi

echo "started user=${JOBWRIGHT_USER:-legacy} repo=${REPO_ROOT}" > "${STATUS_FILE}"

PID="$(python3 -c "
import os, subprocess, sys
repo = sys.argv[1]
script = sys.argv[2]
p = subprocess.Popen(
    ['bash', script],
    cwd=repo,
    env=os.environ,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
print(p.pid)
" "${REPO_ROOT}" "${PIPELINE}")"
echo "${PID}" > "${JOBWRIGHT_DIR}/MORNING_PID"
echo "${PID}" > "${JOBWRIGHT_DIR}/MORNING_PID_${TODAY}"
echo "Detached morning pipeline pid=${PID} dir=${JOBWRIGHT_DIR}"
