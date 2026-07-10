#!/usr/bin/env bash
# Register Hermes cron jobs for the job apply pipeline.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HERMES_SCRIPTS="${HOME}/.hermes/scripts"

STAGES_SRC="${REPO_ROOT}/scripts/job_apply_stages_1_5.sh"
APPLY_SRC="${REPO_ROOT}/scripts/job_apply_stage6.sh"
STAGES_NAME="job_apply_stages_1_5.sh"
APPLY_NAME="job_apply_stage6.sh"

chmod +x "${STAGES_SRC}" "${APPLY_SRC}" "${REPO_ROOT}/bin/job-apply-pp-cli"
mkdir -p "${HERMES_SCRIPTS}"

install -m 755 "${STAGES_SRC}" "${HERMES_SCRIPTS}/${STAGES_NAME}"
install -m 755 "${APPLY_SRC}" "${HERMES_SCRIPTS}/${APPLY_NAME}"

find_job_id() {
  local name="$1"
  hermes cron list 2>/dev/null | awk -v n="${name}" '
    $0 ~ n { id=$1; sub(/[^a-f0-9].*$/, "", id); if (length(id) >= 8) { print id; exit } }
  '
}

upsert_job() {
  local name="$1"
  local schedule="$2"
  local script="$3"

  local job_id
  job_id="$(find_job_id "${name}" || true)"

  if [[ -n "${job_id}" ]]; then
    hermes cron edit "${job_id}" \
      --schedule "${schedule}" \
      --script "${script}" \
      --no-agent \
      --workdir "${REPO_ROOT}"
  else
    hermes cron create "${schedule}" \
      --name "${name}" \
      --script "${script}" \
      --no-agent \
      --deliver local \
      --workdir "${REPO_ROOT}"
  fi
}

upsert_job "job-apply-discover" "0 7 * * 1-5" "${STAGES_NAME}"
upsert_job "job-apply-submit" "0 9,17 * * 1-5" "${APPLY_NAME}"

echo "Hermes cron jobs registered (scripts in ${HERMES_SCRIPTS}):"
hermes cron list
