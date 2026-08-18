# jobwright

An autonomous job-search pipeline that finds roles, scores fit, tailors your resume and cover letter per job, surfaces people in your network worth reaching out to, and can optionally submit applications for you. Pair it with **Hermes** (or any chat agent you run on your machine) and it becomes a **daily career advisor**: curated opportunities delivered to WhatsApp or another chat app, with application materials already prepared.

The console command is `jobwright`.

**Agents (Cursor, Claude, Hermes):** read [AGENTS.md](AGENTS.md) first for end-to-end flow, paths, and pointers to operational playbooks.

---

## The Daily Brief: how it works with Hermes

jobwright does the heavy lifting of a job search. You provide a **base resume**, **profile** (skills, experience, preferences), **search criteria** (titles, locations, salary floor), and optionally a **LinkedIn connections export**. Everything else can run on a schedule.

Each day (or on demand), the pipeline:

1. **Discovers** jobs across job boards and company career sites, filtered to your criteria.
2. **Enriches** each listing with the full description and apply link.
3. **Scores** every job with an LLM (1–10 fit against your profile). Weak matches are dropped early.
4. **Selects portfolio highlights** (when configured): the most relevant projects from your profile for each role.
5. **Tailors** your resume per strong match. Facts come from your base resume only; the LLM rewrites emphasis and wording, it does not invent experience.
6. **Writes a cover letter** per job, also from your base materials and examples you provide.
7. **Exports DOCX** files ready to upload or attach.
8. **Suggests connections** at each company from your LinkedIn network (ranked by relevance to the role).

When paired with **Hermes**, the results land in your chat app:

| When | What you get |
|------|----------------|
| After the brief completes | **One WhatsApp list** of new jobs (scores, links to the dashboard) |
| When you open a job link | Tailored resume + cover letter DOCX, connections, and apply in the dashboard |
| Any time | `job status`, `find jobs now`, `notify`, or plain-language questions |

**What to expect:** jobwright prepares materials for your **best matches** (not every job on the internet). Some days boards block scraping or nothing clears your score bar; you still get a clear message instead of silence. Always review tailored documents before you send them.

**Your job is to review and apply.** jobwright finds opportunities, prepares materials, and highlights who to network with. You decide which roles to pursue and submit using the tailored documents (or ask Hermes to apply on your behalf if that mode is enabled).

```
You provide once          jobwright (daily)              Hermes → your chat
─────────────────         ─────────────────              ────────────────
base resume.pdf     →     discover → score → tailor  →   notify (job list + links)
profile.json              cover → docx → connect        dashboard (materials)
searches.yaml                                           network suggestions
connections.csv (opt.)
```

### What each user needs

| Input | Purpose |
|-------|---------|
| `resume/base.pdf` | Source of truth for tailoring (markdown is derived); LLM never fabricates beyond this |
| `profile.json` | Contact info, skills, experience, compensation floor, work auth |
| `searches.yaml` | Queries, locations, boards, title exclusions, min salary |
| `cover-letter/examples/` | Style and tone for generated cover letters |
| `connections.csv` (optional) | LinkedIn export for per-job "who to reach out to" |
| `.env` API keys | LLM for score, tailor, cover (e.g. Fireworks or Gemini) |

Multi-profile setups use `users/<id>/` under the repo (or `~/.jobwright/` for a single user). Each profile gets its own daily notify list and dashboard materials.

### Safety defaults

- **Find and prepare only** by default. Nothing is submitted without an explicit opt-in.
- **Apply** (browser agent, stage 6) is dry-run by default and never runs from cron automatically.
- Live apply runs only from the dashboard apply button (with a confirm step) or an explicit `jobwright apply --live`, and only when the profile has apply enabled.
- LinkedIn jobs can appear in the brief with materials; auto-apply to LinkedIn is blocked by design.
- **Partial success is OK:** if some pipeline stages fail, the notify list still includes whatever jobs are ready, with a short run-stats footer.
- **Quality gate:** failed resume validation is not saved or delivered as DOCX.

Hermes setup: [docs/agents/hermes-setup.md](docs/agents/hermes-setup.md). Human-facing WhatsApp guide: [docs/agents/whatsapp-user-guide.md](docs/agents/whatsapp-user-guide.md).

---

## What it does

