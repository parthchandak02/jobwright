# Repo map (jobwright)

Detailed paths for agents. Summary: [../../AGENTS.md](../../AGENTS.md).

## Source code

| Path | Purpose |
|------|---------|
| `src/jobwright/cli.py` | Typer CLI: `run`, `tailor-job`, `apply`, `notify`, `status`, `doctor`, `users`, `network`, `targets` |
| `src/jobwright/pipeline.py` | Stage orchestration (`STAGE_ORDER`, streaming mode) |
| `src/jobwright/run_registry.py` | Durable Auto Search / CLI runs (`users/<id>/logs/web_runs.json`) |
| `src/jobwright/resume.py` | PDF source of truth → cached `resume/base.md` |
| `src/jobwright/notify.py` | Daily WhatsApp job list + deep links |
| `src/jobwright/config.py` | `JOBWRIGHT_DIR` paths, environment loading, `set_active_user` |
| `src/jobwright/users.py` | Multi-profile registry (`users/users.yaml`) |
| `src/jobwright/database.py` | SQLite `jobs` table, Kanban `funnel_stage` / `stage_history`, pipeline state |
| `src/jobwright/web/` | FastAPI Kanban dashboard (`app.py` + routers); serves `frontend/dist` |
| `frontend/` | Vite + React Kanban SPA (dev `:5120`, proxies `/api` → `:8002`). Profile: chips + `ProfileMaterials` (`ResumePreview`). Runs: `useAutoSearch` / `useTailorMaterials` + `RunProgressDialog` / `RunProgressButton`. Drawer: `CustomTailorDialog` |
| `src/jobwright/discovery/` | JobSpy (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`, known-URL skip), Workday (known-URL skip), smart extract; `DISCOVER_MODE=fast|full` |
| `src/jobwright/enrichment/` | Full JD fetch (JSON-LD, CSS, LLM) |
| `src/jobwright/scoring/` | Scorer, tailor, `tailor_instructions.py` (dashboard Auto/Custom prompts), cover letter, portfolio, PDF, DOCX, validator |
| `src/jobwright/apply/` | Stage 6: launcher, Chrome workers, ATS helpers, providers |
| `src/jobwright/apply/providers/` | `cursor-sdk` (default), `cursor-cli`, `claude` |
| `src/jobwright/network/` | LinkedIn CSV ranking + per-job connect + Exa research |
| `src/jobwright/targets/` | Target company list builder |
| `src/jobwright/config/*.yaml` | Shipped employers, sites, search templates; in `sites.yaml`, `blocked` = discovery (never surface), `apply_blocked` = LinkedIn (brief OK, never auto-apply) |
| `bin/job-apply-pp-cli` | Agent-native JSON wrapper over `jobwright` |
| `scripts/` | Hermes cron installers, Daily Brief (`run_daily_brief.sh` -> `jobwright notify`), repo resolution |
| `tests/` | pytest |

**Legacy:** `src/applypilot/` is unmaintained; do not extend.

Package-specific agent notes: [../../src/jobwright/AGENTS.md](../../src/jobwright/AGENTS.md).

## User data (not in git)

| Scope | Location |
|-------|----------|
| API keys | `<repo>/.env` (shared across profiles) |
| Legacy single user | `~/.jobwright/` |
| Registry | `<repo>/users/users.yaml` |
| Per-user dir | `<repo>/users/<user_id>/` |

Override: `JOBWRIGHT_USERS_ROOT`, `JOBWRIGHT_REPO`, `JOBWRIGHT_DIR`, `JOBWRIGHT_USER`.

Always: `jobwright --user <id> status` (`--user` before subcommand).

WhatsApp resolve: `scripts/resolve_user_from_whatsapp.sh 'whatsapp:…'`.

## Scripts (Hermes / cron)

| Script | Role |
|--------|------|
| `_jobwright_repo.sh` | Resolve repo root |
| `install_skills.sh` | Install thin Hermes/Cursor skill pointer |
| `install_hermes_scripts.sh` | Copy cron scripts to `~/.hermes/scripts/` |
| `setup_hermes_cron.sh` | Optional shell shortcut; prefer Hermes agent per `docs/agents/hermes-setup.md` |
| `jobwright_brief.sh` | Daily Brief (detached wrapper → `run_daily_brief.sh`) |
| `run_daily_brief.sh` | Background pipeline (discover → connect) then `jobwright notify` |
| `resolve_user_from_whatsapp.sh` | JID → `user_id` |
| `validate_pipeline.sh` | Doctor + unit checks |
| `restart.sh` | **Primary:** PM2/tmux restart (`--backend-only`, `--frontend-only`, `--prod-ui`, `--tmux`) |
| `ops_pm2.sh` | Alias → `restart.sh` |
| `dashboard_deploy.sh` | Alias → `restart.sh --prod-ui` |

Cron names: `jobwright-brief-<id>` (one daily brief per user, ~6:00). It runs the pipeline then `jobwright notify`, which sends ONE WhatsApp message listing newly prepared jobs with dashboard deep links (`jobwright.parthchandak.info/jobs/<job_id>`). No separate send/check crons.

Kanban hosting: [dashboard-hosting.md](dashboard-hosting.md) (`jobwright.parthchandak.info`; local HMR `http://127.0.0.1:5120`).

## Dashboard API (high level)

| Method | Route | Role |
|--------|-------|------|
| `POST` | `/api/run` | Start pipeline (Auto Search); returns `run_id`, `pid`, `log_path` |
| `GET` | `/api/runs`, `/api/runs/{run_id}` | List / status (memory + `web_runs.json`) |
| `POST` | `/api/runs/{run_id}/stop` | SIGTERM then SIGKILL process group |
| `GET` | `/api/stream/{run_id}` | SSE logs |
| `POST` / `GET` | `/api/notify`, `/api/notify/preview` | Send or preview WhatsApp list |
| `GET` | `/api/jobs/by-id/{job_id}` | Resolve deep link |
| `POST` | `/api/jobs/{url}/tailor` | Spawn `jobwright tailor-job` (SSE handle; optional custom instructions) |
| `GET` | `/api/tailor/defaults` | Default Auto Tailor instruction text |
| `GET` / `PUT` | `/api/settings`, `/profile`, `/searches`, `/resume.pdf` | Searches, base resume PDF |
| `PUT` / `GET` / `DELETE` | `/api/settings/cover-letters`, `/cover-letters/{id}/pdf` | Cover letter example PDFs |

PM2 process names: `jobwright-api`, `jobwright-ui`, `jobwright-tunnel`.

## Environment variables

| Variable | Role |
|----------|------|
| `FIREWORKS_API_KEY` / `GEMINI_API_KEY` | Stages 3-5 (+ docx/connect LLM); Gemini is also Fireworks empty-response failover |
| `GEMINI_FALLBACK_MODEL` | Fallback model (default `gemini-3.7-flash`) |
| `GEMINI_THINKING_LEVEL` | Gemini 3.x thinking (`low` default; `minimal\|low\|medium\|high`) |
| `EXA_API_KEY` | Optional web research for per-job connections |
| `CURSOR_API_KEY` | Stage 6 (default provider) |
| `AGENT_PROVIDER` | `cursor-sdk` \| `cursor-cli` \| `claude` |
| `JOBWRIGHT_REPO` | Repo root for shell scripts |
| `JOBWRIGHT_USERS_ROOT` | Registry root (default `<repo>/users`) |
| `JOBWRIGHT_DIR` | Active user data directory |
| `JOBWRIGHT_USER` | Set by Hermes wrappers after resolution |
| `JOBWRIGHT_DASHBOARD_USER` | Kanban API profile (default `richa`) |
| `JOBWRIGHT_PUBLIC_BASE_URL` | Deep-link base for `jobwright notify` (default `https://jobwright.parthchandak.info`) |
| `JOBWRIGHT_CORS_ORIGINS` | Comma-separated CORS origins for dashboard |
| `DISCOVER_MODE` | `fast` (tier-1, skip smart-extract) or `full` |
| `JOBWRIGHT_DISCOVER_BOARDS` | Restrict JobSpy boards without editing searches.yaml (e.g. `indeed`) |
| `JOBWRIGHT_DISCOVER_WORKERS` | JobSpy parallel worker cap (default 4) |
| `JOBWRIGHT_WEB_RUN_ID` | Set by `/api/run` so CLI does not create a second registry row |
| `JOBWRIGHT_LOG_LEVEL` | `DEBUG` when `jobwright run --verbose` (Auto Search always passes `--verbose`) |

Templates: `.env.example`, `config/live.env.example`.
