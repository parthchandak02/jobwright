# Jobwright contexts for humanizer

Apply humanizer whenever you produce or edit user-facing prose in this repo.

## High priority (user sees this directly)

| Context | Location / trigger | Notes |
|---------|-------------------|-------|
| Cover letters | `src/jobwright/scoring/cover_letter.py` output, tailored application text | Keep facts from resume and job posting; no invented employers or dates |
| WhatsApp digests | `scripts/jobwright_send.sh` output, Daily Brief summaries | Short, specific, no chatbot closings |
| CLI messages | `src/jobwright/cli.py`, wizard prompts | Clear and direct; avoid sales tone |
| README / docs | `README.md`, `docs/**`, `skills/**` | Technical accuracy first; personality only when appropriate |

## Medium priority

| Context | Notes |
|---------|-------|
| Commit message bodies | Prose in commit bodies, not subject lines |
| Handoffs | Lean runtime notes; still human, not boilerplate |
| PR descriptions | When user asks to write or polish them |
| Skill files | Instructions for humans; keep concise |

## Do not humanize

- Code, SQL, YAML config keys, environment variable names
- JSON / structured data
- Test assertions and fixture strings (unless explicitly user-facing copy)
- Quoted third-party text, job posting excerpts, resume bullets (preserve source wording)
- AGPL / license attribution blocks in `docs/UPSTREAM.md`

## Voice for job applications

When humanizing cover letters or application answers:

1. Match the candidate's resume voice when a sample or profile is available.
2. Never add employers, titles, dates, skills, or metrics not in the source material.
3. Prefer specific, modest claims over inflated legacy language.
4. One page or less; cut generic optimism at the end.
