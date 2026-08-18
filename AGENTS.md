# Agent guide (jobwright)

Entry point for **Cursor, Claude Code, Hermes, and cron wrappers**. Read this first; load linked docs only for your task (progressive disclosure).

**Humans:** [README.md](README.md). **Hermes skill install:** [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## What this is

**Product model:** jobwright is a daily career advisor. Each user supplies a base resume, profile, and search criteria. The pipeline discovers jobs, scores fit with an LLM, tailors resume + cover letter per strong match (from base materials only), exports DOCX, and ranks LinkedIn connections per job. The web dashboard is the primary surface: it shows every job as a card with tailored materials, connections, and a gated apply button. Once per day the pipeline sends ONE WhatsApp message listing the newly prepared jobs, each with a deep link to open that job in the dashboard. The user reviews and applies from the dashboard; optional browser apply is gated and never runs from cron. When LinkedIn jobs are discovered (included in default boards), they appear as cards and in connections; only auto-apply is blocked (`apply_blocked` in `sites.yaml`).

**Pipeline:** discover → enrich → score → portfolio → tailor → cover → **docx** → **connect**, then `jobwright notify` (one WhatsApp list of new jobs). Optional **apply** (browser agent) is opt-in. Brief stages are cron-safe. Apply is dry-run by default, never auto-submit from cron.

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
- `jobwright users set <id> --apply` (enables live apply for that profile)
- Deleting user data (`users remove --delete-data`)
- Multi-file refactors outside the task scope
- Committing or pushing (only when user asks)

## Never do

- Auto-apply from cron
- LinkedIn job apply (blocked in code)
- `jobwright apply --live` from cron (apply only from the dashboard or an explicit manual command)
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

# Send ONE WhatsApp list of newly prepared jobs (deep links to the dashboard).
# --dry-run previews the message without sending or marking jobs notified.
jobwright --user <id> notify
jobwright --user <id> notify --dry-run

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

Env: `FIREWORKS_API_KEY` (stages 3-5, preferred), `GEMINI_API_KEY` (runtime failover: retried automatically when Fireworks returns empty content), `GEMINI_FALLBACK_MODEL` (default `gemini-3.7-flash`), `GEMINI_THINKING_LEVEL` (default `low`; `minimal|low|medium|high` for Gemini 3.x), optional `EXA_API_KEY` (per-job web connections), `CURSOR_API_KEY` + `AGENT_PROVIDER=cursor-sdk` (stage 6), `DISCOVER_MODE=fast|full` (default `fast`: skip smart-extract, tier-1 queries; Workday skips detail fetch for known URLs), `SCORE_BATCH_SIZE` (default `10`: jobs per scoring LLM call; set `1` for sequential), `JOBWRIGHT_HOURS_OLD` (override discover freshness window; default 72 in the non-tech template), `JOBWRIGHT_DISCOVER_BOARDS` (restrict JobSpy boards, e.g. `indeed`, without editing searches.yaml), `BRIEF_SMOKE=1` (narrow E2E: 3 queries, SF+Remote, Indeed-only, 168h; `jobwright_smoke.sh` pins gpt-oss-120b, waits for `done RC=`, and reports the `notify` result), `JOBWRIGHT_PUBLIC_BASE_URL` (deep-link base for `notify`; default `https://jobwright.parthchandak.info`), `JOBWRIGHT_DASHBOARD_USER` (Kanban API active profile; default `richa`). Templates: `.env.example`.

---

## End-to-end flow (dashboard + one daily notice)

**User inputs (once per profile):** `resume/base.txt`, `profile.json`, `searches.yaml`, `cover-letter/examples/`, optional `connections.csv`.

**Daily brief cron** (`jobwright-brief-<user>`, ~6:00): runs discover → connect via `run_daily_brief.sh`, then `jobwright --user <id> notify`. Notify sends ONE plain-text WhatsApp message to the user's `whatsapp_target` group listing the newly prepared jobs, each with a `jobwright.parthchandak.info/jobs/<job_id>` deep link. Each job is marked `whatsapp_notified_at` so it is never re-sent; notify skips silently when nothing new is ready.

**Dashboard (primary surface):** the user opens a deep link (or the board directly). Cards show tailored resume + cover letter, ranked connections, a "WhatsApp Notified" chip, and a gated apply button. The "Auto Search" button triggers discovery; the "Notify WhatsApp" button sends the same daily list on demand (`POST /api/notify`, preview via `GET /api/notify/preview`).

**Apply:** dry-run by default. Live apply requires `apply_enabled=true` for the profile and runs only from the dashboard apply button (confirm gate) or an explicit `jobwright apply --live`. Never from cron.

**User's job:** review curated roles from the dashboard, use tailored DOCX, act on network suggestions, apply manually or via gated agent apply.

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
| Commit / push / deploy workflow | [.cursor/skills/deploy/SKILL.md](.cursor/skills/deploy/SKILL.md) |
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

**Last verified:** `0.5.0`, Kanban dashboard (`src/jobwright/web/`, funnel_stage + stage_history, ADR-004) is the primary surface, simplified WhatsApp flow: one daily `jobwright notify` message listing new `prepare` jobs with dashboard deep links (`src/jobwright/notify.py`, `POST /api/notify`), stamped `whatsapp_notified_at` so jobs are never re-sent. Daily cron `jobwright-brief-<user>` runs `run_daily_brief.sh` (pipeline then notify); the old `jobwright-send` / `jobwright-check` crons and the digest/materials-N/CONFIRM-APPLY-over-WhatsApp scripts are removed. LinkedIn on default discover boards + `apply_blocked` (cards + connections OK, auto-apply blocked), docx + connect, `SCORE_BATCH_SIZE=10`, `DISCOVER_MODE=fast|full`, Fireworks LLM with Gemini failover (`gemini-3.7-flash` + `GEMINI_THINKING_LEVEL=low`), shared location filter, Canada Workday skip when reject includes canada, `users/` registry, `cursor-sdk` default apply provider.
