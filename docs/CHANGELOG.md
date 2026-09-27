# Changelog

All notable changes to jobwright will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- WhatsApp chats are admin-managed: non-admins see their connected chat read-only (Welcome and Profile pages) and cannot list chats or change it; test sends go only to their own chat; onboarding no longer requires a chat.

### Added
- **Weekly summary** (`jobwright summary [--dry-run] [--days 7] [--force]`, `summary.py`): one WhatsApp recap per profile (new jobs found, sent, applied, moved to interviews / offer, closed, top 3 open jobs with dashboard links, due follow-ups). Mark-then-send via `logs/weekly_summary.json`; skips when sent in the last 6 days or nothing happened. `jobwright-weekly-summary` Hermes cron (Sunday 18:00, `--deliver local`) runs it for every profile and is part of `jobwright ops install-crons`. Per-user opt-out `weekly_summary` in `users.yaml` (default true), editable on Profile → WhatsApp
- **Follow-up reminders** (`followups.py`): applied jobs with no stage change for `followup_days` (per user, default 10) are due. Board cards and the job drawer show "Follow up? Applied N days ago"; drawer actions "Followed up" (stamps `followed_up_at`, snoozes N days via `follow_up_at`) and "No response" (closes, `close_reason=no_response`, outcome `ghosted`). `POST /api/jobs/{key}/followup`. Up to 3 due follow-ups are appended to the daily notify message and the weekly summary
- **Cost per profile** on the Admin page: `GET /api/admin/costs?days=30` (admins only) reads each profile's `llm_usage` read-only and reports calls, tokens and estimated cost (stored `cost_usd`, else `JOBWRIGHT_LLM_PRICES`), plus a total
- `PUT /api/profile` accepts `weekly_summary` and `followup_days` (the brief cron is only touched when schedule or chat change)
- `jobwright hermes channels [--apply] [--prune] [--config PATH]`: per-profile Hermes WhatsApp group instructions generated from `users.yaml` (system prompt scoped to that user only, channel prompt, skill binding, `group_allow_from`). ruamel.yaml round-trip keeps comments and key order; backup + atomic write; orphans reported, removed only with `--prune`; honors `JOBWRIGHT_HERMES_DRY_RUN`. Admin page card "WhatsApp group instructions" with Apply (`/api/admin/hermes-channels`). New dependency `ruamel.yaml>=0.18`.
- **Admin console v2 API** (admins only, see `docs/agents/admin-console-spec.md`): `GET /api/admin/overview` (system strip: bridge, Access, Hermes group instructions, ops target name; one row per person with setup state, health, last brief, WhatsApp chat name, schedule, cutoff + recommended cutoff from the latest stored eval, list size, gates, 7-day counts, due follow-ups, 30-day AI cost, Hermes status, brief cron present). System sources run in parallel with a 6 s cap; a broken profile yields a `fail` row instead of an error. `PATCH /api/admin/users/{id}` also accepts `whatsapp_target`, `hour`+`minute` or `schedule`, `notify_threshold` (stored in that profile's `match_criteria.notify_threshold`, derived rules stay derived), `weekly_summary`, `followup_days`; schedule/chat changes re-sync the brief cron only for set-up profiles; returns the updated overview row. `POST /api/admin/users/{id}/test-message` and `POST /api/admin/users/{id}/run` (default brief stages in that profile's context and run registry)

## [0.6.0] - 2026-09-26

Multi-user, high-confidence matching, robust ops. See ADR-005, ADR-006, ADR-007.

