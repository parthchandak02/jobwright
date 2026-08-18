#!/usr/bin/env bash
# Register Hermes cron jobs for multi-profile Daily Brief.
# Creates brief + send + check cron per registry user.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_DELIVER="${HERMES_JOB_APPLY_DELIVER:-whatsapp:120363427933075836}"
UPSERT="${SCRIPT_DIR}/_upsert_one_cron.sh"

"${SCRIPT_DIR}/install_hermes_scripts.sh"
chmod +x "${UPSERT}"

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

# Remove all old naming
for name in job-apply-discover job-apply-submit \
  job-apply-morning job-apply-digest job-apply-watchdog; do
  pause_or_delete_legacy "${name}"
done

USERS_JSON="$(
  cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
import json
from jobwright.users import list_users
users = [
    {
        'user_id': u.user_id,
        'whatsapp_target': u.whatsapp_target,
        'schedule': u.schedule,
        'digest_schedule': u.digest_schedule,
    }
    for u in list_users()
]
print(json.dumps(users))
" 2>/dev/null || echo '[]'
)"

USER_COUNT="$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])))" "${USERS_JSON}")"

if [[ "${USER_COUNT}" -eq 0 ]]; then
  echo "No registry users — registering single-user crons."
  bash "${UPSERT}" "jobwright-brief" "0 6 * * *" "jobwright_brief.sh" "${DEFAULT_DELIVER}" ""
  bash "${UPSERT}" "jobwright-send" "30 6 * * *" "jobwright_send.sh" "${DEFAULT_DELIVER}" ""
  bash "${UPSERT}" "jobwright-check" "0 10 * * *" "jobwright_check.sh" "${DEFAULT_DELIVER}" ""
else
  python3 - <<PY
import json, subprocess, sys
users = json.loads("""${USERS_JSON}""")
upsert = "${UPSERT}"
default_deliver = "${DEFAULT_DELIVER}"
for u in users:
    uid = u["user_id"]
    deliver = u.get("whatsapp_target") or default_deliver
    if not deliver:
        print(f"SKIP {uid}: no whatsapp_target", file=sys.stderr)
        continue
    sched = u.get("schedule") or "0 6 * * *"
    dig = u.get("digest_schedule") or "30 6 * * *"
    env = f"JOBWRIGHT_USER={uid}"
    for name, schedule, script in [
        (f"jobwright-brief-{uid}", sched, "jobwright_brief.sh"),
        (f"jobwright-send-{uid}", dig, "jobwright_send.sh"),
        (f"jobwright-check-{uid}", "0 10 * * *", "jobwright_check.sh"),
    ]:
        subprocess.check_call(["bash", upsert, name, schedule, script, deliver, env])
PY
  for uid in $(python3 -c "import json,sys; print(' '.join(u['user_id'] for u in json.loads(sys.argv[1])))" "${USERS_JSON}"); do
    pause_or_delete_legacy "job-apply-morning-${uid}"
    pause_or_delete_legacy "job-apply-digest-${uid}"
    pause_or_delete_legacy "job-apply-watchdog-${uid}"
  done
fi

echo "Hermes cron jobs registered (scripts in ${HOME}/.hermes/scripts):"
hermes cron list
