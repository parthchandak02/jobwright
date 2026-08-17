---
name: research
description: Produces current, source-backed technical guidance: official docs first, implementation patterns, conflict synthesis, root-cause analysis. Use before non-trivial fixes or new features.
---

# Research

## Purpose

Build source-backed guidance before making a recommendation or writing
non-trivial code. Ground claims in current sources rather than memory,
especially for version-sensitive facts, APIs, and error messages.

## When to apply

Apply when the request involves:

- researching a topic or comparing approaches
- checking best practices before implementing
- grounding a plan in current documentation
- investigating an error or unexpected behavior

## Tooling (soft-gate)

Use whatever research tools are available in the current environment:

- If dedicated research/search tools are available (for example a
  documentation lookup tool, a web-search tool, or a synthesis/reasoning
  tool), use them.
- If not, use whatever web fetch or web search capability is available, and
  read official documentation directly.
- Never fail or refuse the skill because a specific tool is missing; fall
  back to the next-best available method and say which sources were
  actually used.

## Required workflow

1. **Build a context packet before searching.** Capture, and mark "unknown"
   if genuinely unknown:
   - topic and desired outcome
   - stack, exact versions of relevant dependencies
   - environment (OS, runtime, deployment target)
   - constraints (performance, security, compatibility, simplicity)
   - exact error text / stack trace / repro steps, if debugging
   - what has already been tried
   - recency requirement (for example "as of `<current year>`")
   - desired output shape (decision, comparison, migration path, code
     pattern, checklist)

   Ask a focused clarifying question only if a missing field would change
   the conclusion.

2. **Official docs first.** Find and read the authoritative documentation for
   the library, framework, or API in question: API reference, migration
   guide, or release notes tied to the request. Prefer the exact version in
   use over the latest if they differ.

3. **Implementation-pattern discovery.** Search broadly for how others have
   solved this: blog posts, issue trackers, community discussions, code
   examples. Collect a handful of credible, reasonably recent sources rather
   than the first result.

4. **Independent synthesis when sources conflict.** When docs, examples, and
   community advice disagree, cross-check the specific disputed claim against
   another independent source before deciding. Do not silently pick one.

5. **Resolve conflicts by priority:**
   1. Official docs and release notes
   2. Recent primary sources (maintainers, changelogs)
   3. Secondary summaries (blog posts, forum answers)

   State the conflict explicitly if it is material, then commit to one
   recommendation.

## Error investigation mode

When debugging:

- Identify the likely root cause before proposing a change; do not patch a
  symptom while the underlying cause is still unclear.
- Validate the fix direction against official docs plus at least one
  independent source.
- Recommend the simplest fix that addresses the root cause, not the first
  thing that makes the symptom disappear.
- Include the full error context (message, stack trace excerpt, repro steps,
  expected vs. observed) in every query.

## Output format

1. **Recommendation** - one clear approach.
2. **Why this approach** - 2-4 concise reasons, focused on robustness and
   simplicity.
3. **Implementation notes** - practical steps, version caveats, constraints.
4. **Risks and checks** - failure modes and how to validate quickly.
5. **Sources** - links or citations for any non-obvious, version-sensitive,
   or disputed claim.

## Quality gate

Before finalizing:

- At least one official documentation source was consulted (not just
  secondary sources).
- Version-specific guidance matches the versions actually in use, and is not
  based on a deprecated API.
- The recommendation is explicit and actionable, not a list of options with
  no pick.
- Any real conflict between sources was surfaced and resolved, not silently
  dropped.
