#!/usr/bin/env bash
# Deliver digest job N DOCX files to WhatsApp via hermes send (no LLM agent).
# Uses official MEDIA:<path> syntax in message body.
# Usage: JOBWRIGHT_USER=richa bash jobwright_deliver_materials.sh [index]
set -euo pipefail

INDEX="${1:-${AUTO_MATERIALS_INDEX:-1}}"
if [[ "${INDEX}" == "0" ]] || [[ -z "${INDEX}" ]]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_jobwright_repo.sh"
REPO_ROOT="$(_jobwright_resolve_repo)"

if [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$(_jobwright_default_user_dir "${JOBWRIGHT_USER}")}"
  USER_FLAG=(--user "${JOBWRIGHT_USER}")
else
  export JOBWRIGHT_DIR="${JOBWRIGHT_DIR:-$HOME/.jobwright}"
  USER_FLAG=()
fi
export JOBWRIGHT_REPO="${REPO_ROOT}"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

TODAY="$(date +%Y%m%d)"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/MATERIALS_DELIVERED_${TODAY}_${INDEX}"
if [[ -f "${DELIVERED_MARKER}" ]]; then
  echo "Materials ${INDEX} already delivered today."
  exit 0
fi

# Resolve WhatsApp target: env > user registry > default
DELIVER="${HERMES_JOB_APPLY_DELIVER:-}"
if [[ -z "${DELIVER}" ]] && [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  DELIVER="$(cd "${REPO_ROOT}" && python3 -c "
from jobwright.users import get_user
u = get_user('${JOBWRIGHT_USER}')
print(u.whatsapp_target if u and u.whatsapp_target else '')
" 2>/dev/null || true)"
fi
if [[ -z "${DELIVER}" ]]; then
  echo "No WhatsApp deliver target (set HERMES_JOB_APPLY_DELIVER or user whatsapp_target)." >&2
  exit 1
fi

cd "${REPO_ROOT}"
JSON="$(python3 -m jobwright.cli "${USER_FLAG[@]}" materials --index "${INDEX}" --json 2>/dev/null)" || {
  echo "Materials ${INDEX} not ready." >&2
  exit 1
}

FILES="$(python3 -c "
import json, sys
from pathlib import Path
data = json.loads(sys.argv[1])
files = [p for p in data.get('files', []) if p and Path(p).exists()]
print('\n'.join(files))
" "${JSON}")"

if [[ -z "${FILES}" ]]; then
  echo "No DOCX files for materials ${INDEX}." >&2
  exit 1
fi

TITLE="$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('title') or 'Job')" "${JSON}")"
COMPANY="$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('company') or '')" "${JSON}")"

MSG="Materials ${INDEX}: ${TITLE}"
if [[ -n "${COMPANY}" ]]; then
  MSG="${MSG} @ ${COMPANY}"
fi
while IFS= read -r fpath; do
  [[ -n "${fpath}" ]] || continue
  MSG="${MSG}"$'\n'"MEDIA:${fpath}"
done <<< "${FILES}"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI not found; cannot deliver materials." >&2
  exit 1
fi

hermes send --to "${DELIVER}" --quiet "${MSG}"
touch "${DELIVERED_MARKER}"
echo "Delivered materials ${INDEX} to ${DELIVER}"
