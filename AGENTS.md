# Agent guide (jobwright)

Entry point for **Cursor, Claude Code, Hermes, and cron wrappers**. Read this first; load linked docs only for your task (progressive disclosure).

**Humans:** [README.md](README.md). **Hermes skill install:** [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## What this is

**Product model:** jobwright is a daily career advisor for **any number of invited users**. Each user supplies a base resume, profile, search criteria and match criteria. The pipeline discovers jobs, scores fit with an LLM (scoring v2), tailors resume + cover letter per strong match (from base materials only), exports DOCX, and ranks LinkedIn connections per job. The web dashboard is the primary surface: every job is a card with tailored materials, connections, a match explanation, one-tap rating, and a gated apply button. Once per day the pipeline sends ONE WhatsApp message listing newly ready jobs, each with a deep link into the dashboard. The user reviews and applies from the dashboard; optional browser apply is gated and never runs from cron. LinkedIn jobs appear as cards; only auto-apply is blocked (`apply_blocked` in `sites.yaml`).

**Multi-user model (v0.6, [ADR-005](docs/adr/ADR-005-multi-user-auth-and-request-context.md)):** profiles live in `users/users.yaml` + `users/<id>/`. Each profile lists the Cloudflare Access login `emails` that may open it; a top-level `admins` list (plus `JOBWRIGHT_ADMIN_EMAILS`) may open, switch to, create and edit any profile; `ops_target` is where operator alerts go. A login with no profile lands on `/welcome`: six steps (About you → Resume upload with an LLM draft of profile, searches and match criteria → Your search → How we judge fit → Daily list (admins pick the chat; everyone else sees the connected chat read-only) + send time → Cover letters), then a review. Required steps are resume, profile and searches; a chat is not required. WhatsApp chats are admin-managed: only admins can list chats (`GET /api/whatsapp/chats`, 403 otherwise) or change a profile's `whatsapp_target` (`PUT /api/profile`, admin `PATCH`); everyone else sees their connected chat read-only (`whatsapp_chat_name` on `GET /api/profile`) and `POST /api/whatsapp/test` only reaches their own chat. When setup creates a profile's brief cron (resume + profile present, chat set), `welcome.py` sends a one-time welcome to that chat and a heads-up to `ops_target` (marker `users/<id>/logs/welcome_sent.json`; skipped under `JOBWRIGHT_HERMES_DRY_RUN`). The API binds the active profile per request (`config.user_context`, a ContextVar), so concurrent users never share paths. The Cloudflare Access allow policy `jobwright users` is kept equal to every profile email plus admins (`jobwright access sync`, Admin page card, and automatically after email/admin/profile changes when `CLOUDFLARE_API_TOKEN` is set; other policies are never touched).

**Auth:** `JOBWRIGHT_AUTH_MODE=cloudflare` (production pm2) verifies the `Cf-Access-Jwt-Assertion` header (or `CF_Authorization` cookie) against the team JWKS at `https://$JOBWRIGHT_CF_TEAM_DOMAIN/cdn-cgi/access/certs`, audience `JOBWRIGHT_CF_AUD`. `dev` (local, `restart.sh --tmux`) trusts the caller (`JOBWRIGHT_DEV_EMAIL`, or anonymous admin) and refuses requests carrying Cloudflare edge headers. Default: `cloudflare` when `JOBWRIGHT_CF_TEAM_DOMAIN` is set, else `dev`.

**Pipeline:** discover → enrich → score → portfolio → tailor → cover → **docx** → **connect**, then `jobwright notify`. CLI also has a **pdf** stage (`run pdf` / `run all`); the daily brief and Auto Search skip it. `jobwright run` with no stages runs the default brief list (honors `human_gate`); explicit stage lists run verbatim. Runs hold a per-user `flock` (`<user dir>/.pipeline.lock`) so cron, dashboard and CLI never overlap, and write `logs/last_run.json`. Discovery computes a cross-board `dedupe_key` (company | title | place); pruned or duplicate jobs are **tombstoned** (`job_tombstones`) so they never come back. After `score`, duplicate open cards already on the board (same key, or same company + title with a near-identical description, i.e. multi-location postings) are closed with outcome `duplicate` (`duplicate_of` = keeper job_id; rows and labels kept; applied/offer or hand-added cards are only reported); `jobwright dedupe` previews, `--apply` writes. **Human gate** (`human_gate` per user): default stages stop before materials (`discover enrich score portfolio connect`); notify sends a review-first top-N list; materials are generated on demand (dashboard Auto Tailor, or `jobwright run tailor cover docx`).

**Scoring v2 ([ADR-006](docs/adr/ADR-006-scoring-v2-labels-and-evals.md)):** one structured-output call per job (`scoring/matcher.py`) returns dealbreakers / concerns / location_ok / seniority / fit / confidence / reasoning, judged against the user's **match criteria** (`profile.json` `match_criteria`; derived from `job_preferences` when absent) and the 12 most similar **labeled past decisions** (TF-IDF, at least 4 positives). Gates are applied in code: hard dealbreaker or bad location caps at 3, salary below floor at 4, unknown location at 6. Default model `accounts/fireworks/models/glm-5p3-flash` with `reasoning_effort=low` (`JOBWRIGHT_REASONING_T1`), `JOBWRIGHT_SCORE_WORKERS` concurrent calls (default 16). Optional Jev prefilter (`jev_hybrid` in the user config; `on` = reject-only, never accepts). Escalation to a stronger model is opt-in (`LLM_ESCALATION_MODEL`, off). Every machine score goes to `score_history`, token use to `llm_usage`. `JOBWRIGHT_SCORER=v1` restores the legacy single-number scorer (the only path that still reads `SCORE_BATCH_SIZE`). Social-impact title caps/pruning are opt-in per user (`searches.yaml` `scoring: {mission_guard: true}`).

**Labels and evals:** human ratings are append-only in `score_labels` (with a job snapshot, so they survive pruning); `jobs.user_fit_score` mirrors the latest. Dashboard ratings (thumbs + reason chips) and "Not for me" dismissals with reasons both append labels and become retrieved examples on the next scoring run. `jobwright eval` replays the scorer on the labeled set and reports precision/recall at 6/7/8 versus stored production scores (report JSON in the user's `logs/`); run it before changing prompts, models or criteria logic.

**Ops ([ADR-007](docs/adr/ADR-007-ops-alerts-backups-internal-disk.md)):** `run_daily_brief.sh` runs `jobwright preflight --fix` (installs the Playwright Chromium the package needs), the pipeline, `notify` (writes `notify_sent N` / `notify_skipped <reason>` / `notify_failed <error>`), and always ends with `jobwright ops brief-report`, which alerts `ops_target` on any problem and writes `logs/ops_health.json` for the dashboard banner. Hermes crons (all `--no-agent`, `--deliver local`): `jobwright-brief-<user>`, `jobwright-ops-watchdog` (08:30, missed runs), `jobwright-backup` (02:30, `jobwright ops backup` to `JOBWRIGHT_BACKUP_DIR`), `jobwright-weekly-summary` (Sunday 18:00, `jobwright summary` for every profile; per-user opt-out `weekly_summary` in `users.yaml`). Recommended deployment: a checkout on the internal disk (e.g. `/Users/parthchandak/apps/jobwright`) with pm2 running uvicorn without `--reload`; the external SSD only holds backups.

**Kanban dashboard:** FastAPI + React at `jobwright.parthchandak.info` (local `:8002`). Lanes `backlog → prepare → applied → in_progress → offer → closed`; agent auto-advances to prepare; human owns Applied+. Pages: board, `/jobs/:jobId` (deep link, mobile-first drawer), `/profile` ("Settings": Search, Match rules, Documents, Daily list, About you), `/quality` (Match quality: plain-language accuracy, one-tap "Use N+" cutoff; eval/rescore and AI usage admin-only), `/admin` (admins only), `/welcome`. Every page has the phone menu. UI follows design v2 ("calm & refined"); build from the primitives in [.cursor/skills/frontend-tasteful](.cursor/skills/frontend-tasteful/SKILL.md) (WP6, board + drawer, pending). See [dashboard-hosting.md](docs/agents/dashboard-hosting.md) and [ADR-004](docs/adr/ADR-004-kanban-funnel-stage.md).

**Human-readable overview:** [README.md#the-daily-brief-how-it-works-with-hermes](README.md#the-daily-brief-how-it-works-with-hermes).

Version: `pyproject.toml` / `jobwright --version`.

---

## Always do

- Put `--user` **before** subcommands: `jobwright --user <id> status`
- Resolve WhatsApp sender before profile commands: `scripts/resolve_user_from_whatsapp.sh`
- Export `JOBWRIGHT_HERMES_DRY_RUN=1` in any sandbox, worktree or test run that could touch Hermes (cron create/edit and `hermes send` become log lines). `restart.sh --tmux` sets it by default.
- Run `jobwright --user <id> eval` before and after any scoring prompt/model/criteria change; report the precision/recall delta
- Run quality gate before commit: `pytest tests/ -v` and `ruff check src/`
- Sync [AGENTS.md](AGENTS.md) before commit/push if you changed CLI, stages, paths, scripts, or safety gates (see [.cursor/rules/agents-doc-sync.mdc](.cursor/rules/agents-doc-sync.mdc))
- Hermes ops: set `JOBWRIGHT_REPO` to your clone; install thin skill via `./scripts/install_skills.sh` ([docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md))

## Ask first

- Live apply (`jobwright apply --live`)
- `jobwright users set <id> --apply` (enables live apply for that profile)
- Deleting user data (`users remove --delete-data`, Admin page delete)
- Changing `admins`, a profile's `emails`, or `ops_target`
- `jobwright access sync --yes` (rewrites who can log in through Cloudflare Access)
- `jobwright rescore` on a real profile (replaces current scores; history is kept)
- Multi-file refactors outside the task scope
- Committing or pushing (only when user asks)

## Never do

- Auto-apply from cron
- LinkedIn job apply (blocked in code)
- `jobwright apply --live` from cron (apply only from the dashboard or an explicit manual command)
- Send test WhatsApp messages to a real user's group (e.g. richa's). Test sends go only to a chat the owner picks, or run with `JOBWRIGHT_HERMES_DRY_RUN=1`
- Finish setup (`PUT /api/profile`, admin `PATCH`) for a real profile outside dry run just to try it: the welcome message is real and one-time (delete `users/<id>/logs/welcome_sent.json` only if the owner asks for a resend)
- Run `jobwright_smoke.sh` or a brief for a real profile from a sandbox without `JOBWRIGHT_HERMES_DRY_RUN=1` (it sends the real WhatsApp list)
- Run prod uvicorn with `--reload`, or point prod pm2 at a working tree agents edit
- Use `gpt-oss*` models (banned by the owner)
- Commit `.env`, `users/`, `~/.jobwright/`, or secrets

---

## Commands

```bash
# Setup
pip install -e ".[dev,web]"        # or run everything via: uv run --extra dev --extra web ...
.venv/bin/playwright install chromium   # enrich + apply; `jobwright preflight --fix` does this

# Health
jobwright doctor
jobwright --user <id> preflight [--fix] [--json]   # exit 1 on a blocking failure
pytest tests/ -v
ruff check src/
bash scripts/validate_pipeline.sh

# Daily Brief pipeline (multi-profile)
jobwright --user <id> run -w 4 --min-score 7          # default brief stages (honors human_gate)
DISCOVER_MODE=full jobwright --user <id> run discover enrich score portfolio tailor cover docx connect -w 4
jobwright --user <id> notify [--dry-run]              # ONE WhatsApp list; --dry-run previews only
jobwright --user <id> briefstats --days 14            # per-brief precision proxy
jobwright --user <id> dedupe [--apply]                # duplicate open cards (preview by default)
jobwright [--user <id>] summary [--dry-run] [--days 7] [--force]   # weekly WhatsApp recap (all profiles without --user)

# Scoring v2: criteria, labels, evals
jobwright --user <id> criteria show
jobwright --user <id> criteria suggest [--save]      # draft from resume + ratings
jobwright --user <id> labels list --limit 30
jobwright --user <id> labels export /tmp/labels.jsonl
jobwright --user <id> eval [--limit 60] [--examples 12] [--escalation-model <m>]
jobwright --user <id> rescore --scope active|labeled|all|since:<days> [--dry-run]

# Ops
jobwright --user <id> ops brief-report [--status-file F] [--force]
jobwright ops watchdog [--grace 120]
jobwright ops set-target 'whatsapp:<jid>'            # '' clears
jobwright ops backup [--dest DIR] [--keep 14]
jobwright ops install-crons [--backup-dest DIR]   # upsert every jobwright Hermes cron (briefs, watchdog, backup, weekly summary); skips briefs for profiles that haven't finished setup (resume + profile)
jobwright access status                           # Cloudflare Access allowlist diff vs users.yaml
jobwright access sync [--yes]                     # dry-run unless --yes; writes only policy "jobwright users"
jobwright hermes channels [--apply] [--prune] [--config PATH]   # per-profile WhatsApp group prompts in ~/.hermes/config.yaml; then hermes gateway restart

# Per-job materials (dashboard Auto/Custom Tailor)
jobwright --user <id> tailor-job --url "https://example.com/jobs/123"
jobwright --user <id> tailor-job --url "https://..." --resume-only --resume-instructions-file /tmp/r.txt
jobwright --user <id> tailor-job --url "https://..." --cover-only --cover-instructions-file /tmp/c.txt

# Apply: dry-run unless --live (and live needs apply_enabled)
jobwright --user <id> apply --limit 1
jobwright --user <id> apply --live --url "https://..."

# Kanban dashboard
cp ecosystem.config.example.js ecosystem.config.js   # once
./scripts/restart.sh --tmux                          # dev: api --reload (auth dev, Hermes dry-run) + Vite :5120
./scripts/restart.sh                                 # pm2 api :8002 + Vite :5120
# ./scripts/restart.sh --backend-only | --frontend-only | --prod-ui
# Prod on this host: ./scripts/dashboard_deploy.sh  (docs/agents/dashboard-hosting.md)

# Agent JSON
./bin/job-apply-pp-cli status --agent --user <id>

# Users (CLI; emails/admins are edited in the dashboard Admin page or users.yaml)
jobwright users list
jobwright users add <id> --name "Name" --whatsapp "whatsapp:..." --template nontech-bay-area
jobwright users set <id> --human-gate --brief-top-n 10

# Hermes install (from clone)
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh
# Crons: docs/agents/hermes-setup.md (the dashboard creates/edits jobwright-brief-<user> on save)
```

`--stream` was removed from `jobwright run`. The dashboard spawns runs with `python -m jobwright` so the run registry records real exit codes.

Env (full list with comments: `.env.example`): `FIREWORKS_API_KEY` (preferred), `LLM_MODEL` (default `accounts/fireworks/models/glm-5p3-flash`), `JOBWRIGHT_LLM_MODEL` (brief scripts: overrides `LLM_MODEL`), `GEMINI_API_KEY` (failover on empty content; `GEMINI_FALLBACK_MODEL` default `gemini-3.7-flash`, `GEMINI_THINKING_LEVEL` default `low`), `JOBWRIGHT_SCORE_WORKERS` (default 16), `JOBWRIGHT_REASONING_T1` (default `low`), `LLM_ESCALATION_MODEL` (off), `JOBWRIGHT_SCORER` (`v2` default, `v1` rollback), `JOBWRIGHT_LLM_PRICES` (cost estimates), `JOBWRIGHT_BRIEF_MAX_AGE_DAYS` (default 7), `JOBWRIGHT_AUTH_MODE`, `JOBWRIGHT_CF_TEAM_DOMAIN`, `JOBWRIGHT_CF_AUD`, `JOBWRIGHT_ADMIN_EMAILS`, `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (Access allowlist sync), `JOBWRIGHT_CF_HOSTNAME`, `JOBWRIGHT_DEV_EMAIL` (dev-mode identity), `JOBWRIGHT_PUBLIC_BASE_URL` (deep-link base, default `https://jobwright.parthchandak.info`), `JOBWRIGHT_BACKUP_DIR` (default `~/jobwright-backups`), `JOBWRIGHT_OPS_TARGET`, `JOBWRIGHT_OPS_HEARTBEAT`, `JOBWRIGHT_HERMES_DRY_RUN`, `DISCOVER_MODE=fast|full`, `JOBWRIGHT_HOURS_OLD`, `JOBWRIGHT_DISCOVER_BOARDS`, `JOBWRIGHT_DISCOVER_WORKERS` (default 4), `JOBWRIGHT_CONNECT_LIMIT` (default 15), `EXA_API_KEY`, `CURSOR_API_KEY` + `AGENT_PROVIDER=cursor-sdk` (apply), `JOBWRIGHT_WEB_RUN_ID` (set by dashboard spawns), `JOBWRIGHT_LOG_LEVEL`, `JOBWRIGHT_DASHBOARD_USER` (fallback active profile when a login may open several), `BRIEF_SMOKE=1` (narrow E2E; `jobwright_smoke.sh` waits for `done RC=` and reports notify). A profile may add `users/<id>/.env` (e.g. `TYPESAFE_API_KEY`); only that profile's CLI runs see it.

---

## End-to-end flow (dashboard + one daily notice)

**User inputs (once per profile, usually via `/welcome`):** `resume/base.pdf`, `profile.json` (incl. `match_criteria`), `searches.yaml`, `cover-letter/examples/`, optional `connections.csv`, WhatsApp chat + brief time.

**Daily brief cron** (`jobwright-brief-<user>`, default 6:00, `--deliver local`): `jobwright_brief.sh` launches `run_daily_brief.sh` detached (an already-running brief is left alone): preflight → default stages → `notify` → `ops brief-report`. Notify sends ONE plain-text WhatsApp message to the user's `whatsapp_target` listing new jobs (discovered within `JOBWRIGHT_BRIEF_MAX_AGE_DAYS`), each with a `/jobs/<job_id>` deep link, stamps `whatsapp_notified_at`, and skips when nothing is new. Up to 3 due follow-ups (Applied with no stage change for `followup_days`, default 10) are appended at the end. Problems alert `ops_target`, not the user's chat.

**Dashboard:** `GET /api/me` returns the login, admin flag and openable profiles; `POST /api/session` switches profile (only to allowed ones). **Auto Search** runs the prep pipeline (`POST /api/run`, SSE `GET /api/stream/{run_id}`, **Stop** `POST /api/runs/{run_id}/stop`; runs persist in `users/<id>/logs/web_runs.json`). **WhatsApp** header dialog: pending count and **Send now** (`POST /api/notify`). Settings → Daily list: admins get the chat picker (`GET /api/whatsapp/chats`, admin-only, every chat Hermes can post to); others see the connected chat read-only. Test send (`POST /api/whatsapp/test`: admins may pass a `target`, others always hit their own chat), brief time; autosave (`PUT /api/profile`) re-syncs `jobwright-brief-<user>` only when the schedule or chat changes, or the per-user wrapper is missing (`hermes_cron.brief_cron_installed`). Job drawer: match explanation, rating (`PATCH /api/jobs/{url}` → label), stage picker, follow-up reminder with "Followed up" / "No response" (`POST /api/jobs/{url}/followup`), dismiss with reasons, materials with Auto/Custom Tailor (`POST /api/jobs/{url}/tailor/resume|cover`). Status banner (`GET /api/status`): last run, ops health, WhatsApp bridge. Quality (`/api/quality`, `/api/quality/eval`, `/api/quality/rescore`), criteria (`GET`/`PUT /api/criteria`, `PATCH /api/criteria {notify_threshold}` cutoff-only so derived rules stay derived, `POST /api/criteria/suggest`), admin (`/api/admin/overview`, `/api/admin/users` (+ `PATCH`/`DELETE /api/admin/users/{id}`, `POST /api/admin/users/{id}/test-message`, `POST /api/admin/users/{id}/run`), `/api/admin/costs`, `/api/admin/settings`, `/api/admin/access[/sync]`, `/api/admin/hermes-channels[/apply]`, `/api/admin/watchdog`, `/api/admin/ops-test`), onboarding (`/api/onboarding/status|profile|draft|confirm`).

**Apply:** dry-run by default. Live apply requires `apply_enabled=true` and runs only from the dashboard apply button (confirm gate) or an explicit `jobwright apply --live`. Never from cron.

**User's job:** review curated roles, rate them (this trains the scorer), use tailored DOCX, act on network suggestions, apply manually or via gated agent apply.

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
| Kanban dashboard hosting, auth, app surfaces | [docs/agents/dashboard-hosting.md](docs/agents/dashboard-hosting.md) |
| Multi-user auth / request context | [ADR-005](docs/adr/ADR-005-multi-user-auth-and-request-context.md) |
| Scoring v2, labels, evals | [ADR-006](docs/adr/ADR-006-scoring-v2-labels-and-evals.md) |
| Alerts, backups, internal disk | [ADR-007](docs/adr/ADR-007-ops-alerts-backups-internal-disk.md) |
| Dashboard UI (build / polish / primitives) | [.cursor/skills/frontend-tasteful/SKILL.md](.cursor/skills/frontend-tasteful/SKILL.md) |
| Cursor stage 6 | [docs/agents/cursor-setup.md](docs/agents/cursor-setup.md) |
| Human WhatsApp UX | [docs/agents/whatsapp-user-guide.md](docs/agents/whatsapp-user-guide.md) |
| Package code | [src/jobwright/AGENTS.md](src/jobwright/AGENTS.md) |
| Glossary / ADRs | [docs/GLOSSARY.md](docs/GLOSSARY.md), [docs/adr/](docs/adr/) |
| Contributing | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) |
| Commit / push / deploy workflow | [.cursor/skills/deploy/SKILL.md](.cursor/skills/deploy/SKILL.md) |
| Cursor agent workflow (todos, skills, finish end-to-end) | [.cursor/rules/agent-orchestration.mdc](.cursor/rules/agent-orchestration.mdc) |
| Codebase exploration (graphify by symbol, then grep/read) | [.cursor/rules/graphify.mdc](.cursor/rules/graphify.mdc) |
| Pipeline / Hermes ops (skill entry) | [.cursor/skills/pipeline-operator/SKILL.md](.cursor/skills/pipeline-operator/SKILL.md) |

Full agent doc index: [docs/agents/README.md](docs/agents/README.md). Cursor skills: `.cursor/skills/` (22 skills; commit/push/deploy is `.cursor/skills/deploy`, not a separate commit skill).

---

## Hermes vs repo

| What | Where |
|------|-------|
| Code, tests, scripts | This git clone (`JOBWRIGHT_REPO`) |
| Agent docs | `AGENTS.md`, `docs/agents/` (in clone) |
| Hermes skill | `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/` (thin loader + `JOBWRIGHT_REPO` file) |
| Hermes cron scripts | `~/.hermes/scripts/jobwright_*.sh`; generated `wrap_jobwright-brief-<user>.sh`, `jobwright_ops_watchdog.sh`, `jobwright_backup.sh` |
| Repo path references | `~/.hermes/scripts/_jobwright_repo.sh`, the skill `JOBWRIGHT_REPO` file, `~/.hermes/config.yaml` (per-profile group prompts; regenerate with `jobwright hermes channels --apply`), generated wrappers; update all of them when the checkout moves |

Cloning this repo does **not** register Hermes skills automatically. Run `./scripts/install_skills.sh` from your clone path.

---

**Last verified:** `0.6.0` (2026-09-26). Multi-user: Cloudflare Access JWT → `users.yaml` `emails` / `admins` / `ops_target`, per-request `config.user_context` (`src/jobwright/web/auth.py`, `web/session.py`, `config.py`). Scoring v2 (`scoring/matcher.py`, `pipeline_v2.py`, `criteria.py`, `examples.py`, `evaluate.py`, `criteria_miner.py`; tables `score_labels`, `score_history`, `llm_usage`; default `glm-5p3-flash` + `reasoning_effort=low`). Tombstones + cross-board dedupe (`job_tombstones`, `discovery/dedupe.py`). Ops (`ops.py`, `preflight.py`, `hermes_cron.py`: brief/watchdog/backup crons, `--deliver local`). Onboarding + admin-managed WhatsApp chats (`onboarding.py`, `whatsapp.py` incl. `chat_name` with a 10-minute group-name cache, `welcome.py`, `web/routers/{onboarding,whatsapp,admin,quality}.py`). Design v2 WP1–WP5 (2026-09-27): `frontend/src/components/{ui,welcome,profile,admin}/`. Apply dry-run unless `--live`. Quality gate: `uv run --extra dev --extra web pytest tests/ -q`; scoped `ruff check` on changed `src/` files. Dashboard Access session: 30d (`720h`). Hermes loader template is `3.1.0`; re-run `./scripts/install_skills.sh` after pull.

## graphify

Local product map (gitignored `graphify-out/`). Cursor rule: [.cursor/rules/graphify.mdc](.cursor/rules/graphify.mdc). Exclude list: `.graphifyignore`.

After clone: `graphify update .`. Optional cluster names: `graphify label . --backend gemini` (Gemini batch 1/2 may fail with `Unterminated string`; do not invent names).

Query **symbols** (`get_connection`, `run_pipeline`, `JobDrawer`), not slogans. `path` for A→B, `explain` for one node. Skip for known-file one-line edits. After code or ignore changes: `graphify update .`. Never commit `graphify-out/`.
