# Agent documentation (jobwright)

Canonical agent-facing docs live **in this repo**, not inside Hermes or Cursor skill directories.

## Model

| Layer | Location | Role |
|-------|----------|------|
| Entry map | [../AGENTS.md](../AGENTS.md) | Any agent starts here |
| Deep ops (Hermes) | [hermes-operator-guide.md](hermes-operator-guide.md) | WhatsApp, cron, multi-user |
| Hermes install | [install-hermes-skill.md](install-hermes-skill.md) | Point Hermes at your clone |
| Repo map | [repo-map.md](repo-map.md) | Paths, scripts, source layout |
| Kanban dashboard hosting | [dashboard-hosting.md](dashboard-hosting.md) | cloudflared + PM2 + Auto Search / Profile / tailor |
| WhatsApp group (Richa) | [whatsapp-group-jobwright.md](whatsapp-group-jobwright.md) | Skills checklist for this WhatsApp group |
| WhatsApp routing | [whatsapp-routing.md](whatsapp-routing.md) | Inbound phrase → action |
| Cron / scripts | [hermes-setup.md](hermes-setup.md) (Hermes agent creates crons) | `install_hermes_scripts.sh`, crons |
| Cursor apply | [cursor-setup.md](cursor-setup.md) | Stage 6, RESULT protocol |
| Human UX | [whatsapp-user-guide.md](whatsapp-user-guide.md) | Share with WhatsApp users |

## Hermes skill (lives on your machine)

Hermes loads skills from `~/.hermes/skills/`. The repo ships a **thin loader** in [../../templates/hermes-skill/SKILL.md](../../templates/hermes-skill/SKILL.md) that points back to this directory.

After clone:

```bash
cd /path/to/jobwright
./scripts/install_skills.sh      # copies thin skill → ~/.hermes/skills/… + records JOBWRIGHT_REPO
./scripts/install_hermes_scripts.sh
```

See [install-hermes-skill.md](install-hermes-skill.md) for manual setup or custom paths.

## Cursor / Claude Code

Open the repo in your editor. Read [../AGENTS.md](../AGENTS.md) first. Dashboard UI: [../../.cursor/skills/frontend-tasteful/SKILL.md](../../.cursor/skills/frontend-tasteful/SKILL.md). Optional: `./scripts/install_skills.sh` adds the same thin loader to `~/.cursor/skills/pp-job-apply`.
