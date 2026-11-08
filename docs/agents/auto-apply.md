# Automatic applications (safe apply core)

How jobwright applies for a consenting person: 1-2 applications a day, only to jobs scoring 8+, under the
person's own email, with every answer traceable. Design record: [ADR-008](../adr/ADR-008-safe-automatic-apply.md).

> **Default since ADR-009:** profiles apply through the person's **own Claude** (`apply_via: connector`,
> [claude-connector.md](claude-connector.md)), with the same gates, answer bank and evidence as below. The
> server-side runner described here only runs live for profiles set to `apply_via: server`
> (`jobwright users set <id> --apply-via server`, admins only on the dashboard).

## Rules the code enforces

| Rule | Where |
|------|-------|
| Attestations (work authorization, sponsorship, criminal record / background check, EEO, age, "I certify", salary, start date, relocation / on-site, worked here before) come **only** from the person's saved answers. Missing → the job is skipped and the question is posted to their group. | `apply/answers.py` (classifier), `apply/tools.py` (refuses), `apply/runner.py` (re-checks filler output) |
| Open questions may be written from the resume, truthfully, nothing invented. | `apply/prompt.py`, `AnthropicApplyAgent.answer_open_question` |
| No CAPTCHA solving, no email access, no LinkedIn Easy Apply. | `hitl.py`, `safety.check_job` (apply-URL host check) |
| Passwords are generated per employer, stored 0600 under the user dir, typed by `fill_secret`, never shown to the model; every tool result is scrubbed. | `apply/secret_store.py`, `tools.fill_secret`, `evidence.Transcript` |
| Own browser profile per person (`<user dir>/apply-browser/profile`), never the operator's Chrome. Domain allowlist on every request. | `apply/browser.py` |
| Dry run: no final submit, no account, no sign-in, and every non-GET request is aborted at the network. Screenshots and the answer record are still produced. | `browser._route`, `tools.click` / `fill_secret` |
| Applied only when the confirmation page is verified (URL / text / success element; `high` or `medium`). Otherwise `unverified`, reported, not moved to Applied. | `apply/verify.py`, filler `verify()` |
| Kill switch `JOBWRIGHT_APPLY_KILL`, `apply_enabled`, `apply_daily_cap` (2), `apply_min_score` (8), dedupe by `dedupe_key`, `apply_employer_cap` (1 per 30 days), auto-pause after 2 failed/unverified live attempts in a row. | `apply/safety.py` |

## The person's answers

Stored in `profile.json` → `application_answers` (`{version, answers: {key: {value, source, updated_at}}, custom:
{normalized question: {question, value, source, updated_at}}}`). Keys match the deterministic fillers
(`apply/ats/forms.py`): `work_authorized, requires_sponsorship, criminal_record, background_check, age_18_plus,
certify, salary_expectation, start_date, relocation, onsite, previously_worked_here, eeo_gender, eeo_race,
eeo_hispanic, eeo_veteran, eeo_disability, eeo_lgbtq (optional)`, plus common facts (`phone, city, state,
country, education_highest, how_heard, ...`). `custom` is sent to the fillers as `questions`.

- Dashboard: Settings → **Applications** (`GET/PUT /api/answers`).
- CLI: `jobwright --user <id> answers show|set <key> <value>|missing|import-profile`.

## Daily flow (veto window, default for the first two weeks)

`users.yaml`: `apply_enabled: true`, `apply_mode: veto` (default) or `auto`, `apply_veto_minutes: 180`,
`apply_daily_cap: 2`, `apply_min_score: 8`, `apply_employer_cap: 1`.

1. `jobwright --user <id> apply pick` (or `apply auto`): picks up to the cap from Backlog/Prepare (not touched by
   the person, not LinkedIn, never a vetoed or already-picked job, one per employer), stores them in
   `apply_picks`, and posts "I'll apply to these at 9:30 AM unless you reply skip <n> / skip all".
2. The person replies "skip 2" / "skip all" in their group; the group's Hermes agent runs
   `jobwright --user <id> apply veto --number 2 --by whatsapp` / `apply veto all --by whatsapp`. Also the
   "Don't apply" button in the job drawer and on the evidence page (`POST /api/apply/picks/{id}/veto`). A veto
   after the apply time is refused ("Too late").
3. `jobwright --user <id> apply due`: applies every planned pick whose time has passed (tailors resume + cover
   letter first when missing), then posts "Applied today" with an evidence link per job and the confirmation
   screenshot (`hermes send "... MEDIA:<path>"`; `JOBWRIGHT_HERMES_MEDIA=off` sends links only).

`apply_mode: auto` applies right after picking (`apply auto` = pick + due).

Rehearse without sending anything: `jobwright --user <id> apply auto --dry-run`.

