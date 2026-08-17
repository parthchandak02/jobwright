---
name: handoff
description: Write a lean handoff under TMPDIR so a fresh agent can continue: goal, state, next steps, landmines, suggested skills. Point at files; redact secrets.
---

# Handoff

Compact the current conversation into a lean handoff so a fresh agent can continue with minimal ramp-up.

## Trigger cues

Use when ending a session, switching agents or machines, before a context reset, or when the user asks for a handoff. If the user names what the next session should focus on, tailor the doc to that.

## Write location

Save under the OS temp directory, never the workspace (unless the user explicitly asks for a repo path).

```bash
mktemp -t handoff-XXXXXX.md
```

Write the document to the path `mktemp` prints, then print that absolute path to the user.

If `mktemp` is unavailable or blocked, ask the user for a path, or use `$TMPDIR` / `/tmp` with a unique name such as `handoff-<timestamp>.md`. Do not commit scratch handoffs to the repo without consent.

Optional section labels and stack bullets: [references/RUNTIME-TEMPLATE.md](./references/RUNTIME-TEMPLATE.md).

## Structure

Keep it lean. A handoff longer than the work it describes is failing its job.

1. **Goal** - one line: what the session was trying to achieve.
2. **State** - done / in progress / blocked. Include stack-specific run state when relevant (below). Point at files, branches, PRs, tickets by path or URL - do not paste large code.
3. **Next steps** - ordered, concrete, first action first.
4. **Landmines** - decisions made and why; dead ends already ruled out.
5. **Suggested skills** - sibling skills the next agent should consider, by name:
   - `grill-with-docs` - plan / terminology still fuzzy
   - `prototype` - need to try a design before committing
   - `improve-codebase-architecture` - deepening or seam work
   - `research` - version-sensitive or contested facts
   - `advisor` - costly fork, stuck, or need a second opinion
   - `ponytail` - risk of over-building; force the minimal path

Only list skills that fit the next work. Omit the rest.

## Reference, do not duplicate

Point at artifacts that already hold the truth:

- Code: file paths (and line ranges where useful), not pasted bodies.
- Docs: `CONTEXT.md`, ADRs, `AGENTS.md`, README, issue/PR URLs.
- Git: branch name, short `git status` summary, unpushed commits by hash/subject.
- Open PR / ticket by URL or key.

## Stack-specific run state

Infer the primary stack from the workspace; if several apply, prefer what the next session will focus on.

### Node / web

- Package manager and key scripts (`dev`, `build`, `test`, `typecheck`).
- Node/runtime version if constrained.
- Env files or config touched (names only; never values that look like secrets).
- Dev server URL or proxy notes.

### Python

- Interpreter / venv tool (`uv`, `poetry`, `pip`, `.venv` path).
- Entry command for the app or tests.
- Important env var *names* or `pyproject` tool sections.

### Xcode / iOS

- Project/workspace path (`.xcodeproj` / `.xcworkspace`).
- Scheme and configuration (Debug/Release).
- Destination (simulator model/OS or device).
- Codesigning/provisioning symptoms if any.
- Last successful or failed `xcodebuild` / test command if known.
- SPM notes (local packages, binary targets) when relevant.

## Guardrails

- **Redact secrets**: tokens, passwords, API keys, private key paths, connection strings with credentials. Prefer env var *names* over values.
- ASCII only. Use hyphen (`-`), not em or en dashes.
- Do not invent status you did not observe; mark unknowns as unknown.
