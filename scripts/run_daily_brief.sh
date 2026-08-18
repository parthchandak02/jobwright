#!/usr/bin/env bash
# Background daily brief: discover through cover, docx, connect, digest + manifest.
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

# Narrow E2E smoke test: 3 queries × SF+Remote, JobSpy only, top 3 digest jobs.
if [[ "${BRIEF_SMOKE:-}" == "1" ]]; then
  export DISCOVER_MODE=fast
  export DISCOVER_WORKDAY=0
  export JOBWRIGHT_DISCOVER_MAX_QUERIES=3
  export JOBWRIGHT_DISCOVER_LOCATIONS="San Francisco, CA|Remote"
  export JOBWRIGHT_RESULTS_PER_SITE=15
  export APPLY_LIMIT="${APPLY_LIMIT:-3}"
  export APPLY_PREP_LIMIT="${APPLY_PREP_LIMIT:-3}"
  export APPLY_MIN_SCORE="${APPLY_MIN_SCORE:-7}"
  WORKERS="${APPLY_WORKERS:-2}"
fi

MIN_SCORE="${APPLY_MIN_SCORE:-5}"
MAX_ATTEMPTS="${APPLY_MAX_ATTEMPTS:-3}"
WORKERS="${WORKERS:-${APPLY_WORKERS:-4}}"
APPLY_LIMIT="${APPLY_LIMIT:-5}"
TODAY="$(date +%Y%m%d)"
LOG="${JOBWRIGHT_DIR}/logs/brief_${TODAY}.log"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
MANIFEST_FILE="${JOBWRIGHT_DIR}/APPLY_MANIFEST_${TODAY}"
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

# Always attempt the digest/manifest, even on a non-zero pipeline RC. A partial
# failure (e.g. some jobs failed to score) must not suppress the WhatsApp brief
# when other jobs are ready. The writer no-ops gracefully when nothing is ready.
if [ "${RC}" -ne 0 ]; then
  echo "pipeline_rc=${RC} (writing digest from ready jobs anyway)" >> "${STATUS_FILE}"
fi

export DIGEST_FILE MANIFEST_FILE MIN_SCORE APPLY_LIMIT MAX_ATTEMPTS PIPELINE_RC="${RC}"
JOBWRIGHT_USER="${JOBWRIGHT_USER:-}" JOBWRIGHT_DIR="${JOBWRIGHT_DIR}" \
PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
import os
from pathlib import Path
from jobwright.config import load_env, ensure_dirs, set_active_user, set_app_dir
from jobwright.database import init_db
from jobwright.apply.launcher import (
    gather_brief_health,
    write_morning_digest_and_manifest,
)
from jobwright.users import is_apply_enabled, get_user

user_id = os.environ.get('JOBWRIGHT_USER') or None
if user_id:
    set_active_user(user_id)
else:
    set_app_dir(os.environ.get('JOBWRIGHT_DIR', str(Path.home() / '.jobwright')))

load_env()
ensure_dirs()
init_db()

pipeline_rc = int(os.environ.get('PIPELINE_RC', '0'))
health = gather_brief_health(pipeline_rc=pipeline_rc)

apply_on = is_apply_enabled(user_id) if user_id else True
label = None
if user_id:
    u = get_user(user_id)
    label = (u.name if u else user_id) or user_id

write_morning_digest_and_manifest(
    Path(os.environ['DIGEST_FILE']),
    Path(os.environ['MANIFEST_FILE']),
    min_score=int(os.environ['MIN_SCORE']),
    limit=int(os.environ['APPLY_LIMIT']),
    max_attempts=int(os.environ['MAX_ATTEMPTS']),
    apply_enabled=apply_on,
    user_label=label,
    pipeline_rc=pipeline_rc,
    health=health,
)
" >> "${LOG}" 2>&1
echo 'digest_written' >> "${STATUS_FILE}"

# Chat delivery: digest text first, then materials for job 1 (single coordinated send).
if [[ "${AUTO_DELIVER_CHAT:-1}" != "0" ]]; then
  if bash "${REPO_ROOT}/scripts/jobwright_deliver_digest.sh" >> "${LOG}" 2>&1; then
    echo "digest_delivered" >> "${STATUS_FILE}"
  else
    echo "digest_delivery_failed" >> "${STATUS_FILE}"
  fi
fi

if [[ "${AUTO_MATERIALS_INDEX:-1}" != "0" ]]; then
  bash "${REPO_ROOT}/scripts/jobwright_deliver_materials.sh" "${AUTO_MATERIALS_INDEX:-1}" \
    >> "${LOG}" 2>&1 && echo "materials_delivered index=${AUTO_MATERIALS_INDEX:-1}" >> "${STATUS_FILE}" \
    || echo "materials_delivery_failed index=${AUTO_MATERIALS_INDEX:-1}" >> "${STATUS_FILE}"
fi
