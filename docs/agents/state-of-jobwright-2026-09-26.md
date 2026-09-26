# State of jobwright — 2026-09-26 audit

End-to-end review (engineering, UI/UX, ops, product). Read-only audit; nothing was changed except adding this file. Items marked ✅ were re-verified directly in code.

## 1. What it is

Daily career advisor for one real user (richa: Example MBA, Bay Area, non-tech impact/CSR/foundation/CoS roles). Operator: Parth.

Loop: `discover → enrich → score → (portfolio) → connect` at 06:00 via Hermes cron → `notify` (one WhatsApp list with `/jobs/<id>` deep links) → review in Kanban dashboard → on-demand Auto Tailor (human_gate) → apply manually → track `backlog → prepare → applied → in_progress → offer → closed`.

Topology (single Mac, repo+data on `/Volumes/ExternalSSD`): pm2 runs `jobwright-api` (uvicorn :8002 serving `frontend/dist`) and `jobwright-tunnel` (cloudflared → `jobwright.parthchandak.info`, Cloudflare Access OTP). Hermes cron → `~/.hermes/scripts/jobwright_brief.sh` (copy) → `scripts/run_daily_brief.sh` → `hermes send` via WhatsApp adapter :3000. LLM: Fireworks `glm-5p3-flash`, Gemini 3.7-flash failover, TypeSafe Jev in shadow.

Stack: Python 3 / Typer CLI / SQLite (WAL) / JobSpy + Workday + Playwright; FastAPI (8 routers); React 19 + Vite 7 + Tailwind 4 + shadcn + dnd-kit, no data-fetching lib.

## 2. Usage reality (richa, Aug 18 – Sep 26)

| Metric | Value |
|---|---|
| URLs ingested | 18,551 (~475/day, now ~1,000/day) — 64% LinkedIn, 29% Indeed |
| Retained after prune | 601 (3.2%) |
| Notified | 294 (~12% dupes by title+company) |
| Applied / in_progress | 25 (8.5% of notified), avg 12 days notify→applied |
| Responses logged | 0 |
| Closed | 282, 281 as "cancelled" (reason lost) |
| DOCX produced | 32 of 263 tailored |
| Scoring precision | Of LLM ≥7 jobs the human rescored, **63% rated ≤3, only 19% ≥6**. Rejection (<5) is reliable. |
| Supply since Sep 20 | ~0–2 fresh ≥7 jobs/day |
| Brief health | 15/36 runs had pipeline_rc=1; Sep 25 never ran; Sep 26 WhatsApp delivery failed — nothing alerted |

**Core diagnosis:** precision and trust, not features. Scorer measures skills overlap; the user's real criteria are categorical (mission, function, no fundraising, no license). Human rescores (154) are stored but never fed back.

## 3. Critical issues (fix first)

| # | Issue | Where |
|---|---|---|
| 1 ✅ | `jobwright apply` with no flag submits **live** and skips `apply_enabled` check (check only runs under `--live`) | `cli.py:500,518-532` |
| 2 ✅ | SPA fallback path traversal: `GET /%2e%2e/...` serves files outside `dist` (incl. `users/richa/.env`) | `web/app.py:68-75` |
| 3 ✅ | `/api/download?path=` allows `APP_DIR` root → `.env`, DB, profile.json (password); `startswith` prefix check | `web/routers/materials.py:53-70` |
| 4 | Multi-user not request-safe: middleware mutates module-global config per request in threadpool; per-user `.env` leaks into `os.environ`; any Access user can switch profiles via cookie; runs not user-scoped | `web/session.py:40-53`, `config.py:46-85,478`, `runs.py:44` |
| 5 | Enrich broken since Sep 22 (playwright 1.62 wants headless_shell-1234, not installed in `.venv`) | `brief_20260926.log` |
| 6 | No operator alerting; `BRIEF_STATUS` says `notify_sent` on "Nothing to send"; no missed-run detection | `run_daily_brief.sh:97` |
| 7 | No backup of `users/`; SSD still disconnects | — |
| 8 ✅ | Prod pm2 runs `uvicorn --reload` from the live working tree | `ecosystem.config.js:38,43` |
| 9 | Vite dev binds 0.0.0.0 and proxies `/api` → LAN bypasses Access | `vite.config.ts:15`, `restart.sh:141` |
| 10 | Shell injection: WhatsApp JID interpolated into `python3 -c` | `scripts/resolve_user_from_whatsapp.sh:19-24` |
| 11 | Apply agent prompt contains plaintext password, runs with bypass/force on untrusted pages | `apply/prompt.py:589` |

