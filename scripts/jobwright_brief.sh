#!/usr/bin/env bash
# Daily Brief launcher: runs scripts/run_daily_brief.sh detached. Does NOT apply.
# If a brief is already running for this user it is left alone (never killed).
# Launches run_daily_brief.sh detached so cron exits instantly (300s limit).
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
PIPELINE="${REPO_ROOT}/scripts/run_daily_brief.sh"
if [[ ! -f "${PIPELINE}" ]]; then
  PIPELINE="${SCRIPT_DIR}/run_daily_brief.sh"
fi

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

# Brief model (run_daily_brief.sh re-applies this): glm-5p3-flash, gpt-oss banned.
export LLM_MODEL="${JOBWRIGHT_LLM_MODEL:-${LLM_MODEL:-accounts/fireworks/models/glm-5p3-flash}}"
export APPLY_DRY_RUN=true
unset APPLY_LIVE 2>/dev/null || true

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
mkdir -p "${JOBWRIGHT_DIR}/logs"

if [ -f "${JOBWRIGHT_DIR}/BRIEF_PID" ]; then
  OLD_PID=$(cat "${JOBWRIGHT_DIR}/BRIEF_PID" 2>/dev/null || echo "")
  if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null \
     && ps -p "${OLD_PID}" -o command= 2>/dev/null | grep -q "run_daily_brief"; then
    echo "Daily brief already running for ${JOBWRIGHT_USER:-legacy} (pid=${OLD_PID}); not starting another."
    exit 0
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
echo "${PID}" > "${JOBWRIGHT_DIR}/BRIEF_PID"
echo "${PID}" > "${JOBWRIGHT_DIR}/BRIEF_PID_${TODAY}"
echo "Detached daily brief pipeline pid=${PID} dir=${JOBWRIGHT_DIR}"
