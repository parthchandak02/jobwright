# Skills directory

This repo does **not** ship a full Hermes skill here. Agent docs live in:

- [AGENTS.md](../AGENTS.md) (start here)
- [docs/agents/](../docs/agents/) (Hermes, WhatsApp, repo map)

## Install Hermes / Cursor loader

From your clone (any path):

```bash
./scripts/install_skills.sh
```

This copies a **thin skill** from [templates/hermes-skill/SKILL.md](../templates/hermes-skill/SKILL.md) to:

- `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/`
- `~/.hermes/skills/autonomous-ai-agents/jobwright/` (alias)
- `~/.cursor/skills/pp-job-apply/`

Each install writes `JOBWRIGHT_REPO` with the absolute path to **your** clone.

Manual setup: [docs/agents/install-hermes-skill.md](../docs/agents/install-hermes-skill.md).
