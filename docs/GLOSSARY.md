# Glossary

| Term | Definition |
|------|------------|
| Pipeline | Prep stages `discover → enrich → score → portfolio → tailor → cover → pdf → docx → connect` (SQLite `jobs` table). Daily brief and Auto Search skip `pdf`. Optional `apply` is gated. |
| Job | Database row keyed by `url`; also has a short `job_id` (blake2b of the URL) for dashboard deep links and material file names |
| Tombstone | Row in `job_tombstones` for a pruned or duplicate job; a trigger blocks re-inserting that URL, so it never returns |
| Dedupe key | Normalized `company \| title \| place` used to drop cross-board duplicates before enrich/score |
| Profile | One user's data dir `users/<id>/` plus its `users.yaml` entry (`emails`, `whatsapp_target`, `schedule`, `human_gate`, `brief_top_n`, `apply_enabled`) |
| Admin | Login email in `users.yaml` `admins` (or `JOBWRIGHT_ADMIN_EMAILS`); may open, create and edit every profile |
| Auth mode | `JOBWRIGHT_AUTH_MODE`: `cloudflare` verifies the Cloudflare Access JWT; `dev` trusts local callers and refuses Cloudflare traffic |
| Onboarding | `/welcome`: new login uploads a resume, reviews the drafted profile / searches / match criteria, picks a WhatsApp chat and time |
| Match criteria | `profile.json` `match_criteria`: summary, dealbreakers, good-fit role types, locations, seniority, pay floor, notify threshold. Derived from `job_preferences` until edited |
| Scoring v2 | Default scorer: one structured call per job with criteria + retrieved examples; gates in code. `JOBWRIGHT_SCORER=v1` restores the legacy scorer |
| Gate | Code-applied cap on the model's fit: dealbreaker or bad location → 3, salary below floor → 4, unknown location → 6 |
| Label | Human rating appended to `score_labels` (dashboard rating, dismissal reason, or import); never overwritten. `jobs.user_fit_score` mirrors the latest |
| Retrieved examples | The 12 labeled past decisions most similar to a job (TF-IDF, at least 4 positives), included in its scoring prompt |
| Eval | `jobwright eval`: replays the scorer over labeled jobs; precision/recall at 6/7/8 vs stored production scores |
| Jev prefilter | Optional TypeSafe Jev tier (`jev_hybrid`); in v2 it only fast-rejects, never accepts |
| Ops target | WhatsApp target for operator alerts (`users.yaml` `ops_target` or `JOBWRIGHT_OPS_TARGET`) |
| Brief report | `jobwright ops brief-report`: end-of-brief summary; alerts the ops target on problems, writes `logs/ops_health.json` |
| Watchdog | `jobwright-ops-watchdog` cron (`jobwright ops watchdog`): alerts when a brief never started or never finished |
| Preflight | `jobwright preflight [--fix]`: profile/resume, LLM key, disk, Playwright (blocking); Hermes CLI, WhatsApp bridge (warn) |
| Hermes dry-run | `JOBWRIGHT_HERMES_DRY_RUN=1`: cron changes and WhatsApp sends are logged, not executed |
| Prepare | Funnel stage for strong matches with materials; agent auto-advances here; notify lists only these |
| Backlog | Discovered/scored jobs not yet handed to the human. Low-score rows (and off-track rows when `mission_guard` is on) are pruned and tombstoned after scoring. Score 7+ jobs get tailored into Prepare (or listed for review under human gate). Mid-score jobs stay here as maybes. |
| Auto Search | Dashboard action that starts the full prep pipeline (`discover`→`connect`) via `POST /api/run` with live logs. Daily Hermes cron (`jobwright-brief-<user>`) runs the same pipeline on `schedule` (default 6:00 AM), then `notify`. Dashboard **WhatsApp** dialog edits that schedule and target and creates the cron if missing. |
| Run registry | Durable run list at `users/<id>/logs/web_runs.json` so the UI can attach, stream, or stop after reload; records real exit codes |
| Run lock | Per-user `flock` on `<user dir>/.pipeline.lock`; a second concurrent run exits instead of overlapping |
| Notify | `jobwright notify`: one WhatsApp text list of new `prepare` jobs with deep links; stamps `whatsapp_notified_at` |
| Deep link | `{JOBWRIGHT_PUBLIC_BASE_URL}/jobs/<job_id>` opens the board and that job's drawer. `/profile` opens Profile. |
| Base resume | `resume/base.pdf` is source of truth; `resume.py` derives cached `resume/base.md` for LLM stages |
| Auto Tailor | Dashboard per-job run: `jobwright tailor-job` with default instructions (`tailor_instructions.py`) |
| Custom Tailor | Same run after the user edits resume + cover instructions in `CustomTailorDialog` |
| Portfolio | Structured projects in `profile.json` used for per-job selection |
| Query tiers | T1 daily (`DISCOVER_MODE=fast`); T2/T3 weekly deep crawl (`full`) |
| Known-URL skip | Discovery skips already-stored postings before expensive fetch (JobSpy and Workday) |
| AgentProvider | Pluggable stage-6 backend (`cursor-sdk`, `cursor-cli`, `claude`) |
| Worker | Parallel apply unit with isolated Chrome CDP port and workdir; also JobSpy `-w` for discover |
| RESULT protocol | Agent output codes: `RESULT:APPLIED`, `RESULT:FAILED:reason`, etc. |
| Dry-run gate | `jobwright apply` fills forms without submitting unless `--live`; emits `RESULT:DRYRUN` |
| Tier | Feature gate: 1=discover, 2=LLM, 3=auto-apply |
| pp-cli | `job-apply-pp-cli` Printing Press agent-native wrapper |
