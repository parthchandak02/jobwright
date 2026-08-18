#!/usr/bin/env bash
# Deliver today's text digest to WhatsApp via hermes send.
# Usage: JOBWRIGHT_USER=<id> bash scripts/jobwright_deliver_digest.sh
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
export PATH="${HOME}/.local/bin:${PATH}"

TODAY="$(date +%Y%m%d)"
DIGEST_FILE="${JOBWRIGHT_DIR}/DIGEST_${TODAY}"
DELIVERED_MARKER="${JOBWRIGHT_DIR}/DIGEST_DELIVERED_${TODAY}"

if [[ -f "${DELIVERED_MARKER}" ]]; then
  echo "Digest already delivered today."
  exit 0
fi

if [[ ! -f "${DIGEST_FILE}" ]]; then
  echo "No digest file for today (${DIGEST_FILE})." >&2
  exit 1
fi

DELIVER="${HERMES_JOB_APPLY_DELIVER:-}"
if [[ -z "${DELIVER}" ]] && [[ -n "${JOBWRIGHT_USER:-}" ]]; then
  export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
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

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI not found; cannot deliver digest." >&2
  exit 1
fi

hermes send --to "${DELIVER}" --quiet "$(cat "${DIGEST_FILE}")"
touch "${DELIVERED_MARKER}"
echo "Delivered digest to ${DELIVER}"
