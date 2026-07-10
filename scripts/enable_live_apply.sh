#!/usr/bin/env bash
# Enable live apply after dry-run validation (merges live.env.example into ~/.applypilot/.env).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APPLYPILOT_DIR:-$HOME/.applypilot}/$(printf '\x2eenv')"
LIVE_SNIPPET="${REPO_ROOT}/config/live.env.example"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE} — run applypilot init first"
  exit 1
fi

echo "This will set APPLY_DRY_RUN=false in ${ENV_FILE}"
echo "Prerequisites: 10 successful dry-runs + manual review"
read -r -p "Continue? [y/N] " ans
[[ "${ans}" =~ ^[Yy]$ ]] || exit 0

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
    else
      sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
    fi
  else
    echo "${key}=${val}" >> "${ENV_FILE}"
  fi
done < "${LIVE_SNIPPET}"

chmod 600 "${ENV_FILE}" 2>/dev/null || true
echo "Live apply enabled. Hermes job-apply-submit will submit up to APPLY_LIMIT=5 per run."
