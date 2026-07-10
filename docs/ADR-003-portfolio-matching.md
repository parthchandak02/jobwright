# ADR-003: Portfolio-Aware Project Selection

## Status

Accepted

## Context

Generic resume tailoring under-emphasizes relevant projects. Abdrakib/job-agent demonstrates selecting 4–5 portfolio projects per job description.

## Decision

Add `portfolio` array to `profile.json`. New pipeline stage `portfolio` runs after `score` for jobs with `fit_score >= min_score`. Store selected project IDs in `portfolio_project_ids` column. Inject into tailor and cover letter prompts.

## Algorithm

1. Keyword overlap scoring between each portfolio entry and `full_description`
2. LLM judge ranks top 4–5 from candidates
3. Never fabricate — only select from declared portfolio entries

## Consequences

- Users must populate `profile.json` portfolio section during init
- Extra LLM call per eligible job (batched in `run_portfolio_selection`)
