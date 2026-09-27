# ADR-006: Scoring v2: per-user criteria, retrieved examples, labels, evals

- **Status:** Accepted
- **Date:** 2026-09-26
- **Version:** 0.6.0

## Context

The owner's success metric is "relevant jobs with high confidence". On richa's
labeled history only ~20% of jobs the v1 scorer sent (score >= 7) were wanted.
v1 asked for a bare 1-10 skills-overlap number; her real filters are categorical
(fundraising roles, license requirements, location, level). Human rescores were
stored in `jobs.user_fit_score` (overwritten on every edit) and only the 12 most
recent were pasted into the prompt. glm-5p3-flash also spent its whole token
budget on hidden reasoning, producing hundreds of empty responses per run.

## Decision

1. **Labels are append-only.** `score_labels` keeps every human rating with a
   snapshot of the job (title, company, description) so labels survive pruning.
   The pre-v0.6 rescores were imported once. `jobs.user_fit_score` mirrors the
   latest label. Dashboard ratings (thumbs + reason chips) and "Not for me"
   dismissals with reasons both append labels.
2. **Per-user match criteria** (`profile.json` `match_criteria`): summary,
   dealbreakers `{id,label,description}`, good-fit role types, locations,
   seniority, pay floor, notify threshold. Derived from `job_preferences` when
   absent; editable in Profile → Match rules; "Suggest from my ratings" drafts
   them from resume + labels (`criteria_miner.py`).
3. **Structured judgment, rules in code.** One call per job returns
   dealbreakers / concerns / location_ok / seniority / fit / confidence /
   reasoning (json_schema). A hard dealbreaker or bad location caps the score at
   3 in code; salary below floor caps at 4; seniority informs fit (no cap: evals
   showed candidates apply to stretch roles).
4. **Retrieved few-shot.** TF-IDF over the user's labeled decisions picks the 12
   most similar past decisions (at least 4 positives), leave-one-out safe.
5. **Cost tiers.** Cheap model (`LLM_MODEL`, glm-5p3-flash) with
   `reasoning_effort=low`; optional Jev reject-only prefilter (Jev fast-accept was
   only 58% precise, so it never accepts); escalation to a stronger model is
   opt-in (`LLM_ESCALATION_MODEL`) because glm-5p3 and kimi-k3 gave no gain.
6. **Evals gate changes.** `jobwright eval` replays the scorer on the labeled set
   and reports precision/recall at 6/7/8 vs the stored production scores, on all
   labels and on explicit labels only ("closed without applying" is a weak
   negative). Every machine score is appended to `score_history`.

## Results (richa, 249 labeled jobs, 40 relevant)

| At score 7+ | Precision (all) | Precision (explicit labels) | Recall |
|---|---|---|---|
| v1 production | 0.20 | 0.35 | 1.00 (selection bias) |
| v2 | 0.44-0.58 | 1.00 | 0.35-0.45 |

Remaining misses are mostly stretch jobs the user applied to despite her own
rules; the "worth a look" lane (5-6, no hard dealbreaker) surfaces those
without polluting the daily list. Scoring errors went from hundreds/run to 0.

## Update 2026-09-27 (G4, recall)

Error analysis of the 26 relevant jobs scored below 7 (v2.3): about 10 carry the
user's own negative reason (applied then rated 1-4, or rated 7-8 with "too
senior", "requires a license", "mission not exciting"); about 9 break her own
rules (fundraising core duties, onsite outside her areas, executive roles); the
rest were location caps on NY/remote roles she is open to, seniority dragging
fit to 2-4, and a few 5-6s.

| Explicit labels | 5+ P / R | 6+ P / R | 7+ P / R |
|---|---|---|---|
| v2.3 | 0.857 / 0.45 | 0.882 / 0.375 | 1.00 / 0.35 |
| v2.4 (two runs) | 0.73-0.79 / 0.55 | 0.90-0.95 / 0.45-0.475 | 1.00 / 0.35-0.375 |

- **v2.4 kept:** derived criteria include `job_preferences.company_types`
  (carried "open to NY/LA and US remote"), and seniority lowers fit by 1-2
  points instead of vetoing a role type the user wants.
- **Threshold sweep kept:** `jobwright eval` reports P/R/F0.5 for 3-9 and a
  recommended threshold (max recall with explicit precision >= 0.85, at least 3
  hits), shown on the Match quality page. It does not change `notify_threshold`.
- **Borderline second opinion rejected (default off):** a second call for 5-6
  scores (`JOBWRIGHT_BORDERLINE_BAND=5-6`, `_MODEL`, `_COMBINE=max|mean`) with
  positive-balanced examples moved scores by +/-1 like noise; glm-5p3 as the
  second opinion added a false positive and no hits.
- **Remote tag skipping the location cap rejected:** +1 hit at 7+, but job
  boards tag non-US roles "(Remote)" too (added a false positive at 6+).
- `jobwright eval --reuse <report>` re-gates a stored run and only pays for new
  calls, so gate and second-opinion experiments cost ~60k tokens, not ~930k.

## Consequences

- `JOBWRIGHT_SCORER=v1` restores the legacy scorer.
- Precision improves as users rate; the Match quality page shows ratings,
  sent-and-advanced rate, the latest accuracy check and token use.
