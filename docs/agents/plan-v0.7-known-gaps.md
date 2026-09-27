# Plan v0.7: known gaps after the v0.6.0 deploy

- **Date:** 2026-09-27
- **Owner:** Parth (admin)
- **Baseline:** v0.6.0 on `main`, prod at `/Users/parthchandak/apps/jobwright`

## Users (done 2026-09-27)

| Profile | Login email | Access |
|---|---|---|
| (admin) | user2@example.com | every profile, can switch and create |
| richa | user3@example.com | own profile only |
| muskaan | user1@example.com | own profile only |
| suchi | user4@example.com | own profile only |

## Todo

| # | Gap | Work | Status |
|---|---|---|---|
| G1 | New emails must be allowed in Cloudflare Access by hand | `jobwright access sync`: set the Access app's allow policy to exactly the emails in `users.yaml` (+ admins); Admin page shows drift and a Sync button; runs after profile/email changes. Needs `CLOUDFLARE_API_TOKEN` (Access: Apps and Policies Edit) | done: live policy `jobwright users` in sync (4 emails); token from `~/.hermes/.env` copied to repo `.env` |
| G2 | Duplicate postings already in backlogs (e.g. Google.org x3) | `jobwright dedupe [--dry-run]`: group open jobs by `dedupe_key`, keep the best row (most advanced stage, then labeled, then highest score, then newest), close the rest as `duplicate` with tombstones; never touch labeled/applied rows' history | merged to `dev`; dry-run on richa copy: 19 groups, 28 cards to close |
| G3 | Hermes chat instructions are Richa-only and name a stale model | `jobwright hermes channels [--apply]`: multi-user operator prompt (resolve sender to profile), remove model line, per-user group overrides generated from `users.yaml`; back up `config.yaml` first | in progress |
| G4 | Recall is ~35% at 7+ | Eval options: borderline band escalation (5-6 to a stronger model), threshold sweep; Quality page shows a recommended threshold per user | merged to `dev`: prompt v2.4; richa 6+ gives P 0.90-0.95 / R 0.45-0.475 (v2.3 7+: P 1.0 / R 0.35); band second opinion built but off (no gain) |
| G5 | Old SSD copy and dev worktree on SSD | Move dev worktree to `/Users/parthchandak/apps/jobwright-dev`; delete `jobwright.pre-migration-20260926` after owner OK | done 2026-09-27: old copy deleted, dev worktree at `/Users/parthchandak/apps/jobwright-dev` (branch `dev`); `~/projects` symlink to SSD kept (space for ~40 projects) |
| G6 | UI copy drift ("Location: NA" on cards vs "Location not stated" in drawer) | Consistent empty-state labels | merged to `dev` |
| G7 | No weekly summary | Sunday WhatsApp summary per user: new jobs, applied, in progress, responses, top 3 still open | merged to `dev` |
| G8 | No follow-up reminders | Applied jobs with no stage change after N days (default 10) appear in the brief and on the board | merged to `dev` |
| G9 | Cost per user not visible to admin | Admin page: 30-day tokens and estimated cost per profile from `llm_usage` | merged to `dev` |
| G10 | First brief on the new setup unverified | Check 2026-09-27 06:00 run: `last_run.json`, `ops_health.json`, WhatsApp delivery | pending (after 06:00) |

## Rules for this phase

- Feature work in worktrees, merged to `dev` (`/Users/parthchandak/apps/jobwright-dev`), then to `main` after tests, ruff, and `pnpm run build` pass.
- Sandboxes set `JOBWRIGHT_HERMES_DRY_RUN=1` and use copies of user data in `/tmp`.
- WhatsApp test sends only to Parth's DM (`whatsapp:555000000000006@lid`).
- Prod deploy: `git pull` in the prod checkout, `pnpm run build`, `pm2 restart jobwright-api`.
