# Claude connector (use jobwright from your own Claude)

People use jobwright, including applying, from **their own Claude**: claude.ai, Claude Desktop or the mobile
app, with **Claude in Chrome** in their own browser for filling forms. jobwright spends none of its model
tokens on this. Design record: [ADR-009](../adr/ADR-009-users-own-claude-applies.md). Code:
`src/jobwright/connector/` (OAuth, MCP endpoint, tools) and `src/jobwright/apply/connector.py` (gates, claims,
evidence).

## For the person: add the connector

1. In Claude: **Settings → Connectors → Add custom connector**.
2. Name `jobwright`, URL **`https://jobwright.parthchandak.info/mcp`** (shown with a Copy button in the
   dashboard: Settings → **Claude**).
3. Claude opens a jobwright page. Sign in exactly as on the dashboard (Cloudflare Access). The page shows which
   Claude is asking, the profile (a picker when the login opens several) and three permissions: see your jobs
   (always), change your board, apply for you. Press **Allow**.
4. For applying, turn on **Claude in Chrome**. Then ask, for example: "Apply to today's jobwright picks with
   Claude in Chrome. Ask me before anything you are unsure of."

The dashboard walks people through this: Settings → **Claude** (also "Use with Claude" in the sidebar, a
phone tab when the bar has room, and a dismissable board card until a Claude is connected) is a four-step
checklist with live status: connect (done when a Claude is connected), save application answers (done when
none are missing), Claude in Chrome and the daily scheduled task (both ticked by the person, stored in
localStorage), then copy-ready "Things to ask" prompts. `GET /api/connector` carries what it needs:
`missing_answers` (count of required answers still empty), `apply_paused` (paused or kill switch) and
`daily_pick` (`scheduled`, `time`, `days`, `next_at`, `apply_at` = next pick + `veto_minutes`).
`daily_pick.scheduled` is true when `jobwright_apply_pick_<user>.sh` exists in the Hermes scripts dir
(`JOBWRIGHT_HERMES_SCRIPTS_DIR`); the time comes from the enabled Hermes job running that script in
`cron/jobs.json` next to it (`JOBWRIGHT_HERMES_CRON_JOBS` overrides the path). No script: the guide says picks
aren't scheduled yet and to ask the admin.

Disconnect any time: dashboard Settings → Claude → Disconnect (ends every token of that connection at once),
or remove the connector in Claude.

## What Claude can do (tools)

| Tool | Scope | What it does |
|------|-------|--------------|
| `get_overview` | jobs:read | Board counts, best new jobs (36 h, 7+), today's picks, open questions, apply settings and how many applications are left today |
| `list_jobs(stage, min_score, query, limit)` | jobs:read | Jobs, best score first |
| `get_job(job_id)` | jobs:read | Posting text (marked as data), score explanation, application URL, ATS family |
| `list_picks` | jobs:read | Recent picks with status (planned / claimed / applied / failed / vetoed) |
| `get_pending_inputs` | jobs:read | Open questions from earlier attempts |
| `request_tailoring(job_id)` | jobs:read | Base resume, posting, the dashboard's tailoring instructions and the person's cover-letter samples, so **Claude** tailors (no model call here) |
| `rate_job(job_id, thumbs or score, reason)` | jobs:write | Appends a label (`source: connector`), like the dashboard |
| `move_job(job_id, stage, outcome, note, person_confirmed)` | jobs:write | Lane change through the board's own `_apply_move`; Applied only when the person says they applied by hand |
| `set_answers(answers, custom, person_stated_attestations)` | jobs:write | Answer bank; attestations only with the person's explicit word and the flag |
| `veto_pick(pick_id / number / all_picks)` | jobs:write | Same as replying "skip" |
| `save_tailored_materials(job_id, resume_markdown, cover_letter_text)` | jobs:write | Stores `<prefix>.md` / `<prefix>_CL.md`, renders DOCX (and PDF when Chromium is there), returns 15-minute links |
| `get_application_packet(job_id)` | apply | Preview of the packet, no claim |
| `start_application(job_id, person_confirmed)` | apply | Runs every gate, claims the job (2 h), returns the packet |
| `record_submission(job_id, outcome, fields[], claim_id, confirmation_text, confirmation_url, screenshot_png_base64, notes)` | apply | Evidence + verification; closes the claim |

