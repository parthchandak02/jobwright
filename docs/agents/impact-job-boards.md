# Impact / social-sector job boards

Curated boards for social-impact profiles. Implemented in
`src/jobwright/discovery/impactboards.py` as **deterministic scrapers** — no LLM
calls, one request per board (two need Playwright) — so they run on **every**
daily brief.

## Why not `sites.yaml`

`config/sites.yaml` is only read by `discovery/smartextract.py`, and smart-extract
runs only when `DISCOVER_MODE=full` (one LLM planning call + a Playwright render
per target). The daily brief runs `DISCOVER_MODE=fast`, so anything added to
`sites.yaml` never reaches the daily digest. Adding boards there would look
configured while producing nothing.

## Wiring

`pipeline._run_discover` calls `run_impact_boards()` in both fast and full mode,
after JobSpy/Workday and before smart-extract. Jobs are stored through
`smartextract._store_jobs_filtered`, so the user's location accept/reject lists
and `exclude_titles` / `min_salary` filters apply exactly as for other sources.
Rows carry `strategy='impact_board'` and `site=<board name>`.

Env knobs:

| Var | Default | Effect |
|-----|---------|--------|
| `IMPACT_BOARDS` | `1` | `0` disables the whole module |
| `IMPACT_BOARDS_BROWSER` | `1` | `0` skips the Playwright boards |
| `IMPACT_BOARDS_MAX_AGE_DAYS` | `14` | age window for boards/sheets that expose a posting date |
| `IMPACT_BOARDS_MAX_PER_BOARD` | `150` | per-board cap on jobs kept per run |

Health check: `JOBWRIGHT_USER=<user> .venv/bin/python scripts/check_impact_boards.py`
(exits non-zero if any board errors; a healthy second run reports `new=0`).

## Board inventory

Working, server-rendered (HTTP, no browser):

| Board | Source | Notes |
|-------|--------|-------|
| The Impact Job | RSS `theimpactjob.com/rss/jobs` | ~100 items, title/company/location/description |
| GIIN | `jobs.thegiin.org` | `/job/<id>/<slug>/`, paginated |
| Rippleworks | `careers.rippleworks.org/jobs` | company slug parsed from URL |
| Next Billion | `nextbillion.net/jobs/` | `/jobs/<slug>/` |
| FinDev Gateway | `findevgateway.org/jobs` | `/jobs-internships/<slug>` |
| WAVE | `members.women-wave.org/jobs/` | `/jobs/Details/<slug>` |
| On Purpose | `onpurposecareers.org/jobboard` | cards link out to employer ATS |
| SIS Global tracker | Google Sheet `1yM5C…SxI` | gviz CSV export; sheet itself is stale (no rows inside the age window) |
| CSR Jobs tracker | Google Sheet `15UJRV…RIkE` | gviz CSV export; most links are LinkedIn URLs already found by JobSpy, so few are new |

Working, needs a browser (JS-rendered or 403 to plain HTTP):

| Board | Notes |
|-------|-------|
| Skoll Foundation | `skoll.org/job/<slug>`, listings load via "Load more" |
| Net Impact | `careers.netimpact.org/job/<slug>`, 403 to httpx, fine in Chromium |

Not yet wired (feasible, needs per-site API work):

| Board | Path forward |
|-------|--------------|
| Probably Good | GraphQL backend `backend.jobs.probablygood.org` + Algolia key endpoint |
| 80,000 Hours | Algolia index (`w6km1udib3-dsn.algolia.net`) |
| Chingona Ventures | Airtable embed `appTK9dwNEKEErM2X/shrAQSkUuX8oROunz` — use the share API |
| Raise for Good | Google Doc embedded via Embedly on the page |

Not feasible:

| Board | Reason |
|-------|--------|
| Campground | login wall (`community.campground.fyi/auth/login`) |
| Google Groups (social-enterprise-jobs) | mailing list, no public listing surface |
| Impact Opportunity | security-blocked (Cloudflare-style block, no stealth browser) |
| ImpactAlpha | blog archive, not a job board |
| Second Day / All Raise | no job listings on the site |

## Pitfalls

- **Never `DELETE FROM jobs` to purge test rows.** The `trg_jobs_tombstone_on_delete`
  trigger writes every deleted URL into `job_tombstones`, and
  `trg_jobs_block_tombstoned` then blocks re-inserting it forever — a purge
  silently poisons those URLs (they come back as `existing`, never as `new`).
  To undo, delete the tombstone rows (`where site in (<boards>) and removed_at >= <ts>`)
  before re-running. Use a scratch DB for experiments instead.
- Google Sheets must be link-shared; the gviz `tq?tqx=out:csv` endpoint returns
  CSV without auth. `format=csv` (export endpoint) does not.
- Tracker sheets hold a full year of postings — the age window is what keeps
  them from flooding scoring.
