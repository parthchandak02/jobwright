# Glossary

| Term | Definition |
|------|------------|
| Pipeline | Six stages + portfolio pick, backed by SQLite `jobs` table |
| Job | Database row keyed by `url`, progresses through stages |
| Portfolio | Structured projects in `profile.json` used for per-job selection |
| AgentProvider | Pluggable stage-6 backend (`cursor-sdk`, `cursor-cli`, `claude`) |
| Worker | Parallel apply unit with isolated Chrome CDP port and workdir |
| RESULT protocol | Agent output codes: `RESULT:APPLIED`, `RESULT:FAILED:reason`, etc. |
| Dry-run gate | `--dry-run` fills forms without submitting; emits `RESULT:DRYRUN` |
| Tier | Feature gate: 1=discover, 2=LLM, 3=auto-apply |
| pp-cli | `job-apply-pp-cli` Printing Press agent-native wrapper |
