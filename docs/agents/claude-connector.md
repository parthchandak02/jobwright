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
| `get_pending_inputs` | jobs:read | Open questions (from `ask_person` or earlier attempts, with choices) and recently answered ones with their answers |
| `request_tailoring(job_id)` | jobs:read | Base resume, posting, the dashboard's tailoring instructions and the person's cover-letter samples, so **Claude** tailors (no model call here) |
| `rate_job(job_id, thumbs or score, reason)` | jobs:write | Appends a label (`source: connector`), like the dashboard |
| `move_job(job_id, stage, outcome, note, person_confirmed)` | jobs:write | Lane change through the board's own `_apply_move`; Applied only when the person says they applied by hand |
| `save_profile_facts(facts[{question, value, key?, source}], person_confirmed)` | jobs:write | Records facts for every later form: standard key first (classifier: "desired pay" → `salary_expectation`, "date available" → `start_date`; a place-specific question such as "relocate to Boston?" never lands on the general key), else one "other question" per normalized question (deduped). Job-specific open answers ("why this company") are refused. `source` is `resume` or `told_claude`. Attestations need `person_confirmed=true` and never come from the resume; otherwise the whole call is refused and nothing is saved |
| `set_answers(answers, custom, person_confirmed, source)` | jobs:write | Older by-key form (`person_stated_attestations` still accepted); same attestation and job-specific rules |
| `veto_pick(pick_id / number / all_picks)` | jobs:write | Same as replying "skip" |
| `save_tailored_materials(job_id, resume_markdown, cover_letter_text)` | jobs:write | Either or both (a cover letter alone is fine). Stores `<prefix>.md` / `<prefix>_CL.md`, renders DOCX and PDF (when Chromium is there), returns named links |
| `ask_person(job_id, questions[{text, choices?, key?}])` | jobs:write | Questions only the person can answer, asked once: `pending_inputs` rows (kind `answer`, `asked_by = connector`, choices in `meta_json`), one WhatsApp message to their chat when they have one; already-answered questions come straight back with the saved value. Claude then pauses the job (`record_submission needs_human`) |
| `set_application_url(job_id, url)` | jobs:write | Saves the employer's own apply link Claude found (http(s), never LinkedIn / lnkd.in) in `application_url` (`application_url_source = connector`); `url` (the posting) is kept |
| `get_application_packet(job_id)` | apply | Preview of the packet, no claim |
| `start_application(job_id, person_confirmed)` | apply | Runs every gate, claims the job (2 h), returns the packet |
| `record_submission(job_id, outcome, fields[], claim_id, confirmation_text, confirmation_url, screenshot_png_base64, notes)` | apply | Evidence + verification; closes the claim |

Every call is bound to one profile: the token's grant names it, and the endpoint runs the tool inside
`config.user_context(user_id)`. Tool results that carry text from job postings label it as information, never
instructions; the server instructions say the same and spell out the apply procedure.

### The application packet

