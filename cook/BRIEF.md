# Brief: jobwright dashboard UI polish

Target: Make the jobwright Kanban dashboard look and feel like a finished, polished job-search assistant (design v2 calm and refined). Stack: React + Vite + Tailwind v2 tokens.

Size: Light. Time cap: 2h hard. Started: 2026-11-15 03:05 UTC.

References: Worker collected R01 to R06 from live job-search and productivity products (local `cook/refs/`, gitignored). Same quality, own style (not layout clone).

Shots: S01 board `/` | S02 job drawer `/jobs/{hero}` | S03 review `/review` | S04 settings `/profile?tab=about` | S05 match quality `/quality`. Viewports 390x844 and 1440x900, light and dark.

Bar (1 to 10, target 9 each): layout 9 | type 9 | color 9 | components 9 | polish 9 | motion 9.

Calibration offset: none yet.

Rules: Cook default slop ban list. Project overrides win: [docs/DESIGN.md](../docs/DESIGN.md), [frontend-tasteful](../.cursor/skills/frontend-tasteful/SKILL.md), no landing-page taste skills.

Time: cap 2h from 2026-11-15 03:05 UTC.

Deliverable: working build, passing CI checks, PR with scores and stills paths.

Permissions: commit each round yes, push yes to `cook/ui-polish`, deploy no, publish no third-party refs.

Judges: 2 fresh subagents per round when available; else logged self-score (never decisive).

Gate: Parth not watching per round (no ping). Stills in `cook/stills/`, ledger in `cook/ROUNDS.md`.

Dev: `scripts/cook_demo_server.py` on 127.0.0.1:8831, fixture API from `readme_images.py`.

## Decisions

- 2026-11-15 Intake pre-answered per factory Cook task (defaults), because unattended Worker run.
- 2026-11-15 Size Light cap 2h, 2 critics per round, because task brief.
- 2026-11-15 References collected from Huntr, Teal, Linear app chrome, Notion product, Wellfound browse, own style, because no refs given.
- 2026-11-15 Demo server reuses readme_images fixtures, because no prod users data in worktree.
- 2026-11-15 Gate skip ping Parth each round, because brief says Orchestra gate off.

Parth's words: "Make the UI look and feel like a finished, polished product. It is Parth's job search assistant."