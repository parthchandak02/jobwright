---
name: pp-job-apply
description: >-
  jobwright: multi-user job pipeline, WhatsApp digests, optional CONFIRM APPLY.
  Thin Hermes loader — canonical docs live in your jobwright clone (JOBWRIGHT_REPO).
  Triggers: jobwright, job digest, find jobs, CONFIRM APPLY, improve jobwright.
version: 2.0.0
author: parthchandak
license: AGPL-3.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [jobwright, job-search, job-apply, cursor, automation, cron, whatsapp, confirmation-gate, multi-profile]
    related_skills: [hermes-cron-jobs, cursor-agent]
    aliases: [jobwright, job-apply, job-search]
    requires_toolsets: [terminal]
---

# pp-job-apply (jobwright) — Hermes loader

This directory is a **thin pointer** installed by `install_skills.sh`. Operational docs live in your clone, not here.

## 1. Repo path

Read `JOBWRIGHT_REPO` from the file next to this skill, or set manually:

```bash
export JOBWRIGHT_REPO="$(cat "${HERMES_SKILL_DIR}/JOBWRIGHT_REPO")"
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"
cd "${JOBWRIGHT_REPO}"
```

If missing, set `JOBWRIGHT_REPO` to your clone path and re-run `./scripts/install_skills.sh` from that clone.

## 2. Read order

| Step | Doc |
|------|-----|
| Start | `${JOBWRIGHT_REPO}/AGENTS.md` |
| Hermes ops | `${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md` |
| WhatsApp inbound | `${JOBWRIGHT_REPO}/docs/agents/whatsapp-routing.md` |
| Cron / install | `${JOBWRIGHT_REPO}/docs/agents/hermes-setup.md` (Hermes agent registers crons) |
| Repo map | `${JOBWRIGHT_REPO}/docs/agents/repo-map.md` |
| Human UX | `${JOBWRIGHT_REPO}/docs/agents/whatsapp-user-guide.md` |

## 3. Quick Hermes commands

```bash
USER_ID="$(bash "${JOBWRIGHT_REPO}/scripts/resolve_user_from_whatsapp.sh" 'whatsapp:SENDER_JID')"
export JOBWRIGHT_USER="${USER_ID}"
jobwright --user "${USER_ID}" status
JOBWRIGHT_USER="${USER_ID}" bash ~/.hermes/scripts/job_apply_morning.sh
```

## 4. Safety (never break)

No cron auto-apply. No LinkedIn apply. Live apply only via CONFIRM APPLY + `apply_enabled`. Never commit `users/` or `.env`.

Full rules: `${JOBWRIGHT_REPO}/AGENTS.md`