| Stage | Command | What happens |
|-------|---------|--------------|
| 1. Discover | `run discover` | Scrapes Indeed, Google Jobs, ZipRecruiter, Workday portals, and direct career sites |
| 2. Enrich | `run enrich` | Fetches the full job description (JSON-LD, CSS selectors, or LLM extraction) |
| 3. Score | `run score` | LLM rates each job 1-10 against your resume; low-fit jobs stop here |
| 3b. Portfolio | `run portfolio` | Picks the 4-5 most relevant projects from your profile per job |
| 4. Tailor | `run tailor` | Rewrites your resume per job from your base resume (never fabricates) |
| 5. Cover letter | `run cover` | Writes a targeted cover letter per job from your examples and profile |
| 5a. PDF | `run pdf` | Optional HTML/PDF export; skipped by the daily brief and dashboard Auto Search |
| 5b. DOCX | `run docx` | Exports tailored resume and cover letter as Word documents |
| 5c. Connect | `run connect` | Ranks people in your LinkedIn network relevant to each job |
| 6. Apply | `apply` | A browser agent fills forms, uploads documents, and submits (optional, gated) |

Stages 1–5c are fully automated and safe (5a is optional). Stage 6 (apply) is opt-in and dry-run by default. The dashboard Auto Search and daily brief run 1–5c except 5a.

---

## Requirements

| Component | Needed for | Notes |
|-----------|-----------|-------|
| Python 3.11+ | Everything | Core runtime |
| `FIREWORKS_API_KEY` or `GEMINI_API_KEY` | Stages 3-5 (score, tailor, cover) | Fireworks is the default for daily brief; Gemini is used as fallback when configured |
| Node.js 18+ | Stage 6 apply | Runs the Playwright MCP server |
| `CURSOR_API_KEY` | Stage 6 apply | Default agent provider (`cursor-sdk`) |
| Chrome/Chromium | Stage 6 apply | Auto-detected on most systems |
| Hermes + `hermes` CLI | Chat delivery | Sends the daily job list to WhatsApp (or other channels); materials live on the dashboard |

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

- **`.env`** (repo root) - `FIREWORKS_API_KEY` (preferred), `GEMINI_API_KEY` (failover), `LLM_MODEL`, optional `CURSOR_API_KEY` and `CAPSOLVER_API_KEY`.

Your per-profile data lives under `~/.jobwright/` (single user) or `users/<id>/` under the repo (multi-profile), and holds only user-specific files:

- **`profile.json`** - contact info, work authorization, compensation, experience, skills, and your `portfolio` projects. Start from [`profile.example.json`](profile.example.json).
- **`searches.yaml`** - your search queries, target titles, locations, and boards.

Board and site definitions ship inside the package at `src/jobwright/config/` (`employers.yaml`, `sites.yaml`, `searches.example.yaml`).

---

## Find and tailor jobs (stages 1-5)

```bash
# Run the full prep pipeline in parallel, keeping only strong matches
# (same stages as daily brief / Auto Search; `pdf` is optional via `run pdf` or `run all`)
jobwright run discover enrich score portfolio tailor cover docx connect -w 4 --min-score 7

jobwright status      # pipeline statistics
jobwright dashboard   # open the local HTML results snapshot

# Hosted Kanban (optional): install .[web], then:
# ./scripts/restart.sh          # API :8002 + Vite HMR :5120
# open http://127.0.0.1:5120
# Profile page edits search keywords, resume PDF, and cover-letter example PDFs.
# See docs/agents/dashboard-hosting.md for jobwright.parthchandak.info
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

Safety: dry-run is the default, LinkedIn jobs can appear in the brief with materials (auto-apply to LinkedIn is blocked by design), live workers are capped at 1, and multi-profile users must be explicitly opted in (`apply_enabled`). See [docs/agents/whatsapp-routing.md](docs/agents/whatsapp-routing.md) and [docs/agents/install-hermes-skill.md](docs/agents/install-hermes-skill.md).

---

## Scheduling and multi-profile (Hermes + chat delivery)

jobwright runs per-profile prep on a Hermes cron and sends one WhatsApp notification per day to each user's group:

- **Morning brief:** one cron per user runs discover through connect, then `jobwright notify`.
- **Notification:** a single text message listing the newly prepared jobs, each with a dashboard deep link (`jobwright.parthchandak.info/jobs/<job_id>`). If nothing new is ready, nothing is sent.
- **Review + apply:** happen in the dashboard, not over chat. Open a job's deep link to see its details, materials, and connections; live apply stays gated behind per-user enablement.

See [The Daily Brief](#the-daily-brief-how-it-works-with-hermes) above for the full picture.

```bash
./scripts/install_skills.sh      # install the pp-job-apply skill for Cursor + Hermes
./scripts/install_hermes_scripts.sh
```

Hermes cron setup: paste the block at the top of [docs/agents/hermes-setup.md](docs/agents/hermes-setup.md) to your WhatsApp Hermes agent (it registers crons via `hermes cron`).

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
