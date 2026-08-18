# Agent guide (jobwright)

Entry point for **Cursor, Claude Code, Hermes, and cron wrappers**. Read this first; load linked docs only for your task (progressive disclosure).

**Humans:** [README.md](README.md). **Hermes skill install:** [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## What this is

**Product model:** jobwright is a daily career advisor. Each user supplies a base resume, profile, and search criteria. The pipeline discovers jobs, scores fit with an LLM, tailors resume + cover letter per strong match (from base materials only), exports DOCX, and ranks LinkedIn connections per job. Hermes (or another agent) delivers the digest and materials to the user's chat app. The user reviews and applies; optional browser apply is gated and never runs from cron. When LinkedIn jobs are discovered (included in default boards), they may appear in materials, digest, and connections; only auto-apply is blocked (`apply_blocked` in `sites.yaml`).

**Pipeline:** discover → enrich → score → portfolio → tailor → cover → **docx** → **connect** → digest. Optional **apply** (browser agent) is opt-in. Brief stages are cron-safe. Apply is dry-run by default, never auto-submit from cron.

**Kanban dashboard (optional):** FastAPI + React board at `jobwright.parthchandak.info` (local `:8002`). Single-axis lanes `backlog → prepare → applied → in_progress → offer → closed`; agent auto-advances to prepare; human owns Applied+. See [docs/agents/dashboard-hosting.md](docs/agents/dashboard-hosting.md) and [docs/adr/ADR-004-kanban-funnel-stage.md](docs/adr/ADR-004-kanban-funnel-stage.md).

**Human-readable overview:** [README.md#the-daily-brief-how-it-works-with-hermes](README.md#the-daily-brief-how-it-works-with-hermes).

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
pip install -e ".[web]"          # Kanban dashboard (FastAPI + uvicorn)
playwright install chromium   # stage 6 only

# Health
jobwright doctor
pytest tests/ -v
ruff check src/
bash scripts/validate_pipeline.sh

# Daily Brief pipeline (multi-profile)
# DISCOVER_MODE=fast (default for cron): JobSpy + Workday tier-1 only; skip smart-extract
# DISCOVER_MODE=full: all query tiers + smart-extract (weekly deep crawl)
DISCOVER_MODE=fast jobwright --user <id> run discover enrich score portfolio tailor cover docx connect -w 4 --min-score 7

# Materials for WhatsApp (DOCX paths)
jobwright --user <id> materials --index 1

# Kanban dashboard (local hot reload)
cp ecosystem.config.example.js ecosystem.config.js   # once
./scripts/restart.sh                                 # api :8002 + Vite :5120
# open http://127.0.0.1:5120
# ./scripts/restart.sh --backend-only | --frontend-only | --prod-ui | --tmux
# Prod on this host: ./scripts/dashboard_deploy.sh  (docs/agents/dashboard-hosting.md)

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

Env: `FIREWORKS_API_KEY` (stages 3-5, preferred), `GEMINI_API_KEY` (runtime failover: retried automatically when Fireworks returns empty content), `GEMINI_FALLBACK_MODEL` (default `gemini-3.7-flash`), `GEMINI_THINKING_LEVEL` (default `low`; `minimal|low|medium|high` for Gemini 3.x), optional `EXA_API_KEY` (per-job web connections), `CURSOR_API_KEY` + `AGENT_PROVIDER=cursor-sdk` (stage 6), `DISCOVER_MODE=fast|full` (default `fast`: skip smart-extract, tier-1 queries; Workday skips detail fetch for known URLs), `SCORE_BATCH_SIZE` (default `10`: jobs per scoring LLM call; set `1` for sequential), `JOBWRIGHT_HOURS_OLD` (override discover freshness window; default 72 in the non-tech template), `JOBWRIGHT_DISCOVER_BOARDS` (restrict JobSpy boards, e.g. `indeed`, without editing searches.yaml), `BRIEF_SMOKE=1` (narrow E2E: 3 queries, SF+Remote, Indeed-only, 168h, top 3 digest; `jobwright_smoke.sh` pins gpt-oss-120b, waits for `done RC=`, and asserts `digest_written`), `JOBWRIGHT_DASHBOARD_USER` (Kanban API active profile; default `richa`). Templates: `.env.example`.

---

## End-to-end flow (Hermes + chat)

**User inputs (once per profile):** `resume/base.txt`, `profile.json`, `searches.yaml`, `cover-letter/examples/`, optional `connections.csv`.

**Daily brief cron** (`jobwright-brief`, ~6:00): runs discover → connect, writes digest + DOCX. On completion, sends digest text then editable DOCX for **every job shown** via `hermes send` (`AUTO_DELIVER_CHAT=1`, `AUTO_MATERIALS_ALL=1`; set `AUTO_MATERIALS_ALL=0` for legacy single-job `AUTO_MATERIALS_INDEX`). Users no longer need to reply `materials N` to receive materials; that reply is now an optional resend.

**Digest cron** (`jobwright-send`, ~6:30): fallback if chat delivery was off during the brief; otherwise no-op once `DIGEST_DELIVERED_*` exists.

**User replies:** `materials N` for other jobs; `CONFIRM APPLY` only if `apply_enabled: true` → `jobwright_confirm.sh` + `jobwright_on_confirm.sh`.

**User's job:** review curated roles, use tailored DOCX, act on network suggestions, apply manually or via gated agent apply.

Detail: [docs/agents/hermes-operator-guide.md](docs/agents/hermes-operator-guide.md), [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md).

---

## Task → read next

| Task | Doc |
|------|-----|
| Hermes skill setup | [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md) |
| Hermes / WhatsApp ops | [docs/agents/hermes-operator-guide.md](docs/agents/hermes-operator-guide.md) |
| WhatsApp group / skills checklist | [docs/agents/whatsapp-group-jobwright.md](docs/agents/whatsapp-group-jobwright.md) |
| WhatsApp phrases | [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md) |
| Cron / scripts | [docs/agents/hermes-setup.md](docs/agents/hermes-setup.md) |
| Paths / scripts map | [docs/agents/repo-map.md](docs/agents/repo-map.md) |
| Kanban dashboard hosting | [docs/agents/dashboard-hosting.md](docs/agents/dashboard-hosting.md) |
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
| Hermes cron scripts | `~/.hermes/scripts/jobwright_*.sh` |

Cloning this repo does **not** register Hermes skills automatically. Run `./scripts/install_skills.sh` from your clone path.

---

**Last verified:** `0.5.0`, Kanban dashboard (`src/jobwright/web/`, funnel_stage + stage_history, ADR-004), Daily Brief product model in README, LinkedIn on default discover boards + `apply_blocked` (brief OK, auto-apply blocked), docx + connect, `SCORE_BATCH_SIZE=10`, `DISCOVER_MODE=fast|full`, Fireworks LLM with Gemini failover (`gemini-3.7-flash` + `GEMINI_THINKING_LEVEL=low`), shared location filter, Canada Workday skip when reject includes canada, `users/` registry, `cursor-sdk` default apply provider. Full smoke E2E (discover -> digest + WhatsApp materials) validated for `richa`; Indeed-only + 72-168h window + diversified tier-1 queries yields ~50+ fresh roles per narrow run.
