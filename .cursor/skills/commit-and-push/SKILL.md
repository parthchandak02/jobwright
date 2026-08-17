---
name: commit-and-push
description: Lands changes: syncs stale docs, runs the project's quality gate, splits work into logical commit clusters, pushes only when asked. Use when the user asks to commit or push changes.
---

# Commit and Push

Generic end-to-end workflow for landing changes: probe first, sync docs the diff makes stale, run whatever quality gate the project defines, split into logical commit clusters, and push only when explicitly asked.

## Trigger cues

Use when the user asks to commit, land changes, "commit this", or commit and push. Push is not automatic: only push when the request includes push, or says "commit and push" / "land this". If it is ambiguous whether to push, ask once.

## Workflow

```
Phase 0  Probe          git status, branch, diff (scope + intent)
Phase 1  Doc sync       update docs the diff makes stale
Phase 2  Quality gate   run the project's verify/test/lint if one exists
Phase 3  Commit         cluster staging, one concern per commit
Phase 4  Push           only when the user asked
Phase 5  Next steps     optional follow-ups, review only
```

## Phase 0: Probe

From the repo root:

```bash
git status --short
git branch -vv
git diff --stat
```

Confirm: not detached HEAD, a tracking remote exists if pushing is in scope, and the changes match what the user described. If work spans sessions, read any handoff notes or history the project already keeps for that purpose.

## Phase 1: Doc sync

Before the first commit, check whether the diff makes any project documentation stale. Common candidates:

- `AGENTS.md`, `CLAUDE.md`, or other agent-facing instructions
- `README.md`
- `CONTEXT.md` or a project glossary
- Rule files under `.cursor/rules/`, `.claude/rules/`, or similar
- Architecture decision records

If the project keeps its own doc-sync matrix (which files to update for which kind of change), follow it. Otherwise use [references/project-overlay.md](references/project-overlay.md) as a template, or reason directly: does this diff change a route, contract, config shape, workflow, or entry point that a doc describes? If so, update that doc in the same change set.

Do not invent a documentation convention the project does not already have. If nothing needs updating, say so and move on.

## Phase 2: Quality gate

Run whatever the project already defines as its pre-merge or pre-commit check: a `verify` script, `lint`/`test`/`build` commands, or a `pre-commit` hook. Look for these in `package.json` scripts, a `Makefile`, `scripts/`, or contributor docs.

- Do not invent a gate the project does not have.
- Fix failures before committing, or get explicit user sign-off to commit anyway.
- If the gate output includes something like a test count or "last verified" note tracked elsewhere, refresh it as part of the commit.

## Phase 3: Clustered commits

### Safety rules (hard)

- Only commit when the user asked.
- Never run `git config`.
- Never use `--force`, `--force-with-lease`, `--no-verify`, or history rewrites unless the user explicitly asks and understands the consequences.
- Never amend a commit unless the user explicitly requested amend, or the commit succeeded and a hook auto-modified files that need including - and only when that commit has not been pushed and was created in this session. If a commit fails or is rejected by a hook, fix the issue and create a **new** commit; never amend a failed commit.
- Never stage or commit secrets (`.env`, keys, credentials, tokens).
- Write commit messages via HEREDOC so multi-line messages format correctly:

```bash
git commit -m "$(cat <<'EOF'
<subject line>

<body, if any>
EOF
)"
```

### Grouping

Prefer one commit per concern. For a small change that is one concern, use one commit. For a larger pass, split into roughly 2-8 commits, in this order when applicable:

1. Docs / rules / config that other commits depend on being read correctly.
2. Backend / core logic.
3. Shared libraries or primitives.
4. Feature-level or UI code that consumes those primitives.
5. Scripts, tooling, CI.

Do not lump unrelated concerns into one commit (for example, a bug fix and an unrelated refactor). Stage explicitly (`git add -- <paths>`) rather than `git add -A` when the working tree has unrelated dirty files.

### Message style

Match the project's existing commit message convention (check `git log` for a prefix style such as `feat:`, `fix(scope):`, or plain sentences). Write the "why" in the body when it is not obvious from the subject line, not just the "what".

## Phase 4: Push

Push only when the user's request included pushing:

```bash
git push -u origin "$(git branch --show-current)"
```

If push fails (for example, diverged history), report the exact error and ask before force-pushing or rebasing.

## Phase 5: Next steps (optional)

After a successful commit or push, if the diff touched architecture or left known follow-up work, offer a short "Next steps" note in the response (not a new file): blockers, should-fix items, or open questions. Do not implement further unless asked.

## Output contract

Report:
1. **Doc sync**: files updated, or "none needed".
2. **Gate**: command run and result, or "no gate found".
3. **Commits**: subject line per commit (and cluster rationale if more than one).
4. **Push**: remote and branch, or why it was skipped.
5. **Remaining dirty state**: any `git status --short` lines left over.
