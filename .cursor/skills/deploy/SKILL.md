---
name: deploy
description: Lands changes end-to-end: doc sync, quality gate, commit clusters, push when asked, and conditional dashboard deploy. Use when the user asks to commit, push, deploy, ship, or /deploy.
---

# Deploy

End-to-end workflow for jobwright: probe, sync stale docs, run a **scoped** quality gate, commit in logical clusters, push when asked, then deploy only what changed.

**Fast by default:** skip deploy steps that the diff does not require. Never restart `jobwright-ui` for production.

## Trigger cues

| User says | Commit | Push | Deploy |
|-----------|--------|------|--------|
| commit / land this | yes | no | no |
| commit and push | yes | yes | no |
| deploy / ship it / /deploy | yes | yes (unless commit-only) | yes |
| push only | no | yes | no |

If push or deploy intent is ambiguous, ask once.

## Workflow

```
Phase 0  Probe          git status, branch, diff (scope + deploy targets)
Phase 1  Doc sync       [.cursor/commit-overlay.md](../../commit-overlay.md)
Phase 2  Quality gate   scoped to changed paths (see overlay)
Phase 3  Commit         cluster staging, one concern per commit
Phase 4  Push           only when the user asked
Phase 5  Deploy         only when deploy is in scope; path-conditional
Phase 6  Next steps      optional follow-ups only
```

## Phase 0: Probe

From repo root:

```bash
git status --short
git branch -vv
git diff --stat
git diff --stat HEAD   # include unstaged
```

Classify the diff into deploy buckets (see Phase 5). Confirm not detached HEAD; remote exists if pushing.

## Phase 1: Doc sync

Follow [.cursor/commit-overlay.md](../../commit-overlay.md). Update `AGENTS.md` **Last verified** when the quality gate ran.

## Phase 2: Quality gate (scoped)

Read overlay. Run the **minimum** gate for what changed. Prefer the repo's tracked commands (same as AGENTS.md **Last verified**):

```bash
uv run --extra dev --extra web pytest tests/ -q
```

| Changed paths | Gate |
|---------------|------|
| `src/`, `tests/`, `scripts/` | pytest (above) + **scoped ruff** on changed Python under `src/` (see below) |
| `frontend/` only | `cd frontend && pnpm build` (catches TS/build errors; also used by deploy) |
| docs / `.cursor/` only | skip tests; skim for accuracy |
| both backend + frontend | pytest + scoped ruff + `pnpm build` (deploy may build again; acceptable) |

### Ruff (scoped, not whole tree)

Full `ruff check src/` hits many pre-existing warnings (e.g. `BLE001` in `pipeline.py`). Gate only **files you changed**:

```bash
# From repo root; empty if no src/ changes
git diff --name-only HEAD -- 'src/**/*.py' ':(exclude)src/**/__pycache__/**'
# Then, for each path (or pass all at once):
uv run ruff check src/jobwright/discovery/cleanup.py ...
```

Fix new violations in touched files before commit. Do not "fix" unrelated hubs in the same deploy unless the user asked.

Optional when pipeline scripts changed: `bash scripts/validate_pipeline.sh`.

Fix failures before commit unless the user explicitly approves committing with failures.

### Pre-commit: git-secrets

Commits run a `git-secrets` hook. New `env.setdefault(...)` lines for pipeline env vars often false-positive.

- **Never** use `--no-verify` unless the user explicitly asks.
- Add an allowlist regex to [`.gitallowed`](../../../.gitallowed) (mirror existing `JOBWRIGHT_*` env var lines).
- Re-stage `.gitallowed` in the same backend commit when needed.
- Preview: `git secrets --scan --cached`

## Phase 3: Clustered commits

### Safety rules (hard)

- Only commit when the user asked.
- Never run `git config`.
- Never use `--force`, `--force-with-lease`, `--no-verify`, or history rewrites unless the user explicitly asks.
- Never amend unless user requested amend, or a successful commit was auto-modified by a hook in this session and not pushed.
- Never stage secrets (`.env`, `cloudflared-config-jobwright.yml`, credentials, `users/`).
- HEREDOC commit messages:

```bash
git commit -m "$(cat <<'EOF'
<subject>

<body if needed>
EOF
)"
```

### Grouping

Prefer one commit per concern (2-8 max). Order: docs/rules → backend → frontend → scripts/tests.

