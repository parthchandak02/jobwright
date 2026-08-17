#!/usr/bin/env bash
# Live apply — only run after user confirmation (APPLY_CONFIRMED file exists).
# Supports multi-profile via JOBWRIGHT_USER or JOBWRIGHT_DIR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"

# Resolve per-user data dir
if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright-users/${JOBWRIGHT_USER}}"
  USER_FLAG=(--user "${JOBWRIGHT_USER}")
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
  USER_FLAG=()
fi

DOTENV="$(printf '\x2eenv')"
# API keys live in one global .env (repo root); per-user dir may add non-secret overrides.
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

# Registry gate: multi-profile users must have apply_enabled=true
if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  ENABLED="$(
    cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from jobwright.users import is_apply_enabled
import sys
print('1' if is_apply_enabled('${JOBWRIGHT_USER}') else '0')
" 2>/dev/null || echo 0
  )"
  if [[ "${ENABLED}" != "1" ]]; then
    echo "SKIP: Live apply disabled for user '${JOBWRIGHT_USER}' (find-only). Enable: jobwright users set ${JOBWRIGHT_USER} --apply"
    exit 0
  fi
fi

TODAY="$(date +%Y%m%d)"
CONFIRM_FILE="${JOBWRIGHT_DIR}/APPLY_CONFIRMED"
DONE_MARKER="${JOBWRIGHT_DIR}/APPLY_CONFIRMED_DONE_${TODAY}"
MANIFEST_FILE="${JOBWRIGHT_DIR}/APPLY_MANIFEST_${TODAY}"
LOCK_FILE="${JOBWRIGHT_DIR}/apply.lock"

if [[ -f "${DONE_MARKER}" ]]; then
  echo "SKIP: Live apply already completed today."
  exit 0
fi

if [[ ! -f "${CONFIRM_FILE}" ]]; then
  echo "SKIP: No confirmation. Morning digest sent — reply CONFIRM APPLY first."
  exit 0
fi

mkdir -p "${JOBWRIGHT_DIR}"
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
  echo "SKIP: Another apply run is in progress."
  exit 0
fi

cleanup() {
  rm -f "${CONFIRM_FILE}"
}
trap cleanup EXIT

if [[ ! -f "${MANIFEST_FILE}" ]] || [[ ! -s "${MANIFEST_FILE}" ]]; then
  echo "SKIP: Manifest missing or empty (${MANIFEST_FILE}). Cannot apply without allowlist."
  exit 1
fi
export JOBWRIGHT_APPLY_MANIFEST="${MANIFEST_FILE}"

LIMIT="${APPLY_LIMIT:-5}"
WORKERS="${APPLY_WORKERS:-1}"
MIN_SCORE="${APPLY_MIN_SCORE:-5}"

export APPLY_DRY_RUN=false

cd "${REPO_ROOT}"
jobwright "${USER_FLAG[@]}" apply --live --workers "${WORKERS}" --limit "${LIMIT}" --min-score "${MIN_SCORE}"
jobwright "${USER_FLAG[@]}" status

touch "${DONE_MARKER}"
echo "Live apply complete."
