# ADR-009: The person's own Claude applies (jobwright connector)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Builds on:** [ADR-008](ADR-008-safe-automatic-apply.md) (gates, answer bank, evidence), [ADR-005](ADR-005-multi-user-auth-and-request-context.md) (identity, per-request profile)

## Context

ADR-008's server-side runner applies with our Claude API key (`claude-sonnet-5-5`, tens of tool turns per
application), in a Playwright profile on the Mac mini. That costs our tokens for every person and every
application, and the hard parts (CAPTCHAs, email codes, account sign-ups) need a person at the Mac mini.
Every invited person already has their own Claude, which can drive their own browser with Claude in Chrome,
where they are signed in, their password manager works and they can solve a CAPTCHA themselves. The owner
already runs two remote MCP connectors on the same pattern (Tandem, Wedding Looks).

## Decision

1. **jobwright is a remote MCP server** (`/mcp`, streamable HTTP, stateless, JSON responses, official `mcp`
   Python SDK 2.x) inside the existing FastAPI app: one process, the same code paths as the dashboard.
2. **OAuth 2.1 as Claude's custom connectors expect** (discovery metadata, dynamic registration, S256 PKCE,
   rotating refresh tokens), but **signed in with the dashboard's identity**: `/oauth/authorize` stays behind
   Cloudflare Access and maps the verified login email to the profiles that list it. Grants are per person,
   per profile, per client; scoped (`jobs:read`, `jobs:write`, `apply`); hashed at rest; revocable from the
   dashboard; dead as soon as the login leaves the profile.
3. **The person's Claude does the model work**: tailoring (we hand it the base resume, posting and our
   instructions; we only store and render the result), open-question drafting and form filling. jobwright
   makes no model call for the connector.
4. **jobwright keeps the rules**: `start_application` runs ADR-008's gates (kill switch, pause, daily cap,
   LinkedIn, dedupe, employer cap) plus the veto window, and claims the job atomically so two clients (or
   the server runner) never apply twice. Attestations come only from the answer bank, saved only on the
   person's explicit word. `record_submission` stores the evidence in ADR-008's `submissions` table and moves
   the card to Applied only with confirmation evidence.
5. **Submit is a person's decision unless the owner enabled it**: `apply_enabled` + minimum score → Claude may
   press Submit; otherwise Claude fills and the person submits.
6. **`apply_via` per profile** (`connector` default, `server`, `off`): the server runner stays available but is
   off unless chosen (admins only).

## Alternatives considered

- **Keep the server runner as the main path.** Proven gates and our own tools, but our tokens, our machine,
  and a person at the Mac mini for every CAPTCHA. Kept as `apply_via: server`.
- **Passphrase sign-in like Tandem / Wedding Looks.** Fine for two people sharing one dataset; jobwright has
  many people with separate data, so the token must name a profile. Reusing Cloudflare Access gives real
  per-person identity with no new password.
- **A separate connector process on its own port** (Tandem's choice, so the tunnel can only reach connector
  routes). jobwright already authenticates every `/api` request itself (Access JWT), so one process with
  path-scoped Access bypass is simpler and reuses `config.user_context`, the board's move logic and the
  apply gates without an internal HTTP hop.
- **The SDK's built-in OAuth provider classes.** We need the consent step to read the Access identity and pick
  a profile, plus grant-level revocation and reuse detection; a few hundred lines of our own are easier to audit than
  adapting the provider protocol.

## Consequences

- Owner adds one Access application with a Bypass policy for `/mcp`, `/.well-known/oauth-*`,
  `/oauth/register`, `/oauth/token`, `/oauth/revoke` ([claude-connector.md](../agents/claude-connector.md)).
- New optional extra `connector` (`mcp>=2.3,<3`); migration 5 adds `submissions.client_id`.
- Evidence is Claude's report (fields, confirmation text, screenshot), checked for consistency, not observed
  by us. Verification rules are the same as the runner's; `high` needs a screenshot.
- Mobile-only users can read and tailor but not apply (no Claude in Chrome there).
