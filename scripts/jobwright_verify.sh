#!/usr/bin/env bash
# Hermes-friendly health check: doctor, status, brief status, digest preview.
# Usage: JOBWRIGHT_USER=richa bash scripts/jobwright_verify.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_jobwright_repo.sh"
REPO_ROOT="$(_jobwright_resolve_repo)"

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
  USER_FLAG=(--user "${JOBWRIGHT_USER}")
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
  USER_FLAG=()
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
LOG="${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"

echo "=== jobwright verify user=${JOBWRIGHT_USER:-legacy} ==="
echo "repo=${REPO_ROOT}"
echo "dir=${JOBWRIGHT_DIR}"
echo ""

cd "${REPO_ROOT}"
jobwright "${USER_FLAG[@]}" doctor
echo ""
jobwright "${USER_FLAG[@]}" status
echo ""

if [[ -f "${STATUS_FILE}" ]]; then
  echo "--- BRIEF_STATUS_${TODAY} ---"
  cat "${STATUS_FILE}"
  echo ""
else
  echo "No BRIEF_STATUS_${TODAY} (brief not run today)."
  echo ""
fi

if [[ -f "${DIGEST_FILE}" ]]; then
  echo "--- DIGEST preview (first 40 lines) ---"
  head -40 "${DIGEST_FILE}"
  echo ""
  echo "Full digest: ${DIGEST_FILE}"
else
  echo "No DIGEST_${TODAY} yet."
  [[ -f "${LOG}" ]] && echo "Log: ${LOG}" && tail -5 "${LOG}"
fi
