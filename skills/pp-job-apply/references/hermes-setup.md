# Hermes setup for pp-job-apply

## Skill location

Hermes loads skills from `~/.hermes/skills/`. Install via:

```bash
./scripts/install_skills.sh
```

Or symlink manually:

```bash
ln -sfn /path/to/jobwright/skills/pp-job-apply \
  ~/.hermes/skills/autonomous-ai-agents/pp-job-apply
```

## Cron registration

```bash
./scripts/setup_hermes_cron.sh
```

Hermes `cron create` syntax:

```bash
hermes cron create "0 7 * * 1-5" \
  --name job-apply-discover \
  --script job_apply_stages_1_5.sh \
  --no-agent \
  --deliver local \
  --workdir /path/to/jobwright
```

Scripts must live in `~/.hermes/scripts/` (setup script copies them).

## LLM vs no_agent

- **Stages 1–5 & 6 scripts**: `no_agent=true` — runs shell, zero tokens.
- **Ad-hoc agent tasks**: Attach skill `pp-job-apply` to a Hermes prompt for status, triage, or manual dry-run orchestration.

## Env for cron

API keys live in a single gitignored `.env` at the repo root. The cron wrappers pin `JOBWRIGHT_REPO` and the pipeline scripts source `${JOBWRIGHT_REPO}/.env` automatically, so cron picks up keys without per-user copies.

To load them manually in a shell:

```bash
set -a && source "${JOBWRIGHT_REPO:-$HOME/projects/jobwright}/.env" && set +a
```

The repo `.env` is gitignored (`*.env`); it is never committed.
