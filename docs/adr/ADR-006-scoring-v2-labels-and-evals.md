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

## Consequences

- `JOBWRIGHT_SCORER=v1` restores the legacy scorer.
- Precision improves as users rate; the Match quality page shows ratings,
  sent-and-advanced rate, the latest accuracy check and token use.
