# jobwright

An autonomous, multi-stage job application pipeline. It discovers jobs across many boards, scores them against your resume with an LLM, tailors your resume and cover letter per job, and can optionally submit applications for you through a browser agent.

The console command is `jobwright`.

**Agents (Cursor, Claude, Hermes):** read [AGENTS.md](AGENTS.md) first for end-to-end flow, paths, and pointers to operational playbooks.

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
jobwright init      # collects resume, profile, preferences, and API keys
jobwright doctor    # shows what is installed and what is missing
```

### Configuration files (created by `jobwright init`)

API keys live in a **single gitignored `.env` at the repo root**, shared across all profiles (never committed):

- **`.env`** (repo root) - `GEMINI_API_KEY`, `LLM_MODEL`, optional `CURSOR_API_KEY` and `CAPSOLVER_API_KEY`.

Your per-profile data lives under `~/.jobwright/` (single user) or `users/<id>/` under the repo (multi-profile), and holds only user-specific files:

- **`profile.json`** - contact info, work authorization, compensation, experience, skills, and your `portfolio` projects. Start from [`profile.example.json`](profile.example.json).
- **`searches.yaml`** - your search queries, target titles, locations, and boards.

Board and site definitions ship inside the package at `src/jobwright/config/` (`employers.yaml`, `sites.yaml`, `searches.example.yaml`).

---

## Find and tailor jobs (stages 1-5)

```bash
# Run the full prep pipeline in parallel, keeping only strong matches
jobwright run discover enrich score portfolio tailor cover -w 4 --min-score 7

jobwright status      # pipeline statistics
jobwright dashboard   # open the HTML results dashboard
```

If tailoring is flaky on the Gemini free tier, add `--validation lenient`.

---

## Apply for jobs (stage 6)

Stage 6 launches a browser agent that navigates the application form, fills your details, uploads the tailored resume and cover letter, answers screening questions, and submits.

**It is dry-run by default and never runs from cron automatically.**

```bash
export CURSOR_API_KEY=...

# Fill forms WITHOUT submitting (recommended first pass)
jobwright apply --dry-run --limit 1

# Submit for real, one job at a time
jobwright apply --url "https://boards.greenhouse.io/example/jobs/123"
```

Agent provider is selectable via `AGENT_PROVIDER`:

```bash
export AGENT_PROVIDER=cursor-sdk   # default: cursor-sdk Python package
export AGENT_PROVIDER=cursor-cli   # fallback: the `agent` CLI
export AGENT_PROVIDER=claude       # legacy upstream behavior
```

Safety: dry-run is the default, LinkedIn apply is blocked, live workers are capped at 1, and multi-profile users must be explicitly opted in (`apply_enabled`). See [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md) and [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## Scheduling and multi-profile (optional)

jobwright can run per-profile prep on a Hermes cron and deliver a digest to each user, with live apply gated behind an explicit `CONFIRM APPLY` reply:

```bash
./scripts/install_skills.sh      # install the pp-job-apply skill for Cursor + Hermes
./scripts/setup_hermes_cron.sh   # register per-profile prep + digest crons
```

Full workflow, onboarding, and safety rules: [AGENTS.md](AGENTS.md) and [docs/agents/](docs/agents/). Hermes users: run `./scripts/install_skills.sh` after clone.

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
├── AGENTS.md                 # agent entry point (Cursor, Claude, Hermes)
├── CLAUDE.md                 # pointer to AGENTS.md
├── docs/agents/              # Hermes/WhatsApp ops (canonical, in repo)
├── templates/hermes-skill/   # thin loader copied to ~/.hermes/skills/
├── skills/README.md          # how to install Hermes skill (not a skill itself)
├── LICENSE                   # AGPL-3.0
├── pyproject.toml
├── profile.example.json      # onboarding template
├── src/jobwright/           # the package (discovery, enrichment, scoring, apply, ...)
├── bin/job-apply-pp-cli      # agent-native CLI wrapper
├── scripts/                  # Hermes cron + install helpers
├── config/live.env.example   # live-apply env template
├── tests/
└── docs/                     # all documentation (see docs/README.md)
```

---

## Documentation

Everything else lives in [`docs/`](docs/): [contributing](docs/CONTRIBUTING.md), [changelog](docs/CHANGELOG.md), [glossary](docs/GLOSSARY.md), [attribution](docs/UPSTREAM.md), and [architecture decision records](docs/adr/). **Agent map:** [AGENTS.md](AGENTS.md). **Hermes install:** [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

## License and attribution

jobwright is licensed under the [GNU Affero General Public License v3.0](LICENSE). If you deploy a modified version as a service, you must release your source under the same license.

Portions of the pipeline originate from an earlier AGPL-3.0 codebase; that attribution is retained in [docs/UPSTREAM.md](docs/UPSTREAM.md) as required by the license.
