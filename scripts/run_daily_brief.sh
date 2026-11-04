#!/usr/bin/env bash
# Background daily brief: preflight (self-heals the Playwright browser), run the
# default brief stages for this user (human_gate honored by the pipeline), send
# ONE WhatsApp notification, then an operator report (alerts on problems).
# Multi-profile: set JOBWRIGHT_USER + JOBWRIGHT_DIR (wrappers do this).
#
# Deadline: preflight + pipeline must finish within JOBWRIGHT_BRIEF_TIMEOUT
# seconds (default 10800 = 3h). Each step runs in its own process group; at the
# deadline that group is killed (TERM, then KILL after 30s), the status file
# gets "timeout ...", and notify (bounded by JOBWRIGHT_NOTIFY_TIMEOUT, default
# 300s) and the brief report still run.
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
  USER_FLAG=()  # expanded as ${USER_FLAG[@]+...}: bash 3.2 + set -u rejects an empty array
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
# API keys live in one global .env (repo root); per-user dir may add non-secret overrides.
GLOBAL_ENV="${JOBWRIGHT_ENV:-${JOBWRIGHT_REPO:-${REPO_ROOT:-}}/${DOTENV}}"
[[ -f "${GLOBAL_ENV}" ]] && set -a && source "${GLOBAL_ENV}" && set +a
[[ -f "${JOBWRIGHT_DIR}/${DOTENV}" ]] && set -a && source "${JOBWRIGHT_DIR}/${DOTENV}" && set +a

# Daily brief model: glm-5p3-flash (Parth, Sep 2026; gpt-oss banned). Scoring v2
# bounds its hidden reasoning with reasoning_effort, so the old empty-response
# retries no longer happen. JOBWRIGHT_LLM_MODEL overrides.
export LLM_MODEL="${JOBWRIGHT_LLM_MODEL:-${LLM_MODEL:-accounts/fireworks/models/glm-5p3-flash}}"
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

MIN_SCORE="${APPLY_MIN_SCORE:-7}"
WORKERS="${WORKERS:-${APPLY_WORKERS:-4}}"
TODAY="$(date +%Y%m%d)"
LOG="${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"
STATUS_FILE="${JOBWRIGHT_DIR}/BRIEF_STATUS_${TODAY}"
mkdir -p "${JOBWRIGHT_DIR}/logs"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

# Python resolution: prefer the repo venv (has jobwright + playwright deps).
# Bare `python3` resolves to Homebrew, which has NEITHER — enrich then dies
# with "No module named 'playwright'" (Sep 19 evening run) and scores whatever
# descriptions already exist, silently skipping fresh detail enrichment.
if [[ -x "${REPO_ROOT}/.venv/bin/python3" ]]; then
  PY="${REPO_ROOT}/.venv/bin/python3"
else
  PY="$(command -v python3)"
fi

BRIEF_TIMEOUT="${JOBWRIGHT_BRIEF_TIMEOUT:-10800}"
NOTIFY_TIMEOUT="${JOBWRIGHT_NOTIFY_TIMEOUT:-300}"
START_EPOCH="$(date +%s)"
DEADLINE_EPOCH=$(( START_EPOCH + BRIEF_TIMEOUT ))
TIMEOUT_MARK="${JOBWRIGHT_DIR}/.brief_timeout.$$"
rm -f "${TIMEOUT_MARK}"
echo "brief_started at=$(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ timeout=${BRIEF_TIMEOUT}s" >> "${STATUS_FILE}"

# run_bounded <seconds> <cmd...>: run cmd in its own process group; kill the
# whole group (python + any browsers it started) when the time is up. Returns
# the command's exit code, or 124 when it was killed at the deadline.
run_bounded() {
  local limit="$1"; shift
  if [ "${limit}" -le 0 ]; then
    touch "${TIMEOUT_MARK}"
    return 124
  fi
  set -m  # background jobs get their own process group
  "$@" </dev/null &
  local child=$!
  set +m
  CURRENT_CHILD="${child}"
  (
    # The timer's own sleep dies with it, so no 3h sleeps are left behind.
    trap 'kill "${sp:-}" 2>/dev/null; exit 0' TERM
    sleep "${limit}" & sp=$!
    wait "${sp}"
    touch "${TIMEOUT_MARK}"
    kill -TERM -- "-${child}" 2>/dev/null || kill -TERM "${child}" 2>/dev/null
    sleep 30 & sp=$!
    wait "${sp}"
    kill -KILL -- "-${child}" 2>/dev/null || true
  ) </dev/null >/dev/null 2>&1 &
  local timer=$!
  local rc=0
  wait "${child}" || rc=$?
  CURRENT_CHILD=""
  kill "${timer}" 2>/dev/null || true
  wait "${timer}" 2>/dev/null || true
  if [ -f "${TIMEOUT_MARK}" ]; then
    return 124
  fi
  return "${rc}"
}

