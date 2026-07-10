---
name: pp-job-apply
description: >-
  Runs the applypilot-cursor job pipeline — discover, enrich, score, portfolio
  match, tailor, cover letter, and browser apply via Cursor SDK. Use when the
  user asks to apply for jobs, run job pipeline, job-apply-pp, apply next job,
  dry-run apply, applypilot status, or schedule job applications. Covers
  Hermes cron and Cursor agent workflows. Never commit ~/.applypilot secrets.
version: 1.0.0
author: parthchandak
license: AGPL-3.0
platforms: [macos, linux]
metadata:
  openclaw:
    requires:
      bins: [applypilot, job-apply-pp-cli]
      env: [GEMINI_API_KEY, CURSOR_API_KEY]
    primaryEnv: GEMINI_API_KEY
  hermes:
    tags: [job-search, applypilot, cursor, automation, cron]
    related_skills: [hermes-cron-jobs, cursor-agent]
---

# pp-job-apply

Agent-native guide for **applypilot-cursor** — fork of ApplyPilot with Cursor SDK stage-6 apply, portfolio matching, and Hermes scheduling.

**User data lives only in `~/.applypilot/`** (never in the git repo): `profile.json`, `resume.txt`, `.env`, `applypilot.db`.

## Quick health check

```bash
applypilot doctor
job-apply-pp-cli doctor --agent
```

Tier 3 requires: `GEMINI_API_KEY`, `CURSOR_API_KEY`, Chrome, Node/npx, `cursor-sdk`.

## Pipeline stages

| Stage | Command fragment | Backend |
|-------|------------------|---------|
| 1 discover | `discover` | python-jobspy (Indeed/Google/ZipRecruiter — **not LinkedIn**) |
| 2 enrich | `enrich` | JSON-LD / CSS / LLM |
| 3 score | `score` | Gemini (`LLM_MODEL=gemini-2.5-flash`) |
| 3b portfolio | `portfolio` | Keyword + LLM picks 4–5 projects |
| 4 tailor | `tailor` | Gemini JSON resume (`--validation lenient` if flaky) |
| 5 cover | `cover` | Gemini |
| 6 apply | `applypilot apply` | Cursor SDK + Playwright MCP |

## Standard commands

```bash
export APPLYPILOT_DIR="${APPLYPILOT_DIR:-$HOME/.applypilot}"

# Full pipeline (stages 1–5)
applypilot run discover enrich score portfolio tailor cover -w 4 --min-score 7 --validation lenient

# Dry-run apply (fills forms, does NOT submit)
applypilot apply --dry-run --limit 1 --workers 1

# Agent JSON wrapper
job-apply-pp-cli pipeline run --stages discover,enrich,score,portfolio,tailor,cover
job-apply-pp-cli queue ready --agent --min-score 7
job-apply-pp-cli apply next --dry-run
```

## Environment (`~/.applypilot/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GEMINI_API_KEY` | — | Stages 1–5 |
| `LLM_MODEL` | `gemini-2.5-flash` | Do not use deprecated `gemini-2.0-flash` |
| `CURSOR_API_KEY` | — | Stage 6 SDK |
| `AGENT_PROVIDER` | `cursor-sdk` | `cursor-sdk`, `cursor-cli`, `claude` |
| `APPLY_DRY_RUN` | `true` | Keep true until 10 reviewed dry-runs |
| `APPLY_MIN_SCORE` | `7` | Min fit score for apply |
| `APPLY_LIMIT` | `5` | Max applies per cron run |
| `APPLY_MAX_WORKERS` | `2` | Parallel Chrome workers |

## Safety & ToS rules

1. **Never auto-apply via LinkedIn** — blocked in `sites.yaml`; discovery boards exclude LinkedIn.
2. **Exclude current employer** — `exclude_companies` in `~/.applypilot/searches.yaml`.
3. **Dry-run gate** — agent must emit `RESULT:DRYRUN` when `APPLY_DRY_RUN=true`.
4. **No secrets in git** — only `profile.example.json` and `.env.example` in repo.
5. **Salary floor** — use `profile.json` compensation fields; never below user minimum.
6. **10 dry-runs** before `./scripts/enable_live_apply.sh`.

## Hermes scheduling

Scripts install to `~/.hermes/scripts/` via `scripts/setup_hermes_cron.sh`:

| Job | Schedule | Mode |
|-----|----------|------|
| `job-apply-discover` | `0 7 * * 1-5` | `no_agent` → stages 1–5 |
| `job-apply-submit` | `0 9,17 * * 1-5` | `no_agent` → stage 6 |

Hermes does **not** fill ATS forms — use Cursor SDK for stage 6 only.

See [references/hermes-setup.md](references/hermes-setup.md).

## Cursor agent

Stage 6 uses `cursor-sdk` with inline Playwright MCP per worker CDP port. Fallback: `AGENT_PROVIDER=cursor-cli` (`agent -p --trust --force`).

See [references/cursor-setup.md](references/cursor-setup.md).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Gemini 404 on score/tailor | Set `LLM_MODEL=gemini-2.5-flash` in `.env` |
| Tailor `exhausted_retries` | Run `--validation lenient`; ensure `responseMimeType` JSON in llm |
| Apply missing PDF | Tailored `*_JOB.txt` needs matching `*_JOB.pdf` in `tailored_resumes/` |
| `pip not found` | Use `python3 -m pip` on macOS |
| No jobs to apply | Run discover on non-LinkedIn boards; check `fit_score` and `tailored_resume_path` |

## Install

```bash
cd /path/to/applypilot-cursor
python3 -m pip install -e .
python3 -m pip install --no-deps python-jobspy && python3 -m pip install pydantic tls-client requests markdownify regex
playwright install chromium
./scripts/install_skills.sh   # Cursor + Hermes skill symlinks
```