## 4. Correctness bugs

Pipeline:
- ✅ Tailor/cover prompts send `COMPANY: {job['site']}` (= "indeed"/"linkedin") instead of `company` — `scoring/tailor.py:285`, `scoring/cover_letter.py:176`.
- ✅ Material filenames are `site_title` → two same-title jobs overwrite each other — `tailor.py:419`, `cover_letter.py:250`. Use `job_id`.
- ✅ Persona logic hardcoded for everyone: `prune_after_score` deletes all non-"impact track" jobs (`discovery/cleanup.py:271-280`), CSR rules in scorer prompt (`scorer.py:55-58`), title ceilings (`filters.py:196-215`).
- Pruned rows are hard-deleted → drop out of known-URL set → rediscovered/re-scored daily (cost + empty-response storms, now 483 retries/run). Also orphans `stage_history`.
- `run_daily_brief.sh:87` hardcodes gated stage list for all users (ignores `human_gate`).
- Connect is a no-op in the brief (`list_ready_jobs` requires tailored) and overwrites `job_contacts_latest.json` with 5 jobs each run.
- `--url` uses `LIKE '%url%'` (matches wrong job, skips score check) — `apply/launcher.py:255-266`.
- DOCX batch applies `LIMIT` before filtering done jobs → stalls — `docx_export.py:162-195`.
- Scores persisted only at end of run; crash loses all — `scorer.py:744`.
- Billing breaker trips on substring "401/403/quota" in any error text — `scorer.py:278`.
- `keywords` missing from strict score schema → always empty — `scorer.py:225-237`.
- Tailor/cover/pdf runners return `ok` when every job failed — `pipeline.py:208-238`.
- `llm.py`: no retry on 5xx/transport errors; uncapped `Retry-After`; Gemini key in URL (leaks into logs); `load_env()` drops LLM singleton per web request (httpx leak).
- `--stream` mode broken in multiple ways (dead code; delete).
- No run lock: cron brief and dashboard Auto Search can run concurrently on the same rows. `web_runs.json`/`users.yaml` written non-atomically.
- Notify: no timeout on `hermes send`, send+mark not atomic, gated query hardcodes `fit_score >= 7` — `notify.py:60,138,216`.
- Schema: `CREATE TABLE` drifted from `_ALL_COLUMNS`; no schema_version; no indexes on `fit_score`/`funnel_stage`/`job_id`; `get_job_by_id` full-scans.

