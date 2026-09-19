# jobwright Sep 19 incident: "day 2, still not fixed" — root causes + fixes

## What Parth saw
Daily brief sent Richa 10 jobs, all score 7, many fundraising-heavy (Campaign Lead @ NatureBridge,
Fund Director, Senior Engagement Manager @ Blood Cancer United) — exactly what Richa's Sep 16
feedback excluded. Duplicate Mozilla posting twice in one list.

## Root causes (verified in logs + DB, not assumed)
1. **OpenRouter out of credits (402 on every call).** Sep 18: 4,356 hits. Sep 19: 15,958 hits.
   Both days scored 0 fresh jobs (`score: error: 2658 scoring failures`). The Sep 16 "fix"
   (route via OpenRouter) died when credits ran out and NOTHING alerted — the brief still
   delivered, so failure was invisible.
2. **Model config drift.** Handoff says `deepseek-v4-flash-0731` but `users/richa/.env` had
   `deepseek/deepseek-chat` (older OpenRouter id) and `JOBWRIGHT_LLM_MODEL` was set nowhere.
   load_env(override=True) lets user .env stomp the script default silently.
3. **Notify fallback surfaced a stale pool.** `get_unnotified_gated_jobs` picks unnotified
   backlog fit>=7 with NO age filter. The 10 sent jobs were scored Aug 20-21 under the OLD
   resume/excludes/location rules and sat unnotified for a month. Fresh scoring died ->
   stale pool drained -> fundraising jobs appeared "new".
4. **SINGLE_MAX_TOKENS=300 breaks on Fireworks thinking models.** glm-5p3-flash emits ~880
   reasoning tokens on full-size prompts (resume + 6000-char JD). 300 budget => 100%
   reasoning, finish_reason=length, empty content => "Empty structured LLM response" storms.
5. **Jev shadow never ran.** users.yaml lacked `jev_hybrid` (handoff claimed richa=shadow);
   zero jev_ rows in DB. Silent config skip.

## Fixes shipped (commit 041d12b)
- `scorer.py`: billing circuit breaker (`_note_billing_error`, `_BillingDead`); any
  402/401/403 opens the breaker, workers raise immediately, run_scoring raises RuntimeError
  when 0 scored -> pipeline reports error, notify finds nothing fresh, sends nothing.
- `scorer.py`: SINGLE_MAX_TOKENS 300 -> 1200 (verified: 3/3 then 150/150 scored, 10.5s/57s).
- `notify.py`: freshness guard — gated pool requires `discovered_at >= now-7d`
  (JOBWRIGHT_BRIEF_MAX_AGE_DAYS). Stale unnotified jobs can never resurface.
- `users/users.yaml`: richa `jev_hybrid: shadow` (Jev calibration data starts accumulating).
- `users/richa/.env`: stripped dead OpenRouter LLM_URL/LLM_API_KEY/stale LLM_MODEL ->
  Fireworks glm-5p3-flash (key verified 200 live).
- Wrapper `~/.hermes/scripts/wrap_jobwright-brief-richa.sh`: pins
  JOBWRIGHT_LLM_MODEL=accounts/fireworks/models/glm-5p3-flash explicitly.
- Swept the 7 stale unnotified fit=7 jobs -> closed (cancelled) with stage_history audit rows.
- Launched full catch-up scoring of 2,505 pending jobs (pid 11216, users/richa/logs/catchup_20260919_full.log).

## Verification
- 186 tests pass. Ruff n/a; ast-clean. Live scoring: sane scores (SAP/customs roles = 1,
  banking = 2 for impact-investing MBA; fundraising Campaign Lead = 3-5).
- notify --dry-run after sweep: "Nothing to send" (correct — no fresh scored jobs yet).

## Lessons
- "Fixed" without an alerting path = not fixed. Billing/auth failures must fail LOUD
  (circuit breaker -> stage error -> empty brief, not stale brief).
- Never let the notify pool be unbounded by age; a stale pool converts invisible
  upstream failure into confidently-wrong output.
- Thinking-mode models need 3-4x token budget for small-JSON tasks; test max_tokens
  against the actual prompt size before trusting any model switch.
- Config claimed in a handoff doc is not config in the repo; diff docs vs .env.
