# Agent guide (jobwright)

Entry point for **Cursor, Claude Code, Hermes, and cron wrappers**. Read this first; load linked docs only for your task (progressive disclosure).

**Humans:** [README.md](README.md). **Hermes skill install:** [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## What this is

Six-stage job pipeline (`jobwright` CLI, `src/jobwright/`): discover → enrich → score → portfolio → tailor → cover → optional **apply** (browser agent). Stages 1-5 are cron-safe. Stage 6 is opt-in, dry-run by default, never auto-submit from cron.

Version: `pyproject.toml` / `jobwright --version`.

---

## Always do

- Put `--user` **before** subcommands: `jobwright --user <id> status`
- Resolve WhatsApp sender before profile commands: `scripts/resolve_user_from_whatsapp.sh`
- Run quality gate before commit: `pytest tests/ -v` and `ruff check src/`
- Sync [AGENTS.md](AGENTS.md) before commit/push if you changed CLI, stages, paths, scripts, or safety gates (see [.cursor/rules/agents-doc-sync.mdc](.cursor/rules/agents-doc-sync.mdc))
- Hermes ops: set `JOBWRIGHT_REPO` to your clone; install thin skill via `./scripts/install_skills.sh` ([docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md))

## Ask first

- Live apply (`jobwright apply` without `--dry-run`)
- `jobwright users set <id> --apply` (enables CONFIRM APPLY path)
- Deleting user data (`users remove --delete-data`)
- Multi-file refactors outside the task scope
- Committing or pushing (only when user asks)

## Never do

- Auto-apply from cron
- LinkedIn job apply (blocked in code)
- `jobwright apply --live` for WhatsApp users (use confirm scripts)
- Commit `.env`, `users/`, `~/.jobwright/`, or secrets
- Extend `src/applypilot/` (legacy snapshot; use `src/jobwright/`)

---

## Commands

```bash
# Setup
pip install -e ".[dev]"
playwright install chromium   # stage 6 only

# Health
jobwright doctor
pytest tests/ -v
ruff check src/
bash scripts/validate_pipeline.sh

# Pipeline (multi-profile)
jobwright --user <id> run discover enrich score portfolio tailor cover -w 4 --min-score 7

# Agent JSON
./bin/job-apply-pp-cli status --agent --user <id>

# Users
jobwright users list
jobwright users add <id> --name "Name" --whatsapp "whatsapp:..." --template nontech-bay-area

# Hermes install (from clone)
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh
# Crons: ask Hermes agent — docs/agents/hermes-setup.md (paste block at top)
```

Env: `FIREWORKS_API_KEY` (stages 3-5, preferred), `GEMINI_API_KEY` (fallback), `CURSOR_API_KEY` + `AGENT_PROVIDER=cursor-sdk` (stage 6). Templates: `.env.example`.

---

## End-to-end flow (Hermes + WhatsApp)

Prep cron runs stages 1-5 → digest cron → WhatsApp. Live apply only if user sends `CONFIRM APPLY` and `apply_enabled: true` → `job_apply_confirm.sh` + `job_apply_on_confirm.sh`.

Detail: [docs/agents/hermes-operator-guide.md](docs/agents/hermes-operator-guide.md), [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md).

---

## Task → read next

| Task | Doc |
|------|-----|
| Hermes skill setup | [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md) |
| Hermes / WhatsApp ops | [docs/agents/hermes-operator-guide.md](docs/agents/hermes-operator-guide.md) |
| WhatsApp phrases | [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md) |
| Cron / scripts | [docs/agents/hermes-setup.md](docs/agents/hermes-setup.md) |
| Paths / scripts map | [docs/agents/repo-map.md](docs/agents/repo-map.md) |
| Cursor stage 6 | [docs/agents/cursor-setup.md](docs/agents/cursor-setup.md) |
| Human WhatsApp UX | [docs/agents/whatsapp-user-guide.md](docs/agents/whatsapp-user-guide.md) |
| Package code | [src/jobwright/AGENTS.md](src/jobwright/AGENTS.md) |
| Glossary / ADRs | [docs/GLOSSARY.md](docs/GLOSSARY.md), [docs/adr/](docs/adr/) |
| Contributing | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) |
| Commit workflow | [.cursor/skills/commit-and-push/SKILL.md](.cursor/skills/commit-and-push/SKILL.md) |
| Cursor agent workflow (todos, skills, finish end-to-end) | [.cursor/rules/agent-orchestration.mdc](.cursor/rules/agent-orchestration.mdc) |
| Pipeline / Hermes ops (skill entry) | [.cursor/skills/pipeline-operator/SKILL.md](.cursor/skills/pipeline-operator/SKILL.md) |

Full agent doc index: [docs/agents/README.md](docs/agents/README.md). Cursor skills: `.cursor/skills/` (21 skills; see orchestration rule routing table).

---

## Hermes vs repo

| What | Where |
|------|-------|
| Code, tests, scripts | This git clone (`JOBWRIGHT_REPO`) |
| Agent docs | `AGENTS.md`, `docs/agents/` (in clone) |
| Hermes skill | `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/` (thin loader + `JOBWRIGHT_REPO` file) |
| Hermes cron scripts | `~/.hermes/scripts/job_apply_*.sh` |

Cloning this repo does **not** register Hermes skills automatically. Run `./scripts/install_skills.sh` from your clone path.

---

**Last verified:** `0.4.0`, Fireworks LLM provider, `users/` registry, `cursor-sdk` default apply provider.
