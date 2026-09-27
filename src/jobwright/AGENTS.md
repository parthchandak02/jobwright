# jobwright package (`src/jobwright/`)

Nested agent notes for the Python package. Root context: [../../AGENTS.md](../../AGENTS.md).

## Layout

| Module | Role |
|--------|------|
| `cli.py` | Typer entry; `--user` before subcommands. Stages: discover, enrich, score, portfolio, tailor, cover, pdf, docx, connect. Also `tailor-job`, `notify`, `briefstats`, `eval`, `rescore`, `criteria show\|suggest`, `labels list\|export`, `preflight`, `ops brief-report\|watchdog\|set-target\|backup`, `access status\|sync`, `users`. `apply` is dry-run unless `--live` |
| `__main__.py` | `python -m jobwright` (dashboard spawns); records the exit code in the run registry |
| `pipeline.py` | `STAGE_ORDER`, stage runners, `default_brief_stages()` (honors `human_gate`), per-user `pipeline_lock()` (flock), `logs/last_run.json`; prunes backlog junk after `score` |
| `run_registry.py` | Durable pipeline runs in `users/<id>/logs/web_runs.json`; honors `JOBWRIGHT_WEB_RUN_ID` |
| `resume.py` | PDF source of truth; pymupdf4llm markdown cache at `resume/base.md` for LLM stages |
| `notify.py` | One WhatsApp list of new jobs + dashboard deep links; `send_via_hermes` (honors `JOBWRIGHT_HERMES_DRY_RUN`) |
| `config.py` | Per-user paths on a `_PathState`; `set_active_user` (CLI, process default), `user_context(user_id)` (web, per request via ContextVar), `user_env()` (per-user `.env` read without touching `os.environ`) |
| `users.py` | Registry at `<repo>/users/users.yaml`: users (`emails`, schedule, `human_gate`, `brief_top_n`, `apply_enabled`), `admins`, `ops_target`; `users_for_email`, `is_admin_email` |
| `cf_access.py` | Cloudflare API v4 client: find the Access app (aud, else hostname), read app + reusable policies, `plan_sync` / `apply_sync` of the `jobwright users` allow policy only, `auto_sync` (best effort, web) |
| `onboarding.py` | New profile bound to a login email; LLM draft of profile / searches / criteria from a resume; `apply_draft` |
| `whatsapp.py` | Chat picker (`hermes send --list whatsapp --json` + bridge names; non-admins see only chats with their phone) and test send |
| `hermes_cron.py` | Create/edit/remove `jobwright-brief-<user>` (`--no-agent --deliver local`, generated wrapper), `jobwright-ops-watchdog`, `jobwright-backup`; `hermes_dry_run()` |
| `ops.py` | Brief report, missed-run watchdog, alert delivery to `ops_target`, `logs/ops_health.json`, `backup_users` |
| `preflight.py` | Pre-run checks (profile/resume, LLM key, disk, Playwright with `--fix`, Hermes CLI, WhatsApp bridge) |
| `labels.py` | Append-only `score_labels`, `record_label`, eval set (explicit labels + board signals) |
| `job_identity.py` | `resolve_company` (never a board name), `material_prefix` (`<company>_<title>_<job_id>`) |
| `llm.py` | Fireworks (default `accounts/fireworks/models/glm-5p3-flash`) / Gemini failover / OpenAI-compatible; `reasoning_effort`, structured output, usage flushed to `llm_usage` |
| `database.py` | SQLite schema: `jobs`, `stage_history`, `job_tombstones` (+ triggers), `score_labels`, `score_history`, `llm_usage`, `schema_meta`; `job_id` (blake2b of URL), `advance_funnel`, stats |
| `web/` | FastAPI: `auth.py` (Cloudflare Access JWT / dev), `session.py` (identity + per-request profile middleware), `jobkeys.py` (job routes accept `job_id`), routers `board`, `materials`, `runs`, `settings`, `notify`, `system` (`/me`, `/session`, `/profile`, `/status`), `onboarding`, `whatsapp`, `admin`, `quality`, `connections`, `jobs` |
| `discovery/` | `jobspy.py` (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`, known-URL skip), `workday.py`, `filters.py` (fit caps; `mission_guard` opt-in), `dedupe.py` (cross-board `dedupe_key`), `cleanup.py` (`prune_after_score`), `known_urls.py`, `smartextract.py` (`DISCOVER_MODE`) |
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
| `tests/test_scorer.py` | Legacy batch score JSON mapping |
| `tests/test_llm_hardening.py` | LLM retries, structured-output fallback, usage + cost |
| `tests/test_pipeline_integrity.py` | Tombstones, dedupe, run lock, run summary / stage failures |
| `tests/test_ops.py` | Brief report, watchdog, preflight, backups |
| `tests/test_notify.py` | Notify formatting and status lines |
| `tests/test_resume.py` | PDF → markdown, cache |
| `tests/test_run_registry.py` | `web_runs.json`, `JOBWRIGHT_WEB_RUN_ID` |
| `tests/test_runs_api.py` | `POST /api/run`, list/stop/stream |
| `tests/test_materials_tailor_api.py` | `POST /api/jobs/{url}/tailor` (spawns `tailor-job`) |
| `tests/test_subtle_tailor.py` | Dashboard instruction prompts |
| `tests/test_cover_letter_examples.py` | Cover-letter example PDF settings API |
| `tests/test_cf_access.py` | Access allowlist plan/apply against a mocked Cloudflare API, admin-only routes, best-effort sync hooks |
| `tests/test_hermes_cron.py` | Parse `hermes cron list`; create/edit brief cron; dry-run |

Add tests for new provider behavior, user-resolution logic, or dashboard APIs.
