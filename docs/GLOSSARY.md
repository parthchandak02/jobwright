# Glossary

| Term | Definition |
|------|------------|
| Pipeline | Prep stages `discover → enrich → score → portfolio → tailor → cover → pdf → docx → connect` (SQLite `jobs` table). Daily brief and Auto Search skip `pdf`. Optional `apply` is gated. |
| Job | Database row keyed by `url`; also has a short `job_id` (blake2b of the URL) for dashboard deep links |
| Prepare | Funnel stage for strong matches with materials; agent auto-advances here; notify lists only these |
| Auto Search | Dashboard action that starts the full prep pipeline (`discover`→`connect`) via `POST /api/run` with live logs |
| Run registry | Durable run list at `users/<id>/logs/web_runs.json` so the UI can attach, stream, or stop after reload |
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
| Dry-run gate | `--dry-run` fills forms without submitting; emits `RESULT:DRYRUN` |
| Tier | Feature gate: 1=discover, 2=LLM, 3=auto-apply |
| pp-cli | `job-apply-pp-cli` Printing Press agent-native wrapper |
