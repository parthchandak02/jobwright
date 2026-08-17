#!/usr/bin/env bash
# Live apply — only run after user confirmation (APPLY_CONFIRMED file exists).
# Supports multi-profile via APPLYPILOT_USER or APPLYPILOT_DIR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"

# Resolve per-user data dir
if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
  USER_FLAG=(--user "${APPLYPILOT_USER}")
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
  USER_FLAG=()
fi

DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

# Registry gate: multi-profile users must have apply_enabled=true
if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  ENABLED="$(
    cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from applypilot.users import is_apply_enabled
import sys
print('1' if is_apply_enabled('${APPLYPILOT_USER}') else '0')
" 2>/dev/null || echo 0
  )"
  if [[ "${ENABLED}" != "1" ]]; then
    echo "SKIP: Live apply disabled for user '${APPLYPILOT_USER}' (find-only). Enable: applypilot users set ${APPLYPILOT_USER} --apply"
    exit 0
  fi
fi

TODAY="$(date +%Y%m%d)"
CONFIRM_FILE="${APPLYPILOT_DIR}/APPLY_CONFIRMED"
DONE_MARKER="${APPLYPILOT_DIR}/APPLY_CONFIRMED_DONE_${TODAY}"
MANIFEST_FILE="${APPLYPILOT_DIR}/APPLY_MANIFEST_${TODAY}"
LOCK_FILE="${APPLYPILOT_DIR}/apply.lock"

if [[ -f "${DONE_MARKER}" ]]; then
  echo "SKIP: Live apply already completed today."
  exit 0
fi

if [[ ! -f "${CONFIRM_FILE}" ]]; then
  echo "SKIP: No confirmation. Morning digest sent — reply CONFIRM APPLY first."
  exit 0
fi

mkdir -p "${APPLYPILOT_DIR}"
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
export APPLYPILOT_APPLY_MANIFEST="${MANIFEST_FILE}"

LIMIT="${APPLY_LIMIT:-5}"
WORKERS="${APPLY_WORKERS:-1}"
MIN_SCORE="${APPLY_MIN_SCORE:-5}"

export APPLY_DRY_RUN=false

cd "${REPO_ROOT}"
applypilot "${USER_FLAG[@]}" apply --live --workers "${WORKERS}" --limit "${LIMIT}" --min-score "${MIN_SCORE}"
applypilot "${USER_FLAG[@]}" status

touch "${DONE_MARKER}"
echo "Live apply complete."
