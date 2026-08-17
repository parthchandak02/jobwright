#!/usr/bin/env bash
# Resolve the repo root even when this script lives under ~/.hermes/scripts/.
# Order: explicit APPLYPILOT_REPO env -> git checkout of the caller -> common
# install paths (jobwright and legacy applypilot-cursor) -> SCRIPT_DIR/..
_applypilot_resolve_repo() {
  if [[ -n "${APPLYPILOT_REPO:-}" && -f "${APPLYPILOT_REPO}/pyproject.toml" ]]; then
    echo "${APPLYPILOT_REPO}"
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
    "${HOME}/projects/applypilot-cursor" \
    "/Users/parthchandak/projects/jobwright" \
    "/Users/parthchandak/projects/applypilot-cursor" \
    "/Volumes/ExternalSSD/Projects/jobwright" \
    "/Volumes/ExternalSSD/Projects/applypilot-cursor"
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
  echo "ERROR: Cannot find the jobwright repo. Set APPLYPILOT_REPO." >&2
  return 1
}
