# Install the Hermes skill for jobwright

Hermes skills live on **your machine** under `~/.hermes/skills/`, not inside the git clone. The clone holds the **docs and code**; the skill is a thin pointer so Hermes knows where your clone is.

## Recommended: install script

From your jobwright clone (any path):

```bash
cd /path/to/your/jobwright    # e.g. ~/projects/jobwright
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh
```

`install_skills.sh` does:

1. Copies [templates/hermes-skill/SKILL.md](../../templates/hermes-skill/SKILL.md) to `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/`
2. Writes `JOBWRIGHT_REPO` with the absolute path to your clone
3. Creates alias `~/.hermes/skills/autonomous-ai-agents/jobwright`
4. Also installs the thin loader for Cursor (`~/.cursor/skills/pp-job-apply`)

Verify:

```bash
cat ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO
test -f ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/SKILL.md && echo OK
```

Re-run `./scripts/install_skills.sh` after pulling repo updates that change the skill template.

## Manual: create your own Hermes skill

If you prefer not to use the script:

1. Pick a skill id, e.g. `pp-job-apply` or `jobwright`.
2. Create `~/.hermes/skills/autonomous-ai-agents/<id>/SKILL.md` with YAML frontmatter (`name`, `description`, `metadata.hermes.tags`).
3. In the body, set your clone path and point to repo docs:

```markdown
# jobwright

export JOBWRIGHT_REPO=/path/to/your/jobwright-clone
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"

Read order:
1. ${JOBWRIGHT_REPO}/AGENTS.md
2. ${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md
3. ${JOBWRIGHT_REPO}/docs/agents/whatsapp-routing.md
```

4. Copy Hermes cron scripts: `./scripts/install_hermes_scripts.sh`
5. Ask Hermes to register crons using [hermes-setup.md](hermes-setup.md) (agent playbook; do not rely on `setup_hermes_cron.sh` unless you want a non-agent shell shortcut)

## Multiple clones or machines

Each machine runs `install_skills.sh` from **its** clone. The `JOBWRIGHT_REPO` file in the Hermes skill dir records that machine's path. Do not commit `~/.hermes/` to git.

## What is NOT in the skill directory

Operational playbooks, WhatsApp routing tables, and repo maps stay in the clone under `docs/agents/` and `AGENTS.md`. When docs change, pull the repo; you only re-run `install_skills.sh` if the thin `SKILL.md` template changed.
