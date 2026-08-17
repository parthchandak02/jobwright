#!/usr/bin/env bash
# Install thin pp-job-apply loader into Hermes, Cursor, and .agents/skills.
# Canonical docs stay in the repo (AGENTS.md, docs/agents/). The installed skill
# only records JOBWRIGHT_REPO and points back to those files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${REPO_ROOT}/templates/hermes-skill/SKILL.md"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "ERROR: Missing ${TEMPLATE}" >&2
  exit 1
fi

install_loader() {
  local dst="$1"
  if [[ -e "${dst}" ]]; then
    rm -rf "${dst}"
  fi
  mkdir -p "${dst}"
  cp "${TEMPLATE}" "${dst}/SKILL.md"
  printf '%s\n' "${REPO_ROOT}" > "${dst}/JOBWRIGHT_REPO"
  echo "  ${dst}"
}

echo "Installing pp-job-apply thin loader (JOBWRIGHT_REPO=${REPO_ROOT})"
echo ""

mkdir -p "${HOME}/.cursor/skills" \
  "${HOME}/.hermes/skills/autonomous-ai-agents" \
  "${HOME}/.agents/skills"

install_loader "${HOME}/.cursor/skills/pp-job-apply"
install_loader "${HOME}/.hermes/skills/autonomous-ai-agents/pp-job-apply"
install_loader "${HOME}/.hermes/skills/autonomous-ai-agents/jobwright"
install_loader "${HOME}/.agents/skills/pp-job-apply"
install_loader "${HOME}/.hermes/skills/pp-job-apply"

echo ""
echo "Canonical agent docs (in repo, not in skill dir):"
echo "  ${REPO_ROOT}/AGENTS.md"
echo "  ${REPO_ROOT}/docs/agents/"
echo ""
echo "Hermes cron scripts: run ./scripts/install_hermes_scripts.sh"
echo "Manual setup guide:  ${REPO_ROOT}/docs/agents/install-hermes-skill.md"
