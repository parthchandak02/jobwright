---
name: pp-job-apply
description: >-
  jobwright repository: Daily Brief pipeline that ends with one WhatsApp notify
  message (new jobs + dashboard deep links). Primary Hermes skill for this clone
  (aliases: jobwright, job-apply). Load when the user asks about jobwright, job
  search, this repo, or job crons. Canonical docs live in JOBWRIGHT_REPO
  (AGENTS.md, docs/agents/).
version: 3.0.0
author: parthchandak
license: AGPL-3.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [jobwright, job-search, job-apply, cursor, automation, cron, whatsapp, multi-profile]
    related_skills: [hermes-cron-jobs, cursor-agent]
    aliases: [jobwright, job-apply, job-search]
    requires_toolsets: [terminal]
---

# pp-job-apply (jobwright) - Hermes loader

Thin pointer installed by `install_skills.sh`. Operational docs live in the clone.

## 1. Repo path

```bash
export JOBWRIGHT_REPO="$(cat "${HERMES_SKILL_DIR}/JOBWRIGHT_REPO")"
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"
cd "${JOBWRIGHT_REPO}"
```

If missing, set `JOBWRIGHT_REPO` to the clone path and re-run `./scripts/install_skills.sh`.

## 2. Read order

| Step | Doc |
|------|-----|
| Start | `${JOBWRIGHT_REPO}/AGENTS.md` |
| This WhatsApp group | `${JOBWRIGHT_REPO}/docs/agents/whatsapp-group-jobwright.md` |
| Hermes ops | `${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md` |
| WhatsApp inbound | `${JOBWRIGHT_REPO}/docs/agents/whatsapp-routing.md` |
| Cron / install | `${JOBWRIGHT_REPO}/docs/agents/hermes-setup.md` |
| Repo map | `${JOBWRIGHT_REPO}/docs/agents/repo-map.md` |

## 3. WhatsApp must-know (every turn)

| Need | Do |
|------|----|
| Resolve user | `bash scripts/resolve_user_from_whatsapp.sh 'whatsapp:SENDER_JID'` -> `$USER_ID` **before** any profile command |
| E2E demo | Follow Post-deploy demo in `whatsapp-group-jobwright.md` |
| Replace resume / Connections.csv | `whatsapp-routing.md` -> File uploads (backup then write under `users/$USER_ID/`) |
| Review jobs / materials | Open the dashboard at `jobwright.parthchandak.info/jobs/<job_id>` (deep links come from the daily notify) |
| find jobs now | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/jobwright_brief.sh` (~20-30 min; sends the notify when done) |
| send notify now | `jobwright --user $USER_ID notify` (one WhatsApp list of new jobs; `--dry-run` to preview) |
| User reports bug / wants fix | `hermes-operator-guide.md` -> Continuous improvement (reproduce first) |
| Crons | Only `jobwright-brief-<id>` - never recreate `job-apply-*`, `jobwright-send`, or `jobwright-check` |

## 4. Quick commands

```bash
USER_ID="$(bash "${JOBWRIGHT_REPO}/scripts/resolve_user_from_whatsapp.sh" 'whatsapp:SENDER_JID')"
export JOBWRIGHT_USER="${USER_ID}"
jobwright --user "${USER_ID}" status
jobwright --user "${USER_ID}" doctor
JOBWRIGHT_USER="${USER_ID}" bash ~/.hermes/scripts/jobwright_brief.sh
jobwright --user "${USER_ID}" notify --dry-run
```

## 5. Safety (never break)

No cron auto-apply. No LinkedIn apply. Live apply only from the dashboard apply button (confirm gate) or an explicit `jobwright apply --live` with `apply_enabled`. Never commit `users/` or `.env`. After script/skill changes: `pip install -e ".[dev]"` in clone, then `./scripts/install_hermes_scripts.sh` and/or `./scripts/install_skills.sh`.

Full rules: `${JOBWRIGHT_REPO}/AGENTS.md`
