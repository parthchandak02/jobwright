# Frontend Polish Audit Checklist

Use this checklist after scanning peers, tokens, and shared primitives.

## Structure and primitives

- Does the screen follow the project's established page shell, sections, cards,
  forms, tables, or action patterns?
- Is a shared primitive available before a new local component is added?
- Is the change correctly scoped to a screen, shared primitive, or theme token?
- Does the layout preserve the product's intended information density?

## Tokens and visual language

- Use project design tokens or theme values for color, spacing, typography,
  radius, elevation, and motion.
- Avoid new hardcoded colors and duplicated spacing literals.
- Keep typography hierarchy coherent with peer screens.
- Avoid a new visual style that competes with the existing design system.

## Controls and state

- Preserve action names, request behavior, validation, permissions, and gating.
- Keep status colors, badges, and icons semantically consistent.
- Make hover, focus-visible, active, disabled, loading, success, error, and
  empty states clear.
- Use native or shared accessible controls rather than hand-rolled substitutes.

## Accessibility and responsiveness

- Keyboard navigation reaches and visibly identifies every interactive control.
- Labels, descriptions, and error messages remain available to assistive
  technology.
- Touch targets, contrast, and text scaling meet project conventions.
- Narrow layouts retain hierarchy and avoid horizontal overflow.

## CSS and implementation hygiene

- Prefer scoped styles and avoid broad selectors with cross-screen effects.
- Reuse tokens instead of creating theme-like local constants.
- Remove dead styles only when their ownership is clear.
- Do not introduce no-op wrappers, props, or abstractions.

## Anti-slop guardrails

- No decorative hero treatment, novelty layout, or excessive whitespace unless
  product direction calls for it.
- No heavy animation, scroll effects, or motion that slows work.
- No wholesale framework, font, or component-library replacement as a polish
  patch.
- No visual change that obscures workflows, data density, or familiar labels.
