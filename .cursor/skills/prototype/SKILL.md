---
name: prototype
description: Builds a disposable runnable experiment that answers one design or logic question before production work, then cleans up. Use when prototyping or exploring a few design options.
---

# Prototype

A prototype is throwaway code that answers one question. The question decides
the shape: UI-shaped ("what should this look like") or logic-shaped ("does
this state model / data shape hold up").

## Ground rules (apply to every prototype)

1. **State the question first.** One sentence, at the top of the prototype
   file or in your response, before writing code. A prototype that answers the
   wrong question is pure waste.
2. **Throwaway from day one.** Name files and code so it is obviously
   disposable (`prototype`, `PROTOTYPE`, a scratch route, a debug-only
   target).
3. **One command to run.** Use whatever the host project already uses to run
   code; do not add a new package manager, runtime, or task runner just for
   this.
4. **In-memory by default.** No real database or persistent store unless the
   question is specifically about persistence; then use an obviously-scratch
   store.
5. **No live side effects.** Never mutate production systems, send real
   payments, control physical or hardware systems, or send real external
   communications (email, SMS, webhooks) from a prototype. Stub or mock any
   such calls.
6. **Skip polish.** No tests, minimal error handling, no abstractions beyond
   what keeps it runnable.
7. **Surface state.** After every action or variant switch, show the full
   relevant state so the answer is visible, not inferred.
8. **Clean up when done.** Once the question is answered, fold the winning
   code into the real codebase (rewritten to production standard) and delete
   the rest. Do not leave prototype code or scratch routes lying around.

## Pick a branch

Identify which question is being answered, from the request or surrounding
code:

- **"What should this look like?"** -> UI-shaped. Follow
  [references/UI.md](references/UI.md).
- **"Does this logic / state model / data shape hold up?"** -> Logic-shaped.
  Follow [references/LOGIC.md](references/LOGIC.md).

If ambiguous, default to what surrounding code suggests (a UI component or
page -> UI-shaped; a module, service, or data model -> logic-shaped) and state
the assumption up front.

## When done

The answer is the only thing worth keeping. Say what was learned and which
variant (or which pieces of which variants) won, in your response or the
commit message that lands the real change. Do not create a separate notes
file unless the user asks for one.
