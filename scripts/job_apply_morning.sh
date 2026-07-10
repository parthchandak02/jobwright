#!/usr/bin/env bash
# Morning prep: discover → cover letter. Does NOT apply. Sends queue to WhatsApp via Hermes.
set -euo pipefail

export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"
export PATH="${HOME}/.local/bin:${PATH}"
DOTENV="$(printf '\x2eenv')"
[[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]] && set -a && source "${APPLYPILOT_DIR}/${DOTENV}" && set +a

export LLM_MODEL="${LLM_MODEL:-gemini-2.5-flash}"
export APPLY_DRY_RUN=true
unset APPLY_LIVE 2>/dev/null || true

MIN_SCORE="${APPLY_MIN_SCORE:-5}"
WORKERS="${APPLY_WORKERS:-4}"

# Clear yesterday's confirmation gate
rm -f "${APPLYPILOT_DIR}/APPLY_CONFIRMED"

applypilot run discover enrich score portfolio tailor cover \
  -w "${WORKERS}" --min-score "${MIN_SCORE}" --validation lenient

echo ""
echo "=== Job Apply Morning Digest ==="
echo "Date: $(date '+%Y-%m-%d %H:%M %Z')"
applypilot status

READY=$(sqlite3 "${APPLYPILOT_DIR}/applypilot.db" \
  "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL AND fit_score>=${MIN_SCORE} AND (apply_status IS NULL OR apply_status NOT IN ('skipped','in_progress','applied')) AND site NOT LIKE '%linkedin%';" 2>/dev/null || echo 0)

echo ""
echo "Ready to apply (non-LinkedIn, score>=${MIN_SCORE}): ${READY}"
echo ""
sqlite3 -header -column "${APPLYPILOT_DIR}/applypilot.db" \
  "SELECT title, fit_score, site, substr(url,1,60) AS url FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL AND fit_score>=${MIN_SCORE} AND (apply_status IS NULL OR apply_status NOT IN ('skipped','in_progress','applied')) AND site NOT LIKE '%linkedin%' ORDER BY fit_score DESC LIMIT 10;" 2>/dev/null || true

echo ""
echo "Reply CONFIRM APPLY to submit up to ${APPLY_LIMIT:-5} jobs (live)."
echo "Or: hermes -z 'confirm job apply' with pp-job-apply skill attached."
