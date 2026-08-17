---
name: frontend-tasteful
description: Audits and polishes frontend UI for token discipline and anti-slop while preserving density, shared primitives, and behavior. Use for visual consistency or UI polish.
---

# Frontend Tasteful

Use this skill to improve frontend visual quality without changing behavior,
contracts, accessibility, or the product's established visual language.

This is not a marketing redesign skill. Preserve information density and
operator or workflow efficiency where the product needs it.

## Read first

Identify the project's:

1. Design tokens and theme definitions.
2. Shared component library and route-level primitives.
3. Existing peer screens that solve comparable layout, state, and interaction
   problems.
4. Accessibility, responsive, and frontend contribution conventions.

The project supplies its own paths for its design tokens and shared component
library. Prefer those sources over generic UI patterns.

## Workflow

### 1. Scan

Inventory before editing:

- The touched screen and comparable peers.
- Shared primitives already used in the area.
- Existing tokens for color, spacing, typography, radius, elevation, and motion.
- Whether the need is screen-level, shared-component-level, or theme-level.
- User-visible states: loading, empty, error, disabled, hover, focus, active,
  success, and responsive layouts.

### 2. Diagnose

Use [references/audit-checklist.md](references/audit-checklist.md). Identify the
highest-risk regressions first, especially action gating, status meaning,
keyboard behavior, dense scanning, and user-facing terminology.

State the visual and behavioral constraints before changing code.

### 3. Make the smallest fix

- Extend an existing primitive or token before adding a one-off style.
- Prefer a small local correction to broad restyling.
- Keep labels, data meaning, control semantics, and request behavior unchanged.
- Use subtle, short motion only when it clarifies state or continuity.
- Remove dead styles or duplicated ad-hoc values when safely in the edited area.

Do not replace frameworks, swap fonts, add decorative animation, or expand
whitespace substantially without explicit product direction.

### 4. Pre-flight

Before finishing, confirm:

- Tokens and shared primitives are used where appropriate.
- No hardcoded color, spacing, typography, or interaction drift was introduced.
- Focus-visible behavior is clear for interactive controls.
- Keyboard, screen-reader, loading, error, empty, disabled, and responsive
  behavior still work.
- Dense screens remain fast to scan.
- UI changes did not alter business behavior, data contracts, or action gating.

## Output

Report what changed, the user-visible benefit, what behavior was deliberately
preserved, and any follow-up debt that should remain separate.
