#!/usr/bin/env bash
# Print DOCX paths for digest job N (for Hermes to attach on WhatsApp).
# Usage: JOBWRIGHT_USER=richa bash jobwright_send_materials.sh 1
set -euo pipefail

INDEX="${1:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_jobwright_repo.sh"
else
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh"
fi
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

cd "${REPO_ROOT}"
jobwright "${USER_FLAG[@]}" materials --index "${INDEX}" --json
