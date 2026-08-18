#!/usr/bin/env bash
# Prune noise jobs from a user's DB (Canada sites, bad locations, excluded titles).
# Usage:
#   JOBWRIGHT_USER=richa bash scripts/cleanup_user_jobs.sh           # dry-run prune
#   JOBWRIGHT_USER=richa bash scripts/cleanup_user_jobs.sh --apply   # prune
#   JOBWRIGHT_USER=richa bash scripts/cleanup_user_jobs.sh --reset --apply  # wipe all jobs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_jobwright_repo.sh"
REPO_ROOT="$(_jobwright_resolve_repo)"

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

APPLY=false
RESET=false
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --reset) RESET=true ;;
  esac
done
if [[ "$APPLY" == true ]]; then
  DRY_RUN_PY=False
else
  DRY_RUN_PY=True
fi
if [[ "$RESET" == true ]]; then
  RESET_PY=True
else
  RESET_PY=False
fi

cd "${REPO_ROOT}"
python3 -c "
import json
import jobwright.config as cfg
from jobwright.config import set_active_user, load_env, load_search_config
from jobwright.database import init_db, close_connection
from jobwright.discovery.cleanup import prune_noise_jobs

user = __import__('os').environ.get('JOBWRIGHT_USER')
if user:
    set_active_user(user)
else:
    from pathlib import Path
    cfg.set_app_dir(Path(__import__('os').environ['JOBWRIGHT_DIR']))
load_env()
conn = init_db(cfg.DB_PATH)
search_cfg = load_search_config()
stats = prune_noise_jobs(conn, search_cfg, dry_run=${DRY_RUN_PY}, reset=${RESET_PY})
print(json.dumps(stats, indent=2))
close_connection(cfg.DB_PATH)
"
