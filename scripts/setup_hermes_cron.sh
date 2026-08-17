#!/usr/bin/env bash
# Register Hermes cron jobs for multi-profile job pipeline.
# Creates morning + digest + watchdog cron per registry user.
# Legacy single-user (~/.applypilot) kept if no registry users exist.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_DELIVER="${HERMES_JOB_APPLY_DELIVER:-whatsapp:120363427933075836}"
UPSERT="${SCRIPT_DIR}/_upsert_one_cron.sh"

"${SCRIPT_DIR}/install_hermes_scripts.sh"
chmod +x "${UPSERT}"

pause_legacy_job() {
  local name="$1"
  local job_id
  job_id="$(hermes cron list 2>/dev/null | awk -v n="${name}" '
    $0 ~ n { id=$1; sub(/[^a-f0-9].*$/, "", id); if (length(id) >= 8) { print id; exit } }
  ')"
  if [[ -n "${job_id}" ]]; then
    hermes cron pause "${job_id}" 2>/dev/null || true
    echo "Paused legacy cron: ${name} (${job_id})"
  fi
}

pause_legacy_job "job-apply-discover"
pause_legacy_job "job-apply-submit"

USERS_JSON="$(
  cd "${REPO_ROOT}" && PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
import json
from applypilot.users import list_users
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
  echo "No registry users — registering legacy single-user crons."
  bash "${UPSERT}" "job-apply-morning" "0 5 * * 1-5" "job_apply_morning.sh" "${DEFAULT_DELIVER}" ""
  bash "${UPSERT}" "job-apply-digest" "0 6-10 * * 1-5" "job_apply_digest.sh" "${DEFAULT_DELIVER}" ""
  bash "${UPSERT}" "job-apply-watchdog" "0 11 * * 1-5" "job_apply_watchdog.sh" "${DEFAULT_DELIVER}" ""
else
  # Keep legacy crons running unless explicitly paused (Parth's ~/.applypilot).
  # Multi-user crons are namespaced: job-apply-morning-<id>, etc.
  if [[ "${PAUSE_LEGACY:-0}" == "1" ]]; then
    pause_legacy_job "job-apply-morning"
    pause_legacy_job "job-apply-digest"
    pause_legacy_job "job-apply-watchdog"
  else
    echo "Keeping legacy job-apply-* crons active (set PAUSE_LEGACY=1 to pause them)."
  fi

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
    sched = u.get("schedule") or "0 */3 * * 1-5"
    dig = u.get("digest_schedule") or "15 */3 * * 1-5"
    env = f"APPLYPILOT_USER={uid}"
    for name, schedule, script in [
        (f"job-apply-morning-{uid}", sched, "job_apply_morning.sh"),
        (f"job-apply-digest-{uid}", dig, "job_apply_digest.sh"),
        (f"job-apply-watchdog-{uid}", "0 11 * * 1-5", "job_apply_watchdog.sh"),
    ]:
        subprocess.check_call(["bash", upsert, name, schedule, script, deliver, env])
PY
fi

echo "Hermes cron jobs registered (scripts in ${HOME}/.hermes/scripts):"
hermes cron list