Dashboard:
- Drawer can only step ±1 stage; closing a backlog job on mobile requires passing through Applied, permanently stamping `applied_at` — `DrawerStageNav.tsx:63`, `board.py:143-163`.
- Cards are `touch-none` → board can't scroll on phones (users arrive from WhatsApp on phones); Board is default view on mobile — `JobCardView.tsx:69,82`.
- WhatsApp (N) counts `prepare` but gated notify sends `backlog ≥7` — `App.tsx:132` vs `notify.py:60`.
- ProfilePage user switch writes user A's searches into user B's `searches.yaml` — `ProfilePage.tsx:118,193`.
- Tailor runs not reattached on drawer reopen → duplicate runs; `useAutoSearch.start()` adopts any running run (incl. tailor / other user's).
- Auto Search on a finished run silently starts a new full LLM pipeline.
- Notes autosave race overwrites typing; toast on every save.
- SSE re-reads whole log every 0.5s, reports RC=0 for unknown exit codes, no reconnect.
- URL-as-path-key double-decodes `%xx` URLs; unknown `/api/*` GETs return index.html 200.
- No apply UI despite docs; ~8 endpoints unused (`/response`, `/history`, full `/tailor`, `/apply`, `PUT /settings/profile`, `/notify/preview`).
- Build skips `tsc`; no ESLint, no frontend tests; `JobsTable.tsx` 861 LOC, `App.tsx` 518 LOC.

## 5. Quality / ops

- Tests: 188 pass, **1 fails** — `tests/test_review_fixes.py:48` hardcodes `discovered_at='2026-09-17'`, now outside the 7-day freshness window. No CI.
- Untested: `pipeline.py`, `cli.py`, `enrichment/detail.py`, `discovery/smartextract.py`, `web/session.py`, billing breaker, notify status, scripts.
- Hand-patched Hermes wrapper (model pin) will be overwritten by `_upsert_one_cron.sh:37-46`; scripts copied not symlinked (`install_hermes_scripts.sh:18`).
- `jobwright_smoke.sh` kills a live brief and sends real WhatsApp; `validate_pipeline.sh` swallows all errors.
- `stale_check.py:87` hardcodes `richa`.
- Doc drift: default LLM (`gpt-oss-120b` vs `glm-5p3-flash`) in AGENTS.md:101,160 + whatsapp docs; `SCORE_BATCH_SIZE` presented as primary (real knob `JOBWRIGHT_SCORE_WORKERS`); `.env.example` missing 4 vars; CHANGELOG stops before 0.3; `src/applypilot` referenced but gone; skill count 22 vs 24; no ADRs for LLM failover / human gate / Jev.

## 6. Roadmap

**Now — restore trust (1–2 wks)**
1. Safety: apply dry-run by default + always enforce `apply_enabled`; fix SPA traversal; replace `/api/download?path=` with job-scoped routes; bind Vite to 127.0.0.1; drop `--reload` in prod; sanitize JID script.
2. Reliability: `playwright install chromium` in `.venv` + preflight in `doctor`/brief; operator heartbeat (per-stage RC, scored/failed, empty-response %, notify sent/skipped/failed) + 08:00 missed-run watchdog; nightly `sqlite3 .backup` of `users/` off the SSD.
3. Fix flaky test; add CI (pytest + ruff + `tsc --noEmit`).
4. Correctness: `company` not `site`; `job_id` filenames; soft-close instead of delete on prune; honest stage status; incremental score persistence; per-user run lock.

**Next — precision + mobile review (3–6 wks)**
5. Precision sprint: categorical gate (mission / function / excluded duties) before fit score; few-shot from 154 human labels; offline eval set gating prompt/model changes. Target precision@10 (human ≥6) 19% → ≥50%.
6. One-tap feedback on cards (Relevant / Not + reason chip); required close reason; feed labels into scoring.
7. Mobile-first drawer: sticky header with Open & Apply / Mark applied / Dismiss / Move to…; List default on mobile; fix touch scroll; single "Prepare materials" action; reattach tailor runs.
8. Fuzzy dedupe (company+title+location) across boards and in notify.
9. Persona out of code → per-user config (prune rules, prompt guidance, title ceilings).
10. Persona-fit sources (Idealist, PND, foundation ATS lists, impact VC boards, company watchlist); prune irrelevant Workday employers, ZipRecruiter/Glassdoor.

**Later**
11. Request-scoped `UserContext`, Cf-Access JWT → user mapping (needed before any 2nd user).
12. Post-apply loop: follow-up reminders, "got a reply", stage timeline, weekly scorecard (shown → relevant → applied → response).
13. Referral-first cards (top connection + drafted intro); contacts in DB.
14. TanStack Query, OpenAPI-generated TS types, split big components, lean `/board` DTO.
15. Decide fate of Jev (0 fast-path decisions) and portfolio (always skipped).

## 7. Open questions for the owner

1. Personal tool for richa, or product for many niche seekers? (Drives multi-tenancy, onboarding, hosting.)
2. North star: applications/week, interviews, or offers? Will richa log responses?
3. Are the Sep 16 rescores trustworthy ground truth for an eval set?
4. Near-empty brief since Sep 20 — widen automatically (tier-2 queries, remote/NYC) when supply drops?
5. LLM budget/provider policy after Fireworks/OpenRouter outages?
6. Keep LinkedIn as primary source (64% of ingestion, most noise)?
7. Is DOCX/cover generation valued (32 DOCX total)?
8. Move host/data off the ExternalSSD?
9. Keep Jev and portfolio?
