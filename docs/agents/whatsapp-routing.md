# WhatsApp routing for Hermes agents

When a WhatsApp message arrives, Hermes must map the **sender** to a **jobwright user** before running any profile-specific command.

## Step 1: Identify the sender

Hermes provides the WhatsApp JID or deliver target (e.g. `whatsapp:120363...@g.us` or a phone JID).

Normalize to `whatsapp:<id>` format.

## Step 2: Resolve user

```bash
cd "${JOBWRIGHT_REPO:-/Volumes/ExternalSSD/Projects/jobwright}"
USER_ID="$(bash scripts/resolve_user_from_whatsapp.sh 'whatsapp:120363...@g.us')" \
  || { echo "Unknown sender — not registered."; exit 1; }
export JOBWRIGHT_USER="${USER_ID}"
export JOBWRIGHT_DIR="${JOBWRIGHT_USERS_ROOT:-$JOBWRIGHT_REPO/users}/${USER_ID}"
```

Or via Python: `jobwright users list`.

## Step 3: Handle inbound phrases

| User message (case insensitive) | Agent action |
|--------------------------------|--------------|
| `job status`, `how are my jobs` | `jobwright --user $USER_ID status` |
| `verify brief`, `health check` | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_verify.sh` |
| `find jobs now`, `run pipeline`, `run brief` | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_brief.sh` (detached; ~20-30 min). Uses `run_daily_brief.sh`: discover->connect then `jobwright notify`, `JOBWRIGHT_LLM_MODEL` default `gpt-oss-120b`, `--validation lenient`. Monitor: `users/$USER_ID/logs/brief_YYYYMMDD.log`, `BRIEF_STATUS_YYYYMMDD`. |
| `notify`, `send jobs`, `resend list` | `jobwright --user $USER_ID notify` (one WhatsApp list of new prepare jobs with dashboard deep links; `--dry-run` to preview). Skips silently when nothing new. |
| `smoke test`, `run smoke brief` | `BRIEF_SMOKE=1 JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_smoke.sh` (narrow: 3 queries, SF+Remote; JobSpy only - **not** for daily cron) |
| `materials`, `resume`, `open job` | Point the user to the dashboard deep link from the daily notify (`jobwright.parthchandak.info/jobs/<job_id>`); tailored DOCX + connections live on the card. |
| `update resume`, resume attachment | File upload recipe -> `resume/base.txt` (+ `base.pdf` if PDF) |
| `connections`, LinkedIn `Connections.csv` | File upload recipe -> `connections.csv`; smoke-test with `jobwright --user $USER_ID network --top 5` |
| `bug: ...`, `this is broken` | Operator guide -> Continuous improvement (reproduce first; do not guess) |
| `help jobs` | Summarize Daily Brief + one daily notify + dashboard + find-only vs apply |
| `turn off apply` | `jobwright users set $USER_ID --no-apply` (confirm first) |
| `network`, `connections` (text only) | `jobwright --user $USER_ID network` -> paste digest |
| `targets`, `companies` | `jobwright --user $USER_ID targets` -> paste digest |

### How jobs reach the user

The daily brief (`run_daily_brief.sh`) runs the pipeline then `jobwright notify`, which sends ONE WhatsApp message listing the newly prepared jobs, each with a `jobwright.parthchandak.info/jobs/<job_id>` deep link. Each job is stamped `whatsapp_notified_at` so it is never re-sent. The user clicks a link to open the job in the dashboard, where the tailored resume + cover letter, ranked connections, and gated apply button live. To resend the current list on demand, run `jobwright --user $USER_ID notify`.

### Pipeline env (Hermes / cron)

After code changes in the clone:

```bash
cd "${JOBWRIGHT_REPO}"
python3 -m pip install -e ".[dev]"
./scripts/install_hermes_scripts.sh
./scripts/install_skills.sh   # if SKILL.md changed
```

Brief pipeline defaults (in `run_daily_brief.sh`):

