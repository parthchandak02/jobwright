# Changelog

All notable changes to jobwright will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Fit scores for generic ops / CoS without a social-impact mission cap at 4; JobSpy also searches `target_companies`
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
