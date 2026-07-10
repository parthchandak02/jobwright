#!/usr/bin/env bash
# Run discovery through cover letter (stages 1-5 + portfolio).
set -euo pipefail

export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
export PATH="${HOME}/.local/bin:${PATH}"

MIN_SCORE="${APPLY_MIN_SCORE:-7}"
WORKERS="${APPLY_WORKERS:-4}"

applypilot run discover enrich score portfolio tailor cover -w "${WORKERS}" --min-score "${MIN_SCORE}"
applypilot status
