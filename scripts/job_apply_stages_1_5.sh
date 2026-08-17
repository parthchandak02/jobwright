#!/usr/bin/env bash
# Run discovery through cover letter (stages 1-5 + portfolio).
set -euo pipefail

export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
export PATH="${HOME}/.local/bin:${PATH}"

MIN_SCORE="${APPLY_MIN_SCORE:-7}"
WORKERS="${APPLY_WORKERS:-4}"

jobwright run discover enrich score portfolio tailor cover -w "${WORKERS}" --min-score "${MIN_SCORE}"
jobwright status
