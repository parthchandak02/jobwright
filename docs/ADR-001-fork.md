# ADR-001: Fork ApplyPilot for Cursor/Hermes Agent Integration

## Status

Accepted

## Context

ApplyPilot (Pickle-Pixel/ApplyPilot) provides a mature 6-stage job application pipeline. Stage 6 hardcodes Claude Code CLI subprocess invocation. The user requires Cursor Agent and Hermes orchestration without Claude Code dependency.

## Decision

Fork ApplyPilot as `applypilot-cursor` under AGPL-3.0. Reuse stages 1–5 unchanged. Replace stage 6 with a pluggable `AgentProvider` abstraction defaulting to `cursor-sdk`.

## Consequences

- Upstream improvements must be cherry-picked manually
- AGPL obligations apply to distributed copies
- Attribution to Pickle-Pixel/ApplyPilot required in README and LICENSE

## Upstream

https://github.com/Pickle-Pixel/ApplyPilot
