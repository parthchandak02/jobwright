#!/usr/bin/env bash
# Live apply — only run after user confirmation (APPLY_CONFIRMED file exists).
set -euo pipefail

export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

CONFIRM_FILE="${APPLYPILOT_DIR}/APPLY_CONFIRMED"
if [[ ! -f "${CONFIRM_FILE}" ]]; then
  echo "SKIP: No confirmation. Morning digest sent — reply CONFIRM APPLY first."
  exit 0
fi

LIMIT="${APPLY_LIMIT:-5}"
WORKERS="${APPLY_MAX_WORKERS:-1}"
MIN_SCORE="${APPLY_MIN_SCORE:-5}"

export APPLY_DRY_RUN=false

applypilot apply --live --workers "${WORKERS}" --limit "${LIMIT}" --min-score "${MIN_SCORE}"
applypilot status

rm -f "${CONFIRM_FILE}"
echo "Live apply complete. Confirmation gate cleared."
