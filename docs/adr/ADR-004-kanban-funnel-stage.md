# ADR-004: Stored funnel_stage Kanban with agent handoff

- **Status:** Accepted
- **Date:** 2026-08-18
- **Version:** 0.5.0

## Context

jobwright already tracks an agent pipeline via timestamps (`discovered_at`, `scored_at`, `tailored_at`, `cover_letter_at`, `applied_at`). We needed a hosted Kanban board that also covers post-apply human outcomes (screen, interview, offer, closed) and manual job entry, with history for future analytics.

Deriving board position only from pipeline timestamps cannot express interview/offer, and re-running the pipeline would clobber human moves (zombie re-tailor / accidental apply).

## Decision

1. **Store `funnel_stage`** on `jobs` as the Kanban lane: `backlog → prepare → applied → in_progress → offer → closed`.
2. Keep **pipeline eligibility SQL timestamp-based**; the board field rides alongside.
3. All stage changes go through **`advance_funnel(url, to_stage, actor)`**, which also writes `stage_history`.
4. **Agent auto-advance caps at `prepare`** (handoff). Human (or gated apply via `system`/`human`) owns Applied onward.
5. Anti-clobber: pipeline pending/ready/digest queries skip human-held cards and post-handoff stages; manual `source='manual'` jobs are excluded from digest/auto-apply.
6. `first_response_at` captures reply without an extra lane; `outcome` on Closed enables learning later.

## Consequences

- Schema migration is additive (`ensure_columns` + `stage_history` CREATE IF NOT EXISTS + one-time backfill).
- Dashboard hosting (FastAPI + SPA + cloudflared + Zero Trust) is a new surface; auth is edge-only.
- Analytics (v2) can use `stage_history` + `first_response_at` without changing the board model.
