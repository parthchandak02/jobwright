#!/usr/bin/env bash
# Install the personal-data guard as pre-commit and pre-push hooks (keeps existing hooks).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOKS="$(git rev-parse --git-common-dir)/hooks"
MARK="# jobwright-privacy-guard"
PY='PY="$(git rev-parse --show-toplevel)/.venv/bin/python3"; [ -x "$PY" ] || PY=python3;'
add_hook() {
  local name="$1" line="$2" file="${HOOKS}/$1"
  [[ -f "${file}" ]] || printf '#!/usr/bin/env bash\n' > "${file}"
  grep -q "${MARK}" "${file}" || printf '%s\n%s\n' "${MARK}" "${line}" >> "${file}"
  chmod +x "${file}"
  echo "installed ${name}"
}
if [[ -f "${HOOKS}/pre-commit" ]] && grep -q '^git secrets --pre_commit_hook -- "\$@"$' "${HOOKS}/pre-commit"; then
  sed -i.bak 's/^git secrets --pre_commit_hook -- "\$@"$/git secrets --pre_commit_hook -- "$@" || exit 1/' "${HOOKS}/pre-commit" && rm -f "${HOOKS}/pre-commit.bak"
fi
add_hook pre-commit "${PY} \"\$PY\" \"\$(git rev-parse --show-toplevel)/scripts/check_private_data.py\" --staged || exit 1"
add_hook pre-push "${PY}"' while read -r _l lsha _r rsha; do case "$lsha" in *[!0]*) ;; *) continue ;; esac; case "$rsha" in *[!0]*) range="$rsha..$lsha" ;; *) range="$lsha" ;; esac; "$PY" "$(git rev-parse --show-toplevel)/scripts/check_private_data.py" --push "$range" || exit 1; done'