time_left() {
  echo $(( DEADLINE_EPOCH - $(date +%s) ))
}

record_timeout() {
  local step="$1"
  echo "timeout after $(( $(date +%s) - START_EPOCH ))s in ${step} (JOBWRIGHT_BRIEF_TIMEOUT=${BRIEF_TIMEOUT}s)" >> "${STATUS_FILE}"
  rm -f "${TIMEOUT_MARK}"
}

RC=0
CURRENT_CHILD=""
on_term() {
  if [ -n "${CURRENT_CHILD}" ]; then
    kill -TERM -- "-${CURRENT_CHILD}" 2>/dev/null || kill -TERM "${CURRENT_CHILD}" 2>/dev/null || true
  fi
  echo "killed by signal (brief launcher or operator)" >> "${STATUS_FILE}"
  RC=143
  exit "${RC}"
}
trap on_term TERM INT

finish_status() {
  rm -f "${TIMEOUT_MARK}"
  echo "done RC=${RC}" >> "${STATUS_FILE}"
  # Operator report: alerts the admin on stage failures, empty briefs, notify
  # failures (never blocks or changes RC).
  "${PY}" -m jobwright.cli ${USER_FLAG[@]+"${USER_FLAG[@]}"} ops brief-report --status-file "${STATUS_FILE}" >> "${LOG}" 2>&1 || true
}
trap finish_status EXIT

PRE_RC=0
run_bounded "$(time_left)" "${PY}" -m jobwright.cli ${USER_FLAG[@]+"${USER_FLAG[@]}"} preflight --fix >> "${LOG}" 2>&1 || PRE_RC=$?
if [ "${PRE_RC}" -ne 0 ]; then
  if [ "${PRE_RC}" -eq 124 ]; then
    record_timeout preflight
  fi
  echo "preflight_failed (see ${LOG})" >> "${STATUS_FILE}"
  RC=2
  # Non-zero so callers and schedulers see the failure; the EXIT trap still
  # writes "done RC=2" and runs ops brief-report (which alerts ops_target).
  exit "${RC}"
fi

# No explicit stage list: the pipeline picks the user's default brief stages
# (human_gate users stop before tailor/cover/docx; others run everything).
run_bounded "$(time_left)" "${PY}" -m jobwright.cli ${USER_FLAG[@]+"${USER_FLAG[@]}"} run \
  -w "${WORKERS}" --min-score "${MIN_SCORE}" --validation lenient >> "${LOG}" 2>&1 || RC=$?

if [ "${RC}" -eq 124 ]; then
  record_timeout pipeline
elif [ "${RC}" -eq 75 ]; then
  # Another run (dashboard Auto Search, a manual run) holds this profile's lock.
  echo "pipeline_locked (another run holds this profile's lock; see ${LOG})" >> "${STATUS_FILE}"
elif [ "${RC}" -ne 0 ]; then
  echo "pipeline_rc=${RC} (notifying on ready jobs anyway)" >> "${STATUS_FILE}"
fi

# One WhatsApp message (deep links to the dashboard). notify writes its own
# truthful status line: notify_sent N / notify_skipped <reason> / notify_failed.
# A notify failure must not fail the whole brief.
# Bounded separately so a pipeline timeout still delivers what is ready.
NOTIFY_RC=0
run_bounded "${NOTIFY_TIMEOUT}" "${PY}" -m jobwright.cli ${USER_FLAG[@]+"${USER_FLAG[@]}"} notify --status-file "${STATUS_FILE}" >> "${LOG}" 2>&1 || NOTIFY_RC=$?
if [ "${NOTIFY_RC}" -eq 124 ]; then
  rm -f "${TIMEOUT_MARK}"
  echo "notify_uncertain killed after ${NOTIFY_TIMEOUT}s (JOBWRIGHT_NOTIFY_TIMEOUT); jobs stay marked" >> "${STATUS_FILE}"
fi

# Exit with the pipeline result (the EXIT trap still records "done RC=N" and reports).
exit "${RC}"
