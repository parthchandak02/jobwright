---
name: pp-job-apply
description: >-
  Runs the jobwright job pipeline  -  discover, enrich, score, portfolio
  match, tailor, cover letter, and optional browser apply via Cursor SDK.
  Supports multiple local profiles (Hermes-routed digests per user). Uses a
  confirmation-gated workflow: prep delivers a digest; live apply only after
  CONFIRM APPLY and only if that user has apply_enabled. Never commit
  ~/.applypilot or ~/.applypilot-users secrets.
version: 1.3.0
author: parthchandak
license: AGPL-3.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [job-search, applypilot, cursor, automation, cron, confirmation-gate, captcha, multi-profile]
    related_skills: [hermes-cron-jobs, cursor-agent]
---

# pp-job-apply

Agent-native guide for **jobwright**  -  multi-profile job finder with optional apply.

**Legacy single-user data:** `~/.applypilot/`
**Multi-profile registry:** `~/.applypilot-users/users.yaml`
**Per-user data:** `~/.applypilot-users/<user_id>/` (`profile.json`, `resume.txt`, `searches.yaml`, `.env`, `applypilot.db`)

Repo: `~/projects/jobwright`

## Multi-profile (Hermes onboarding)

When someone new wants job help over Hermes/WhatsApp:

1. Collect: name, WhatsApp deliver target (`whatsapp:<id>`), resume text (or path), role preferences (titles, locations, salary floor), whether they want auto-apply (default: **no** / find-only).
2. Register:
   ```bash
   cd ~/projects/jobwright
   applypilot users add <id> --name "Full Name" --whatsapp "whatsapp:...." --template nontech-bay-area
   # Default .env is a stub (no silent API-key copy). For family/shared keys:
   #   applypilot users add <id> ... --copy-env ~/.applypilot/.env
   # apply stays OFF unless they explicitly ask:
   # applypilot users set <id> --apply
   ```
3. Write their files into `~/.applypilot-users/<id>/`:
   - `resume.txt` (required for score/tailor/cover)
   - `profile.json` (from `profile.example.json`; set `experience.target_role`, `compensation.salary_expectation`)
   - `searches.yaml` (seeded by `--template`, or customize)
   - Optional: `connections.csv` (LinkedIn export) for `applypilot network`
4. Always put `--user` **before** the subcommand:
   ```bash
   applypilot --user <id> doctor
   applypilot --user <id> run discover enrich score ...
   ```
5. Re-register crons so digests route to their WhatsApp:
   ```bash
   ./scripts/setup_hermes_cron.sh
   # Legacy Parth crons stay active unless PAUSE_LEGACY=1
   ```
6. Manual run / status:
   ```bash
   applypilot --user <id> doctor
   applypilot --user <id> run discover enrich score portfolio tailor cover -w 4 --min-score 5 --validation lenient
   applypilot --user <id> status
   ```

**Freshness:** near-real-time is cron (`0 */3 * * 1-5`) + `hours_old: 24` in searches. Boards are Indeed/Google/ZipRecruiter/Workday/direct sites; LinkedIn jobs stay blocked. Salary floor keeps unknown salaries for the scorer.

**Apply for new users:** keep `apply_enabled: false` until a Workday/Greenhouse dry-run shows `RESULT:DRYRUN` on a live form. Do not enable apply after an Indeed 404/`EXPIRED`.

### Useful user commands

```bash
applypilot users list
applypilot users show richa
applypilot users set richa --whatsapp "whatsapp:..." --no-apply
applypilot --user richa network
applypilot --user richa targets
```

## Quick health check

```bash
cd ~/projects/jobwright
applypilot doctor
# or: applypilot --user richa doctor
```

Tier 3 (apply only) requires: `GEMINI_API_KEY`, `CURSOR_API_KEY`, Chrome, Node/npx, `cursor-sdk`.

## Pipeline stages

| Stage | Command | Backend |
|-------|---------|---------|
| 1 discover | `applypilot [--user ID] run discover` | python-jobspy (Indeed, Google, ZipRecruiter  -  not LinkedIn) |
| 2 enrich | `run enrich` | JSON-LD / CSS / LLM |
| 3 score | `run score` | Gemini (`LLM_MODEL=gemini-2.5-flash`) |
| 3b portfolio | `run portfolio` | Keyword + LLM picks 4-5 projects |
| 4 tailor | `run tailor` | Gemini JSON resume (`--validation lenient` if flaky) |
| 5 cover | `run cover` | Gemini |
| 6 apply | `apply --live` | Cursor SDK + Playwright MCP (**optional**, per-user `apply_enabled`) |

Extra commands: `network` (LinkedIn CSV), `targets` (company list).

## Confirmation gate workflow

SAFETY-FIRST: prep finds + tailors; live apply only if that profile opted in.

**Prep cron (per user, often every few hours)**
1. `job_apply_morning.sh` with `APPLYPILOT_USER=<id>` via Hermes cron (`no_agent`)
2. Clears stale `APPLY_CONFIRMED` in that user's data dir
3. Runs: `applypilot --user <id> run discover enrich score portfolio tailor cover ...`
4. Digest delivered to that user's `whatsapp_target`

**User replies CONFIRM APPLY** (only if `apply_enabled`)
1. `APPLYPILOT_USER=<id> job_apply_confirm.sh`
2. `APPLYPILOT_USER=<id> job_apply_on_confirm.sh`  -  refuses if apply disabled
3. Report results

Find-only digests omit the CONFIRM APPLY line.

## Safety rules

1. Never auto-apply from cron
2. Never apply via LinkedIn (blocked in sites.yaml)
3. Dry-run is default; only `--live` on explicit CONFIRM APPLY
4. Multi-profile: apply also requires registry `apply_enabled: true` (default false)
5. Confirmation gate: APPLY_CONFIRMED cleared each prep run, one-shot per day
6. No secrets in git (`~/.applypilot/` and `~/.applypilot-users/` never committed)
7. Workers=1 for live apply
8. LinkedIn networking uses **exported Connections.csv only** (no scraping)

## Hermes scheduling

```bash
./scripts/setup_hermes_cron.sh
```

Creates per-user crons `job-apply-morning-<id>`, `job-apply-digest-<id>`, `job-apply-watchdog-<id>` with wrappers that export `APPLYPILOT_USER`. Each delivers to that user's `whatsapp_target`.

**Pitfall:** no_agent cron scripts have a 300s hard timeout. Morning pipeline launches detached; digest cron delivers later.

## Install

```bash
cd ~/projects/jobwright
pip install -e .
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex
playwright install chromium
./scripts/install_skills.sh
./scripts/setup_hermes_cron.sh
```
