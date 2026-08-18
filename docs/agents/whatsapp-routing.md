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
| `CONFIRM APPLY` | Verify sender matches `whatsapp_target`. Then: `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_confirm.sh` then `jobwright_on_confirm.sh`. Report stdout. |
| `job status`, `how are my jobs` | `jobwright --user $USER_ID status` |
| `verify brief`, `health check` | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_verify.sh` |
| `find jobs now`, `run pipeline`, `run brief` | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_brief.sh` (detached; ~20–30 min). Uses `run_daily_brief.sh`: discover→connect, `JOBWRIGHT_LLM_MODEL` default `gpt-oss-120b`, `--validation lenient`. Monitor: `users/$USER_ID/logs/brief_YYYYMMDD.log`, `BRIEF_STATUS_YYYYMMDD`. |
| `send digest`, `post digest`, `show digest` | If digest ready: `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_send.sh` → paste stdout to WhatsApp. If pipeline still running, say so and point to log. |
| `smoke test`, `run smoke brief` | `BRIEF_SMOKE=1 JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_smoke.sh` (narrow: 3 queries, SF+Remote, top 3 digest; JobSpy only — **not** for daily cron) |
| `materials N`, `send N`, `files N`, `deliver materials N` | `jobwright --user $USER_ID materials --index N --json` → send each path in `files` as a WhatsApp **document**. Or: `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_deliver_materials.sh N` (uses `hermes send` + `MEDIA:` paths). |
| `update resume`, resume attachment | File upload recipe → `resume/base.txt` (+ `base.pdf` if PDF) |
| `connections`, LinkedIn `Connections.csv` | File upload recipe → `connections.csv`; smoke-test with `jobwright --user $USER_ID network --top 5` |
| `bug: …`, `this is broken`, `fix digest` | Operator guide → Continuous improvement (reproduce first; do not guess) |
| `help jobs` | Summarize Daily Brief + materials N + find-only vs apply |
| `turn off apply` | `jobwright users set $USER_ID --no-apply` (confirm first) |
| `network`, `connections` (text only) | `jobwright --user $USER_ID network` → paste digest |
| `targets`, `companies` | `jobwright --user $USER_ID targets` → paste digest |

### Materials delivery (DOCX)

**Cron** (`jobwright-send-<user>`) posts the **text digest** only (stdout from `jobwright_send.sh`).

**Agent** sends editable DOCX when the user asks `materials N`:

1. Parse index N from the message.
2. Run `jobwright --user $USER_ID materials --index N --json` (or `jobwright_deliver_materials.sh N`).
3. For each path in JSON `files`, send as a WhatsApp document (or use `MEDIA:` via `jobwright_deliver_materials.sh`).
4. If `files` is empty, say materials are not ready and suggest `find jobs now`.

**Auto-materials:** When `run_daily_brief.sh` finishes, it auto-sends editable DOCX for **every job in the digest** via `jobwright_deliver_materials.sh` (`AUTO_MATERIALS_ALL=1` default, one send per job with a short gap). Users don't need to reply `materials N` to get materials; that reply is only an optional resend. Set `AUTO_MATERIALS_ALL=0` to fall back to legacy single-job delivery (`AUTO_MATERIALS_INDEX=1`, or `0` to disable).

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
| `BRIEF_SMOKE` | unset | Set only via `jobwright_smoke.sh` — do not use for production brief |

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

## CONFIRM APPLY safety checklist

1. Sender JID matches registry `whatsapp_target` for `$USER_ID`.
2. `jobwright users show $USER_ID` → `apply_enabled: true`.
3. Do **not** run `jobwright apply --live --url ...` for WhatsApp users.
4. Use only `jobwright_confirm.sh` + `jobwright_on_confirm.sh`.

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
ls "${JOBWRIGHT_REPO}/users/${USER_ID}/DIGEST_DELIVERED_"* 2>/dev/null
```
