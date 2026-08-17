#!/usr/bin/env bash
# User confirmation gate — run when user says CONFIRM APPLY (Hermes or manual).
# Supports multi-profile via JOBWRIGHT_USER.
set -euo pipefail

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright-users/${JOBWRIGHT_USER}}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi

CONFIRM_FILE="${JOBWRIGHT_DIR}/APPLY_CONFIRMED"
mkdir -p "${JOBWRIGHT_DIR}"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${CONFIRM_FILE}"
chmod 600 "${CONFIRM_FILE}"
echo "Confirmed for ${JOBWRIGHT_DIR}."
echo "Run: JOBWRIGHT_USER=${JOBWRIGHT_USER:-} scripts/job_apply_on_confirm.sh"
