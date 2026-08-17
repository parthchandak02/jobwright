#!/usr/bin/env bash
# Morning prep: discover → cover letter. Does NOT apply.
# Launches run_morning_pipeline.sh detached so cron exits instantly (300s limit).
# Multi-profile: set APPLYPILOT_USER + APPLYPILOT_DIR (wrappers do this).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer installed helper next to this script (Hermes), else repo scripts/
if [[ -f "${SCRIPT_DIR}/_applypilot_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_applypilot_repo.sh"
else
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_applypilot_repo.sh"
fi
REPO_ROOT="$(_applypilot_resolve_repo)"
PIPELINE="${REPO_ROOT}/scripts/run_morning_pipeline.sh"
if [[ ! -f "${PIPELINE}" ]]; then
  PIPELINE="${SCRIPT_DIR}/run_morning_pipeline.sh"
fi

if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
fi
export APPLYPILOT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

export LLM_MODEL="${LLM_MODEL:-gemini-2.5-flash}"
export APPLY_DRY_RUN=true
unset APPLY_LIVE 2>/dev/null || true

TODAY="$(date +%Y%m%d)"
LOG="${APPLYPILOT_DIR}/logs/morning_${TODAY}.log"
STATUS_FILE="${APPLYPILOT_DIR}/MORNING_STATUS_${TODAY}"
mkdir -p "${APPLYPILOT_DIR}/logs"

rm -f "${APPLYPILOT_DIR}/DIGEST_DELIVERED_${TODAY}"

CONFIRM_FILE="${APPLYPILOT_DIR}/APPLY_CONFIRMED"
if [[ -f "${CONFIRM_FILE}" ]]; then
  CONFIRM_DAY="$(date -r "${CONFIRM_FILE}" +%Y%m%d 2>/dev/null || stat -f %Sm -t %Y%m%d "${CONFIRM_FILE}" 2>/dev/null || echo "")"
  [[ "${CONFIRM_DAY}" != "${TODAY}" ]] && rm -f "${CONFIRM_FILE}"
fi

if [[ ! -f "${CONFIRM_FILE}" ]]; then
  rm -f "${APPLYPILOT_DIR}/APPLY_MANIFEST_${TODAY}"
  rm -f "${APPLYPILOT_DIR}/APPLY_CONFIRMED_DONE_${TODAY}"
fi

if [ -f "${APPLYPILOT_DIR}/MORNING_PID" ]; then
  OLD_PID=$(cat "${APPLYPILOT_DIR}/MORNING_PID" 2>/dev/null || echo "")
  if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
    # Kill process group if possible (pipeline uses start_new_session)
    kill -- "-${OLD_PID}" 2>/dev/null || kill "${OLD_PID}" 2>/dev/null || true
  fi
fi

echo "started user=${APPLYPILOT_USER:-legacy} repo=${REPO_ROOT}" > "${STATUS_FILE}"

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
echo "${PID}" > "${APPLYPILOT_DIR}/MORNING_PID"
echo "${PID}" > "${APPLYPILOT_DIR}/MORNING_PID_${TODAY}"
echo "Detached morning pipeline pid=${PID} dir=${APPLYPILOT_DIR}"
