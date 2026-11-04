# Changelog

All notable changes to jobwright will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed (scoring rate limits and blocked boards, 2026-11-04)
- **Rate limits no longer drop jobs from scoring.** Structured scoring calls retry 429/5xx and transport errors up to `JOBWRIGHT_LLM_STRUCTURED_ATTEMPTS` (6) times with jittered exponential backoff (2-32s) that honors `Retry-After`, capped at 60s. `score_jobs` shares an adaptive limiter across its `JOBWRIGHT_SCORE_WORKERS` threads: a 429 halves the calls in flight (once per burst), successes raise it back by one; a call backing off gives up its slot. Only successful responses are counted in `llm_usage`. 401/402/403 still stop the stage (`BillingDead`). The score stage detail has `retries`, `rate_limited`, `workers`, `workers_min`; brief-report prints `scored N jobs (E failed, R rate-limit retries)`.
- **Blocked job boards are skipped, not retried all run.** A per-run circuit breaker (`discovery/site_breaker.py`) skips a JobSpy board after `JOBWRIGHT_SITE_BLOCK_THRESHOLD` (3) blocked responses in a row (JobSpy's logged 403 / 429), and the LinkedIn guest client after 3 searches it gave up on. A board blocked for the whole run sits out `JOBWRIGHT_SITE_COOLDOWN_DAYS` (3) days (`logs/site_cooldown.json`), then gets one probe. Source health lists it as `blocked` / `cooldown`, brief-report shows `zip_recruiter: blocked, skipped until <date>` instead of an error per query, and it does not make discover `partial`.
- **ZipRecruiter is no longer a default board** (it answered HTTP 403 to every query for days). Default JobSpy boards are Indeed and LinkedIn; a profile whose `searches.yaml` lists `zip_recruiter` in `boards` still gets it. The profile templates and the Settings "recommended boards" match.

### Fixed (ops reliability review, 2026-11-03; ADR-007 §7)
- **Brief report told the truth only when the pipeline finished.** `ops brief-report` now fails on a nonzero `pipeline_rc`, a run killed at its deadline, or a `logs/last_run.json` that is not this run's (it must start after the status file's `brief_started at=`, and not be a dashboard run: "no fresh run summary"); a run skipped because another run held the lock (`jobwright run` exits 75, status `pipeline_locked`) warns and names the holder; 0 scored jobs warns. Paused profiles stay ok.
- **Broken job boards are visible.** Discovery records `{new, errors, rate_limited, status}` per source in `last_run.json` (`discover.detail.sources`): JobSpy boards with per-site errors, the LinkedIn guest client's requests given up after repeated 429/999, Workday employer errors, each impact board, smart extract. The report prints one `sources:` line and warns on 0 new with errors, rate limiting or a `partial` discover.
- **A failed WhatsApp list is retried.** The hourly watchdog re-runs `notify` for a profile whose brief ended `notify_failed` (or never notified) once hermes and the bridge are healthy, at most `JOBWRIGHT_NOTIFY_RETRIES` (3) per day (`logs/notify_retries.json`, `notify_retry N/M` status lines).
- **Alerts no longer depend only on Hermes.** When `hermes send` fails (or no ops target is set), alerts go to `JOBWRIGHT_OPS_FALLBACK`: `macos` (Notification Center; default on macOS) and/or an ntfy topic URL (`JOBWRIGHT_OPS_NTFY_TOKEN` optional), `off` disables.
- **No duplicate WhatsApp lists.** Notify claims rows atomically (`UPDATE ... RETURNING`, `BEGIN IMMEDIATE` fallback) under a per-profile non-blocking lock (`.notify.lock`; a second caller returns "already sending"), sends only what it claimed and releases only its own claim on failure. A hermes timeout is "maybe delivered": the claim is kept, nothing is resent automatically, the jobs are logged in `logs/notify_uncertain.json`, status `notify_uncertain`; `jobwright --user <id> ops release-uncertain` unmarks them after checking the chat.
- **Backups.** Any crash alerts (an unmounted backup volume is reported, never created on the internal disk); every copied DB gets `PRAGMA integrity_check`; old snapshots are not pruned after a snapshot with errors; stale `*.bak` / `*-wal` / `smoke*.db` files are skipped; SQLite connections are closed. New `jobwright ops restore --snapshot <name|latest> --user <id> [--to DIR] [--force]` restores to a separate folder by default (a live profile only with `--force`, moved aside first) and integrity-checks the result. `ops backup` also deletes brief status/PID files and brief logs older than 30 days (`--cleanup-days`).
- **Runs cannot hang forever.** `run_daily_brief.sh` has a hard deadline for preflight + pipeline (`JOBWRIGHT_BRIEF_TIMEOUT`, default 3h): the step's process group is killed, status `timeout ...`, and notify (`JOBWRIGHT_NOTIFY_TIMEOUT`, 300s) and the report still run; the script now exits with the pipeline's code. Enrich has a soft budget (`JOBWRIGHT_STAGE_BUDGET_ENRICH`, 45 min; any stage via `JOBWRIGHT_STAGE_BUDGET_<STAGE>`). The watchdog reports "brief still running for Xh" / "timed out" / "process gone" instead of "no brief started", and honours the schedule's day-of-week (and day-of-month, month).
- **Dedupe false merges.** Work-arrangement words are stripped only as title annotations (`(Contract)`, `- Temporary`, `Remote - ...`), so "Contract Manager" no longer equals "Manager". A closed card blocks a repost only within the 45-day window, so a role that reopens later comes back.
- **Scorer example bias.** Only human closes with outcome `not_interested` are implicit negatives; bulk "Not for me" closes record `source=bulk_dismiss` and fill at most a quarter of the few-shot block; examples are deduped by company + title and show the label's reason chips.
- CI runs the backend on Python 3.11 and 3.13 and lints `tests/`; `privacy.yml` pins actions to commit SHAs.

