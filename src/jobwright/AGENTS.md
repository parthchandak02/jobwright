# jobwright package (`src/jobwright/`)

Nested agent notes for the Python package. Root context: [../../AGENTS.md](../../AGENTS.md).

## Layout

| Module | Role |
|--------|------|
| `cli.py` | Typer entry; `--user` before subcommands. Stages: discover, enrich, score, portfolio, tailor, cover, pdf, docx, connect. Also `tailor-job`, `notify`, `briefstats`, `dedupe` (`--apply`), `summary`, `eval`, `rescore`, `criteria show\|suggest`, `labels list\|export`, `preflight`, `ops brief-report\|watchdog\|set-target\|backup\|install-crons`, `hermes channels`, `access status\|sync`, `users`. `apply` is dry-run unless `--live` |
| `__main__.py` | `python -m jobwright` (dashboard spawns); records the exit code in the run registry |
| `pipeline.py` | `STAGE_ORDER`, stage runners, `default_brief_stages()` (honors `human_gate`), per-user `pipeline_lock()` (flock), `logs/last_run.json`; prunes backlog junk after `score` |
| `run_registry.py` | Durable pipeline runs in `users/<id>/logs/web_runs.json`; honors `JOBWRIGHT_WEB_RUN_ID` |
| `resume.py` | PDF source of truth; pymupdf4llm markdown cache at `resume/base.md` for LLM stages |
| `notify.py` | One WhatsApp list of new jobs + dashboard deep links; `send_via_hermes` (honors `JOBWRIGHT_HERMES_DRY_RUN`) |
| `summary.py` | Weekly WhatsApp recap per profile (`jobwright summary`); mark-then-send via `logs/weekly_summary.json`; `run_summary_all` loops `users.yaml`; `_moved` counts a stage move only if the job is still in that stage (or further along) |
| `followups.py` | Follow-up reminders: Applied with no stage change for `followup_days`; `due_followups`, `record_followed_up` (snooze), `record_no_response` (close) |
| `config.py` | Per-user paths on a `_PathState`; `set_active_user` (CLI, process default), `user_context(user_id)` (web, per request via ContextVar), `user_env()` (per-user `.env` read without touching `os.environ`) |
| `users.py` | Registry at `<repo>/users/users.yaml`: users (`emails`, schedule, `human_gate`, `brief_top_n`, `apply_enabled`, `weekly_summary`, `followup_days`), `admins`, `ops_target`; `users_for_email`, `is_admin_email` |
| `cf_access.py` | Cloudflare API v4 client: find the Access app (aud, else hostname), read app + reusable policies, `plan_sync` / `apply_sync` of the `jobwright users` allow policy only, `auto_sync` (best effort, web) |
| `onboarding.py` | New profile bound to a login email; LLM draft of profile / searches / criteria from a resume; `apply_draft`; `onboarding_status` (complete = resume + profile + searches; no chat needed), `is_set_up` (resume + profile: gates brief crons and the welcome) |
| `calibration.py` | Optional post-setup "rate a few jobs": `select_jobs` mixes borderline (5-7, twice as often), high and low scores, one per company/title, skips labeled/closed/dead jobs; `calibration()` backs `GET /api/onboarding/calibration` (no LLM) |
| `welcome.py` | One-time welcome in the person's chat + operator heads-up to `ops_target` when setup creates their brief cron (`PUT /api/profile`, admin `PATCH`); `send_welcome_async`; marker `logs/welcome_sent.json`; no-op in dry run. Real messages: never trigger for a real profile to test |
| `whatsapp.py` | Chat list for the admin picker (`hermes send --list whatsapp --json` + bridge names; `GET /api/whatsapp/chats` is admin-only), `chat_name` (display name for a target; resolved group names cached 10 minutes in `_name_cache` so the admin overview doesn't flip to raw ids), test send |
| `hermes_cron.py` | Create/edit/remove `jobwright-brief-<user>` (`--no-agent --deliver local`, generated wrapper), `jobwright-ops-watchdog`, `jobwright-backup`, `jobwright-weekly-summary`; `brief_cron_installed` (wrapper exists); `hermes_dry_run()` |
| `hermes_channels.py` | Per-profile WhatsApp group entries in `~/.hermes/config.yaml` (override prompt, channel prompt, skill binding, allow list) via ruamel round-trip; `plan` / `apply` (backup, atomic, dry-run aware), orphan detection |
| `ops.py` | Brief report, missed-run watchdog, alert delivery to `ops_target`, `logs/ops_health.json`, `backup_users` |
| `preflight.py` | Pre-run checks (profile/resume, LLM key, disk, Playwright with `--fix`, Hermes CLI, WhatsApp bridge) |
| `labels.py` | Append-only `score_labels`, `record_label`, eval set (explicit labels + board signals) |
| `job_identity.py` | `resolve_company` (never a board name), `material_prefix` (`<company>_<title>_<job_id>`) |
| `llm.py` | Fireworks (default `accounts/fireworks/models/glm-5p3-flash`) / Gemini failover / OpenAI-compatible; `reasoning_effort`, structured output, usage flushed to `llm_usage` |
| `database.py` | SQLite schema: `jobs`, `stage_history`, `job_tombstones` (+ triggers), `score_labels`, `score_history`, `llm_usage`, `schema_meta`; `job_id` (blake2b of URL), `advance_funnel`, stats |
| `web/` | FastAPI: `auth.py` (Cloudflare Access JWT / dev), `session.py` (identity + per-request profile middleware), `jobkeys.py` (job routes accept `job_id`), routers `board`, `materials`, `runs`, `settings`, `notify`, `system` (`/me`, `/session`, `/profile` incl. `whatsapp_chat_name`; `PUT /profile` chat change admin-only, cron re-sync only on schedule/chat change or missing wrapper), `onboarding`, `whatsapp` (admin-only chats; non-admin test goes to own chat), `admin`, `quality` (`PATCH /criteria` cutoff-only), `connections`, `jobs` |
| `discovery/` | `jobspy.py` (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`, known-URL skip), `workday.py`, `filters.py` (fit caps; `mission_guard` opt-in), `dedupe.py` (cross-board `dedupe_key`; `collapse_duplicates` closes duplicate open cards after score), `cleanup.py` (`prune_after_score`), `known_urls.py`, `smartextract.py` (`DISCOVER_MODE`) |
| `enrichment/` | `detail.py` (full JD), `sponsorship.py` (LLM, not on discover hot path) |
| `scoring/` | v2: `matcher.py` (structured judgment + gates), `pipeline_v2.py` (select, Jev reject-only, persist, `score_history`), `criteria.py` (`match_criteria`), `examples.py` (TF-IDF retrieval), `evaluate.py` (`jobwright eval`), `criteria_miner.py`. Legacy: `scorer.py` (`JOBWRIGHT_SCORER=v1`, `SCORE_BATCH_SIZE`), `fastpath.py` (Jev). Also `tailor`, `tailor_instructions`, `cover_letter`, `portfolio`, `pdf`, `docx_export`, `validator` |
| `network/` | CSV rank, per-job connect, Exa research |
| `apply/` | `launcher`, `chrome`, `prompt`, `dashboard`, `ats/` |
| `apply/providers/` | `base.parse_result_output`, `cursor_sdk`, `cursor_cli`, `claude` |
| `wizard/init.py` | `jobwright init` onboarding (PDF resume, not `.txt`) |
| `config/*.yaml` | Shipped employers, sites, search templates |

## Conventions

- Read paths from `jobwright.config` after bootstrap (not stale import aliases). Never cache a user path at module import time.
- CLI: `set_active_user(user_id)` before DB/profile access. Web: handlers already run inside `config.user_context(...)`; use `current_user_id(request)` and never switch the process default.
- Per-user settings in web code: `config.user_env(key)`, not `os.environ`.
- LLM calls: `jobwright.llm` (Fireworks preferred via `FIREWORKS_API_KEY`; Gemini failover via `GEMINI_API_KEY`). No `gpt-oss*` models.
- New code paths that send WhatsApp (welcome, test, brief) must stay no-ops under `JOBWRIGHT_HERMES_DRY_RUN`; tests stub `welcome.send_welcome_async` in `conftest.py`.
- Anything that calls `hermes` goes through `hermes_cron._run_hermes` or `notify.send_via_hermes` so `JOBWRIGHT_HERMES_DRY_RUN` is honored.
- Human ratings: `labels.record_label` (append-only). Never overwrite `score_labels`.
- Resume text for LLM stages: `resume.load_resume_text()` (PDF → cached markdown).
- Stage 6 stdout must include one `RESULT:` line (see `apply/providers/base.py`).

## Verify a change

```bash
pytest tests/ -v
ruff check src/jobwright/
python -c "from jobwright.apply.providers.base import parse_result_output; assert parse_result_output('RESULT:APPLIED')=='applied'"
jobwright --user <id> eval --limit 60   # scoring changes only
jobwright --user <id> eval --reuse users/<id>/logs/eval_<ts>.json --borderline 5-6   # re-gate a stored run; only new calls cost tokens
```

Single-user doctor: `jobwright doctor`. Multi-profile: `jobwright --user <id> doctor`.

## Tests

| File | Covers |
|------|--------|
| `tests/conftest.py` | Hermetic fixtures (temp `JOBWRIGHT_USERS_ROOT`) |
| `tests/test_users_and_filters.py` | Registry, user paths, filters, prune, apply dry-run default, `python -m` registers every command |
| `tests/test_web_auth.py` | JWT verification, per-email access, admin switching, concurrent mixed-user requests |
| `tests/test_web_multiuser.py` | Onboarding, non-admin isolation, admin settings, chat filtering, `job_id` routes + labels |
| `tests/test_scoring_v2.py` | Criteria, gates, retrieval, labels, eval metrics, incremental persistence |
| `tests/test_scoring_recall.py` | Borderline second opinion, threshold sweep + recommendation, eval `--reuse`, `/api/quality` recommendation |
| `tests/test_scorer.py` | Legacy batch score JSON mapping |
| `tests/test_llm_hardening.py` | LLM retries, structured-output fallback, usage + cost |
| `tests/test_pipeline_integrity.py` | Tombstones, dedupe, run lock, run summary / stage failures |
| `tests/test_dedupe_backlog.py` | Duplicate open cards: grouping, keeper choice, close + tombstone, CLI, drawer link |
| `tests/test_ops.py` | Brief report, watchdog, preflight, backups |
| `tests/test_notify.py` | Notify formatting and status lines |
| `tests/test_resume.py` | PDF → markdown, cache |
| `tests/test_run_registry.py` | `web_runs.json`, `JOBWRIGHT_WEB_RUN_ID` |
| `tests/test_runs_api.py` | `POST /api/run`, list/stop/stream |
| `tests/test_materials_tailor_api.py` | `POST /api/jobs/{url}/tailor` (spawns `tailor-job`) |
| `tests/test_subtle_tailor.py` | Dashboard instruction prompts |
| `tests/test_cover_letter_examples.py` | Cover-letter example PDF settings API |
| `tests/test_admin_console.py` | Admin v2 API: overview shape + broken profile, patch validation/threshold storage/cron side effects, test message, per-user run |
| `tests/test_cf_access.py` | Access allowlist plan/apply against a mocked Cloudflare API, admin-only routes, best-effort sync hooks |
| `tests/test_followups_summary.py` | Follow-up due logic, snooze, no-response close, notify appendix, weekly summary content and mark-then-send, weekly cron |
| `tests/test_hermes_channels.py` | Hermes config round-trip, per-user prompts, orphans, idempotency, dry-run, backup, CLI + admin API |
| `tests/test_calibration.py` | Calibration selection (band mix, dedupe, exclusions) and `GET /api/onboarding/calibration` with ratings through the label route |
| `tests/test_welcome.py` | Welcome text, send once + operator heads-up, skip without chat or in dry run, failed send retried next time |
| `tests/test_hermes_cron.py` | Parse `hermes cron list`; create/edit brief cron; dry-run |

Add tests for new provider behavior, user-resolution logic, or dashboard APIs.