| Env | Default | Notes |
|-----|---------|--------|
| `JOBWRIGHT_LLM_MODEL` | `accounts/fireworks/models/gpt-oss-120b` | Overrides global `.env` `LLM_MODEL` for scoring/tailor/cover |
| `SCORE_BATCH_SIZE` | `10` | Jobs per scoring LLM call. Do not send the full jobs table in one shot. |
| `DISCOVER_MODE` | `fast` | Tier-1 queries; weekly `full` for deep crawl |
| `APPLY_MIN_SCORE` | `5` | Digest + tailor threshold (user `.env` may override) |
| `BRIEF_SMOKE` | unset | Set only via `jobwright_smoke.sh` - do not use for production brief |
| `JOBWRIGHT_PUBLIC_BASE_URL` | `https://jobwright.parthchandak.info` | Deep-link base used by `jobwright notify` |

## File uploads (resume, Connections.csv)

WhatsApp media paths are ephemeral. Always copy into the user inbox first.

```bash
USER_ID="$(bash scripts/resolve_user_from_whatsapp.sh 'whatsapp:SENDER_JID')"
DIR="${JOBWRIGHT_USERS_ROOT:-$JOBWRIGHT_REPO/users}/${USER_ID}"
INBOX="${DIR}/references/inbox"
mkdir -p "$INBOX" "${DIR}/resume"
# Copy attachment from Hermes media path into inbox:
cp "$HERMES_ATTACHMENT_PATH" "$INBOX/"
STAMP=$(date +%Y%m%d_%H%M%S)
```

### Resume (PDF / DOCX / TXT)

```bash
# Backup existing
cp -a "${DIR}/resume/base.txt" "${DIR}/resume/base.txt.bak.$STAMP" 2>/dev/null || true
cp -a "${DIR}/resume/base.pdf" "${DIR}/resume/base.pdf.bak.$STAMP" 2>/dev/null || true

# Place new file:
# PDF: keep binary + extract text
#   cp "$INBOX/Resume.pdf" "${DIR}/resume/base.pdf"
#   pdftotext -layout "${DIR}/resume/base.pdf" "${DIR}/resume/base.txt"  # or python extract
# TXT: copy to resume/base.txt
# DOCX: convert to UTF-8 text into resume/base.txt (python-docx or textutil)

jobwright --user "$USER_ID" doctor
```

Confirm on WhatsApp: what was replaced + backup path. Leave originals in inbox until the user confirms.

### LinkedIn Connections.csv

```bash
cp -a "${DIR}/connections.csv" "${DIR}/connections.csv.bak.$STAMP" 2>/dev/null || true
cp "$INBOX/Connections.csv" "${DIR}/connections.csv"
jobwright --user "$USER_ID" network --top 5   # smoke-test parse
```

Optional: suggest `find jobs now` so the next Daily Brief uses the new resume/connections.

## Apply safety

Live apply is not driven over WhatsApp. It runs only from the dashboard apply button (confirm gate) or an explicit `jobwright --user $USER_ID apply --live`, and only when `jobwright users show $USER_ID` reports `apply_enabled: true`. Never run apply from cron, and never auto-apply LinkedIn jobs (blocked in code).

## Onboarding a new WhatsApp user

1. Collect name, resume, role prefs, WhatsApp chat JID, apply preference (default: find-only).
2. `jobwright users add <id> --name "..." --whatsapp "whatsapp:..." --template nontech-bay-area`
3. Write `resume/base.txt`, tune `profile.json` and `searches.yaml` in `users/<id>/`.
4. Ask Hermes to register crons per [docs/agents/hermes-setup.md](hermes-setup.md).
5. `./scripts/install_hermes_scripts.sh` + `./scripts/install_skills.sh` after repo updates.
6. Test: `jobwright --user <id> doctor` then `JOBWRIGHT_USER=<id> bash ~/.hermes/scripts/jobwright_brief.sh`.

## Triage (no digest)

```bash
USER_ID=richa
LOG="${JOBWRIGHT_REPO}/users/${USER_ID}/logs/brief_$(date +%Y%m%d).log"
hermes cron list | grep jobwright-
tail -50 "$LOG"
# BRIEF_STATUS_YYYYMMDD ends with `done RC=` plus `notify_sent` or `notify_failed`.
cat "${JOBWRIGHT_REPO}/users/${USER_ID}/BRIEF_STATUS_$(date +%Y%m%d)" 2>/dev/null
```
