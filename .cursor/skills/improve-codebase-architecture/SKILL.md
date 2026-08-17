---
name: improve-codebase-architecture
description: Finds architectural friction and deepens modules through small interfaces, real seams, locality, and testability. Use before large refactors or when pass-through files pile up.
---

# Improve Codebase Architecture

Read this skill as a readonly architecture review unless the user explicitly
asks for implementation. Its goal is to find where a codebase is hard to
change, understand, or verify, then present candidates before proposing a
solution.

## Read first

1. Read the project's architecture map, glossary, decision records, and
   contributor instructions if they exist.
2. Identify the primary stack and its natural seams, such as request handling,
   persistence, processes, UI state, or platform targets.
3. Read nearby modules and their tests before judging their shape.

If breadth would help, use optional parallel readonly explores. They are a
means to gather evidence, not a required workflow.

## Shared vocabulary

Use the terms in [references/LANGUAGE.md](references/LANGUAGE.md) consistently:
Module, Interface, Implementation, Seam, Adapter, Depth, Leverage, and
Locality. Avoid substituting loosely related terms when reviewing architecture.

The key tests are:

- Apply the deletion test to suspected pass-throughs.
- Treat the interface as the test surface.
- Do not add an adapter seam until variation makes it real.

## Review process

### 1. Explore

Map friction in the requested area:

- Where does one concept require hopping among many small files?
- Which Modules are shallow, with an Interface almost as complex as their
  Implementation?
- Which Seams leak implementation details across callers?
- Where is behavior difficult to test through its Interface?
- Where are pure helpers extracted only for tests while the important behavior
  remains scattered among callers?

Use [references/DEEPENING.md](references/DEEPENING.md) to classify dependencies
and evaluate seams.

### 2. Present candidates

Before proposing an interface or implementation, give a numbered list of
candidates. For each, include:

1. Files or Modules involved.
2. The observed friction.
3. A plain-language direction for improvement.
4. Expected Leverage, Locality, and testability gains.
5. Relevant dependency category or decision-record conflict.

Ask which candidate to explore. Do not treat candidate discovery as approval for
a large refactor.

### 3. Grill the chosen candidate

For terminology, scope, or contract ambiguity, use the project's
grill-with-docs process before a large refactor. Resolve one decision at a
time:

- What behavior belongs behind the Interface?
- Where should the Seam live?
- Which invariants, errors, ordering rules, and performance expectations do
  callers need to know?
- What tests survive an internal refactor?
- Does an existing decision record constrain the choice?

Update the project glossary or decision records only when the project already
uses them and a durable decision has been made.

### 4. Compare interfaces when needed

When the user wants interface alternatives, follow
[references/INTERFACE-DESIGN.md](references/INTERFACE-DESIGN.md). Present
multiple materially different designs, compare them by Depth, Locality, and
Seam placement, then recommend one.

## Implementation handoff

After the user selects a direction, state the intended Interface, adapters,
tests, and files in scope. Keep the diff small. Replace obsolete shallow tests
with behavior tests through the new Interface rather than layering both sets.
