# ADR-007: Operator alerts, backups, and running from the internal disk

- **Status:** Accepted
- **Date:** 2026-09-26
- **Version:** 0.6.0

## Context

The daily brief failed silently for days at a time (Playwright browser mismatch
Sep 22-26, provider credit outages, a missed run on Sep 25, WhatsApp bridge down
Sep 26); silence looked like "no jobs today". Repo and all user data lived on an
external SSD that disconnects, with no backups. Production uvicorn ran with
`--reload` from the working tree agents edit.

## Decision

1. **Truthful, loud briefs.** `run_daily_brief.sh` runs `jobwright preflight --fix`
   (installs the Playwright Chromium the package needs), lets the pipeline choose
   stages from `human_gate`, records `notify_sent N` / `notify_skipped <reason>`
   / `notify_failed <error>`, and always ends with `jobwright ops brief-report`,
   which alerts the operator's WhatsApp (`ops_target`) on any problem and writes
   `logs/ops_health.json` for the dashboard banner.
2. **Watchdog.** `jobwright-ops-watchdog` (Hermes, hourly at :30) alerts when a
   user's brief never started (30 min after its time) or never finished (120 min),
   once per problem per day (`logs/watchdog_alerts.json`). It was daily at 08:30
   until 2026-09-30, which silently skipped every brief scheduled after 06:30.
3. **Backups.** `jobwright-backup` (Hermes, 02:30) runs `jobwright ops backup`:
   SQLite online-backup copies plus rsync `--link-dest` snapshots of every
   profile, 14-day retention, to `JOBWRIGHT_BACKUP_DIR` (the external SSD).
4. **Internal disk.** The production checkout and `users/` move to the internal
   disk; the SSD holds backups. Production pm2 runs without `--reload`.
5. **Crons deliver locally.** Brief crons are no-agent and deliver to `local`;
   the brief sends its own WhatsApp list, so a bridge outage cannot turn a good
   run into a failed delivery, and launcher output never reaches the user's chat.
6. **Sandboxes are safe.** `JOBWRIGHT_HERMES_DRY_RUN=1` (default in
   `restart.sh` dev mode) turns cron changes and WhatsApp sends into log lines.

## Consequences

- An SSD outage no longer takes the product down; it only pauses backups (which
  then alert).
- Per-run `logs/last_run.json` and the run registry's real exit codes make
  failures visible in the dashboard, not only in logs.
