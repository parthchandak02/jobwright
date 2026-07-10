---
name: pp-job-apply
description: >-
  Runs the applypilot-cursor job pipeline — discover, enrich, score, portfolio
  match, tailor, cover letter, and browser apply via Cursor SDK. Uses a
  confirmation-gated workflow: morning cron preps jobs and delivers a digest;
  live apply only after user replies CONFIRM APPLY. Use when the user asks to
  apply for jobs, run job pipeline, job-apply-pp, apply next job, dry-run
  apply, applypilot status, or schedule job applications. Covers Hermes cron
  and Cursor agent workflows. Never commit ~/.applypilot secrets.
version: 1.1.0
author: parthchandak
license: AGPL-3.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [job-search, applypilot, cursor, automation, cron, confirmation-gate]
    related_skills: [hermes-cron-jobs, cursor-agent]
---

# pp-job-apply

Agent-native guide for **applypilot-cursor** — fork of ApplyPilot with Cursor SDK stage-6 apply, portfolio matching, and confirmation-gated Hermes scheduling.

**User data lives only in `~/.applypilot/`** (never in the git repo): `profile.json`, `resume.txt`, `.env`, `applypilot.db`.

Repo: `/Users/parthchandak/projects/applypilot-cursor`

## Quick health check

```bash
cd ~/projects/applypilot-cursor
applypilot doctor
```

Tier 3 requires: `GEMINI_API_KEY`, `CURSOR_API_KEY`, Chrome, Node/npx, `cursor-sdk`.

## Pipeline stages

| Stage | Command | Backend |
|-------|---------|---------|
| 1 discover | `applypilot run discover` | python-jobspy (Indeed, Google, ZipRecruiter — not LinkedIn) |
| 2 enrich | `applypilot run enrich` | JSON-LD / CSS / LLM |
| 3 score | `applypilot run score` | Gemini (`LLM_MODEL=gemini-2.5-flash`) |
| 3b portfolio | `applypilot run portfolio` | Keyword + LLM picks 4-5 projects |
| 4 tailor | `applypilot run tailor` | Gemini JSON resume (`--validation lenient` if flaky) |
| 5 cover | `applypilot run cover` | Gemini |
| 6 apply | `applypilot apply --live` | Cursor SDK + Playwright MCP |

## Confirmation gate workflow (current design)

The pipeline uses a SAFETY-FIRST pattern: mornings prepare, user confirms, live apply runs.

