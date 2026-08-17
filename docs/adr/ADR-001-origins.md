# ADR-001: Origins and Pluggable Agent Architecture

## Status

Accepted

## Context

jobwright started from a mature, AGPL-3.0 six-stage job application pipeline. That base hardcoded a single Claude Code CLI subprocess for the browser-apply stage. jobwright needed Cursor Agent and Hermes orchestration without a hard Claude Code dependency, plus portfolio-aware tailoring and multi-profile support.

## Decision

Build jobwright under AGPL-3.0, keeping the proven stages 1-5 and replacing the apply stage with a pluggable `AgentProvider` abstraction that defaults to `cursor-sdk`. Layer on portfolio matching (ADR-003) and multi-profile / Hermes scheduling.

## Consequences

- The project stays AGPL-3.0; source must be provided for distributed and networked deployments.
- Attribution for the AGPL-derived portions is retained in [../UPSTREAM.md](../UPSTREAM.md) and the `LICENSE`.
- Improvements to the original codebase, if adopted, are integrated manually.