### Added
- **Cloudflare Access auth** (`web/auth.py`): `JOBWRIGHT_AUTH_MODE=cloudflare|dev`, JWT verified against `JOBWRIGHT_CF_TEAM_DOMAIN` JWKS and `JOBWRIGHT_CF_AUD`; dev mode refuses requests that came through Cloudflare
- **Per-email profiles**: `users.yaml` users carry `emails`, top-level `admins` (plus `JOBWRIGHT_ADMIN_EMAILS`) and `ops_target`; each login sees only its own profile, admins can switch and create (`GET /api/me`, `POST /api/session`)
- **Onboarding** at `/welcome`: resume upload, LLM-drafted profile / searches / match criteria, review, confirm (`/api/onboarding/*`)
- **WhatsApp chat picker** (`GET /api/whatsapp/chats` from `hermes send --list whatsapp`, names from the bridge) and test send (`POST /api/whatsapp/test`); saving the brief time creates the Hermes cron if missing
- **Admin page** (`/admin`): profiles, emails, human gate, notify cap, admins, ops target, watchdog cron, test alert
- **Scoring v2** (`scoring/matcher.py`, `pipeline_v2.py`): per-user `match_criteria`, retrieved labeled examples, structured output, gates in code (dealbreaker / location cap 3, salary cap 4, unknown location cap 6), Jev reject-only prefilter, opt-in escalation (`LLM_ESCALATION_MODEL`)
- **Labels and history**: append-only `score_labels` (with job snapshot), `score_history` for every machine score, `llm_usage` token ledger; pre-v0.6 human rescores imported once (`source=import_pre_v06`)
- Dashboard **ratings** (thumbs + reason chips), **dismiss with reasons**, **match explanation**, **Match rules** editor, **Match quality** page (`/quality`), status banner
- CLI: `eval`, `rescore`, `criteria show|suggest`, `labels list|export`, `preflight [--fix]`, `ops brief-report|watchdog|set-target|backup`
- **Operator alerts**: every brief ends with `ops brief-report` (alerts `ops_target`, writes `logs/ops_health.json`); `jobwright-ops-watchdog` cron for missed runs
- **Backups**: `jobwright ops backup` (SQLite online backup + rsync `--link-dest` snapshots, 14-day retention) to `JOBWRIGHT_BACKUP_DIR`; `jobwright-backup` cron
- **Job tombstones** (`job_tombstones`) so pruned jobs never return; **cross-board dedupe** (`discovery/dedupe.py`)
- Pipeline per-user `flock` lock and `logs/last_run.json`; run registry records real exit codes (`python -m jobwright`)
- `JOBWRIGHT_HERMES_DRY_RUN=1` turns cron changes and WhatsApp sends into log lines (default in `restart.sh --tmux`)

### Changed
- Default LLM `accounts/fireworks/models/glm-5p3-flash` with `reasoning_effort=low` for scoring; `gpt-oss*` banned
- Active profile is bound per request (`config.user_context` ContextVar) instead of mutating module globals; per-user `.env` overlay applies only to CLI processes
- `jobwright apply` is dry-run unless `--live`; `APPLY_DRY_RUN` removed from `.env.example`
- Brief crons are created `--no-agent --deliver local`; the brief sends its own WhatsApp list and leaves an already-running brief alone
- `run_daily_brief.sh` runs `preflight --fix`, lets the pipeline pick stages from `human_gate`, and writes truthful `notify_sent` / `notify_skipped` / `notify_failed` status lines
- Social-impact mission guard is opt-in per user (`searches.yaml` `scoring: {mission_guard: true}`)
- Generated materials are named `<company>_<title>_<job_id>` so postings never overwrite each other; company comes from the job, never the board name
- Deep links use `/jobs/:jobId` routes; mobile-first job drawer with stage picker
- Production pm2 runs uvicorn without `--reload`; Vite binds to `127.0.0.1`
- Recommended deployment moves the checkout and `users/` to the internal disk; the external SSD holds backups

### Removed
- `jobwright run --stream`
- `SCORE_BATCH_SIZE` as a primary knob (read only by the `JOBWRIGHT_SCORER=v1` fallback)

## [0.3.0 - 0.5.0] (not itemized per release)

