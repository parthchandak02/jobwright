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

7. **Reliability follow-up (2026-11-03).** An ops review found briefs that
   crashed or were locked still reported "ok", broken job boards were
   invisible, a failed notify was never retried, and backups could fail
   silently. Now:
   - The brief report trusts the status file (`pipeline_rc=N` fails,
     `pipeline_locked` warns with the lock holder, `timeout` fails) and only
     uses `logs/last_run.json` when it was written by this run (started after
     `brief_started at=`, not a dashboard run); otherwise "no fresh run
     summary". It warns on 0 scored jobs and on per-source discovery problems.
   - Discovery records `{new, errors, rate_limited, status}` per source
     (JobSpy boards, the LinkedIn guest client's given-up requests, Workday,
     each impact board, smart extract); the report prints one `sources:` line.
   - Alerts fall back to channels that do not need Hermes
     (`JOBWRIGHT_OPS_FALLBACK`: macOS Notification Center, on by default on
     macOS because it is local and needs no secret; an ntfy topic, off unless
     set). The hourly watchdog re-runs a failed notify once hermes and the
     bridge are healthy (at most 3 a day) and reports a brief that is still
     running or timed out instead of "no brief started".
   - Notify never double-sends: rows are claimed atomically under a
     per-profile lock. A `hermes send` timeout is treated as "maybe delivered":
     the claim is kept, nothing is resent automatically, and the operator
     releases it with `ops release-uncertain` if nothing arrived. We prefer a
     missed notice (the jobs are still on the dashboard) to a duplicate.
   - `run_daily_brief.sh` has a hard deadline (`JOBWRIGHT_BRIEF_TIMEOUT`, 3h)
     that kills the step's process group; enrich has a 45-minute soft budget.
   - Backups integrity-check every DB copy, skip stale `*.bak` / `*-wal` /
     `smoke*.db` files, keep every old snapshot after a night with errors,
     alert on any crash (an unmounted SSD is an error, never a new folder on
     the internal disk), and `jobwright ops restore` copies a snapshot to a
     separate folder (a live profile only with `--force`, moved aside first).

## Consequences

- An SSD outage no longer takes the product down; it only pauses backups (which
  then alert).
- Per-run `logs/last_run.json` and the run registry's real exit codes make
  failures visible in the dashboard, not only in logs.
