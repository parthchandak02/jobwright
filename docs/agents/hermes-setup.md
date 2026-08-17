# Hermes setup for pp-job-apply (jobwright)

## Skill location

Hermes loads skills from `~/.hermes/skills/`. Install from the repo:

```bash
cd /Volumes/ExternalSSD/Projects/jobwright   # or ~/projects/jobwright
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh
```

This copies a thin loader (not a symlink to the repo):

- `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/` (+ `JOBWRIGHT_REPO` file)
- `~/.hermes/skills/autonomous-ai-agents/jobwright` (alias)
- `~/.hermes/skills/pp-job-apply`
- `~/.agents/skills/pp-job-apply`
- `~/.cursor/skills/pp-job-apply`

Canonical docs stay in the clone: `AGENTS.md` and `docs/agents/`.

Verify:

```bash
test -f ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/SKILL.md && echo OK
```

## Cron registration

```bash
./scripts/setup_hermes_cron.sh
# Multi-user: set PAUSE_LEGACY=1 if legacy ~/.jobwright crons should stop
```

### Active cron names (current)

| Cron name pattern | Script | Schedule (typical) |
|-------------------|--------|-------------------|
| `job-apply-morning-<id>` | `job_apply_morning.sh` | Per user `schedule` (default every 3h weekdays) |
| `job-apply-digest-<id>` | `job_apply_digest.sh` | Per user `digest_schedule` |
| `job-apply-watchdog-<id>` | `job_apply_watchdog.sh` | Daily check |

Legacy (no registry users): `job-apply-morning`, `job-apply-digest`, `job-apply-watchdog`.

Wrappers export `JOBWRIGHT_USER=<id>` and set `--workdir` to the repo.

### Hermes cron create (manual example)

```bash
hermes cron create "0 7 * * 1-5" \
  --name job-apply-morning-richa \
  --script job_apply_morning.sh \
  --no-agent \
  --deliver "whatsapp:120363...@g.us" \
  --workdir /Volumes/ExternalSSD/Projects/jobwright
```

Scripts must live in `~/.hermes/scripts/` (`install_hermes_scripts.sh` copies them).

## LLM vs no_agent

- **Cron scripts (morning, digest, watchdog, on_confirm):** `--no-agent` — shell only, zero tokens.
- **WhatsApp chat:** Hermes agent loads skill `pp-job-apply` or `jobwright` and uses the `terminal` tool.

## Env for cron

API keys live in one gitignored `.env` at the repo root. Wrappers set `JOBWRIGHT_REPO` and source `.env` automatically.

Manual shell:

```bash
set -a && source "${JOBWRIGHT_REPO}/.env" && set +a
```

## WhatsApp inbound

Cron delivers **outbound** digests. **Inbound** commands (`CONFIRM APPLY`, status, etc.) are handled by the Hermes agent using [whatsapp-routing.md](whatsapp-routing.md).

Human-facing guide: [whatsapp-user-guide.md](whatsapp-user-guide.md).

## After repo updates

```bash
./scripts/install_hermes_scripts.sh
./scripts/install_skills.sh
./scripts/setup_hermes_cron.sh   # if cron definitions changed
```

## Mac mini notes

- Gateway: `launchctl list | grep ai.hermes.gateway`
- Logs: `~/.hermes/logs/gateway.log`
- Cron hard timeout: 300s — morning script detaches long pipeline
- Optional: set `terminal.cwd` in `~/.hermes/config.yaml` to the repo path for interactive sessions

## Deprecated names

Do not register `job-apply-discover` or `job-apply-submit` (paused by setup script). Use `job-apply-morning` / confirm-gated apply instead.
