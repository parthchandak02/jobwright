#!/usr/bin/env bash
# Validation checklist from implementation plan (doctor + unit checks + optional live dry-run).
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

echo "=== applypilot doctor ==="
applypilot doctor || true

echo ""
echo "=== unit checks (providers, RESULT parser, portfolio) ==="
python3 - <<'PY'
from applypilot.apply.providers.base import parse_result_output, get_provider
from applypilot.scoring.portfolio import _keyword_score

assert parse_result_output("x\nRESULT:DRYRUN\n", dry_run=True) == "dryrun"
assert parse_result_output("RESULT:APPLIED") == "applied"
assert parse_result_output("RESULT:FAILED:timeout") == "failed:timeout"
assert parse_result_output("no result") == "failed:no_result_line"

p = {"id": "a", "name": "Playwright Bot", "stack": ["Python", "Playwright"], "bullets": ["Built ATS automation"]}
assert _keyword_score(p, "Senior Python engineer with Playwright experience") >= 4

for name in ("cursor-sdk", "cursor-cli", "claude"):
    prov = get_provider(name)
    assert prov.name == name

print("unit checks: OK")
PY

echo ""
echo "=== dry-run RESULT protocol (10 cases) ==="
python3 - <<'PY'
from applypilot.apply.providers.base import parse_result_output

cases = [
    ("RESULT:DRYRUN", True, "dryrun"),
    ("filled form\nRESULT:DRYRUN\n", True, "dryrun"),
    ("RESULT:APPLIED", False, "applied"),
    ("RESULT:EXPIRED", False, "expired"),
    ("RESULT:CAPTCHA", False, "captcha"),
    ("RESULT:LOGIN_ISSUE", False, "login_issue"),
    ("RESULT:FAILED:timeout", False, "failed:timeout"),
    ("RESULT:FAILED:captcha", False, "captcha"),
    ("garbage", False, "failed:no_result_line"),
    ("partial RESULT:FAILED", False, "failed:unknown"),
]
for i, (out, dry, expected) in enumerate(cases, 1):
    got = parse_result_output(out, dry_run=dry)
    assert got == expected, f"case {i}: {got} != {expected}"
print(f"dry-run protocol: {len(cases)} cases OK")
PY

python3 - <<'PY'
import os
import shutil
from applypilot.config import has_apply_agent, get_agent_provider

print(f"AGENT_PROVIDER={get_agent_provider()}")
print(f"has_apply_agent={has_apply_agent()}")
print(f"CURSOR_API_KEY={'set' if os.environ.get('CURSOR_API_KEY') else 'missing'}")
print(f"agent CLI={'yes' if shutil.which('agent') else 'no'}")
PY

DOTENV="$(printf '\x2eenv')"
if [[ -f "${APPLYPILOT_DIR}/${DOTENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${APPLYPILOT_DIR}/${DOTENV}"
  set +a
fi

if [[ -n "${GEMINI_API_KEY:-}" && -f "${APPLYPILOT_DIR}/resume.txt" ]]; then
  echo ""
  echo "=== pipeline dry-run (discover..cover, limit 2) ==="
  applypilot run discover enrich score portfolio tailor cover --min-score 8 --dry-run 2>&1 | tail -20 || true
else
  echo ""
  echo "SKIP pipeline dry-run: need GEMINI_API_KEY + resume.txt in ${APPLYPILOT_DIR}"
fi

if [[ -n "${CURSOR_API_KEY:-}" ]]; then
  echo ""
  echo "=== apply dry-run (limit 1) — requires tailored jobs in DB ==="
  applypilot apply --dry-run --limit 1 --workers 1 2>&1 | tail -30 || true
else
  echo ""
  echo "SKIP apply dry-run: CURSOR_API_KEY not set"
fi

echo ""
echo "Validation script complete."