### Enabling a schedule (not installed by code yet)

Nothing schedules these. When the owner decides to, add two Hermes crons with `--no-agent --deliver local`
for the profile, e.g. `jobwright --user <id> apply pick` 30 minutes after the brief and
`jobwright --user <id> apply due` every 30 minutes from then until evening. Run both with
`JOBWRIGHT_HERMES_DRY_RUN=1` and `apply auto --dry-run` first.

## Human in the loop (`pending_inputs`)

| Kind | What happens | Resolved by |
|------|--------------|-------------|
| `captcha` | Run pauses (browser stays open up to `JOBWRIGHT_APPLY_WAIT_MINUTES`, default 20), refreshes a live screenshot, posts "Finish this one: <dashboard>/apply/pending/<id>" to the group and to `ops_target`. | Someone solves it in the browser window on the Mac mini (in person or screen sharing), then taps **I solved it** (`POST /api/apply/pending/{id}/provide`) or `apply provide <id>`. |
| `email_code` | Run pauses and posts "please paste the code from <company> (ref <id>)". | The person pastes the code; Hermes runs `jobwright --user <id> apply provide <id> <code>`. The code goes through a 0600 hand-off file the run deletes; the table keeps only a hash. |
| `answer` | Job skipped right away; question posted. | The reply → `apply provide <id> "<answer>"` saves it for that exact question and makes the job eligible again. |

**Limitation:** the live view is a picture, not a remote browser. A remote person cannot click inside it; only
someone at the Mac mini (or screen sharing) can solve a CAPTCHA. Live runs open a visible window by default
(`JOBWRIGHT_APPLY_HEADLESS=1` hides it). Unsolved within the wait → `captcha_timeout`, job retried another day.

## Evidence

`submissions` row per attempt (fields with label / value / source, screenshots `filled` / `review` /
`confirmation`, transcript path, steps, tokens, cost, outcome, verification confidence + evidence) and
`<user dir>/apply-runs/<run_id>/` (0700). Dashboard: `/apply/submissions/<id>`; CLI:
`apply submissions [--json]`. Model usage goes to `llm_usage` with purpose `apply`.

## Commands, endpoints, env

```bash
jobwright --user <id> apply [--live] [--url URL] [--limit N] [--min-score 8]   # one-off (dry run default)
jobwright --user <id> apply auto [--dry-run] [--no-post]
jobwright --user <id> apply pick | veto <pick_id|all> [--number] | due
jobwright --user <id> apply provide <ref> [value] | pending [--all] | submissions | resume
jobwright --user <id> answers show | set <key> <value> | missing | import-profile
jobwright users set <id> --apply-daily-cap 2 --apply-min-score 8 --apply-employer-cap 1
```

API: `GET/PUT /api/answers`, `PUT /api/answers/custom`, `GET /api/apply/status`, `GET /api/apply/pending`,
`GET /api/apply/pending/{id}`, `POST /api/apply/pending/{id}/provide`, `GET /api/apply/pending/{id}/screenshot`,
`GET /api/apply/submissions`, `GET /api/apply/submissions/{id}`,
`GET /api/apply/submissions/{id}/screenshots/{name}`, `GET /api/apply/picks[?job=]`,
`POST /api/apply/picks/{id}/veto`.

Env: `ANTHROPIC_API_KEY`, `AGENT_PROVIDER` (`anthropic` default), `JOBWRIGHT_APPLY_MODEL`
(`claude-sonnet-5-5`), `JOBWRIGHT_APPLY_EFFORT` (`medium`), `JOBWRIGHT_APPLY_FALLBACKS`,
`JOBWRIGHT_APPLY_MAX_STEPS` (60), `JOBWRIGHT_APPLY_TIMEOUT_S` (900), `JOBWRIGHT_APPLY_WAIT_MINUTES` (20),
`JOBWRIGHT_APPLY_HEADLESS`, `JOBWRIGHT_APPLY_EXTRA_HOSTS`, `JOBWRIGHT_APPLY_FILLERS`, `JOBWRIGHT_APPLY_KILL`,
`JOBWRIGHT_HERMES_MEDIA`. Install the SDK with `uv sync --extra web --extra dev --extra apply`.

## Before the first live application

1. `uv sync --extra apply`, set `ANTHROPIC_API_KEY`.
2. The person fills Settings → Applications (`answers missing` prints nothing).
3. `jobwright hermes channels --apply` so the group knows "skip" and codes; restart the gateway.
4. Several `apply auto --dry-run` rehearsals; read each `/apply/submissions/<id>` with the person.
5. Owner: `jobwright users set <id> --apply`; then `apply pick` / `apply due` by hand for the first days.
