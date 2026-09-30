# Repo map (jobwright)

Detailed paths for agents. Summary: [../../AGENTS.md](../../AGENTS.md).

## Source code

| Path | Purpose |
|------|---------|
| `src/jobwright/cli.py` | Typer CLI: `run`, `tailor-job`, `apply` (dry-run unless `--live`), `notify`, `status`, `doctor`, `users`, `network`, `targets`, `eval`, `rescore`, `criteria`, `labels`, `preflight`, `ops` |
| `src/jobwright/pipeline.py` | Stage orchestration (`STAGE_ORDER`, default brief stages, per-user flock, `logs/last_run.json`) |
| `src/jobwright/run_registry.py` | Durable Auto Search / CLI runs (`users/<id>/logs/web_runs.json`) |
| `src/jobwright/resume.py` | PDF source of truth → cached `resume/base.md` |
| `src/jobwright/notify.py` | Daily WhatsApp job list + deep links |
| `src/jobwright/hermes_cron.py` | Create/edit/remove `jobwright-brief-<user>`, `jobwright-ops-watchdog`, `jobwright-backup`, `jobwright-weekly-summary` (`--no-agent --deliver local`); pause legacy send/check crons; `JOBWRIGHT_HERMES_DRY_RUN` |
| `src/jobwright/ops.py` | Brief report, watchdog, alerts to `ops_target`, backups |
| `src/jobwright/preflight.py` | Pre-run checks; `--fix` installs Playwright Chromium |
| `src/jobwright/onboarding.py` | New profile + LLM draft from resume; `onboarding_status`, `is_set_up` (gates brief crons, `install-crons`, welcome) |
| `src/jobwright/welcome.py` | One-time welcome to the person's chat + operator heads-up when setup creates their brief cron (`logs/welcome_sent.json`; dry-run aware) |
| `src/jobwright/whatsapp.py` | Admin chat picker (Hermes targets + bridge names), `chat_name` (10-minute group-name cache), test send |
| `src/jobwright/labels.py` | Append-only human labels (`score_labels`) and eval set |
| `src/jobwright/config.py` | `JOBWRIGHT_DIR` paths, environment loading, `set_active_user` (CLI), `user_context` (per-request web), `user_env` |
| `src/jobwright/users.py` | Multi-profile registry (`users/users.yaml`: users with `emails`, `admins`, `ops_target`) |
| `src/jobwright/database.py` | SQLite `jobs`, `stage_history`, `job_tombstones`, `score_labels`, `score_history`, `llm_usage` |
| `src/jobwright/web/` | FastAPI Kanban dashboard (`app.py` + routers); `auth.py` (Cloudflare Access / dev), `session.py` (per-request profile); serves `frontend/dist` |
| `frontend/` | Vite + React Kanban SPA (dev `:5120`, proxies `/api` → `:8002`). UI (design v2): `.cursor/skills/frontend-tasteful/` catalog; primitives in `components/ui/` + `PageHeader`, `SectionHeader`, `FormField`, `SaveStatus`, `ActionBar`, `EmptyState`, `MobileNav`. Welcome steps: `components/welcome/`. Settings (`ProfilePage`) tabs: `components/profile/*Tab.tsx` + `useAutosave`. Admin: `components/admin/`. WhatsApp: `DailyBriefDialog` (send now), `WhatsAppChatPicker` (admins), `ConnectedChat` (read-only for everyone else). Runs: `useAutoSearch` / `useTailorMaterials` / `useRunStream` + `RunProgressDialog`. Drawer: `MatchExplanation`, `RateJob`, `StagePicker`, `DismissDialog`, `CustomTailorDialog`. Pages: `WelcomePage`, `QualityPage`, `AdminPage`. Identity: `AppGate` + `lib/me.tsx` |
| `src/jobwright/discovery/` | Cross-board dedupe (`dedupe.py`), JobSpy (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`, known-URL skip), LinkedIn guest client (`linkedin.py`: one cookie-less client per run with adaptive pacing, filter cards before description fetch, 7-day reject memory in `logs/linkedin_rejects.json`), Workday (known-URL skip, `exclude_companies`, path fallback when location is blank), smart extract; `DISCOVER_MODE=fast|full` |
| `src/jobwright/enrichment/` | Full JD fetch (JSON-LD, CSS, LLM) |
| `src/jobwright/scoring/` | Scoring v2 (`matcher.py`, `pipeline_v2.py`, `criteria.py`, `examples.py`, `evaluate.py`, `criteria_miner.py`), legacy `scorer.py` (`JOBWRIGHT_SCORER=v1`), tailor, `tailor_instructions.py` (dashboard Auto/Custom prompts), cover letter, portfolio, PDF, DOCX, validator |
| `src/jobwright/apply/` | Stage 6: launcher, Chrome workers, ATS helpers, providers |
| `src/jobwright/apply/providers/` | `cursor-sdk` (default), `cursor-cli`, `claude` |
| `src/jobwright/network/` | LinkedIn CSV ranking + per-job connect + Exa research |
| `src/jobwright/targets/` | Target company list builder |
| `src/jobwright/config/*.yaml` | Shipped employers, sites, search templates; in `sites.yaml`, `blocked` = discovery (never surface), `apply_blocked` = LinkedIn (brief OK, never auto-apply) |
| `bin/job-apply-pp-cli` | Agent-native JSON wrapper over `jobwright` |
| `scripts/` | Hermes cron installers, Daily Brief (`run_daily_brief.sh` -> `jobwright notify`), repo resolution |
| `tests/` | pytest |
| `.graphifyignore` | Graphify exclude list (skills, shadcn ui, `cn()`, PM2 configs). Rebuild: `graphify update .` |

Package-specific agent notes: [../../src/jobwright/AGENTS.md](../../src/jobwright/AGENTS.md).

## User data (not in git)

| Scope | Location |
|-------|----------|
| API keys | `<repo>/.env` (shared across profiles); optional `users/<id>/.env` overlay (CLI runs only) |
| Legacy single user | `~/.jobwright/` |
| Registry | `<repo>/users/users.yaml` |
| Per-user dir | `<repo>/users/<user_id>/` (`logs/last_run.json`, `logs/ops_health.json`, `logs/eval_*.json`, `.pipeline.lock`) |
| Backups | `JOBWRIGHT_BACKUP_DIR` (default `~/jobwright-backups`) |

Recommended deployment: repo + `users/` on the internal disk (e.g. `/Users/parthchandak/apps/jobwright`); the external SSD holds backups only.

Override: `JOBWRIGHT_USERS_ROOT`, `JOBWRIGHT_REPO`, `JOBWRIGHT_DIR`, `JOBWRIGHT_USER`.

Always: `jobwright --user <id> status` (`--user` before subcommand).

WhatsApp resolve: `scripts/resolve_user_from_whatsapp.sh 'whatsapp:…'`.

## Scripts (Hermes / cron)

| Script | Role |
|--------|------|
| `_jobwright_repo.sh` | Resolve repo root |
| `install_skills.sh` | Install thin Hermes/Cursor skill pointer |
| `install_hermes_scripts.sh` | Copy cron scripts to `~/.hermes/scripts/` |
| `setup_hermes_cron.sh` | Installs scripts, retires legacy crons, runs `jobwright ops install-crons` (skips briefs for unfinished profiles) |
| `jobwright_brief.sh` | Daily Brief (detached wrapper → `run_daily_brief.sh`) |
| `run_daily_brief.sh` | `preflight --fix`, default stages, `jobwright notify`, `ops brief-report` |
| `resolve_user_from_whatsapp.sh` | JID → `user_id` |
| `validate_pipeline.sh` | Doctor + unit checks |
| `jobwright_smoke.sh` | Narrow E2E brief (WhatsApp dry-run unless `SMOKE_LIVE=1`) |
| `restart.sh` | **Primary:** PM2/tmux restart (`--backend-only`, `--frontend-only`, `--prod-ui`, `--tmux`; tmux = dev auth + Hermes dry-run) |
| `ops_pm2.sh` | Alias → `restart.sh` |
| `dashboard_deploy.sh` | Alias → `restart.sh --prod-ui` |

Cron names: `jobwright-brief-<id>` (one daily brief per user, ~6:00, `--deliver local`). It runs the pipeline then `jobwright notify`, which sends ONE WhatsApp message listing new jobs (numbered: title @ company, location, dashboard deep link `jobwright.parthchandak.info/jobs/<job_id>`, date posted), then `ops brief-report`. Plus `jobwright-ops-watchdog` (hourly at :30), `jobwright-backup` (02:30) and `jobwright-weekly-summary` (Sunday 18:00, `jobwright summary`). No send/check crons.

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
| `POST` | `/api/jobs/{url}/tailor`, `/tailor/resume`, `/tailor/cover` | Spawn `jobwright tailor-job` (SSE handle; optional custom instructions). `{url}` may be the `job_id` |
| `GET` | `/api/tailor/defaults` | Default Auto Tailor instruction text |
| `GET` | `/api/me` | Login email, `is_admin`, `auth_mode`, openable profiles, active profile |
| `POST` | `/api/session` | Switch active profile (allowed ones only) |
| `GET` | `/api/status` | Last run, ops health, WhatsApp bridge (status banner) |
| `GET` | `/api/profile` | Active user, `apply_enabled`, `schedule` / `schedule_label` / `timezone`, `whatsapp_target`, `whatsapp_chat_name` |
| `PUT` | `/api/profile` | Save `schedule`, `weekly_summary`, `followup_days`, `whatsapp_target` (change is admin-only, 403 otherwise); re-syncs `jobwright-brief-<user>` only when schedule/chat change or the wrapper is missing; first sync after setup sends the one-time welcome |
| `GET` / `POST` | `/api/whatsapp/chats`, `/api/whatsapp/test` | Chat list (admin-only, 403 otherwise); test message (non-admins: own chat only) |
| `GET` / `POST` | `/api/onboarding/status`, `/profile`, `/draft`, `/confirm` | New-profile onboarding |
| `GET` / `PUT` / `PATCH` / `POST` | `/api/criteria`, `/api/criteria/suggest` | Match criteria; `PATCH {notify_threshold}` changes only the cutoff (derived rules stay derived) |
| `GET` / `POST` | `/api/quality`, `/api/quality/eval`, `/api/quality/rescore`, `/api/jobs/{url}/labels` | Match quality, label + score history |
| `GET` / `PATCH` / `DELETE` / `PUT` / `POST` | `/api/admin/users[/{id}]`, `/api/admin/settings`, `/api/admin/watchdog`, `/api/admin/ops-test` | Admin only |
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
| `JOBWRIGHT_DASHBOARD_USER` | Fallback active profile when a login may open several |
| `JOBWRIGHT_AUTH_MODE` / `JOBWRIGHT_CF_TEAM_DOMAIN` / `JOBWRIGHT_CF_AUD` | Dashboard auth (`cloudflare` in prod, `dev` local) |
| `JOBWRIGHT_ADMIN_EMAILS` / `JOBWRIGHT_DEV_EMAIL` | Extra admins; dev-mode identity |
| `LLM_MODEL` / `JOBWRIGHT_LLM_MODEL` | Default `accounts/fireworks/models/glm-5p3-flash`; brief scripts prefer `JOBWRIGHT_LLM_MODEL` |
| `JOBWRIGHT_SCORER` / `JOBWRIGHT_SCORE_WORKERS` / `JOBWRIGHT_REASONING_T1` / `LLM_ESCALATION_MODEL` | Scoring v2 (`v1` rollback; 16 workers; `low`; off) |
| `JOBWRIGHT_BACKUP_DIR` / `JOBWRIGHT_OPS_TARGET` / `JOBWRIGHT_OPS_HEARTBEAT` | Ops |
| `JOBWRIGHT_HERMES_DRY_RUN` | `1` in sandboxes: no cron changes, no WhatsApp sends |
| `JOBWRIGHT_PUBLIC_BASE_URL` | Deep-link base for `jobwright notify` (default `https://jobwright.parthchandak.info`) |
| `JOBWRIGHT_CORS_ORIGINS` | Comma-separated CORS origins for dashboard |
| `DISCOVER_MODE` | `fast` (tier-1, skip smart-extract) or `full` |
| `JOBWRIGHT_DISCOVER_BOARDS` | Restrict JobSpy boards without editing searches.yaml (e.g. `indeed`) |
| `JOBWRIGHT_DISCOVER_WORKERS` | JobSpy parallel worker cap (default 4) |
| `JOBWRIGHT_LINKEDIN` / `JOBWRIGHT_LINKEDIN_INTERVAL` | LinkedIn discovery client: `guest` (default, `discovery/linkedin.py`) or `jobspy` rollback; fastest spacing between LinkedIn requests (default 0.5s, widens on 429) |
| `JOBWRIGHT_WEB_RUN_ID` | Set by `/api/run` so CLI does not create a second registry row |
| `JOBWRIGHT_LOG_LEVEL` | `DEBUG` when `jobwright run --verbose` (Auto Search always passes `--verbose`) |

Templates: `.env.example`, `config/live.env.example`.