### Changed
- **Phone navigation and board** (under 768px; desktop unchanged): the slide-out menu is replaced by a bottom tab bar (Jobs, Quality, Admin for admins, Settings; `SHELL_LINKS` is the single list for it and the desktop sidebar). The board shows one lane at a time under a scrollable stage strip with counts (the `?stage=` filter; the last lane is remembered); swipe sideways to change lanes, and long-press a card to drop it on any stage. The table gets the same strip with "All". The profile switcher and theme toggle sit in the Settings header.

### Added
- **Pause the search** ("Keep looking for new jobs", per person; `search_enabled` in `users.yaml`, default true). When off, the scheduled brief (`jobwright run` with no stages) skips every stage; notify sends no job list, only due follow-ups, and only when that set changed since the last follow-up-only message (`logs/followup_notice.json`); `ops brief-report` reports "paused" (ok, ignores the stale `last_run.json`) and the watchdog never alerts for the profile. Explicit stage lists (`jobwright run discover ...`, dashboard Auto Search) and the dashboard's Send now still work. Set it in Settings → Daily list, from the board banner ("New job search is paused · N jobs in Backlog" with Resume), on the Admin page, via `PUT /api/profile {search_enabled}` / admin `PATCH /api/admin/users/{id}`, or `jobwright users set <id> --pause-search|--search`. Admin overview rows carry `search_enabled` and a `backlog` count. The weekly summary is unchanged.
- **Impact job boards** (`discovery/impactboards.py`): deterministic scrapers for curated social-sector boards (GIIN, The Impact Job, Skoll, Net Impact, Rippleworks, Next Billion, FinDev Gateway, WAVE, On Purpose, SIS Global and CSR Jobs trackers). No LLM, so they run in `DISCOVER_MODE=fast` and the daily brief. Disable with `IMPACT_BOARDS=0`, skip browser boards with `IMPACT_BOARDS_BROWSER=0`. Health check: `scripts/check_impact_boards.py`; notes in `docs/agents/impact-job-boards.md`.
- Dashboard favicon (`frontend/public/favicon.svg`).

### Security
- Purged personal data from the public git history (emails, names, WhatsApp ids, a real profile file, school/employer names in fixtures) with `git filter-repo`; all branches force-pushed on 2026-09-28.
- Personal-data guard: `scripts/check_private_data.py` as pre-commit/pre-push hooks (`scripts/install_git_hooks.sh`), CI workflow `privacy.yml`, and `tests/test_privacy_guard.py`. `jobwright init --template nontech-bay-area` now seeds the generic `profile.example.json`.

