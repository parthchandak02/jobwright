#!/usr/bin/env bash
# User confirmation gate — run when user says CONFIRM APPLY (Hermes or manual).
# Supports multi-profile via APPLYPILOT_USER.
set -euo pipefail

if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
fi

CONFIRM_FILE="${APPLYPILOT_DIR}/APPLY_CONFIRMED"
mkdir -p "${APPLYPILOT_DIR}"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${CONFIRM_FILE}"
chmod 600 "${CONFIRM_FILE}"
echo "Confirmed for ${APPLYPILOT_DIR}."
echo "Run: APPLYPILOT_USER=${APPLYPILOT_USER:-} scripts/job_apply_on_confirm.sh"
