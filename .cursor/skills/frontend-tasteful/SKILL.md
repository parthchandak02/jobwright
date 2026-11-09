---
name: frontend-tasteful
description: Build and polish the jobwright dashboard UI. Use when editing frontend/, adding or changing dashboard screens, components, tokens, shadcn, job cards, sidebar, drawer, profile, admin, quality, welcome, tables, dialogs, or visual consistency. Not for landing pages, marketing redesigns, or Python/pipeline work.
---

# Frontend Tasteful (jobwright dashboard)

Design v2, "calm & refined" (Linear/Notion-like): soft warm-grey neutrals, one indigo accent, crisp system type, subtle depth, generous whitespace on settings-style pages. Users are non-technical job seekers; phone (390px) and desktop have equal priority. Spec and rationale: [docs/agents/design-v2-audit.md](../../../docs/agents/design-v2-audit.md) section 2.

Two densities:

- **Settings-style pages** (Welcome, Settings at `/profile`, Admin, Match quality): open whitespace, 720px (`form`) or 960px (`wide`) column, `PageHeader` + `SectionHeader` + `FormField` with visible hints.
- **Board, table and job drawer**: dense, on v2 since WP6 (catalog "Board and drawer").

**Do not** load `design-taste-frontend` / leonxlnx taste-skill / Three Dials for this product. Do not revert v2 tokens to the old IBM Plex / glass / 30% lane tint look.

## Read first

0. [docs/DESIGN.md](../../../docs/DESIGN.md): the principles (show it, one primary, help behind ⓘ, one meaning per signal) and dated lessons.
1. [references/catalog.md](references/catalog.md) (must-reuse primitives, token families, rules).
2. Peer screens that solve the same problem.
3. `frontend/src/index.css` and `frontend/src/components/ui/` for the exact token or primitive you will extend.
4. Graphify, when the graph exists: `graphify query` / `explain` the nearest primitive before inventing a new one.

## Rules (v2)

- **Primitives first:** new UI must be built from the catalog primitives (`Page`/`PageHeader`, `SectionHeader`, `FormField`, `SaveStatus`, `ActionBar`, `EmptyState`, `ValueChip`/`ChipInput`, `ui/*`). No page-local headers, save indicators, chips, dialogs or confirm flows when a primitive exists.
- **Colour:** one accent (`--primary`, indigo 262). Neutrals from `--background` / `--surface` / `--surface-muted` / `--border` / `--border-strong`. Stage colours are for dots, lane header text and thin bars, never large fills (lane card tint is 7%). Tints use the `tone-tint` recipe (Chip `tone`, Badge variants), never ad-hoc `color-mix` percentages. Form chips are neutral; only semantic negatives (blocked titles, dealbreakers, "locations that don't") use `--destructive`. No new hex/oklch outside `index.css`.
- **Type:** system font stack (`--font-sans`, no font CDN). Use the scale utilities `text-display|title|heading|subheading|body|label|caption|micro`. Nothing below 12px (`text-micro`); no `text-[10px]` / `text-[11px]`. Uppercase only for board lane headers; the `showStage` label on mixed-stage cards and sidebar stage rows are Title Case. `tabular-nums` on numbers, times, scores.
- **Spacing:** `space-y-field` (20px) between fields; `mt-section` / `SectionHeader` (40px desktop, 32px phone) between sections; `px-page-x`, `pt-page-top` for page padding; `max-w-form` / `max-w-wide` columns.
- **Radius:** `rounded-md` (8px) controls and buttons, `rounded-lg` (12px) cards, lists and dialogs, `rounded-popover` (10px) menus, `rounded-full` chips.
- **Elevation:** hairline border by default; `shadow-e1` for popovers, menus, sticky bars, hovered cards; `shadow-e2` for dialogs and sheets. No backdrop blur except the md+ sticky board header.
- **Focus:** global `:focus-visible` 2px `--ring` outline, offset 2px (text fields use offset 0). Don't add `outline-none` without a replacement.
- **Motion:** `ease-out` with `duration-(--dur-1|2|3)` (120/180/240ms). No hover lift. Reduced motion is honoured globally.
- **Touch:** every control is at least 44px on phone. Button sizes already do this (`sm` = 36px desktop / 44px phone); `xs` and `icon-sm` add a `touch-target` hit area. Use `touch-target` (plus `relative`) on any custom small control.
- **Buttons:** one `primary` per view. `secondary` (= old `outline`) for ordinary actions, `ghost` for tertiary/navigation, `destructive` only inside confirm dialogs, `destructive-ghost` for list-level Remove (put it in a `DropdownMenu`), `ai` (accent tint + Sparkles) for AI actions. Real-world side effects (send WhatsApp, run search) are `secondary` with an icon and a confirm.
- **Save model:** autosave (`useAutosave`) + one `SaveStatus` in the section header; explicit-save forms (Match rules) use a sticky `ActionBar` shown only when dirty.
- **Help text:** explanations go behind the ⓘ (`help` on `PageHeader`, `SectionHeader`, `FormField`); a visible `hint` only for a few words needed to act ("Per year"). Placeholders are instructions ("Add a job title"), never example values.
- **Structure:** settings and admin use lists (one surface, divided rows). No bordered box inside a bordered box; nested groups use `bg-surface-muted` without a border.
- **Phone navigation:** the bottom tab bar (`PhoneTabBar`, fed by `SHELL_LINKS`) is the navigation on every page under 768px. A new top-level page gets one `SHELL_LINKS` line. Don't add page-local back-to-menu buttons; don't cover the bar (it hides itself while the job drawer is open).
- **Real chats:** WhatsApp chats are admin-managed. Non-admins see `ConnectedChat` (read-only); only admins get `WhatsAppChatPicker`. Onboarding never offers a test send (`hideTest`).

## Workflow

1. **Scan:** touched screen + peers; the catalog primitive that covers it; the token family; states (loading, empty, error, disabled, hover, focus, active); 1440 and 390, light and dark.
2. **Diagnose** with [references/audit-checklist.md](references/audit-checklist.md). Highest risk first: action gating, status meaning, keyboard, touch targets, user-facing terms.
3. **Smallest change:** extend a primitive or token. Keep labels, API contracts, gating and accessibility.
4. **Promote (same PR, only when needed):** update [references/catalog.md](references/catalog.md) when you add or rename a reusable component or token family, or change a convention. Not for copy tweaks or page-local layout.
5. **Pre-flight:** `cd frontend && pnpm run build`; `rg "#[0-9a-f]{3,6}|oklch\(" frontend/src --glob '!index.css'` returns nothing new; keyboard pass with visible focus; 390px pass (no horizontal scroll, 44px targets); dark mode pass.

## Output

What changed, user-visible benefit, what behaviour was preserved, whether the catalog was promoted, leftover drift to keep separate.