Stage explicitly (`git add -- <paths>`), not `git add -A` when unrelated dirty files exist.

## Phase 4: Push

Only when requested:

```bash
git push -u origin "$(git branch --show-current)"
```

On failure, report the error; do not force-push without explicit approval.

## Phase 5: Deploy (conditional)

Deploy applies to the **Kanban dashboard** at `jobwright.parthchandak.info`. Read [docs/agents/dashboard-hosting.md](../../../docs/agents/dashboard-hosting.md) if unsure.

### Prod vs dev (do not get this wrong)

| PM2 process | Role | Production? |
|-------------|------|-------------|
| `jobwright-api` | FastAPI `:8002`; serves `frontend/dist` after build | **yes** |
| `jobwright-tunnel` | cloudflared → public hostname | **yes** |
| `jobwright-ui` | Vite dev `:5120` with HMR | **no** (local dev only) |

- **Hot reload does NOT update the public site.** Vite HMR only affects `http://127.0.0.1:5120`.
- **Public URL** serves static files from `frontend/dist` via the API. After frontend changes, run a prod build.
- **Backend** with uvicorn `--reload` (ecosystem default) picks up Python edits without a manual restart; still restart if reload is disabled or the process is wedged.

### Deploy matrix (run only matching rows)

From repo root. Use `./scripts/restart.sh` or `./scripts/dashboard_deploy.sh` (alias for `--prod-ui`).

| Diff touches | Command | Notes |
|--------------|---------|-------|
| `frontend/**` (with or without backend) | `./scripts/restart.sh --prod-ui` | `build_frontend()` + restart API + `health_check()`; **default when UI changed** |
| `src/jobwright/**` only (no `frontend/**`) | `./scripts/restart.sh --backend-only` **or skip** if API has `--reload` and health passes | Prefer skip when `curl -sf http://127.0.0.1:8002/api/health` succeeds |
| `cloudflared-config-jobwright.yml`, tunnel ingress | `./scripts/restart.sh --tunnel-only` | Config is gitignored; only if user changed local file |
| `ecosystem.config.js` API args/env | `./scripts/restart.sh --backend-only` | |
| docs / tests only | **skip deploy** | |
| user says "deploy everything" | `./scripts/restart.sh --prod-ui` + `./scripts/restart.sh --tunnel-only` | rare; confirm tunnel needed |

**Mixed frontend + backend:** always `--prod-ui` (prod serves `frontend/dist` through the API; backend-only restart does not rebuild UI).

**Script map (graphify):** `graphify query "restart.sh"` or `graphify explain "build_frontend"` when unsure which flag runs build vs PM2 restart. `./scripts/dashboard_deploy.sh` is a thin alias for `--prod-ui`.

**Never** run `--frontend-only` or restart `jobwright-ui` expecting production to update.

### Post-deploy verify (quick)

```bash
curl -sf http://127.0.0.1:8002/api/health
curl -sI https://jobwright.parthchandak.info/ | head -5   # expect 302 to Cloudflare Access
pm2 list | grep jobwright
```

Skip public URL check if DNS or tunnel is known down; report local health only.

### PM2 persistence

After first successful deploy on a host: `pm2 save` (once per machine, not every commit).

## Graphify (optional, after backend commits)

The pre-commit hook may launch a background `graphify update .`. You do not need to wait on it for deploy.

- After backend changes, if an agent will explore architecture next: `graphify update .` (AST-only, no API cost).
- Never commit `graphify-out/`.
- Query symbols (`run_pipeline`, `build_frontend`), not English slogans. See [.cursor/rules/graphify.mdc](../../rules/graphify.mdc).

Skip graphify during deploy when you already know the script path (e.g. `./scripts/restart.sh --prod-ui`).

## Phase 6: Next steps

Optional blockers or follow-ups in the response only. Do not implement unless asked.

## Output contract

Report:

1. **Doc sync** — files updated, or none needed
2. **Gate** — commands run and result (note if scoped/skipped)
3. **Commits** — subject per commit
4. **Push** — remote/branch, or skipped
5. **Deploy** — commands run, or skipped with reason (e.g. docs-only diff)
6. **Verify** — health / Access redirect, or failure detail
7. **Dirty state** — remaining `git status --short` lines

## Project overlay

Job-specific doc matrix, gates, and clusters: [.cursor/commit-overlay.md](../../commit-overlay.md).
