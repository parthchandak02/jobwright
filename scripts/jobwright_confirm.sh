#!/usr/bin/env bash
# User confirmation gate — run when user says CONFIRM APPLY (Hermes or manual).
# Supports multi-profile via JOBWRIGHT_USER.
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

CONFIRM_FILE="${JOBWRIGHT_DIR}/APPLY_CONFIRMED"
mkdir -p "${JOBWRIGHT_DIR}"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${CONFIRM_FILE}"
chmod 600 "${CONFIRM_FILE}"
echo "Confirmed for ${JOBWRIGHT_DIR}."
echo "Run: JOBWRIGHT_USER=${JOBWRIGHT_USER:-} bash ~/.hermes/scripts/jobwright_on_confirm.sh"
