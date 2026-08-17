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
```

Or via Python:

```bash
jobwright users list   # shows whatsapp targets
```

Legacy single-user (`~/.jobwright`, no registry): if `users list` is empty, omit `--user` / `JOBWRIGHT_USER`.

## Step 3: Handle inbound phrases

| User message (case insensitive) | Agent action |
|--------------------------------|--------------|
| `CONFIRM APPLY` | Verify sender matches user's `whatsapp_target`. Then: `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/job_apply_confirm.sh` then `job_apply_on_confirm.sh`. Report stdout. |
| `job status`, `how are my jobs` | `jobwright --user $USER_ID status` |
| `find jobs now`, `run pipeline` | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/job_apply_morning.sh` (detached prep) |
| `help jobs` | Summarize find-only vs apply-enabled; link to user guide mentally |
| `turn off apply` | `jobwright users set $USER_ID --no-apply` (confirm with user first) |
| `network`, `connections` | `jobwright --user $USER_ID network` → paste digest to WhatsApp |
| `targets`, `companies` | `jobwright --user $USER_ID targets` → paste digest |

## CONFIRM APPLY safety checklist

Before running confirm scripts:

1. Sender JID matches registry `whatsapp_target` for `$USER_ID`.
2. `jobwright users show $USER_ID` → `apply_enabled: true` (else explain find-only mode).
3. Do **not** run `jobwright apply --live --url ...` for WhatsApp users (bypasses gate).
4. Use only `job_apply_confirm.sh` + `job_apply_on_confirm.sh` wrappers.

## Onboarding a new WhatsApp user

1. Collect name, resume, role prefs, WhatsApp chat JID, apply preference (default: find-only).
2. `jobwright users add <id> --name "..." --whatsapp "whatsapp:..." --template nontech-bay-area`
3. Write `resume.txt`, tune `profile.json` and `searches.yaml` in `users/<id>/`.
4. `./scripts/setup_hermes_cron.sh` (re-register per-user crons).
5. `./scripts/install_hermes_scripts.sh` + `./scripts/install_skills.sh` after repo updates.
6. Test: `jobwright --user <id> doctor` then manual morning script.

## Repo path on Mac mini

Wrappers resolve repo via `JOBWRIGHT_REPO` or known paths:

- `/Volumes/ExternalSSD/Projects/jobwright`
- `~/projects/jobwright`

Pin in cron env if the external drive mount is unreliable.

## Triage (no digest)

```bash
USER_ID=richa
LOG="${JOBWRIGHT_REPO}/users/${USER_ID}/logs/morning_$(date +%Y%m%d).log"
hermes cron list | grep job-apply
tail -50 "$LOG"
ls "${JOBWRIGHT_REPO}/users/${USER_ID}/DIGEST_DELIVERED_"* 2>/dev/null
```

## File uploads (resume, Connections.csv)

When Hermes receives a document:

1. Resolve `$USER_ID` from sender.
2. Save to `references/inbox/` temporarily.
3. **File into structured folders:**

| Type | Destination |
|------|-------------|
| Resume | `resume/base.txt` (+ `resume/base.pdf` if PDF) |
| Cover letter example | `cover-letter/examples/<name>.txt` |
| Cover letter template | `cover-letter/template.txt` |
| LinkedIn Connections | `connections.csv` |
| Unknown | leave in `references/inbox/` and ask |

Never store organized resume/cover-letter files under `references/` long term.
