# ADR-002: AgentProvider Abstraction for Stage 6

## Status

Accepted

## Context

Stage 6 browser apply requires an LLM agent with Playwright MCP. Claude Code, Cursor Agent CLI, and Cursor SDK all support MCP but with different invocation patterns.

## Decision

Introduce `apply/providers/` with:

| Provider | Use case |
|----------|----------|
| `cursor-sdk` (default) | Production — inline MCP per worker CDP port |
| `cursor-cli` | Debug fallback — per-workdir `.cursor/mcp.json` |
| `claude` | Legacy upstream compatibility |

Hermes is used for cron orchestration only, not form filling.

## Selection

`AGENT_PROVIDER` environment variable. Tier 3 gate accepts `CURSOR_API_KEY` + Chrome + Node instead of `claude` binary.

## Consequences

- Shared `RESULT:*` parser across all providers
- Cursor SDK requires `cursor-sdk` pip package
- Parallel workers need per-call inline MCP (SDK) or per-workdir config (CLI)
