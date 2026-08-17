---
name: grill-with-docs
description: Stress-test a plan before coding: one question at a time with a recommended answer, sharpen terms, update CONTEXT.md as decisions settle. No implementation during the session.
---

# Grill With Docs

Stress-test a plan against the domain model before implementation. Sharpen terms, resolve decision dependencies one at a time, and update glossary docs only when that is the project convention or the user asks.

## Trigger cues

Use when the user asks to grill a plan, stress-test a design, resolve terminology, align language with code, or lock trade-offs before build.

## Scope and non-goals

Scope:
- Clarify language, boundaries, and trade-offs.
- Resolve dependencies one decision at a time.
- Update glossary context when terms settle (see Doc creation).

Non-goals:
- Do not implement during the grilling session.
- Do not create ADRs for reversible or obvious decisions.
- Do not ask questions the codebase or docs can answer.

If the user shifts to implementation ("go", "implement", "stop grilling"), confirm and end grilling mode.

## Detect primary stack

Infer from the workspace and the user's wording:

| Stack | Signals |
|-------|---------|
| Node / web | `package.json`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `bun.lock` / `bun.lockb` |
| Python | `pyproject.toml`, `requirements.txt`, `setup.cfg`, `Pipfile` |
| Xcode / iOS | `*.xcodeproj`, `*.xcworkspace`, app-local `Package.swift`, heavy `Sources/**/*.swift` |

If several apply, prefer what the user named; otherwise ask once which stack frames the session.

## Required workflow

1. **Probe before asking.** Read relevant code and docs (readonly). Prefer repo exploration over guesses. When API accuracy matters, use official docs or a documentation lookup tool available in the host environment.
2. **Ask one question at a time.** Wait for feedback before the next question.
3. For each question, include:
   - Why it matters.
   - A recommended answer with short rationale.
4. Continue until decisions are explicit and internally consistent.

Do not spawn parallel agents or task runners unless the host environment already supports them and a multi-area probe clearly helps; prefer direct reads and searches.

## Domain awareness

Look for existing documentation during exploration:
- `CONTEXT.md` (glossary)
- `CONTEXT-MAP.md` (multi-context repos)
- `docs/adr/`
- Project agent guides (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/`, etc.) when present

### File structure

Typical single-context layout:

```
/
  CONTEXT.md
  docs/adr/
  src/
```

If `CONTEXT-MAP.md` exists at the root, multiple contexts exist and the map points to each `CONTEXT.md` and its ADRs. Formats: [references/CONTEXT-FORMAT.md](./references/CONTEXT-FORMAT.md), [references/ADR-FORMAT.md](./references/ADR-FORMAT.md).

### Stack annex - glossary and ADR cues

Keep `CONTEXT.md` glossary-only (no implementation detail). Use stack cues only to sharpen terms and spot irreversible choices:

- **Node / web**: routes, resources, auth/session vocabulary; env-specific behaviour; API versioning terms. ADR cues: SSR vs SPA boundaries, caching strategy, deployment topology when hard to reverse.
- **Python**: package boundaries, entrypoints, import graphs as vocabulary ("job", "worker", "pipeline"). ADR cues: sync vs async architecture, persistence layer, packaging/deploy shape when costly to unwind.
- **Xcode / iOS**: targets vs modules vs SPM products; scenes/coordinators vs god `View`; capability names. ADR cues: SPM vs Xcode-native deps, concurrency model (`async` / `MainActor`), persistence or transport choices that bind the app.

## During the session

### Challenge against the glossary

When a user term conflicts with existing language in `CONTEXT.md`, call it out and reconcile.

### Sharpen fuzzy language

When a term is vague or overloaded, propose a precise canonical term tied to domain vocabulary.

### Discuss concrete scenarios

Stress-test relationships with edge-case scenarios that force clear boundaries.

### Cross-reference with code

When the user states how something works, check whether the code agrees. Surface contradictions and resolve them before proceeding.

### Update CONTEXT.md inline

When a term is resolved and Doc creation allows it, update `CONTEXT.md` immediately - do not batch. Follow [references/CONTEXT-FORMAT.md](./references/CONTEXT-FORMAT.md).

### Offer ADRs sparingly

Offer an ADR only when all three are true:
1. Hard to reverse.
2. Surprising without context.
3. Result of a real trade-off.

Use [references/ADR-FORMAT.md](./references/ADR-FORMAT.md). If any condition is missing, skip the ADR.

## Doc creation

Only create or edit `CONTEXT.md` / ADRs when:
- The repo already uses them (or a clear local equivalent), **or**
- The user explicitly asks to update docs.

If neither is true, keep settled terms in the session status output and note that docs were not written. Do not invent a documentation convention mid-grill.

## Output contract

At each step, report:
- **Current Q**: the question.
- **Recommendation**: preferred answer and why.
- **Status**: `resolved` or `open` for that decision.

At session end, report:
- **Resolved**: terms and decisions locked.
- **Open**: remaining decisions and blockers.
- **Next**: next question, or the first implementation step once grilling ends.
