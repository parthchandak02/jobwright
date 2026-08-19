# jobwright package (`src/jobwright/`)

Nested agent notes for the Python package. Root context: [../../AGENTS.md](../../AGENTS.md).

## Layout

| Module | Role |
|--------|------|
| `cli.py` | Typer entry; `--user` before subcommands. Stages: discover, enrich, score, portfolio, tailor, cover, pdf, docx, connect. Also `tailor-job` (one URL, dashboard-spawned) |
| `pipeline.py` | `STAGE_ORDER`, stage runners, `--stream` mode; registers runs via `run_registry` |
| `run_registry.py` | Durable pipeline runs in `users/<id>/logs/web_runs.json`; honors `JOBWRIGHT_WEB_RUN_ID` |
| `resume.py` | PDF source of truth; pymupdf4llm markdown cache at `resume/base.md` for LLM stages |
| `notify.py` | One WhatsApp list of new `prepare` jobs + dashboard deep links |
| `config.py` | `set_active_user`, `set_app_dir`, path constants (`RESUME_PDF_PATH`, `RESUME_MD_PATH`) |
| `users.py` | Registry at `<repo>/users/users.yaml`; cron label/clock helpers for dashboard schedule |
| `hermes_cron.py` | Find/edit existing `jobwright-brief-<user>` via `hermes cron` |
| `database.py` | SQLite schema, `jobs` + `stage_history`, `job_id` (blake2b of URL), `whatsapp_notified_at`, `advance_funnel`, stats |
| `web/` | FastAPI Kanban: board, materials (incl. `POST .../tailor`), runs + SSE, settings (searches/resume.pdf/cover-letter PDFs), notify, gated apply |
| `discovery/` | `jobspy.py` (`-w` / `JOBWRIGHT_DISCOVER_WORKERS`, known-URL skip), `workday.py`, `filters.py`, `known_urls.py`, `smartextract.py` (`DISCOVER_MODE`) |
| `enrichment/` | `detail.py` (full JD), `sponsorship.py` (LLM, not on discover hot path) |
| `scoring/` | `scorer`, `tailor`, `tailor_instructions` (dashboard Auto/Custom prompts), `cover_letter`, `portfolio`, `pdf`, `docx_export`, `validator` |
| `network/` | CSV rank, per-job connect, Exa research |
| `apply/` | `launcher`, `chrome`, `prompt`, `dashboard`, `ats/` |
| `apply/providers/` | `base.parse_result_output`, `cursor_sdk`, `cursor_cli`, `claude` |
| `wizard/init.py` | `jobwright init` onboarding (PDF resume, not `.txt`) |
| `config/*.yaml` | Shipped employers, sites, search templates |

## Conventions

- Read paths from `jobwright.config` after bootstrap (not stale import aliases).
- Multi-profile: `set_active_user(user_id)` before DB/profile access.
- LLM calls: `jobwright.llm` (Fireworks preferred via `FIREWORKS_API_KEY`; Gemini failover via `GEMINI_API_KEY`).
- Resume text for LLM stages: `resume.load_resume_text()` (PDF → cached markdown).
- Stage 6 stdout must include one `RESULT:` line (see `apply/providers/base.py`).

## Verify a change

```bash
pytest tests/ -v
ruff check src/jobwright/
python -c "from jobwright.apply.providers.base import parse_result_output; assert parse_result_output('RESULT:APPLIED')=='applied'"
```

Single-user doctor: `jobwright doctor`. Multi-profile: `jobwright --user <id> doctor`.

## Tests

| File | Covers |
|------|--------|
| `tests/test_users_and_filters.py` | Registry, user paths, filters |
| `tests/test_scorer.py` | Batch score JSON mapping |
| `tests/test_resume.py` | PDF → markdown, cache |
| `tests/test_run_registry.py` | `web_runs.json`, `JOBWRIGHT_WEB_RUN_ID` |
| `tests/test_runs_api.py` | `POST /api/run`, list/stop/stream |
| `tests/test_materials_tailor_api.py` | `POST /api/jobs/{url}/tailor` (spawns `tailor-job`) |
| `tests/test_subtle_tailor.py` | Dashboard instruction prompts |
| `tests/test_cover_letter_examples.py` | Cover-letter example PDF settings API |
| `tests/test_hermes_cron.py` | Parse `hermes cron list`; edit existing brief cron |

Add tests for new provider behavior, user-resolution logic, or dashboard APIs.
