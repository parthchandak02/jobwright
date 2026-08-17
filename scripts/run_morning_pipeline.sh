#!/usr/bin/env bash
# Background morning pipeline: discover through cover, digest + manifest write.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/_applypilot_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_applypilot_repo.sh"
elif [[ -f "${SCRIPT_DIR}/../scripts/_applypilot_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_applypilot_repo.sh"
fi
if declare -F _applypilot_resolve_repo >/dev/null 2>&1; then
  REPO_ROOT="$(_applypilot_resolve_repo)"
elif [[ -f "$(pwd)/pyproject.toml" ]]; then
  REPO_ROOT="$(pwd)"
else
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

if [[ -n "${APPLYPILOT_USER:-}" ]]; then
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot-users/${APPLYPILOT_USER}}"
  USER_FLAG=(--user "${APPLYPILOT_USER}")
else
  export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
  USER_FLAG=()
fi
export APPLYPILOT_REPO="${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

export LLM_MODEL="${LLM_MODEL:-gemini-2.5-flash}"
export APPLY_DRY_RUN=true
unset APPLY_LIVE 2>/dev/null || true

MIN_SCORE="${APPLY_MIN_SCORE:-5}"
MAX_ATTEMPTS="${APPLY_MAX_ATTEMPTS:-3}"
WORKERS="${APPLY_WORKERS:-4}"
APPLY_LIMIT="${APPLY_LIMIT:-5}"
TODAY="$(date +%Y%m%d)"
LOG="${APPLYPILOT_DIR}/logs/morning_${TODAY}.log"
DIGEST_FILE="${APPLYPILOT_DIR}/DIGEST_${TODAY}"
MANIFEST_FILE="${APPLYPILOT_DIR}/APPLY_MANIFEST_${TODAY}"
STATUS_FILE="${APPLYPILOT_DIR}/MORNING_STATUS_${TODAY}"
mkdir -p "${APPLYPILOT_DIR}/logs"

cd "${REPO_ROOT}"

RC=0
finish_status() {
  echo "done RC=${RC}" >> "${STATUS_FILE}"
}
trap finish_status EXIT

applypilot "${USER_FLAG[@]}" run discover enrich score portfolio tailor cover \
  -w "${WORKERS}" --min-score "${MIN_SCORE}" --validation lenient >> "${LOG}" 2>&1 || RC=$?

if [ "${RC}" -eq 0 ]; then
  export DIGEST_FILE MANIFEST_FILE MIN_SCORE APPLY_LIMIT MAX_ATTEMPTS
  APPLYPILOT_USER="${APPLYPILOT_USER:-}" APPLYPILOT_DIR="${APPLYPILOT_DIR}" \
  PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
import os
from pathlib import Path
from applypilot.config import load_env, ensure_dirs, set_active_user, set_app_dir
from applypilot.database import init_db
from applypilot.apply.launcher import write_morning_digest_and_manifest
from applypilot.users import is_apply_enabled, get_user

user_id = os.environ.get('APPLYPILOT_USER') or None
if user_id:
    set_active_user(user_id)
else:
    set_app_dir(os.environ.get('APPLYPILOT_DIR', str(Path.home() / '.applypilot')))

load_env()
ensure_dirs()
init_db()

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
)
" >> "${LOG}" 2>&1
  echo 'digest_written' >> "${STATUS_FILE}"
fi
