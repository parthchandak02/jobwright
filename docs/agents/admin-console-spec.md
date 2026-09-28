# Admin console v2: spec (2026-09-27)

> **Status (2026-09-28):** the page layout below is superseded by design v2 (WP4): system list instead of chips, people table with column headers on desktop, `PersonSheet` bottom sheet on phones, `StatusDot`, `ConfirmDialog`, Remove in a "⋯" menu. See [design-v2-audit.md](design-v2-audit.md) section 3.3 and the Admin table in [.cursor/skills/frontend-tasteful/references/catalog.md](../../.cursor/skills/frontend-tasteful/references/catalog.md). The API contract below is current.

Owner decisions: compact expandable rows (one per person); key settings editable inline; resume, match rules and search terms stay on the person's Profile page (reached with "Open board" / "Open profile").

## Page layout (`/admin`, admins only)

1. **Header:** "Admin" + refresh. Below it a one-line **system strip**: WhatsApp bridge (connected / down), Cloudflare Access (in sync / N pending / not configured, "Sync" button when out of sync), Hermes group instructions (up to date / N need update, "Apply" button + "restart Hermes to apply" hint), operator alerts target name. Each item is a small status chip; problems are amber/red and have the fix action inline.
2. **People** section with "+ Add person" (opens a small dialog: name, login email, optional WhatsApp group picker).
   - **Row (collapsed), one line on desktop:** status dot (green = healthy, amber = warning, red = problem, hollow = setup pending) · name · WhatsApp group name (or "No chat") · daily time · cutoff "6+" · "top 10" · "N new this week" · 30-day AI cost · chevron. On mobile the row wraps to two lines (name + status on line 1, group + time + counts on line 2).
   - **Row (expanded), inline settings, saved on change with a small "Saved" toast; no Save button:**
     - Login emails (chip input)
     - WhatsApp chat (existing `WhatsAppChatPicker`, admin sees all chats) + "Send test" (sends to that chat, confirm dialog because it is a real person's chat)
     - Daily list: time picker, cutoff select 5-9 (show "recommended N+" hint when known), list size (5/10/15/20/all), "Review first" switch (human_gate)
     - Weekly summary switch, "Follow up after N days" number
     - Last brief line: "Today 6:02 AM · 8 sent" or the health problem text
     - Actions: "Open board" (switch profile, go to `/`), "Open profile" (switch, go to `/profile`), "Run search now" (confirm: sends their list to their chat), "Remove" (existing dialog)
     - Setup pending users show a callout instead of the daily-list block: "Waiting for <name> to finish setup at /welcome" + "Do setup for them" (switch profile, go to `/welcome`)
3. **Admins and alerts** (collapsed by default): admin emails, operator alert chat, "Schedule daily health check", "Send test alert".
4. **AI usage** (compact table, collapsed by default; the per-row cost already shows the headline).

Remove the separate big cards for Cloudflare Access and Hermes channels (they become system-strip chips with a details popover).

## API contract

### `GET /api/admin/overview`
```json
{
  "bridge": "connected",
  "access": {"configured": true, "in_sync": true, "add": [], "remove": [], "error": null},
  "hermes": {"changed": false, "pending": 0, "error": null},
  "settings": {"admins": ["..."], "ops_target": "whatsapp:...", "ops_target_name": "Parth"},
  "users": [{
    "user_id": "richa", "name": "Example Person 2", "emails": ["..."],
    "setup_complete": true,
    "health": {"level": "ok|warn|fail|null", "lines": ["..."]},
    "last_brief": {"at": "ISO", "notified": 8, "status": "ok|failed|skipped|null"},
    "whatsapp": {"target": "whatsapp:...@g.us", "name": "Richa - Job Applications", "type": "group|dm|null"},
    "schedule": "0 6 * * *", "schedule_label": "Every day at 6:00 AM", "hour": 6, "minute": 0,
    "notify_threshold": 6, "recommended_threshold": 6,
    "brief_top_n": 10, "human_gate": true, "weekly_summary": true, "followup_days": 10,
    "counts": {"new_7d": 42, "sent_7d": 30, "applied_total": 12, "open": 280, "followups_due": 2},
    "cost_30d": {"tokens": 1088111, "cost_usd": null},
    "hermes_status": "unchanged|add|update|skipped",
    "brief_cron": true
  }]
}
```
Rules: one DB open per user, read-only; a broken profile yields a row with `health.level = "fail"` and an error line instead of failing the whole response. `setup_complete` = resume + profile present (same check as `onboarding_status`). Chat names come from `whatsapp.list_chats(show_all=True)`, then `whatsapp.chat_name` (bridge lookup, 10-minute cache of resolved group names, cached lists), then the id's local part.

### `PATCH /api/admin/users/{user_id}`
Accepts any of: `name`, `emails`, `whatsapp_target`, `hour`+`minute` (or `schedule`), `notify_threshold` (1-10, stored as `profile.match_criteria.notify_threshold`, keeps derived rules derived), `brief_top_n`, `human_gate`, `weekly_summary`, `followup_days`. Side effects: schedule or chat change on a set-up user → `ensure_brief_cron`, and on success the one-time welcome (`welcome.send_welcome_async`: hello in their chat + heads-up to `ops_target`, once per profile, skipped in dry run); emails change → Access auto-sync (existing). Returns `{"user": <overview row>, "access_sync": ..., "cron": ..., "ok": true, "user_id": ..., "emails": [...]}` (`cron` is `null` when no sync ran).

### `POST /api/admin/users/{user_id}/test-message`
Sends the standard hello to that user's `whatsapp_target` (403 unless admin; 404 unknown profile; 400 when no chat; 502 when the send fails). Returns `{"sent": true, "target": "..."}`. Never use it on a real person's chat just to test.

### `POST /api/admin/users/{user_id}/run`
Starts that user's daily brief (same as their Auto Search default stages, runs in that user's context, tagged in the run registry). Returns the run handle used by `RunProgressDialog`.

