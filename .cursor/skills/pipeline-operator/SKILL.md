---
name: pipeline-operator
description: Operates the jobwright pipeline and Hermes/WhatsApp flows — per-user commands, cron scripts, CONFIRM APPLY gates, doctor and validate. Use for morning prep, digests, inbound WhatsApp, onboarding, or triaging pipeline failures.
---

# Pipeline operator (jobwright)

Hermes and Cursor agents running **jobwright ops** (not generic coding). Read [AGENTS.md](../../AGENTS.md) first for safety rules.

## Trigger cues

- WhatsApp inbound, CONFIRM APPLY, digest, morning cron
- `jobwright --user`, multi-profile, user onboarding
- Pipeline stage failures, `doctor`, `validate_pipeline.sh`
- Resume/cover-letter folder hygiene after uploads

## Progressive disclosure (read on demand)

| Task | Doc |
|------|-----|
| Primary Hermes playbook | [docs/agents/hermes-operator-guide.md](../../docs/agents/hermes-operator-guide.md) |
| WhatsApp phrase routing | [docs/agents/whatsapp-routing.md](../../docs/agents/whatsapp-routing.md) |
| Cron install / triage | [docs/agents/hermes-setup.md](../../docs/agents/hermes-setup.md) |
| Hermes skill install | [docs/agents/install-hermes-skill.md](../../docs/agents/install-hermes-skill.md) |
| Repo paths / scripts | [docs/agents/repo-map.md](../../docs/agents/repo-map.md) |
| Stage 6 apply / RESULT | [docs/agents/cursor-setup.md](../../docs/agents/cursor-setup.md) |
| Human WhatsApp UX | [docs/agents/whatsapp-user-guide.md](../../docs/agents/whatsapp-user-guide.md) |

## Hard rules (never)

- Auto-apply from cron
- LinkedIn apply
- `jobwright apply --live` for WhatsApp users (use confirm scripts)
- Commit `.env`, `users/`, secrets

## Quick commands

```bash
# Resolve sender before profile commands
USER_ID="$(bash scripts/resolve_user_from_whatsapp.sh 'whatsapp:SENDER_JID')"
export JOBWRIGHT_USER="${USER_ID}"

jobwright --user "${USER_ID}" doctor
jobwright --user "${USER_ID}" status
bash scripts/validate_pipeline.sh
pytest tests/ -v && ruff check src/
```

Live apply path: see hermes-operator-guide **CONFIRM APPLY** section only when user explicitly confirms and `apply_enabled` is true.
