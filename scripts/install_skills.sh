#!/usr/bin/env bash
# Install pp-job-apply skill for Cursor and Hermes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SRC="${REPO_ROOT}/skills/pp-job-apply"

mkdir -p "${HOME}/.cursor/skills" "${HOME}/.hermes/skills/autonomous-ai-agents"
ln -sfn "${SKILL_SRC}" "${HOME}/.cursor/skills/pp-job-apply"
ln -sfn "${SKILL_SRC}" "${HOME}/.hermes/skills/autonomous-ai-agents/pp-job-apply"

echo "Installed pp-job-apply skill:"
echo "  Cursor: ${HOME}/.cursor/skills/pp-job-apply"
echo "  Hermes: ${HOME}/.hermes/skills/autonomous-ai-agents/pp-job-apply"
