# jobwright documentation

Start with the top-level [README](../README.md) for setup and usage. **Agents** should read [AGENTS.md](../AGENTS.md) first. This folder holds everything else.

## Agent documentation

- [docs/agents/README.md](agents/README.md) - agent doc index (Hermes, WhatsApp, repo map)
- [docs/agents/install-hermes-skill.md](agents/install-hermes-skill.md) - install thin skill to `~/.hermes/skills/`

## Contents

- [CONTRIBUTING.md](CONTRIBUTING.md) - development setup, coding standards, and PR guidelines
- [CHANGELOG.md](CHANGELOG.md) - notable changes per version
- [GLOSSARY.md](GLOSSARY.md) - key terms used across the pipeline
- [UPSTREAM.md](UPSTREAM.md) - attribution and AGPL obligations

## Architecture decision records

- [ADR-001: Origins and pluggable agent architecture](adr/ADR-001-origins.md)
- [ADR-002: AgentProvider abstraction for stage 6](adr/ADR-002-agent-provider.md)
- [ADR-003: Portfolio-aware project selection](adr/ADR-003-portfolio-matching.md)
- [ADR-004: Stored funnel_stage Kanban with agent handoff](adr/ADR-004-kanban-funnel-stage.md)
- [ADR-005: Multi-user dashboard: Cloudflare Access identity, per-request profile](adr/ADR-005-multi-user-auth-and-request-context.md)
- [ADR-006: Scoring v2: per-user criteria, retrieved examples, labels, evals](adr/ADR-006-scoring-v2-labels-and-evals.md)
- [ADR-007: Operator alerts, backups, and running from the internal disk](adr/ADR-007-ops-alerts-backups-internal-disk.md)
