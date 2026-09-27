#!/usr/bin/env bash
# Register Hermes cron jobs for multi-profile Daily Brief.
# Creates ONE daily brief cron per registry user (jobwright-brief-<uid>).
# The brief runs the pipeline then `jobwright notify` (single WhatsApp list).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

"${SCRIPT_DIR}/install_hermes_scripts.sh"

pause_or_delete_legacy() {
  local name="$1"
  local job_id
  job_id="$(hermes cron list 2>/dev/null | awk -v name="${name}" '
    /^[[:space:]]+[a-f0-9]{8,}/ {
      id = $1
      gsub(/^[[:space:]]+/, "", id)
      sub(/ .*/, "", id)
    }
    $0 ~ "Name:[[:space:]]+" name "[[:space:]]*$" {
      if (id != "") { print id; exit }
    }
  ')"
  if [[ -n "${job_id}" ]]; then
    hermes cron pause "${job_id}" 2>/dev/null || true
    hermes cron delete "${job_id}" 2>/dev/null || true
    echo "Removed legacy cron: ${name} (${job_id})"
  fi
}

# Remove all old naming (incl. retired send/check crons from the old flow)
for name in job-apply-discover job-apply-submit \
  job-apply-morning job-apply-digest job-apply-watchdog \
  jobwright-send jobwright-check; do
  pause_or_delete_legacy "${name}"
done

PY="${REPO_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
USER_IDS="$(cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" "${PY}" -c "
from jobwright.users import list_users
print(' '.join(u.user_id for u in list_users()))
")"
for uid in ${USER_IDS}; do
  for legacy in "job-apply-morning-${uid}" "job-apply-digest-${uid}" \
    "job-apply-watchdog-${uid}" "jobwright-send-${uid}" "jobwright-check-${uid}"; do
    pause_or_delete_legacy "${legacy}"
  done
done

# Brief crons deliver to "local": the brief sends its own WhatsApp list, so a
# bridge outage cannot turn a finished run into a failed delivery.
(cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" "${PY}" -m jobwright.cli ops install-crons "$@")

echo "Hermes cron jobs registered (scripts in ${HOME}/.hermes/scripts):"
hermes cron list
