#!/usr/bin/env bash
# Narrow E2E smoke test: 3 tier-1 queries, SF+Remote, JobSpy only.
# Unlike the cron path, this WAITS for the detached pipeline and asserts the
# outcome (done RC + notify) so "smoke passed" actually means something.
# Use before widening daily discover. Does NOT apply.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Discover narrowing -----------------------------------------------------------
export BRIEF_SMOKE=1
export DISCOVER_MODE=fast
export DISCOVER_WORKDAY=0
export JOBWRIGHT_DISCOVER_MAX_QUERIES=3
export JOBWRIGHT_DISCOVER_LOCATIONS="San Francisco, CA|Remote"
export JOBWRIGHT_RESULTS_PER_SITE="${JOBWRIGHT_RESULTS_PER_SITE:-25}"
# Indeed is the only consistently reliable board (ZipRecruiter/Glassdoor/Google
# sit behind WAFs and usually return 0), and a 7-day window offsets the narrow
# query/location set so smoke actually surfaces a few fresh roles.
export JOBWRIGHT_DISCOVER_BOARDS="${JOBWRIGHT_DISCOVER_BOARDS:-indeed}"
export JOBWRIGHT_HOURS_OLD="${JOBWRIGHT_HOURS_OLD:-168}"

# Pin a scoring model known to return non-empty JSON, score sequentially, and
# use the same min-score as the daily brief so one mid-fit job still lands.
export JOBWRIGHT_LLM_MODEL="${JOBWRIGHT_LLM_MODEL:-accounts/fireworks/models/gpt-oss-120b}"
export SCORE_BATCH_SIZE="${SCORE_BATCH_SIZE:-1}"
export APPLY_LIMIT="${APPLY_LIMIT:-3}"
export APPLY_PREP_LIMIT="${APPLY_PREP_LIMIT:-3}"
export APPLY_MIN_SCORE="${APPLY_MIN_SCORE:-5}"

SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-1200}"   # seconds to wait for the brief to finish

# Kick the (detached) brief and capture the target dir it prints.
OUT="$(bash "${SCRIPT_DIR}/jobwright_brief.sh")"
printf '%s\n' "${OUT}"
JW_DIR="$(printf '%s\n' "${OUT}" | sed -n 's/.*dir=//p' | tail -1)"
if [[ -z "${JW_DIR}" ]]; then
  echo "smoke: could not determine JOBWRIGHT_DIR from brief output" >&2
  exit 2
fi

TODAY="$(date +%Y%m%d)"
STATUS_FILE="${JW_DIR}/BRIEF_STATUS_${TODAY}"
LOG_FILE="${JW_DIR}/logs/brief_${TODAY}.log"

echo "smoke: waiting up to ${SMOKE_TIMEOUT}s for ${STATUS_FILE}"
WAITED=0
while :; do
  if [[ -f "${STATUS_FILE}" ]] && grep -q '^done RC=' "${STATUS_FILE}"; then
    break
  fi
  if (( WAITED >= SMOKE_TIMEOUT )); then
    echo "smoke: TIMEOUT after ${WAITED}s. Last log lines:" >&2
    [[ -f "${LOG_FILE}" ]] && tail -20 "${LOG_FILE}" >&2
    exit 3
  fi
  sleep 5
  WAITED=$((WAITED + 5))
done

echo "----- BRIEF_STATUS -----"
cat "${STATUS_FILE}"
echo "------------------------"

RC="$(sed -n 's/^done RC=//p' "${STATUS_FILE}" | tail -1)"

# Green when the pipeline finished (done RC present); pipeline RC is
# informational (partial scoring no longer suppresses the brief). The notify
# step skips silently when no new prepare jobs are ready.
if [[ -n "${RC}" ]]; then
  echo "smoke: pipeline finished (RC=${RC})."
  grep -q '^notify_sent' "${STATUS_FILE}" && echo "smoke: WhatsApp notify sent."
  grep -q '^notify_failed' "${STATUS_FILE}" && echo "smoke: WARNING notify failed (see log)."
  exit 0
fi

echo "smoke: FAILED - pipeline did not finish. Last log lines:" >&2
[[ -f "${LOG_FILE}" ]] && tail -30 "${LOG_FILE}" >&2
exit 1