### Implementation notes (backend, as built)

- `access` also carries `configured: null` when the Cloudflare call errored or timed out; `in_sync` is `null` when not configured.
- `hermes.pending` = users with status `add` or `update`; `hermes.error` is set when `~/.hermes/config.yaml` is missing or unreadable (rows then have `hermes_status: null`).
- Each user row adds `"error": string|null` (the failure line when the profile could not be read). `brief_cron` is `null` when `hermes cron list` failed. `whatsapp.name` falls back to `whatsapp.chat_name` (cached group names), then the chat id's local part, when the chat list is slow or missing.
- System sources (bridge, Access, Hermes plan, chat list, cron list) run in parallel, capped at 6 s total (`OVERVIEW_TIMEOUT`); a slow source degrades to its fallback, never an error.
- `last_brief` reads the newest `BRIEF_STATUS_<date>` file: `at` = file mtime, `status` from its `notify_sent N` / `notify_skipped` / `notify_failed` (or `preflight_failed`) line.
- `setup_complete` = the `resume` and `profile` steps of `onboarding_status` (same as `onboarding.is_set_up`; not its full `complete`, which also needs searches; a chat is no longer required).
- PATCH validation (400): `hour`/`minute` must come together and not with `schedule`; `notify_threshold` 1-10; `brief_top_n` 0-100 (0 = all); `followup_days` 1-90; `name` non-empty; `notify_threshold` needs an existing, valid `profile.json`. `whatsapp_target: ""` clears the chat. The response also keeps the legacy `ok`, `user_id`, `emails` keys so the v1 Admin page keeps working.
- `/run` returns the same handle as `POST /api/run` (`run_id`, `pid`, `user`, `stages`, `log_path`, `kind`). The run is registered in that person's `web_runs.json`; `GET /api/stream/{run_id}` resolves runs for the caller's active profile, so the UI must switch to that profile (`POST /api/session`) before opening `RunProgressDialog`, or show the handle only.

## Quality bar

- Compact: 44px collapsed rows on desktop, no card-in-card nesting, consistent 12/14px type scale from the existing design tokens, icons from lucide.
- Keyboard: rows are buttons (Enter/Space toggle), focus rings visible, dialogs trap focus.
- Empty/loading/error states for every block; optimistic updates with rollback on error.
- Mobile 390px: no horizontal scroll.
- Tests: backend route tests (admin-only, partial failure, patch side effects, threshold storage); frontend `pnpm run build` (tsc) clean.
