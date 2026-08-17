#!/usr/bin/env bash
# Helper invoked by setup_hermes_cron.sh: upsert_job name schedule script deliver env_kv
# env_kv example: JOBWRIGHT_USER=richa
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_jobwright_repo.sh"
REPO_ROOT="$(_jobwright_resolve_repo)"

name="$1"
schedule="$2"
script="$3"
deliver="$4"
env_kv="$5"

find_job_id() {
  local n="$1"
  hermes cron list 2>/dev/null | awk -v name="${n}" '
    $0 ~ name { id=$1; sub(/[^a-f0-9].*$/, "", id); if (length(id) >= 8) { print id; exit } }
  '
}

script_arg="${script}"
if [[ -n "${env_kv}" ]]; then
  # env_kv is JOBWRIGHT_USER=uid — also pin JOBWRIGHT_DIR + JOBWRIGHT_REPO
  uid="${env_kv#JOBWRIGHT_USER=}"
  wrap="${HOME}/.hermes/scripts/wrap_${name}.sh"
  cat > "${wrap}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export JOBWRIGHT_USER="${uid}"
export JOBWRIGHT_DIR="\${HOME}/.jobwright-users/${uid}"
export JOBWRIGHT_REPO="${REPO_ROOT}"
export PATH="\${HOME}/.local/bin:\${PATH}"
exec bash "\${HOME}/.hermes/scripts/${script}"
EOF
  chmod 755 "${wrap}"
  script_arg="$(basename "${wrap}")"
fi

job_id="$(find_job_id "${name}" || true)"
if [[ -n "${job_id}" ]]; then
  hermes cron edit "${job_id}" \
    --schedule "${schedule}" \
    --script "${script_arg}" \
    --no-agent \
    --deliver "${deliver}" \
    --workdir "${REPO_ROOT}"
else
  hermes cron create "${schedule}" \
    --name "${name}" \
    --script "${script_arg}" \
    --no-agent \
    --deliver "${deliver}" \
    --workdir "${REPO_ROOT}"
fi
echo "Upserted cron ${name} -> ${deliver} (${schedule})"
