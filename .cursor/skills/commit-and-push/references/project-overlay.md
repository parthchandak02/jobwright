# Project Overlay Template

Fill this in once per project (or point the agent at an existing equivalent doc)
so `commit-and-push` does not have to re-derive project specifics every time.
Copy this file into the project (for example as `.cursor/commit-overlay.md`) and
fill in the blanks.

## Doc-sync matrix

| File | Update when |
|------|-------------|
| `AGENTS.md` / `CLAUDE.md` | ... |
| `README.md` | ... |
| `CONTEXT.md` | ... |
| `.cursor/rules/*.mdc` or equivalent | ... |
| (add project-specific docs here) | ... |

## Quality gate

- Command: `...`
- Run when: `...` (for example, "any change under `src/`")
- Where the result is tracked (if anywhere): `...`

## Commit clusters (recommended order)

| Order | Cluster | Paths |
|-------|---------|-------|
| 1 | docs / rules | ... |
| 2 | backend | ... |
| 3 | frontend | ... |
| 4 | scripts / tooling | ... |

## Message style

- Prefix convention: `...` (for example `feat(scope):`, `fix:`, or plain sentences)
- Message tool: plain `git commit`, or a project-specific commit-message helper

## Path scoping notes

If this project lives as a subtree of a larger monorepo, note the scoping
prefix here so staging commands do not silently match unrelated files, or fail
with "did not match any files" when a bare pathspec is used from the monorepo
root.
