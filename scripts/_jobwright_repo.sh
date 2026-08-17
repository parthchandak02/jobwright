#!/usr/bin/env bash
# Resolve the repo root even when this script lives under ~/.hermes/scripts/.
# Order: explicit JOBWRIGHT_REPO env -> git checkout of the caller -> common
# install paths -> SCRIPT_DIR/..
_jobwright_resolve_repo() {
  if [[ -n "${JOBWRIGHT_REPO:-}" && -f "${JOBWRIGHT_REPO}/pyproject.toml" ]]; then
    echo "${JOBWRIGHT_REPO}"
    return 0
  fi
  # If the caller lives inside the git checkout, trust the toplevel.
  local caller_dir top
  caller_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}")" 2>/dev/null && pwd)"
  if top="$(git -C "${caller_dir}" rev-parse --show-toplevel 2>/dev/null)" \
     && [[ -f "${top}/pyproject.toml" ]]; then
    echo "${top}"
    return 0
  fi
  local cand
  for cand in \
    "${HOME}/projects/jobwright" \
    "/Volumes/ExternalSSD/Projects/jobwright"
  do
    if [[ -f "${cand}/pyproject.toml" ]]; then
      echo "${cand}"
      return 0
    fi
  done
  # Last resort: SCRIPT_DIR/.. (dev checkout, scripts run in place).
  if [[ -f "${caller_dir}/../pyproject.toml" ]]; then
    echo "$(cd "${caller_dir}/.." && pwd)"
    return 0
  fi
  echo "ERROR: Cannot find the jobwright repo. Set JOBWRIGHT_REPO." >&2
  return 1
}

_jobwright_users_root() {
  if [[ -n "${JOBWRIGHT_USERS_ROOT:-}" ]]; then
    echo "${JOBWRIGHT_USERS_ROOT}"
    return 0
  fi
  local repo
  repo="$(_jobwright_resolve_repo)" || return 1
  echo "${repo}/users"
}

_jobwright_default_user_dir() {
  local uid="$1"
  local root
  root="$(_jobwright_users_root)" || return 1
  echo "${root}/${uid}"
}
