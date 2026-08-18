# Commit overlay (jobwright)

Used by [.cursor/skills/deploy/SKILL.md](.cursor/skills/deploy/SKILL.md) and [.cursor/rules/agents-doc-sync.mdc](.cursor/rules/agents-doc-sync.mdc).

## Doc-sync matrix

| File | Update when |
|------|-------------|
| `AGENTS.md` | CLI, pipeline, environment variables, Always/Ask/Never, task table, version |
| `docs/agents/repo-map.md` | Paths, scripts, source layout |
| `docs/agents/hermes-operator-guide.md` | Hermes workflows, folder layout |
| `docs/agents/whatsapp-routing.md` | Inbound phrases, daily notify, apply safety |
| `docs/agents/hermes-setup.md` | Cron names, install steps |
| `docs/agents/install-hermes-skill.md` | Hermes skill install model |
| `src/jobwright/AGENTS.md` | Package module map or conventions |
| `README.md` | Human setup, stage table, install steps |
| `docs/README.md` | New docs under `docs/` |
| `docs/GLOSSARY.md` | New pipeline terms |
| `docs/CHANGELOG.md` | User-visible release notes |
| `templates/hermes-skill/SKILL.md` | Thin loader content (users re-run `install_skills.sh`) |
| `skills/README.md` | Install instructions for Hermes loader |
| `.cursor/rules/agents-doc-sync.mdc` | Doc-sync policy itself |
| `.cursor/rules/agent-orchestration.mdc` | Agent workflow, skill routing, execution discipline |
| `.cursor/skills/pipeline-operator/SKILL.md` | Hermes/pipeline skill entry points change |

## Quality gate

- Command: `pytest tests/ -v` and `ruff check src/`
- Optional: `bash scripts/validate_pipeline.sh`
- Run when: any change under `src/`, `tests/`, or `scripts/`
- Tracked in: AGENTS.md **Last verified** line

## Commit clusters (recommended order)

| Order | Cluster | Paths |
|-------|---------|-------|
| 1 | Agent docs / rules | `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, `.cursor/` |
| 2 | Core package | `src/jobwright/` |
| 3 | Templates / skills readme | `templates/`, `skills/README.md` |
| 4 | Scripts / bin | `scripts/`, `bin/` |
| 5 | Tests | `tests/` |

## Message style

- Plain sentences or short imperative (match `git log`)
- No secrets in messages or staged files

## Path scoping

Repo root is `jobwright/`. Stage with explicit paths when the working tree has unrelated dirty files.

## Deploy (`/deploy` skill)

Public dashboard: `jobwright.parthchandak.info` (API `:8002` serves `frontend/dist`; tunnel via PM2).

| Diff | Deploy action |
|------|----------------|
| `frontend/**` | `./scripts/restart.sh --prod-ui` |
| `src/jobwright/**` (no frontend) | skip if uvicorn `--reload` + health OK; else `--backend-only` |
| tunnel config / ecosystem API | `--tunnel-only` or `--backend-only` as appropriate |
| docs / tests only | skip deploy |

Do **not** restart `jobwright-ui` for production (Vite HMR is local dev only).
