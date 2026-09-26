# ADR-005: Multi-user dashboard: Cloudflare Access identity, per-request profile

- **Status:** Accepted
- **Date:** 2026-09-26
- **Version:** 0.6.0

## Context

jobwright grew from one user (richa) to "anyone the owner invites". The dashboard
switched users by mutating module-level path globals (`config.DB_PATH`, ...) on
every request while FastAPI ran handlers in a thread pool, so two users at once
could read or write each other's database. Auth was edge-only: anyone past
Cloudflare Access could pick any profile with a cookie.

## Decision

1. **Identity from Cloudflare Access.** The API verifies `Cf-Access-Jwt-Assertion`
   (RS256 against the team JWKS, audience `JOBWRIGHT_CF_AUD`, issuer
   `https://JOBWRIGHT_CF_TEAM_DOMAIN`). `JOBWRIGHT_AUTH_MODE=dev` trusts local
   callers but refuses any request carrying Cloudflare edge headers, so a
   misconfigured prod API fails closed.
2. **Profiles bound to emails.** `users.yaml` users carry `emails: [...]`; a
   top-level `admins: [...]` list (plus `JOBWRIGHT_ADMIN_EMAILS`) may open every
   profile. Non-admins only see profiles that list their email. An unknown
   email gets onboarding (create a profile bound to that email).
3. **Per-request path state.** Per-user paths live on a `_PathState`; the module
   class routes `config.X` reads/writes to the active state. The CLI mutates the
   process default (one process = one user). The web middleware binds a fresh
   state per request with `config.user_context(user_id)` held in a ContextVar,
   which Starlette propagates into thread-pool handlers and streaming bodies.
   The process default is parked on an empty sentinel dir, never a real user.
4. **Per-user settings do not leak.** The per-user `.env` overlay is applied to
   `os.environ` only in CLI processes; web code reads it via `config.user_env()`.
5. Runs, tailor jobs and SSE streams are scoped to the requesting profile.

## Consequences

- New people need two things: an email in the Cloudflare Access policy (owner,
  in the Zero Trust dashboard) and a profile bound to that email (self-serve
  onboarding or the Admin page).
- `tests/test_web_auth.py` covers JWT verification, per-email access, admin
  switching and 40 concurrent mixed-user requests with no cross-over.
