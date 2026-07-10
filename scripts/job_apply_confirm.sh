#!/usr/bin/env bash
# User confirmation gate — run when user says CONFIRM APPLY (Hermes or manual).
set -euo pipefail

export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
CONFIRM_FILE="${APPLYPILOT_DIR}/APPLY_CONFIRMED"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${CONFIRM_FILE}"
chmod 600 "${CONFIRM_FILE}"
echo "Confirmed. Run: scripts/job_apply_on_confirm.sh"
echo "Or: hermes cron run job-apply-live (if scheduled)"