Every call is bound to one profile: the token's grant names it, and the endpoint runs the tool inside
`config.user_context(user_id)`. Tool results that carry text from job postings label it as information, never
instructions; the server instructions say the same and spell out the apply procedure.

### The application packet

`job` (title, company, `application_url`, `ats`, score), `job_posting` (data), `contact` (profile + saved
contact answers; the person's own email), `answers[]` (saved, with `attestation` flags), `custom_answers[]`,
`missing[]` (with `required`, hints, choices), `drafted_open_answers[]` (from earlier attempts at this job),
`materials` (resume / cover letter download links, `resume_tailored`), `gates` (every check, `allowed`,
`refusals`), `submit` (`by`: `claude` | `person` | `nobody`, `why`), `rules[]`, and from `start_application` a
`claim` (`claim_id`, `expires_at`).

### Gates (`apply/connector.py evaluate`)

Refuse the claim: kill switch `JOBWRIGHT_APPLY_KILL`; `apply_via` not `connector`; `apply_paused`; daily cap
(`apply_daily_cap`, counting sent today **plus open claims**); LinkedIn / `apply_blocked` sites; same posting
applied before (`dedupe_key`, `applied_at`); employer cap (30 days); another client's live claim or the
server runner on the job; a pick the person vetoed, or a planned pick still inside its veto window (unless
`person_confirmed`). Do not refuse, but make the person submit: `apply_enabled` off, or score below
`apply_min_score`. Sites that need an account (`manual_ats`) get a note: the person signs in.

### Evidence and verification

`record_submission` writes the existing `submissions` row (`provider: connector`, `model`: client name,
`client_id`, `dry_run: 0`), `fields_json` (label / value / source), the screenshot as `confirmation.png`
(PNG only, at most 3 MB, 0600) and `answers.json` in the run folder. Attestation fields are checked against
the answer bank: answered from anything but `answer_bank` / `person`, or a value that disagrees with the saved
answer, is recorded as a warning (returned and stored in `error`).

Outcome `applied` is verified with `apply/verify.verify_confirmation` on the reported confirmation text / URL:
verified → `applied` (confidence `high` only with a screenshot, else `medium`), job moved to **Applied**
(`stage_history` note "applied by <client>"); not verified → `unverified` (counts toward caps and dedupe, card
stays put). `failed` counts toward the auto-pause; `needs_human` frees the job for another try and puts a
claimed pick back to planned. A claim with no result after 2 hours lapses to `abandoned`.

## Who applies: `apply_via`

Per profile in `users.yaml` (`connector` default | `server` | `off`). Settings → Claude → "Who sends
applications" (people choose My Claude / Nobody; only admins can pick jobwright's server). CLI:
`jobwright users set <id> --apply-via connector|server|off`. With `connector` the server runner refuses live
runs (`safety.check_profile(channel="server")`) and `apply due` leaves the picks for the person's Claude;
`apply pick` still makes the daily picks (the WhatsApp message says "Your Claude may apply to these from
<time> unless you reply skip").

## A scheduled daily apply

Where the person's Claude offers scheduled tasks (for example a Claude Desktop scheduled task with Claude in
Chrome), they can schedule a daily prompt after the pick's veto time, e.g.:

> Every weekday at 10:00: open jobwright, list_picks, and for each planned pick whose apply time has passed,
> start_application and apply with Claude in Chrome following jobwright's instructions. Do not ask me
> anything; if something needs me, record needs_human. Summarise what you did.

The server instructions tell an unattended Claude: only picks whose time has come, never `person_confirmed`,
skip anything needing an answer / code / CAPTCHA / account (`needs_human`), submit only when
`submit.by == "claude"`. The browser must be open and Claude in Chrome running on that computer.

## Operator: endpoints and Cloudflare Access

| Path | Who may reach it | Protection |
|------|------------------|-----------|
| `/.well-known/oauth-protected-resource` (+ `/mcp`) | public | metadata only |
| `/.well-known/oauth-authorization-server` (+ `/mcp`) | public | metadata only |
| `/oauth/register` | public | Claude callbacks or loopback only; 30 / hour / IP |
| `/oauth/token`, `/oauth/revoke` | public | PKCE, single-use codes; 30 failures / 10 min / IP |
| `/mcp`, `/mcp/files/<token>`, `/mcp/icon.png` | public | bearer token (or 15-minute download token); 240 calls / 5 min per connection |
| **`/oauth/authorize`** | **behind Access** | Access JWT → login email → profiles listing it; consent nonce bound to the login; Origin check |

**Change to make (by the owner, not by code):** add a second self-hosted Access application for the public
paths with a single **Bypass** policy (include: Everyone), next to the existing `jobwright` app that keeps
protecting everything else. Example body: [claude-connector-access.example.json](claude-connector-access.example.json).
Do **not** add `/oauth` as a prefix (that would expose `/oauth/authorize`). More specific paths win over the
root app. `cf_access.find_app` matches by `JOBWRIGHT_CF_AUD` first, and the bypass app's domains carry paths,
so the allowlist sync keeps editing only the main app.

The tunnel needs no change (same hostname, same `http://localhost:8002`). If Cloudflare Bot Fight Mode or a
WAF rule challenges non-browser clients, exempt the same paths, or Claude's servers cannot reach them.

Check after the change (from a machine with no Access cookie):

```bash
curl -s https://jobwright.parthchandak.info/.well-known/oauth-authorization-server | jq .issuer
curl -si https://jobwright.parthchandak.info/mcp -X POST | grep -i www-authenticate   # 401 + resource_metadata
curl -si https://jobwright.parthchandak.info/oauth/authorize | head -1                  # 302 to cloudflareaccess.com
```

Deploy: `uv sync --extra web --extra connector` in the live checkout, then restart the API (pm2). Without the
`mcp` package (or with `JOBWRIGHT_CONNECTOR=off`) `/mcp` answers 503 and the dashboard shows the connector as
off.

Env: `JOBWRIGHT_PUBLIC_BASE_URL` (issuer and resource, default `https://jobwright.parthchandak.info`),
`JOBWRIGHT_CONNECTOR` (`off` disables), `JOBWRIGHT_CONNECTOR_DB` (default `<users root>/connector.sqlite`),
`JOBWRIGHT_CONNECTOR_REDIRECTS` (extra exact redirect URIs), `JOBWRIGHT_CONNECTOR_HOSTS` (extra allowed Host
headers for the MCP transport's DNS-rebinding check).

### OAuth design

- Discovery: RFC 9728 protected-resource metadata, RFC 8414 server metadata; `/mcp` 401 carries
  `WWW-Authenticate: Bearer resource_metadata="…", scope="jobs:read jobs:write apply"`.
- Dynamic client registration (RFC 7591), public clients only (`token_endpoint_auth_method: none`), redirect
  URIs limited to `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback` and
  loopback (any port, same path).
- Authorization code + S256 PKCE only; `resource` must be `<base>/mcp` when sent; `iss` on the redirect.
- Consent page behind Access; a one-time consent nonce bound to the login email defeats CSRF; CSP
  `frame-ancestors 'none'`, `form-action` limited to self and the callback origin.
- Tokens: `jwa_` access (1 h), `jwr_` refresh (30 days, rotated on every use; replaying a rotated one revokes
  the grant). Only SHA-256 hashes are stored (`connector.sqlite`, 0600). A new sign-in by the same client
  for the same profile replaces the old grant. Access ends as soon as the login is removed from the profile.
- Revocation: dashboard Disconnect, `POST /oauth/revoke` (RFC 7009), refresh reuse, profile email removal.

## Limitations

- The person's Claude reports what it sent; jobwright cannot watch the browser. The evidence (fields,
  confirmation text, screenshot) is Claude's report, checked for consistency, not proof. Review it on
  `/apply/submissions/<id>`.
- Mobile Claude has no Claude in Chrome: it can read, rate, tailor and answer questions, not fill forms.
- Uploading the resume needs the file on the person's computer: Claude in Chrome opens the download link,
  then uploads from Downloads (or the person attaches it).
- CAPTCHAs, email codes and account creation stay with the person.
- Rate limits are in memory (reset on API restart). The Mac mini must be up for Claude to reach jobwright.
- The consent page relies on Cloudflare Access in production; in dev auth mode it uses `JOBWRIGHT_DEV_EMAIL`.

Tests: `tests/test_connector.py`.
