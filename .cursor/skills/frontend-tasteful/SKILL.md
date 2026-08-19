---
name: frontend-tasteful
description: Build and polish the jobwright Kanban dashboard UI. Use when editing frontend/, adding or changing dashboard screens, components, tokens, shadcn, job cards, sidebar, drawer, profile, tables, dialogs, or visual consistency. Not for landing pages, marketing redesigns, or Python/pipeline work.
---

# Frontend Tasteful (jobwright dashboard)

Dense operator UI: Kanban board, table, job drawer, profile. Visual language is already set (IBM Plex Sans, glass surfaces, stage/lane tokens). This is not a marketing redesign skill.

**Do not** load `design-taste-frontend` / leonxlnx taste-skill / Three Dials for this product.

## Read first

1. [references/catalog.md](references/catalog.md) (must-reuse primitives, token families, little things).
2. Peer screens that solve the same problem (sidebar vs drawer vs card vs table vs profile vs dialog).
3. `frontend/src/index.css` and `frontend/src/components/ui/` for the exact token or primitive you will extend.
4. Graphify, when the graph exists: `graphify query` / `explain` the nearest primitive before inventing a new one.

## Workflow

### 1. Scan

- Touched screen + comparable peers.
- Catalog primitive that already covers this.
- Token family (stage, glass, job-card, sidebar, linkedin, tailor) vs a new hardcoded value.
- Scope: screen, shared component, or theme token.
- States: loading, empty, error, disabled, hover, focus, active.

### 2. Diagnose

Use [references/audit-checklist.md](references/audit-checklist.md). Highest-risk first: action gating, status meaning, keyboard, dense scanning, user-facing terms.

### 3. Smallest change

- Extend an existing primitive or token.
- Keep labels, contracts, gating, and accessibility unchanged.
- Subtle motion only when it clarifies state (`--ease-glass`, respect `prefers-reduced-motion`).
- Do not swap fonts, add heroes, or open up whitespace.

### 4. Promote (same PR, only when needed)

Update [references/catalog.md](references/catalog.md) when you:

- Add or rename a **reusable** domain component (not a page-local helper).
- Add a **reusable** CSS token or class family.
- Change a convention (Chip vs Badge, stage casing, button variants).

Do not rewrite the catalog for copy tweaks, bugfixes, or one-off page layout.

### 5. Pre-flight

- Catalog primitive used where it fits; no new `text-[10px]` / `text-[11px]` / duplicated lane colors.
- Focus-visible on interactive controls.
- Keyboard, loading, empty, error, disabled, and narrow layouts still work.
- Density preserved. Behavior and gating unchanged.

## Output

What changed, user-visible benefit, what behavior was preserved, whether the catalog was promoted, leftover drift to keep separate.
