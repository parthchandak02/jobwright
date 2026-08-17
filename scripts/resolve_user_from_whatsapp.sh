#!/usr/bin/env bash
# Resolve JOBWRIGHT_USER from a WhatsApp JID / deliver target.
# Usage: resolve_user_from_whatsapp.sh whatsapp:120363...@g.us
# Prints user_id on stdout; exit 1 if unknown.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/_jobwright_repo.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/_jobwright_repo.sh"
else
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../scripts/_jobwright_repo.sh"
fi
REPO_ROOT="$(_jobwright_resolve_repo)"
TARGET="${1:?usage: resolve_user_from_whatsapp.sh whatsapp:...}"

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -c "
from jobwright.users import find_user_by_whatsapp
u = find_user_by_whatsapp('''${TARGET}''')
if u is None:
    raise SystemExit(1)
print(u.user_id)
"