**5:00 AM Mon-Fri — Morning prep (no apply)**
1. `job_apply_morning.sh` runs via Hermes cron (no_agent mode)
2. Clears `~/.applypilot/APPLY_CONFIRMED` (revokes yesterday's confirmation)
3. Runs: `applypilot run discover enrich score portfolio tailor cover -w 4 --min-score 5 --validation lenient`
4. Delivers digest to WhatsApp: jobs scored, tailored, and ready for confirmation

**User replies CONFIRM APPLY on WhatsApp**
1. `job_apply_confirm.sh` writes timestamp to `~/.applypilot/APPLY_CONFIRMED`
2. `job_apply_on_confirm.sh` checks the file exists, then runs:
   - `export APPLY_DRY_RUN=false`
   - `applypilot apply --live --limit 5 --workers 1`
3. Result summary delivered to WhatsApp

**One confirmation per day.** Morning script clears the file; confirmation is single-use.

## Standard commands

```bash
cd ~/projects/applypilot-cursor
export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"

# Full pipeline (stages 1-5, discovery through cover)
applypilot run discover enrich score portfolio tailor cover -w 4 --min-score 5 --validation lenient

# Resume tailoring only (on existing jobs)
applypilot run tailor cover -w 4 --min-score 5 --validation lenient

# Status check
applypilot status

# Live apply (only after user says CONFIRM APPLY)
applypilot apply --live --limit 5 --workers 1
```

## Environment (`~/.applypilot/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GEMINI_API_KEY` | — | Stages 1-5 |
| `LLM_MODEL` | `gemini-2.5-flash` | Do not use deprecated `gemini-2.0-flash` |
| `CURSOR_API_KEY` | — | Stage 6 SDK |
| `AGENT_PROVIDER` | `cursor-sdk` | `cursor-sdk`, `cursor-cli`, `claude` |
| `APPLY_DRY_RUN` | `true` | Default safe; `--live` overrides on confirmation |
| `APPLY_MIN_SCORE` | `5` | Min fit score for live apply (lower threshold since non-LinkedIn boards have fewer listings) |
| `APPLY_LIMIT` | `5` | Max applies per confirmation cycle |
| `APPLY_MAX_WORKERS` | `1` | 1 worker for live apply to avoid Chrome collisions |
| `APPLY_WORKERS` | `4` | Workers for discovery/enrichment (stages 1-5) |
| `APPLY_PREP_LIMIT` | `10` (2× APPLY_LIMIT) | Max jobs per morning for portfolio/tailor/cover |

## Verified working (2026-07-10)

Morning prep and apply were tested end-to-end on this machine:

```bash
# Health
applypilot doctor

# Morning prep (Hermes cron or manual) — discovers on indeed/google/zip_recruiter only
~/.hermes/scripts/job_apply_morning.sh

# Dry-run one application (safe, no submit)
applypilot apply --dry-run --limit 1 --min-score 5

# After WhatsApp CONFIRM APPLY
~/.hermes/scripts/job_apply_confirm.sh
~/.hermes/scripts/job_apply_on_confirm.sh
```

**Fixes in applypilot-agent fork:**
- Tailoring uses Gemini native JSON mode (`json_mode=True`, `max_tokens=8192`) — prevents truncated JSON
- Discovery reads `boards:` from `~/.applypilot/searches.yaml` (not hardcoded LinkedIn)
- Portfolio/tailor/cover skip LinkedIn and cap batch size via `APPLY_PREP_LIMIT`
- Validator allows skills listed in `profile.json` `skills_boundary` (e.g. C++)

**Hermes on CONFIRM APPLY:** run `job_apply_confirm.sh` then `job_apply_on_confirm.sh` (or equivalent agent steps). Do not call `apply --live` without confirmation file.

1. **Never auto-apply from cron** — morning prep delivers digest only. Live apply only after user replies `CONFIRM APPLY`. No exceptions.
2. **Never apply via LinkedIn** — blocked in `sites.yaml`; all ready-to-apply queries filter `site NOT LIKE '%linkedin%'`.
3. **Exclude current employer** — `exclude_companies` in `~/.applypilot/searches.yaml` (e.g. Zoox).
4. **Dry-run is default** — `APPLY_DRY_RUN=true` in `.env`. Only `--live` flag overrides on explicit user confirmation.
5. **Confirmation gate** — morning script clears `~/.applypilot/APPLY_CONFIRMED`. Live apply script checks this file exists before proceeding. One-shot per day.
6. **No secrets in git** — `~/.applypilot/` contents never committed or pushed.
7. **Workers=1 for live apply** — live apply runs with 1 worker to avoid form-fill collisions. Discovery/enrichment can use 4.

## Hermes scheduling (current)

Single morning cron, no-agent mode. Scripts at `~/.hermes/scripts/`:

| Job | Script | Schedule | Mode | Workdir |
|-----|--------|----------|------|---------|
| `job-apply-morning` | `job_apply_morning.sh` | `0 5 * * 1-5` | no_agent | `/Users/parthchandak/projects/applypilot-cursor` |

No separate submit cron — live apply is user-triggered only.

**Scripts installed from repo:**
- `job_apply_morning.sh` — discover through cover, clears confirmation, delivers digest
- `job_apply_confirm.sh` — writes APPLY_CONFIRMED timestamp (run by agent on CONFIRM APPLY)
- `job_apply_on_confirm.sh` — checks confirmation file, runs live apply (run by agent after confirm)

Old auto-apply crons (`job-apply-discover`, `job-apply-submit`) are **paused, not deleted** — resume only if switching back to auto-apply mode.

## Install

```bash
cd ~/projects/applypilot-cursor
python3 -m pip install -e .
python3 -m pip install --no-deps python-jobspy && python3 -m pip install pydantic tls-client requests markdownify regex
playwright install chromium
./scripts/install_skills.sh   # Cursor + Hermes skill symlinks
```
