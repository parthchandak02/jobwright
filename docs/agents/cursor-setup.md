# Cursor setup for pp-job-apply

## Skill location

Cursor can read [AGENTS.md](../../AGENTS.md) directly when the repo is open. Optional thin loader:

```bash
./scripts/install_skills.sh
```

Points to your clone via `JOBWRIGHT_REPO` in `~/.cursor/skills/pp-job-apply/`. Deep docs: [docs/agents/](../../docs/agents/).

## Stage 6 provider

Default: `cursor-sdk` with `CURSOR_API_KEY` from Cursor Dashboard → Integrations.

```bash
export AGENT_PROVIDER=cursor-sdk
export APPLY_AGENT_MODEL=composer-2.5
jobwright apply --dry-run --limit 1
```

Fallback CLI:

```bash
export AGENT_PROVIDER=cursor-cli
# Requires `agent` on PATH; per-worker .cursor/mcp.json
```

## RESULT protocol

Agent stdout must include exactly one line:

- `RESULT:DRYRUN` — dry run complete
- `RESULT:APPLIED` — submitted
- `RESULT:FAILED:reason` — permanent or retryable failure

## User data

All PII in `~/.jobwright/profile.json` (chmod 600). Repo contains only `profile.example.json`.