### Documentation
- **README rewritten as a landing page**: hero banner, why, how it works (5 steps + one Mermaid flowchart of the daily brief), screenshot grid, features table, a secret-free 5-minute demo, install split by audience, configuration tables, safety callout, and reference sections in `<details>` blocks.
- Images in `docs/images/` (`hero.png`, `board.png`, `job-drawer.png`, `welcome.png`, `settings-daily-list.png`, `admin.png`, `whatsapp-list.png`) come from `scripts/readme_images.py`: the built dashboard in headless Chromium with every `/api/**` call answered by fake fixtures (a person "Alex Rivera", made-up companies, example.com links) and all other network requests blocked; the WhatsApp image renders the exact text `notify.build_review_notification` + `followups.format_followups` produce for those jobs. Regenerate: `cd frontend && pnpm run build`, then `uv run --extra web --with pillow python scripts/readme_images.py`; `--demo` opens the same fake-data dashboard in a visible window.
- Fixed in the README: the daily brief and Auto Search do not skip `pdf` for profiles without review-first (the full default list is every stage); review-first (`human_gate`) is on for new profiles and runs `discover enrich score portfolio connect`, sending "N new jobs for your review" capped at 10; direct career sites (smart extract) only run with `DISCOVER_MODE=full`, the daily brief runs `fast`; JobSpy boards listed correctly (LinkedIn and Glassdoor were missing, defaults are Indeed, LinkedIn, ZipRecruiter); `python-jobspy` is a normal dependency now, so the `pip install --no-deps python-jobspy` workaround is gone; the `jobwright-weekly-eval` cron (Sunday 17:00, `ops weekly-eval`) was missing; install uses `uv sync --extra web --extra dev`; the dashboard build (Vite 7) needs Node 20.19+, which the old requirements table did not mention.
- README refresh: the screenshot grid is full (new `match-quality.png` and `materials.png`, a prepared job's tailored resume; `scripts/readme_images.py` gained `/api/quality` and `resume_preview`/`cover_preview` fixtures); Install says plainly there is no hosted sign-up; safety and build sections cover the personal-data guard and `scripts/install_git_hooks.sh`; `searches.yaml` row mentions the remote scope (US only or all countries). Fixed: the test count is 349, not 343. The other seven images regenerate byte-identical.

### Changed
- **LinkedIn discovery no longer goes through JobSpy** (`discovery/linkedin.py`). A client for LinkedIn's public (logged-out) job endpoints is shared by every worker: search on the jobs-guest API, descriptions from the public job page (`/jobs/view/<id>`, falling back to jobs-guest `jobPosting/<id>` only when the page has none). It never stores LinkedIn's cookies (a cookie session is throttled to about one request a second; without cookies a 16-search crawl runs roughly twice as fast). Requests start `JOBWRIGHT_LINKEDIN_INTERVAL` apart (default 0.5s); a 429 or 999 widens the spacing once per burst and retries only that request after 2/4/8s, successes narrow it again. Search pages 10 at a time newest first (JobSpy's growing stride skipped results), skips known URLs and applies location, title, company and card-salary filters before fetching a description, fetches each description once per run, and stops after two pages with nothing new. Jobs whose description fails the filters are remembered for 7 days in `logs/linkedin_rejects.json` (cleared when the filter settings change) so daily runs stop re-fetching them. US-scoped Remote searches ask for "United States" plus the remote filter instead of worldwide "Remote", and unknown countries no longer crash a search (`Invalid country string`). Indeed and other boards still use JobSpy, in their own call. `JOBWRIGHT_LINKEDIN=jobspy` restores the old path.
- WhatsApp chats are admin-managed: `GET /api/whatsapp/chats` is admin-only (403 otherwise) and changing `whatsapp_target` via `PUT /api/profile` is admin-only; non-admins see their connected chat read-only (`ConnectedChat`, `whatsapp_chat_name` on `GET /api/profile`) on Welcome and Settings; `POST /api/whatsapp/test` goes only to the caller's own chat for non-admins; onboarding no longer requires a chat (required: resume, profile, searches).
- **Design v2 ("calm & refined")** across Welcome, Settings, Admin and Match quality: system font stack (no font CDN), soft neutrals with one indigo accent (also in dark mode), type scale with a 12px floor, no glass blur, visible field hints, one save model (autosave + `SaveStatus`; sticky `ActionBar` for Match rules), 44px touch targets and bottom-sheet dialogs on phones. Welcome split into six steps (`components/welcome/*`). Profile page renamed **Settings** with underline tabs (`components/profile/*Tab.tsx`, `useAutosave`); the "WhatsApp" tab is now **Daily list** (URL value still `whatsapp`). Admin redesigned (`components/admin/*`: system list, people table with column headers on desktop, `PersonSheet` bottom sheet on phones, `StatusDot`, `ConfirmDialog`, Remove in a "⋯" menu). Match quality speaks plain language to job seekers, keeps eval/rescore and AI usage admin-only, and offers one-tap "Use N+". Board and job drawer (WP6) not yet migrated.
- Profile saves re-sync the brief cron only when the schedule or chat changes, or when the per-user wrapper is missing (`hermes_cron.brief_cron_installed`).
- `jobwright ops install-crons` skips brief crons for profiles that haven't finished setup (`onboarding.is_set_up`: resume + profile).
- Derived match criteria honour a stored `match_criteria.notify_threshold`.
- **WhatsApp daily list is formatted**: each job is a numbered card with a bold title, company and match score, location, posted date and dashboard link, one emoji per line (native WhatsApp `*bold*` / `_italic_`, `whatsapp.bold`/`italic`; `hermes send` does not convert markdown). Follow-ups and the weekly summary use the same style. The posted date comes from the new `jobs.date_posted` column (JobSpy, the LinkedIn guest client and Workday's "Posted N Days Ago"); jobs without one show "Found <date>".
- **Watchdog runs hourly** (was 08:30 daily): alerts once per problem per day (`logs/watchdog_alerts.json`) when a brief has not started 30 min after its time or has not finished 120 min after it started, skips profiles still in setup, and first installs the brief cron (plus the one-time welcome) for any set-up profile with a chat but no cron.
- `PUT /api/profile` only creates a brief cron once setup is done (resume + profile), so an early send-time save no longer schedules a brief that can only fail.

### Fixed
- Daily briefs died before starting when `.env` held unquoted JSON (`JOBWRIGHT_LLM_PRICES={...}`): the launcher `source`s `.env` in bash. `.env.example` now shows the value single-quoted.
- The 08:30 watchdog never checked briefs scheduled after 06:30, so a 07:00 brief could fail silently.
- The discovery salary floor no longer drops jobs over numbers in the description that are not pay (years like "2027", headcounts, "401k", "$50M raised", sign-on bonuses, equity): description scans now read only $ / USD amounts, with hour/month units and a plausible annual range (`filters.parse_salary_from_text`). Structured salary fields are parsed as before.
- Weekly summary counts a stage move only if the job is still in that stage or further along (`summary._moved`).
- Admin overview no longer flips WhatsApp group names to raw ids: `whatsapp.chat_name` caches resolved group names for 10 minutes (`_name_cache`).

### Added
- **Rate a few jobs** after setup (optional): "Find my first jobs" now opens `/welcome/rate`, which waits (polling `GET /api/onboarding/calibration`) until about 10 jobs are scored, then shows up to 10 to rate ("Good fit" / "Not for me" with reason chips, or Skip). Jobs mix borderline (5-7), high and low scores, one per company and title, excluding anything already rated (`calibration.py`, no LLM calls). Ratings use the existing label route (`PATCH /api/jobs/{id}` → `score_labels`). The board shows a dismissible "Rate 10 jobs to sharpen your list" banner until the profile has 10 ratings (dismissal kept per profile in localStorage).
- **Design v2 primitives** (`frontend/src/index.css` tokens; `components/ui/*`): `Page` / `PageHeader` / `PageColumn`, `SectionHeader`, `FormField` (visible hints), `SaveStatus`, `ActionBar`, `EmptyState`, `MobileNav` (menu on every page), `Chip` / `ValueChip` / `ChipInput`, `Switch`, `Segmented`, `Select`, `DropdownMenu`, `Skeleton`, `TabsList variant="underline"`, `DialogContent` sizes (bottom sheet on phones). Rules and catalog: `.cursor/skills/frontend-tasteful/`.
- **Welcome message** (`welcome.py`): when setup creates a person's brief cron (`PUT /api/profile` or admin `PATCH /api/admin/users/{id}`), one welcome goes to their chat and a heads-up to `ops_target`. Once per profile (marker `users/<id>/logs/welcome_sent.json`), skipped under `JOBWRIGHT_HERMES_DRY_RUN`, failed sends retried on the next sync; tests stub `send_welcome_async`.
- `PATCH /api/criteria {notify_threshold}`: change only the daily-list cutoff (1–10); derived rules stay derived. Used by Match quality "Use N+".
- **Weekly summary** (`jobwright summary [--dry-run] [--days 7] [--force]`, `summary.py`): one WhatsApp recap per profile (new jobs found, sent, applied, moved to interviews / offer, closed, top 3 open jobs with dashboard links, due follow-ups). Mark-then-send via `logs/weekly_summary.json`; skips when sent in the last 6 days or nothing happened. `jobwright-weekly-summary` Hermes cron (Sunday 18:00, `--deliver local`) runs it for every profile and is part of `jobwright ops install-crons`. Per-user opt-out `weekly_summary` in `users.yaml` (default true), editable on Settings → Daily list
- **Follow-up reminders** (`followups.py`): applied jobs with no stage change for `followup_days` (per user, default 10) are due. Board cards and the job drawer show "Follow up? Applied N days ago"; drawer actions "Followed up" (stamps `followed_up_at`, snoozes N days via `follow_up_at`) and "No response" (closes, `close_reason=no_response`, outcome `ghosted`). `POST /api/jobs/{key}/followup`. Up to 3 due follow-ups are appended to the daily notify message and the weekly summary
- **Cost per profile** on the Admin page: `GET /api/admin/costs?days=30` (admins only) reads each profile's `llm_usage` read-only and reports calls, tokens and estimated cost (stored `cost_usd`, else `JOBWRIGHT_LLM_PRICES`), plus a total
- `PUT /api/profile` accepts `weekly_summary` and `followup_days` (the brief cron is only touched when schedule or chat change, or the wrapper is missing)
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
