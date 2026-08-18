# jobwright package (`src/jobwright/`)

Nested agent notes for the Python package. Root context: [../../AGENTS.md](../../AGENTS.md).

## Layout

| Module | Role |
|--------|------|
| `cli.py` | Typer entry; `--user` callback before subcommands |
| `pipeline.py` | `STAGE_ORDER`, stage runners, `--stream` mode |
| `config.py` | `set_active_user`, `set_app_dir`, path constants |
| `users.py` | Registry at `<repo>/users/users.yaml` |
| `database.py` | SQLite schema, `jobs` + `stage_history`, `advance_funnel`, stats |
| `web/` | FastAPI Kanban dashboard (board, materials, runs, gated apply) |
| `discovery/` | `jobspy.py`, `workday.py`, `known_urls.py`, `smartextract.py` (`DISCOVER_MODE`) |
| `enrichment/detail.py` | Full JD extraction |
| `scoring/` | `scorer`, `tailor`, `cover_letter`, `portfolio`, `pdf`, `docx_export`, `validator` |
| `network/` | CSV rank, per-job connect, Exa research |
| `apply/` | `launcher`, `chrome`, `prompt`, `dashboard`, `ats/` |
| `apply/providers/` | `base.parse_result_output`, `cursor_sdk`, `cursor_cli`, `claude` |
| `wizard/init.py` | `jobwright init` onboarding |
| `config/*.yaml` | Shipped employers, sites, search templates |

## Conventions

- Read paths from `jobwright.config` after bootstrap (not stale import aliases).
- Multi-profile: `set_active_user(user_id)` before DB/profile access.
- LLM calls: `jobwright.llm` (Gemini via `GEMINI_API_KEY`).
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

Add tests for new provider behavior or user-resolution logic.
