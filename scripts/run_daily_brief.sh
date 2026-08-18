#!/usr/bin/env bash
# Background daily brief: run the pipeline (discover -> connect), then send ONE
# WhatsApp notification listing newly prepared jobs with dashboard deep links.
# Multi-profile: set JOBWRIGHT_USER + JOBWRIGHT_DIR (wrappers do this).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_jobwright_repo.sh"
elif [[ -f "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh"
fi
if declare -F _jobwright_resolve_repo >/dev/null 2>&1; then
  REPO_ROOT="$(_jobwright_resolve_repo)"
elif [[ -f "$(pwd)/pyproject.toml" ]]; then
  REPO_ROOT="$(pwd)"
else
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
  USER_FLAG=(--user "${JOBWRIGHT_USER}")
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
  USER_FLAG=()
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
# API keys live in one global .env (repo root); per-user dir may add non-secret overrides.
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

export LLM_MODEL="${JOBWRIGHT_LLM_MODEL:-accounts/fireworks/models/gpt-oss-120b}"
export SCORE_BATCH_SIZE="${SCORE_BATCH_SIZE:-10}"
export APPLY_DRY_RUN=true
# Daily cron: JobSpy+Workday tier-1 only; skip smart-extract. Set DISCOVER_MODE=full for weekly deep crawl.
export DISCOVER_MODE="${DISCOVER_MODE:-fast}"
unset APPLY_LIVE 2>/dev/null || true

# Narrow E2E smoke test: 3 queries x SF+Remote, JobSpy only.
if [[ "${BRIEF_SMOKE:-}" == "1" ]]; then
  export DISCOVER_MODE=fast
  export DISCOVER_WORKDAY=0
  export JOBWRIGHT_DISCOVER_MAX_QUERIES=3
  export JOBWRIGHT_DISCOVER_LOCATIONS="San Francisco, CA|Remote"
  export JOBWRIGHT_RESULTS_PER_SITE=15
  export APPLY_MIN_SCORE="${APPLY_MIN_SCORE:-7}"
  WORKERS="${APPLY_WORKERS:-2}"
fi

MIN_SCORE="${APPLY_MIN_SCORE:-5}"
WORKERS="${WORKERS:-${APPLY_WORKERS:-4}}"
TODAY="$(date +%Y%m%d)"
LOG="${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
mkdir -p "${JOBWRIGHT_DIR}/logs"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

RC=0
finish_status() {
  echo "done RC=${RC}" >> "${STATUS_FILE}"
}
trap finish_status EXIT

python3 -m jobwright.cli "${USER_FLAG[@]}" run discover enrich score portfolio tailor cover docx connect \
  -w "${WORKERS}" --min-score "${MIN_SCORE}" --validation lenient >> "${LOG}" 2>&1 || RC=$?

if [ "${RC}" -ne 0 ]; then
  echo "pipeline_rc=${RC} (notifying on ready jobs anyway)" >> "${STATUS_FILE}"
fi

# Send one WhatsApp message listing newly prepared jobs (deep links to the
# dashboard). Skips silently when nothing new is ready. A notify failure must
# not fail the whole brief, so it is recorded but does not change RC.
if python3 -m jobwright.cli "${USER_FLAG[@]}" notify >> "${LOG}" 2>&1; then
  echo "notify_sent" >> "${STATUS_FILE}"
else
  echo "notify_failed" >> "${STATUS_FILE}"
fi
