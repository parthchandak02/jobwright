#!/usr/bin/env bash
# Copy jobwright_*.sh into ~/.hermes/scripts/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HERMES_SCRIPTS="${HOME}/.hermes/scripts"

mkdir -p "${HERMES_SCRIPTS}"

for src in "${REPO_ROOT}"/scripts/jobwright_*.sh \
           "${REPO_ROOT}"/scripts/run_daily_brief.sh \
           "${REPO_ROOT}"/scripts/resolve_user_from_whatsapp.sh \
           "${REPO_ROOT}"/scripts/_upsert_one_cron.sh \
           "${REPO_ROOT}"/scripts/_jobwright_repo.sh; do
  [[ -f "${src}" ]] || continue
  chmod +x "${src}" 2>/dev/null || true
  install -m 755 "${src}" "${HERMES_SCRIPTS}/$(basename "${src}")"
done

# Remove legacy names if present (one-time cleanup on install)
for legacy in \
  job_apply_morning.sh job_apply_digest.sh job_apply_watchdog.sh \
  job_apply_confirm.sh job_apply_on_confirm.sh job_apply_stages_1_5.sh \
  job_apply_stage6.sh run_morning_pipeline.sh \
  jobwright_send.sh jobwright_check.sh jobwright_deliver_digest.sh \
  jobwright_deliver_materials.sh jobwright_send_materials.sh \
  jobwright_confirm.sh jobwright_on_confirm.sh; do
  rm -f "${HERMES_SCRIPTS}/${legacy}"
done

echo "Installed jobwright scripts to ${HERMES_SCRIPTS}"
