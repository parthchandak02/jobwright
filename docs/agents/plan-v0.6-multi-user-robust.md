# Plan v0.6: multi-user, high-confidence matching, robust ops

Branch `feat/multi-user-robust`, dev worktree `~/Projects/jobwright-dev`. Prod (`main` on the SSD) is untouched until final verification and deploy. Audit this plan builds on: [state-of-jobwright-2026-09-26.md](state-of-jobwright-2026-09-26.md).

## Owner decisions (2026-09-26)
- Grow from a single-user tool (richa) into one anyone can use: add or switch profiles; onboarding collects profile, resume, cover letters and a WhatsApp chat picked from the list of available chats.
- **Success = relevant jobs found with high confidence.** This is the top priority.
- The Sep 16 human rescores are trusted ground truth. Human rescores are recorded append-only and feed scoring; every future rescore is recorded too.
- Move off the external SSD if it improves reliability. Hermes must keep working. Update the docs.
- Access: each Cloudflare Access email sees only its own profile; admin emails can switch to or create any profile.
- Git: feature branch, commit per phase, deploy once at the end after verification.
- LLM: cheap model plus Jev when it helps; escalate only when needed. It must work, and it must be cost-optimized.
- WhatsApp test sends go only to a chat the owner picks. Never richa's group.

## Known facts
- Cloudflare Access: team `parthchandak.cloudflareaccess.com`, jobwright app AUD `08917e7f0739bbdf1e8c341b04d0beaa654ee4ace12144c6e60106ce771711cc`, policy "Allow Richa and Parth" (2 emails). New users need their email added to that policy by the owner, in the CF dashboard.
- WhatsApp chats: `hermes send --list whatsapp --json` gives ids. Group names come from bridge `GET 127.0.0.1:3000/chat/<jid>` (`subject`), with `~/.hermes/whatsapp/all_groups.json` as a fallback.
- Hermes config references the SSD path in `~/.hermes/config.yaml` (jobwright channel system_prompt + channel note), the `~/.hermes/scripts/_jobwright_repo.sh` / skill `JOBWRIGHT_REPO` file, and the cron wrappers.

## Phases
A. Foundations and safety
   - Hermetic tests.
   - Request-scoped user context (contextvar).
   - Cf-Access JWT to user mapping, plus admin.
   - Apply dry-run by default.
   - Fix SPA traversal; scope downloads.
   - Bind Vite to localhost.
   - JID injection fix.
B. Pipeline correctness
   - Use company, not site; name files by job_id.
   - Soft-filter instead of delete; cross-board dedupe.
   - Honest stage status; incremental score writes; run lock; atomic writes.
   - LLM client hardening.
   - Brief honors human_gate; truthful notify.
   - Persona rules move to per-user config.
C. Precision (top priority)
   - `score_labels` (human, append-only) and `score_history` (machine).
   - Backfill Sep 16 labels.
   - Eval harness.
   - Rubric with hard gates.
   - Retrieved few-shot examples.
   - Jev and cheap-model triage, escalating the shortlist.
   - Cost ledger.
   - `jobwright rescore`.
D. Multi-user product
   - Onboarding wizard: resume, then drafted profile/searches/criteria.
   - Cover letters.
   - WhatsApp chat picker with a test send.
   - Schedule, which creates the Hermes cron.
   - Full profile editor.
   - Admin page.
E. Ops
   - Playwright preflight.
   - Operator alerts and missed-run watchdog.
   - Backups.
   - Deep health check.
   - Prod without `--reload`.
   - SSD to internal disk migration.
   - Docs.
F. UI/UX
   - Mobile-first drawer and actions.
   - Feedback chips and close reasons.
   - Score explanation.
   - TanStack Query; typed API.
   - Split components; a11y.
   - Status banner.
   - Audit bug list.
G. Verify
   - pytest, ruff, tsc and build.
   - Browser e2e at mobile and desktop sizes.
   - Precision before/after report.
   - Sandbox brief end to end.
   - Test WhatsApp send.
   - Migration checks; Hermes cron dry-run.
