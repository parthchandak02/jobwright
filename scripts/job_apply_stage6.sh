#!/usr/bin/env bash
# Run stage-6 browser apply via Cursor agent.
set -euo pipefail

export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
export PATH="${HOME}/.local/bin:${PATH}"
export AGENT_PROVIDER="${AGENT_PROVIDER:-cursor-sdk}"
export APPLY_AGENT_MODEL="${APPLY_AGENT_MODEL:-composer-2.5}"

LIMIT="${APPLY_LIMIT:-5}"
WORKERS="${APPLY_MAX_WORKERS:-2}"
MIN_SCORE="${APPLY_MIN_SCORE:-7}"
DRY_RUN="${APPLY_DRY_RUN:-true}"

ARGS=(apply --workers "${WORKERS}" --limit "${LIMIT}" --min-score "${MIN_SCORE}")

if [[ "${DRY_RUN}" == "true" || "${DRY_RUN}" == "1" ]]; then
  ARGS+=(--dry-run)
fi

applypilot "${ARGS[@]}"
applypilot status
