# Contributing to jobwright

Thank you for your interest in contributing to jobwright. This guide covers everything you need to get started.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git

### Clone and Install

```bash
git clone https://github.com/parthchandak02/jobwright.git
cd jobwright
pip install -e ".[dev]"
playwright install chromium
```

This installs jobwright in editable mode with all development dependencies (pytest, ruff, etc.) and downloads the Chromium browser binary for Playwright. The console command is `jobwright`.

### Verify Installation

```bash
jobwright --version
pytest tests/ -v
ruff check src/
```

## How to Contribute

### Adding New Workday Employers

Workday employer portals are configured in `src/jobwright/config/employers.yaml`. To add a new employer:

1. Find the company's Workday career portal URL (usually `https://company.wd5.myworkdaysite.com/`)
2. Identify the Workday instance number (wd1, wd3, wd5, etc.) and the tenant ID
3. Add an entry to `src/jobwright/config/employers.yaml`:

```yaml
- name: "Company Name"
  tenant: "company_tenant_id"
  instance: "wd5"
  url: "https://company.wd5.myworkdaysite.com/en-US/recruiting"
```

4. Test discovery: `jobwright discover --employer "Company Name"`
5. Submit a PR with the new entry

### Adding New Career Sites

Direct career site scrapers are configured in `src/jobwright/config/sites.yaml`. To add a new site:

1. Inspect the company's careers page and identify the job listing structure
2. Add an entry to `src/jobwright/config/sites.yaml` with CSS selectors:

```yaml
- name: "Company Name"
  url: "https://company.com/careers"
  selectors:
    job_list: ".job-listing"
    title: ".job-title"
    location: ".job-location"
    link: "a.job-link"
    description: ".job-description"
```

3. Test: `jobwright discover --site "Company Name"`
4. Submit a PR

### Bug Fixes and Features

1. Check existing [issues](https://github.com/parthchandak02/jobwright/issues) to avoid duplicating work
2. For new features, open an issue first to discuss the approach
3. Fork the repo and create a feature branch from `main`
4. Write your code with type hints and docstrings
5. Add tests for new functionality
6. Update the CHANGELOG.md under an `[Unreleased]` section
7. Submit a PR

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_scoring.py -v

# Run with coverage
pytest tests/ --cov=src/jobwright --cov-report=term-missing
```

## Linting and Code Style

jobwright uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for issues
ruff check src/

# Auto-fix what can be fixed
ruff check src/ --fix

# Format code
ruff format src/
```

### Code Style Guidelines

- **Type hints**: All function signatures must have type annotations
- **Docstrings**: All public functions and classes must have docstrings (Google style)
- **Naming**: snake_case for functions and variables, PascalCase for classes
- **Imports**: Sorted by Ruff (isort-compatible)
- **Line length**: 120 characters maximum (Ruff `line-length = 120`)

## PR Guidelines

- **One feature per PR.** Keep changes focused and reviewable.
- **Include tests.** New features need test coverage. Bug fixes need a regression test.
- **Update CHANGELOG.md.** Add your changes under `[Unreleased]`.
- **Write a clear PR description.** Explain what changed and why.
- **Keep commits clean.** Squash fixup commits before requesting review.
- **CI must pass.** All linting and tests must be green.

## Project Structure

```
jobwright/
├── README.md                 # Single entry point: setup + how to apply
├── LICENSE                   # AGPL-3.0
├── pyproject.toml            # Package + tooling config
├── profile.example.json      # Onboarding profile template
├── src/jobwright/           # Main package (import name kept from the original codebase)
│   ├── cli.py                # Typer CLI: init/run/apply/status/doctor/...
│   ├── pipeline.py           # Stages 1-5 orchestrator
│   ├── config.py             # Paths, environment, packaged-config loader
│   ├── database.py           # SQLite job store
│   ├── llm.py                # Shared LLM client
│   ├── discovery/            # Stage 1: JobSpy + Workday + smart-extract
│   ├── enrichment/           # Stage 2: full description scrape
│   ├── scoring/              # Stages 3-5 + portfolio + pdf
│   ├── apply/                # Stage 6: browser automation + agent providers
│   ├── network/              # LinkedIn connection ranking
│   ├── targets/              # LLM target-company builder
│   ├── wizard/               # First-run setup
│   └── config/               # Packaged YAML/JSON (employers, sites, searches)
├── bin/job-apply-pp-cli      # Agent-native CLI wrapper
├── scripts/                  # Hermes cron + install helpers
├── config/live.env.example   # Live-apply env template
├── tests/                    # Test suite
└── docs/                     # All docs (this folder)
    └── adr/                  # Architecture decision records
```

## License

By contributing to jobwright, you agree that your contributions will be licensed under the [GNU Affero General Public License v3.0](../LICENSE).