### Added
- Dashboard **WhatsApp** header control: schedule time + target + pending count; Save writes `users.yaml` and edits `jobwright-brief-<user>` (`PUT /api/profile`)
- Dashboard **Auto Search** runs the full prep pipeline (`discover` through `connect`) with live SSE logs, stop, and attach after reload (`run_registry` / `logs/web_runs.json`)
- `jobwright notify` plus `POST /api/notify`: one WhatsApp list of new `prepare` jobs with `/jobs/<job_id>` deep links (`whatsapp_notified_at`)
- Resume PDF source of truth (`resume.py`, pymupdf4llm → `resume/base.md`); `GET`/`PUT /api/settings/resume.pdf`
- Per-job **Auto Tailor** / **Custom Tailor** (`POST /api/jobs/{url}/tailor` spawns `jobwright tailor-job` with SSE; defaults from `GET /api/tailor/defaults`)
- Profile search editors: query tiers, locations, excludes, board toggles
- Cover letter example PDFs on Profile (`PUT /api/settings/cover-letters`); amalgamated into tailor + cover prompts
- JobSpy parallelism (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`) and known-URL skip

### Changed
- Daily brief default `--min-score` is 7 (`APPLY_MIN_SCORE`, same as Auto Search)
- Workday discovery honors `exclude_companies` and uses the posting path when location is blank (drops India-path leaks)
- Fit scores for generic ops / CoS / GTM / clinical-without-mission cap at 4; Auto Search prunes backlog junk after scoring (keeps human-held and prepare+ cards)
- Auto Search tailor batch default `APPLY_PREP_LIMIT=25` so high-fit jobs are not stuck in backlog
- Auto Search no longer redraws the Kanban on every log tick; Board view no longer falls through to an empty table while the board is loading
- Mobile job deep links (`/jobs/:id`, WhatsApp in-app browser): native drawer scroll, opaque sheet, board unpainted while open
- WhatsApp is a pointer into the dashboard; no materials-N, digest, or CONFIRM-APPLY over chat
- Daily cron is pipeline then notify (`jobwright-brief-<user>`); `jobwright-send` / `jobwright-check` retired
- Profile search chips and boards autosave (no Save button)

## [0.2.0] - 2026-02-17

### Added
- **Parallel workers for discovery/enrichment** - `jobwright run --workers N` enables
  ThreadPoolExecutor-based parallelism for Workday scraping, smart extract, and detail
  enrichment. Default is sequential (1); power users can scale up.
- **Apply utility modes** - `--gen` (generate prompt for manual debugging), `--mark-applied`,
  `--mark-failed`, `--reset-failed` flags on `jobwright apply`
- **Dry-run mode** - `jobwright apply --dry-run` fills forms without clicking Submit
- **5 new tracking columns** - `agent_id`, `last_attempted_at`, `apply_duration_ms`,
  `apply_task_id`, `verification_confidence` for better apply-stage observability
- **Manual ATS detection** - `manual_ats` list in `config/sites.yaml` skips sites with
  unsolvable CAPTCHAs (e.g. TCS iBegin)
- **Qwen3 `/no_think` optimization** - automatically saves tokens when using Qwen models
- **`config.DEFAULTS`** - centralized dict for magic numbers (`min_score`, `max_apply_attempts`,
  `poll_interval`, `apply_timeout`, `viewport`)

### Fixed
- **Config YAML not found after install** - moved `config/` into the package at
  `src/jobwright/config/` so YAML files (employers, sites, searches) ship with `pip install`
- **Search config format mismatch** - wizard wrote `searches:` key but discovery code
  expected `queries:` with tier support. Aligned wizard output and example config
- **JobSpy install isolation** - removed python-jobspy from package dependencies due to
  broken numpy==1.26.3 exact pin in jobspy metadata. Installed separately with `--no-deps`
- **Scoring batch limit** - default limit of 50 silently left jobs unscored across runs.
  Changed to no limit (scores all pending jobs in one pass)
- **Missing logging output** - added `logging.basicConfig(INFO)` so per-job progress for
  scoring, tailoring, and cover letters is visible during pipeline runs

### Changed
- **Blocked sites externalized** - moved from hardcoded sets in launcher.py to
  `config/sites.yaml` under `blocked:` key
- **Site base URLs externalized** - moved from hardcoded dict in detail.py to
  `config/sites.yaml` under `base_urls:` key
- **SSO domains externalized** - moved from hardcoded list in prompt.py to
  `config/sites.yaml` under `blocked_sso:` key
- **Prompt improvements** - screening context uses `target_role` from profile,
  salary section includes `currency_conversion_note` and dynamic hourly rate examples
- **`acquire_job()` fixed** - writes `agent_id` and `last_attempted_at` to proper columns
  instead of misusing `apply_error`
- **`profile.example.json`** - added `currency_conversion_note` and `target_role` fields

## [0.1.0] - 2026-02-17

### Added
- 6-stage pipeline: discover, enrich, score, tailor, cover letter, apply
- Multi-source job discovery: Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs
- Workday employer portal support (46 preconfigured employers)
- Direct career site scraping (28 preconfigured sites)
- 3-tier job description extraction cascade (JSON-LD, CSS selectors, AI fallback)
- AI-powered job scoring (1-10 fit scale with rationale)
- Resume tailoring with factual preservation (no fabrication)
- Cover letter generation per job
- Autonomous browser-based application submission via Playwright
- Interactive setup wizard (`jobwright init`)
- Cross-platform Chrome/Chromium detection (Windows, macOS, Linux)
- Multi-provider LLM support (Gemini, OpenAI, local models via OpenAI-compatible endpoints)
- Pipeline stats and HTML results dashboard
- YAML-based configuration for employers, career sites, and search queries
- Job deduplication across sources
- Configurable score threshold filtering
- Safety limits for maximum applications per run
- Detailed application results logging
