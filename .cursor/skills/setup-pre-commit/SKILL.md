---
name: setup-pre-commit
description: Adds stack-appropriate commit-time checks (Husky/lint-staged, pre-commit/Ruff, or Swift lint hooks) while preserving existing formatter, lint, and CI conventions. Use when adding pre-commit hooks.
---

# Setup Pre-Commit Hooks

## Detect primary stack

| Stack | Signals |
|-------|---------|
| Node / web | `package.json` at the repo root or chosen package root |
| Python | `pyproject.toml`, `requirements.txt`, a dominant `.py` tree |
| Swift / iOS | `*.xcodeproj`, `*.xcworkspace`, an app-level `Package.swift` |

In a monorepo with multiple stacks, scope to the subdirectory the user cares
about, or set up hooks per leaf project. Do not install a Node toolchain into
a repo that has none just to get Husky, unless the user explicitly wants
that.

## Preserve what already exists

Before adding anything, check for an existing formatter, linter, hook
manager, or CI check that already does the job (`.prettierrc`,
`.eslintrc*`, `ruff.toml` / `[tool.ruff]` in `pyproject.toml`,
`.swiftlint.yml`, `.swiftformat`, `.pre-commit-config.yaml`, `.husky/`, CI
workflow files). Extend what is there instead of adding a second, competing
tool. Only fill in the pieces that are genuinely missing.

## Node - Husky + lint-staged (+ formatter)

1. **Detect the package manager**: `package-lock.json` -> npm,
   `pnpm-lock.yaml` -> pnpm, `yarn.lock` -> yarn, `bun.lock`/`bun.lockb` ->
   bun. Default to npm if none is present.
2. **Reuse the existing formatter** if one is configured (Prettier, Biome,
   etc.); only add Prettier if nothing is configured.
3. Install as dev dependencies: `husky`, `lint-staged`, and the formatter if
   it needs adding.
4. Initialize Husky (current major version's init command, for example
   `npx husky init`) - creates a hooks directory and a `prepare` script.
5. Add a pre-commit hook that runs `lint-staged`, then the project's
   typecheck and test scripts **if they exist** as `package.json` scripts.
   Do not invent scripts that are not there.
6. Add or extend a `lint-staged` config that runs the formatter (and linter,
   if not already run elsewhere) on staged files only.
7. **Verify**: make a trivial staged change and confirm the hook actually
   runs and blocks/passes as expected before declaring done.

## Python - `pre-commit` framework + Ruff

1. Install `pre-commit` using the project's existing tool (for example
   `uv tool install pre-commit`, `pip install pre-commit`, or via a
   dev-dependency group if the project manages tooling that way).
2. Create or extend `.pre-commit-config.yaml` with a Ruff lint + format hook.
   **Look up the current stable `rev` for the Ruff pre-commit hook at install
   time** (check the hook repo's releases/tags) rather than hardcoding a
   version here, since a pinned version in a skill file goes stale.
3. Add `mypy` (or another type checker) only if the project already uses it
   and it runs fast enough to be a commit-time gate; do not introduce type
   checking that was not already a project convention.
4. Install the git hook: `pre-commit install`.
5. **Verify**: run `pre-commit run --all-files` and confirm it passes (or
   that failures are pre-existing issues the user is aware of), before
   declaring done.

## Swift / iOS

Many Swift/iOS repos do not use Node-based hook managers. Pick one, matching
what the team already tolerates:

- **Repo-level `pre-commit`** - install the Python `pre-commit` tool at the
  repo root (fine even in a Swift-primary repo) and add community hooks for
  SwiftLint / SwiftFormat, pointed at existing config files
  (`.swiftlint.yml`, `.swiftformat`).
- **Xcode Run Script build phase** - add a Run Script phase early in the
  target's build that invokes `swiftlint` / `swiftformat` via
  `${PROJECT_DIR}`; document the one-time tool install for contributors (for
  example via the project's package manager of choice).
- **CI-only** - when local hooks are undesirable, mirror the same checks in
  CI and document that commit-time discipline is enforced there instead.

Never force a Node/Husky setup into a Swift-only repo without an existing
Node toolchain.

## Before declaring done

- [ ] The right pieces exist for the detected stack (hook manager, config,
      lint/format command).
- [ ] Nothing that already existed was duplicated or overridden without
      reason.
- [ ] The hook was actually run once (on a real or sample change) and
      behaved as expected.
- [ ] Any version/rev used was looked up at install time, not copied from
      stale examples.
