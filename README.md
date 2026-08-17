# jobwright

An autonomous, multi-stage job application pipeline. It discovers jobs across many boards, scores them against your resume with an LLM, tailors your resume and cover letter per job, and can optionally submit applications for you through a browser agent.

> **Fork.** jobwright is a fork of [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot), licensed under [AGPL-3.0](LICENSE). It adds pluggable Cursor Agent providers, portfolio-aware tailoring, multi-profile support, and Hermes cron scheduling. See [docs/UPSTREAM.md](docs/UPSTREAM.md) and the [ADRs](docs/adr/). The console command is still `applypilot` (upstream lineage).

---

## What it does

| Stage | Command | What happens |
|-------|---------|--------------|
| 1. Discover | `run discover` | Scrapes Indeed, Google Jobs, ZipRecruiter, Workday portals, and direct career sites |
| 2. Enrich | `run enrich` | Fetches the full job description (JSON-LD, CSS selectors, or LLM extraction) |
| 3. Score | `run score` | LLM rates each job 1-10 against your resume; low-fit jobs stop here |
| 3b. Portfolio | `run portfolio` | Picks the 4-5 most relevant projects from your profile per job |
| 4. Tailor | `run tailor` | Rewrites your resume per job, preserving facts (never fabricates) |
| 5. Cover letter | `run cover` | Writes a targeted cover letter per job |
| 6. Apply | `apply` | A browser agent fills forms, uploads documents, and submits (optional, gated) |

Stages 1-5 are fully automated and safe. Stage 6 (apply) is opt-in and dry-run by default.

---

## Requirements

| Component | Needed for | Notes |
|-----------|-----------|-------|
| Python 3.11+ | Everything | Core runtime |
| `GEMINI_API_KEY` | Stages 3-5 | Free tier is enough. Get one at [aistudio.google.com](https://aistudio.google.com) |
| Node.js 18+ | Stage 6 apply | Runs the Playwright MCP server |
| `CURSOR_API_KEY` | Stage 6 apply | Default agent provider (`cursor-sdk`) |
| Chrome/Chromium | Stage 6 apply | Auto-detected on most systems |

---

## Setup

```bash
git clone https://github.com/parthchandak02/jobwright.git
cd jobwright

pip install -e .
# python-jobspy pins an exact numpy version that breaks pip's resolver but works
# fine at runtime, so install it without deps and add its real runtime deps:
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex

playwright install chromium   # only needed for stage 6 apply
```

Then run the one-time setup wizard and verify your environment:

```bash
applypilot init      # collects resume, profile, preferences, and API keys
applypilot doctor    # shows what is installed and what is missing
```

### Configuration files (created by `applypilot init`)

Your data lives under `~/.applypilot/` (single user) or `~/.applypilot-users/<id>/` (multi-profile), never in the repo:

- **`profile.json`** - contact info, work authorization, compensation, experience, skills, and your `portfolio` projects. Start from [`profile.example.json`](profile.example.json).
- **`searches.yaml`** - your search queries, target titles, locations, and boards.
- **`.env`** - `GEMINI_API_KEY`, `LLM_MODEL`, and optional `CURSOR_API_KEY`.

Board and site definitions ship inside the package at `src/applypilot/config/` (`employers.yaml`, `sites.yaml`, `searches.example.yaml`).

---

## Find and tailor jobs (stages 1-5)

```bash
# Run the full prep pipeline in parallel, keeping only strong matches
applypilot run discover enrich score portfolio tailor cover -w 4 --min-score 7

applypilot status      # pipeline statistics
applypilot dashboard   # open the HTML results dashboard
```

If tailoring is flaky on the Gemini free tier, add `--validation lenient`.

---

## Apply for jobs (stage 6)

Stage 6 launches a browser agent that navigates the application form, fills your details, uploads the tailored resume and cover letter, answers screening questions, and submits.

**It is dry-run by default and never runs from cron automatically.**

```bash
export CURSOR_API_KEY=...

# Fill forms WITHOUT submitting (recommended first pass)
applypilot apply --dry-run --limit 1

# Submit for real, one job at a time
applypilot apply --url "https://boards.greenhouse.io/example/jobs/123"
```

Agent provider is selectable via `AGENT_PROVIDER`:

```bash
export AGENT_PROVIDER=cursor-sdk   # default: cursor-sdk Python package
export AGENT_PROVIDER=cursor-cli   # fallback: the `agent` CLI
export AGENT_PROVIDER=claude       # legacy upstream behavior
```

Safety: dry-run is the default, LinkedIn apply is blocked, live workers are capped at 1, and multi-profile users must be explicitly opted in (`apply_enabled`). See the [pp-job-apply skill](skills/pp-job-apply/SKILL.md) for the full confirmation-gated workflow.

---

## Scheduling and multi-profile (optional)

jobwright can run per-profile prep on a Hermes cron and deliver a digest to each user, with live apply gated behind an explicit `CONFIRM APPLY` reply:

```bash
./scripts/install_skills.sh      # install the pp-job-apply skill for Cursor + Hermes
./scripts/setup_hermes_cron.sh   # register per-profile prep + digest crons
```

Full workflow, onboarding, and safety rules: [skills/pp-job-apply/SKILL.md](skills/pp-job-apply/SKILL.md).

There is also an agent-native CLI wrapper:

```bash
chmod +x bin/job-apply-pp-cli
./bin/job-apply-pp-cli status --agent
./bin/job-apply-pp-cli pipeline run --stages discover,score,portfolio,tailor,cover
```

---

## Project layout

```
jobwright/
├── README.md                 # you are here
├── LICENSE                   # AGPL-3.0
├── pyproject.toml
├── profile.example.json      # onboarding template
├── src/applypilot/           # the package (discovery, enrichment, scoring, apply, ...)
├── bin/job-apply-pp-cli      # agent-native CLI wrapper
├── scripts/                  # Hermes cron + install helpers
├── config/live.env.example   # live-apply env template
├── tests/
└── docs/                     # all documentation (see docs/README.md)
```

---

## Documentation

Everything else lives in [`docs/`](docs/): [contributing](docs/CONTRIBUTING.md), [changelog](docs/CHANGELOG.md), [glossary](docs/GLOSSARY.md), [upstream attribution](docs/UPSTREAM.md), and [architecture decision records](docs/adr/).

## License

jobwright is licensed under the [GNU Affero General Public License v3.0](LICENSE). If you deploy a modified version as a service, you must release your source under the same license.
