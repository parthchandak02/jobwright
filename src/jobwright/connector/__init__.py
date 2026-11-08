"""The jobwright Claude connector: a remote MCP server plus its OAuth 2.1 sign-in.

People add ``<base>/mcp`` as a custom connector in their own Claude (claude.ai,
Claude Desktop, mobile). Their Claude then reads their board and applies for
them in their own browser (Claude in Chrome), so jobwright spends no model
tokens on applying. Design: docs/adr/ADR-009-users-own-claude-applies.md,
guide: docs/agents/claude-connector.md.

- ``store``: SQLite at ``<users root>/connector.sqlite`` (clients, codes,
  grants, hashed tokens, signed download links). Only hashes are stored.
- ``oauth``: discovery metadata, dynamic client registration, the consent
  page (behind Cloudflare Access: same identity as the dashboard), token
  exchange with S256 PKCE, refresh rotation with reuse detection, revocation.
- ``server``: the MCP endpoint at ``/mcp`` (streamable HTTP, stateless,
  JSON responses) with bearer auth that binds every call to one profile.
- ``tools``: what Claude can do, always inside ``config.user_context``.
"""
