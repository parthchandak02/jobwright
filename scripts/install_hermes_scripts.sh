#!/usr/bin/env bash
# Copy job_apply_*.sh (and run_morning_pipeline.sh) into ~/.hermes/scripts/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HERMES_SCRIPTS="${HOME}/.hermes/scripts"

mkdir -p "${HERMES_SCRIPTS}"

for src in "${REPO_ROOT}"/scripts/job_apply_*.sh \
           "${REPO_ROOT}"/scripts/run_morning_pipeline.sh \
           "${REPO_ROOT}"/scripts/resolve_user_from_whatsapp.sh \
           "${REPO_ROOT}"/scripts/_upsert_one_cron.sh \
           "${REPO_ROOT}"/scripts/_jobwright_repo.sh; do
  [[ -f "${src}" ]] || continue
  chmod +x "${src}"
  install -m 755 "${src}" "${HERMES_SCRIPTS}/$(basename "${src}")"
done

echo "Installed job apply scripts to ${HERMES_SCRIPTS}"