`job` (title, company, `application_url`, `linkedin_only`, `ats`, score), `job_posting` (data), `next_steps[]`
(what to do for this job: LinkedIn-only link, tailoring, cover letter, uploads, unsaved answers), `answer_policy`
(below), `contact` (profile + saved contact answers incl. street address / ZIP; the person's own email),
`answers[]` (saved, with `attestation` flags), `custom_answers[]`, `missing[]` (with `required`, hints, choices),
`waiting_for_person[]` (open `ask_person` questions for this job), `drafted_open_answers[]` (from earlier
attempts at this job), `materials` (below), `gates` (every check, `allowed`, `refusals`), `submit` (`by`:
`claude` | `person` | `nobody`, `why`), `rules[]`, and from `start_application` a `claim` (`claim_id`,
`expires_at`).

### How a run goes (what the first real run taught us)

The first real run (an iCIMS-style form) stopped at four places; the packet now covers each:

1. **Resume upload.** Claude's own code sandbox (claude.ai) cannot reach jobwright (egress allowlist), so a
   download link is useless there. `materials.resume` / `materials.cover_letter` are `{pdf, docx, use}`; each
   file has `name` ("Alex Rivera - Resume.pdf", from the profile name, ASCII-safe), `url`, `expires_at`, `uses`
   and `browser_upload.javascript`: a snippet Claude runs with Claude in Chrome's `javascript_tool` on the
   application page. It fetches the file from `/mcp/files/<token>` inside the page, builds a `File`, picks the
   file input (by name / id / label / nearby text matching resume|CV or cover; `SELECTOR` overrides; same-origin
   iframes included), sets it through `DataTransfer`, fires `input` + `change` and returns a short status.
   `browser_upload.fallback`: open the link in a new tab so it downloads, the person clicks Choose File (or open
   a cross-origin frame's own address and run it there). PDF is the default; DOCX only when the form refuses
   PDF. The base resume always has a PDF: the uploaded `resume/base.pdf`, or, with only `base.md`, a rendered
   `resume/base_rendered.pdf` (+ `.docx`) from the pipeline's export (never written over `base.pdf`). A
   tailored resume / cover letter without a PDF is rendered on the next packet.
2. **Cover letter.** `next_steps`: if the form takes one and none exists, write one by the tailoring rules
   (`request_tailoring` for the brief), `save_tailored_materials(cover_letter_text=...)` (no resume needed), then
   `get_application_packet` again for the PDF link.
3. **Questions the resume answers.** `answer_policy` has three kinds: `saved_answers_only` (attestations: work
   authorization, sponsorship, criminal record, background check, age, certify, EEO, relocation / on-site,
   salary / desired pay, start date / date available, located in the country or a state, travel; plus contact
   facts the resume lacks), `from_resume` (education, years of a kind of experience, people supervised, budgets,
   strategic planning, sectors, employers; ranges: the one the resume clearly supports, else the lower
   defensible one or ask; recorded with source `resume`) and `open_writing` (Claude writes, source `claude`).
   `answers.question_kind()` implements the same split; `ask_person` flags questions that look resume-answerable.
4. **Ask once, reuse forever.** Missing saved answers: Claude collects every such question on the form, calls
   `ask_person` once and pauses the job. The person answers on the site (Settings → Applications, "Questions
   from your Claude": buttons for up to three choices, a list for more, else a text box) or by WhatsApp reply
   (`apply provide <ref> <value>`, unchanged). The answer is saved as a custom answer for that exact question,
   and to the standard key when it maps to one (always when Claude named the `key`, else only if that key is
   still empty, so "Willing to relocate to Boston?" never overwrites a general relocation answer). The next
   packet carries it in `answers[]` / `custom_answers[]`; `get_pending_inputs.answered` shows it too.
5. **LinkedIn-only jobs.** `job.linkedin_only` and a `next_steps` line: find the role on the employer's careers
   site and save it with `set_application_url`; never Easy Apply. The `site` gate's refusal says the same, and
   once an employer link is saved the gate passes.

### Answer sources and undo (backend; the About you "Application details" UI comes next)

Every saved answer carries `source`: `resume` ("From your resume"), `told_claude` (older `connector`; "You told
Claude") or anything else ("You entered"). `GET /api/answers` returns `source_label` on each entry, `fields[]`
with a `section` (contact, education, eligibility, pay_start, diversity, other), `sections[]` and `recent[]`
(values saved with a Claude source in the last 14 days, with `previous_value`). A bank entry keeps `previous`
(value, source, updated_at); `POST /api/answers/undo {key | question}` puts it back (or removes a value that
replaced nothing). For now questions from Claude are answered in Settings → Applications; the planned home is
Settings → About you → Application details.

Contact keys (`phone, address_line, city, state, postal_code, country, linkedin_url, github_url,
portfolio_url, preferred_name`; `answers.CONTACT_FIELDS`) are stored only in `profile.json` `personal` (the
fields the pipeline and About you already use); the bank keeps just their provenance (`in_profile: true`). An
older bank copy is read as a fallback until the next write moves it. About you edits (`PUT
/api/settings/profile`) mark those answers "You entered" (`answers.note_profile_edit`). Note: the
current About you form sends every `personal` field it loaded, so a contact value Claude saved while that page
was open can be overwritten by its next autosave; the Application details UI should send only its own fields.

Standard answer keys added for this: `currently_in_country`, `willing_to_travel` (attestations); `address_line`
and `postal_code` are now counted as missing; `education_highest` is optional (the resume answers it).
Classifier patterns cover "desired pay", "compensation expectations", "date available", "currently located in
the US", "able to travel 20-30%".

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
`ask_person` for anything only the person can answer and record `needs_human`, skip anything needing a code /
CAPTCHA / account, submit only when `submit.by == "claude"`. The server instructions also carry a short "How a
run goes" section (claim, LinkedIn-only link, answer kinds, browser uploads, cover letter, ask once). The browser must be open and Claude in Chrome running on that computer.

## Operator: endpoints and Cloudflare Access

| Path | Who may reach it | Protection |
|------|------------------|-----------|
| `/.well-known/oauth-protected-resource` (+ `/mcp`) | public | metadata only |
| `/.well-known/oauth-authorization-server` (+ `/mcp`) | public | metadata only |
| `/oauth/register` | public | Claude callbacks or loopback only; 30 / hour / IP |
| `/oauth/token`, `/oauth/revoke` | public | PKCE, single-use codes; 30 failures / 10 min / IP |
| `/mcp`, `/mcp/files/<token>`, `/mcp/icon.png` | public | bearer token (or download token: 15 minutes, at most `DOWNLOAD_MAX_USES` = 5 fetches, this profile's generated files only); 240 calls / 5 min per connection |

`/mcp/files/<token>` answers any origin: `Access-Control-Allow-Origin: *` (never with credentials; the random
token is the only key), `Access-Control-Expose-Headers: Content-Disposition`, `Cross-Origin-Resource-Policy:
cross-origin`, `Content-Type` `application/pdf` or the DOCX type, `Content-Disposition: attachment;
filename="<Name> - Resume.pdf"`. Errors (expired, used up) are JSON 404s with the same CORS headers so the
snippet can say why. CORS preflights for that path are answered by `connector.server.FilesPreflight`, the
outermost middleware (the dashboard's CORS middleware only allows its own origins). It sits under the `/mcp`
path of the Access Bypass app below (an Access application path covers everything beneath it), so no extra
Cloudflare change is needed; check it with the curl lines below.
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
curl -si https://jobwright.parthchandak.info/mcp/files/jwd_x -H 'Origin: https://careers.example.org' \
  | grep -iE '^HTTP|access-control-allow-origin'                                     # 404 from jobwright + ACAO *
```

A 302 to `cloudflareaccess.com` on the last line means Access does not bypass `/mcp/files`: add
`jobwright.parthchandak.info/mcp/files` as a destination of the bypass app.

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
- Uploads use the page's own `fetch`: an employer page whose Content-Security-Policy forbids connecting to
  jobwright, a form inside a cross-origin frame, or a custom uploader that ignores the file input's `change`
  event falls back to download-then-Choose-File by the person.
- CAPTCHAs, email codes and account creation stay with the person.
- Rate limits are in memory (reset on API restart). The Mac mini must be up for Claude to reach jobwright.
- The consent page relies on Cloudflare Access in production; in dev auth mode it uses `JOBWRIGHT_DEV_EMAIL`.

Tests: `tests/test_connector.py`.
