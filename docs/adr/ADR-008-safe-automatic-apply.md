# ADR-008: Safe automatic applications

- **Status:** Accepted
- **Date:** 2026-11-08
- **Supersedes:** the live path of [ADR-002](ADR-002-agent-provider.md) (the Cursor/Claude MCP providers stay for dry runs only)

## Context

The ApplyPilot-derived apply code had never run for real and was unsafe: it cloned the operator's own Chrome
profile for every worker, ran unpinned `npx ...@latest` MCP servers including a Gmail server with one global
token, told the agent to claim tools the person never used and to "do whatever it takes", defaulted criminal /
age / background answers, declined EEO questions for the person, wrote plaintext passwords into the prompt,
solved CAPTCHAs through a paid service, trusted the agent's own "RESULT:APPLIED" text and created real
accounts in dry runs. The owner wants fully automatic applications (1-2 a day, score 8+) for one consenting
person, under her own email.

## Decision

1. **Identity isolation.** A fresh persistent Playwright profile per person under their data dir; never a copy
   of the system Chrome profile. No email access at all. Pinned dependencies.
2. **Our own tools, not a hosted browser toolset.** The agent (`claude-sonnet-5-5`, Messages API manual
   tool loop) drives our Playwright browser through ten small tools. Anthropic's browser use toolset was
   considered; owning every tool lets the safety rules run in code on every action (attestation check,
   hidden secrets, dry-run submit block, allowlist, evidence). Deterministic Greenhouse / Lever / Ashby
   fillers run first; the agent is the fallback.
3. **Answer bank in `profile.json` (`application_answers`)** rather than a DB table: a small, human-edited,
   per-person document that belongs with the profile in backups/restores/deletes and needs no queries.
   Attestations are answered only from it; missing → skip and ask.
4. **Human in the loop over WhatsApp** (`pending_inputs`): CAPTCHA → "finish this one" link (operator at the
   Mac mini), email code → the person pastes it in their group, missing answer → skip + question.
5. **Evidence and verification** (`submissions`, run folder): Applied only on a verified confirmation page.
6. **Rails:** kill switch, per-person enable / daily cap / min score / employer cap, dedupe, auto-pause, a
   veto window (`apply_picks`, `apply_mode: veto` default) for the first weeks, no cron installed by code.

## Consequences

- New migration 4 (`pending_inputs`, `submissions`, `apply_picks`) after the fillers' migration 3.
- `anthropic` is an optional extra (`--extra apply`); tests use a scripted fake client and a local fake ATS.
- A CAPTCHA can only be solved by someone at (or screen sharing into) the Mac mini; the dashboard shows a
  refreshing picture, not a remote browser.
- Legacy `AGENT_PROVIDER=cursor-sdk|cursor-cli|claude` refuse `--live`.
