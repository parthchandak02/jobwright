# Cursor setup for pp-job-apply

## Skill location

Cursor loads personal skills from `~/.cursor/skills/`. Install via:

```bash
./scripts/install_skills.sh
```

## Stage 6 provider

Default: `cursor-sdk` with `CURSOR_API_KEY` from Cursor Dashboard → Integrations.

```bash
export AGENT_PROVIDER=cursor-sdk
export APPLY_AGENT_MODEL=composer-2.5
applypilot apply --dry-run --limit 1
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

All PII in `~/.applypilot/profile.json` (chmod 600). Repo contains only `profile.example.json`.
