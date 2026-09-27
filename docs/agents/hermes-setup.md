# Hermes setup for jobwright (agent playbook)

**Audience:** Hermes agent on the Mac mini (WhatsApp or CLI). **Humans:** paste the block below to WhatsApp Hermes to register crons.

Hermes should **create and manage crons** via `hermes cron` (not ask the human to run `setup_hermes_cron.sh`). Scripts are shell-only (`--no-agent`); zero LLM tokens per tick.

**Since v0.6 the dashboard manages the brief cron itself:** saving a brief time or WhatsApp chat (`PUT /api/profile`, including at the end of onboarding) runs `hermes_cron.ensure_brief_cron`, which writes `~/.hermes/scripts/wrap_jobwright-brief-<user>.sh` and creates or edits `jobwright-brief-<user>` with `--no-agent --deliver local`. Use this playbook for first-time setup, repairs, and the ops crons.

**Sandboxes:** with `JOBWRIGHT_HERMES_DRY_RUN=1` every cron create/edit/delete and every `hermes send` is only logged (`cron list` still runs). Always set it in worktrees and tests.

---

## Paste to WhatsApp Hermes (one message)

```text
Set up jobwright Hermes crons on this machine.

1. Read JOBWRIGHT_REPO from ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO (or ask me for the clone path).
2. Follow the playbook: ${JOBWRIGHT_REPO}/docs/agents/hermes-setup.md — sections "Prerequisites" through "Register crons".
3. Use jobwright users list for registry users, schedules, and whatsapp_target.
4. Before creating each cron, check hermes cron list for an existing job with the same Name; edit if found, create only if missing.
5. Pause or remove any old job-apply-*, jobwright-send-*, or jobwright-check-* crons for the same users (replaced by a single jobwright-brief-<user>).
6. Report back: cron names, schedules, deliver targets, and next run times.
```

Replace `${JOBWRIGHT_REPO}` with your actual path if the skill file is missing (recommended production checkout on the internal disk, e.g. `/Users/parthchandak/apps/jobwright`).

---

## Prerequisites (Hermes runs these)

```bash
export JOBWRIGHT_REPO="$(cat ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO)"   # or ask the owner for the checkout path
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"
cd "${JOBWRIGHT_REPO}"

# Thin skill + Hermes scripts (safe to re-run)
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh

# Verify
test -f ~/.hermes/scripts/jobwright_brief.sh && echo "scripts OK"
jobwright users list
```

Read full agent context: `${JOBWRIGHT_REPO}/AGENTS.md`, `${JOBWRIGHT_REPO}/docs/agents/whatsapp-group-jobwright.md`, and `${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md`.

### Skills checklist (when user asks "do you have everything for jobwright?")

Answer: load **pp-job-apply** / **jobwright** (this skill), plus **hermes-cron-jobs** for scheduling. See [whatsapp-group-jobwright.md](whatsapp-group-jobwright.md).

---

## Cron design (do not change without user approval)

| Cron name | Script | Mode | Purpose |
|-----------|--------|------|---------|
| `jobwright-brief-<user_id>` | `wrap_jobwright-brief-<user_id>.sh` | `--no-agent --deliver local` | Daily Brief: preflight, pipeline, `jobwright notify` (one WhatsApp list), `ops brief-report` (detached) |
| `jobwright-ops-watchdog` | `jobwright_ops_watchdog.sh` | `--no-agent --deliver local` | 08:30: `jobwright ops watchdog` alerts `ops_target` when a brief never started or never finished |
| `jobwright-backup` | `jobwright_backup.sh` | `--no-agent --deliver local` | 02:30: `jobwright ops backup` to `JOBWRIGHT_BACKUP_DIR` (alerts on failure) |
| `jobwright-weekly-summary` | `jobwright_weekly_summary.sh` | `--no-agent --deliver local` | Sunday 18:00: `jobwright summary` for every profile (per-user opt-out `weekly_summary`) |

There is **one** brief cron per user plus the two shared ops crons. The old `jobwright-send-*` (digest delivery) and `jobwright-check-*` (watchdog) crons are retired: the brief sends the notify itself.

**Deliver is `local`**: the brief sends its own WhatsApp list via `hermes send`, so a bridge outage cannot turn a good run into a failed delivery, and launcher output never reaches the user's chat. Operator alerts go to `ops_target` (`users/users.yaml`, set with `jobwright ops set-target` or the Admin page).

**Never** register `job-apply-discover` or `job-apply-submit` (deprecated).

**Never** keep `job-apply-morning-*` / `job-apply-digest-*` / `job-apply-watchdog-*` / `jobwright-send-*` / `jobwright-check-*` alongside the brief cron. Pause or delete them.

**Never** use agent mode for these jobs. Always `--no-agent` + `--script`.

Schedule comes from `users/users.yaml` per user (`schedule`); `whatsapp_target` is where notify posts (not the cron deliver). Default if missing:

- brief: `0 6 * * *` (6:00 AM every day)

---

## Step 1: Create per-user wrapper scripts

The dashboard generates this file (`hermes_cron.write_brief_wrapper`, which execs `${JOBWRIGHT_REPO}/scripts/jobwright_brief.sh`). To write it by hand, for each registry user `<id>` create `~/.hermes/scripts/wrap_jobwright-brief-<id>.sh` that exports user env then execs the real script:

```bash
USER_ID=richa   # example
REPO="${JOBWRIGHT_REPO}"
USERS_ROOT="${JOBWRIGHT_USERS_ROOT}"

cat > "${HOME}/.hermes/scripts/wrap_jobwright-brief-${USER_ID}.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export JOBWRIGHT_USER="${USER_ID}"
export JOBWRIGHT_USERS_ROOT="${USERS_ROOT}"
export JOBWRIGHT_DIR="${USERS_ROOT}/${USER_ID}"
export JOBWRIGHT_REPO="${REPO}"
export PATH="\${HOME}/.local/bin:\${PATH}"
exec bash "\${HOME}/.hermes/scripts/jobwright_brief.sh"
EOF
chmod 755 "${HOME}/.hermes/scripts/wrap_jobwright-brief-${USER_ID}.sh"
```

Hermes: loop over all users from `jobwright users list` and run the equivalent for each `user_id`.

---

## Step 2: Find existing cron by name (avoid duplicates)

```bash
find_cron_id() {
  local name="$1"
  hermes cron list 2>/dev/null | awk -v name="${name}" '
    /^[[:space:]]+[a-f0-9]{8,}/ {
      id = $1
      gsub(/^[[:space:]]+/, "", id)
      sub(/ .*/, "", id)
    }
    $0 ~ "Name:[[:space:]]+" name "[[:space:]]*$" {
      if (id != "") { print id; exit }
    }
  '
}
```

If `find_cron_id` returns an id, use `hermes cron edit <id> ...`. Otherwise `hermes cron create ...`.

---

## Step 3: Register crons (example: user `richa`)

Values from registry (Hermes should read live from `jobwright users show richa`):

- `schedule`: `0 6 * * *` (or whatever is in users.yaml)
- deliver: always `local` (notify posts to `whatsapp_target` itself)

```bash
REPO="${JOBWRIGHT_REPO}"
DELIVER="local"
UID=richa

upsert_cron() {
  local name="$1" schedule="$2" script="$3"
  local id
  id="$(find_cron_id "${name}")"
  if [[ -n "${id}" ]]; then
    hermes cron edit "${id}" \
      --schedule "${schedule}" \
      --script "${script}" \
      --no-agent \
      --deliver "${DELIVER}" \
      --workdir "${REPO}"
    echo "Edited ${name} (${id})"
  else
    hermes cron create "${schedule}" \
      --name "${name}" \
      --script "${script}" \
      --no-agent \
      --deliver "${DELIVER}" \
      --workdir "${REPO}"
    echo "Created ${name}"
  fi
}

upsert_cron "jobwright-brief-${UID}" "0 6 * * *" "wrap_jobwright-brief-${UID}.sh"
```

Repeat for every user in the registry. Pause any `job-apply-*`, `jobwright-send-*`, or `jobwright-check-*` crons for the same user.

### One command for every cron

```bash
cd "${JOBWRIGHT_REPO}"
.venv/bin/jobwright ops install-crons --backup-dest "$JOBWRIGHT_BACKUP_DIR"   # briefs (deliver local) + watchdog 30 8 + backup 30 2 + weekly summary 0 18 * * 0
.venv/bin/jobwright ops set-target 'whatsapp:<operator jid>'                  # where alerts go
```

`scripts/setup_hermes_cron.sh` installs the scripts, retires legacy crons, then runs the same command. Both are idempotent (upsert by name).

The Admin page has a button for the watchdog cron. Both write their script to `~/.hermes/scripts/` and upsert by name.

---

## Step 4: Verify

```bash
hermes cron list | grep -E 'jobwright-|job-apply-'
jobwright --user richa doctor
jobwright --user richa preflight
```

Confirm exactly **one** cron per name, each with deliver `local`. Report next run times to the user on WhatsApp.

---

## LLM vs no_agent

| Surface | Mode |
|---------|------|
| Cron tick (brief) | `--no-agent` (pipeline + `jobwright notify` sends the WhatsApp list) |
| WhatsApp chat (status, find jobs now, notify, file uploads) | Hermes agent + skill `pp-job-apply` / `jobwright` + terminal |

Inbound WhatsApp routing: [whatsapp-routing.md](whatsapp-routing.md).

---

## Env and API keys

Cron wrappers source `${JOBWRIGHT_REPO}/.env` (then `users/<id>/.env`) automatically inside `jobwright_*.sh`. Do not put API keys in cron definitions. The brief model defaults to `accounts/fireworks/models/glm-5p3-flash` (`JOBWRIGHT_LLM_MODEL` overrides).

Optional: `EXA_API_KEY` enables web research for per-job connections.

---

## After repo updates

```bash
cd "${JOBWRIGHT_REPO}"
./scripts/install_hermes_scripts.sh   # if shell scripts changed
./scripts/install_skills.sh           # only if templates/hermes-skill/SKILL.md changed
```

Re-run cron registration (Step 3) only if schedules or the user list changed. Use **edit** when the cron name already exists.

## Moving the checkout (e.g. SSD → internal disk)

1. Clone or copy to the new path (recommended `/Users/parthchandak/apps/jobwright`) with `users/` and `.env`; `uv sync` / `.venv`, then `jobwright preflight --fix`.
2. From the new checkout: `./scripts/install_skills.sh` (rewrites the skill `JOBWRIGHT_REPO` file) and `./scripts/install_hermes_scripts.sh`.
3. Regenerate wrappers and crons: re-save each user's brief time in the dashboard (or `ensure_brief_cron`), and re-run the ops cron snippet above. Every generated script pins the repo and users root.
4. Regenerate the per-profile group instructions: `jobwright hermes channels --apply` (rewrites the repo path in every managed `system_prompt`); restart the gateway.
5. Point pm2 at the new checkout (no `--reload`). Keep the SSD for `JOBWRIGHT_BACKUP_DIR`.

## WhatsApp group instructions (generated)

Each profile whose `whatsapp_target` is a group (`whatsapp:<jid>@g.us`) gets its own Hermes entry in `~/.hermes/config.yaml`, generated from `users/users.yaml` by `src/jobwright/hermes_channels.py`: `channel_overrides.<jid>.system_prompt` (that user only: `--user <id>`, `jobwright-brief-<id>`, `apply_enabled`, dashboard URL, no model lines), `channel_prompts.<jid>`, a `channel_skill_bindings` entry (pp-job-apply, hermes-cron-jobs, graphify, cursor-agent) and `group_allow_from`.

```bash
jobwright hermes channels                 # show the diff (default ~/.hermes/config.yaml, or $HERMES_CONFIG / --config PATH)
jobwright hermes channels --apply         # backup to <config>.bak-jobwright-<ts>, atomic write, re-parse
jobwright hermes channels --apply --prune # also drop managed entries whose group no longer belongs to a profile
hermes gateway restart                    # Hermes only reads the file at start
```

- Managed prompts carry the line `# managed by jobwright (hermes_channels)`. Entries for other groups are never touched; comments and key order are preserved (ruamel.yaml round-trip).
- A managed entry whose group no profile uses is reported as `orphan` and kept unless `--prune`.
- DMs and empty targets are skipped. Idempotent: a second run reports everything `unchanged`.
- `JOBWRIGHT_HERMES_DRY_RUN=1` never writes. Admin page → "WhatsApp group instructions" shows the same plan with an Apply button (`GET /api/admin/hermes-channels`, `POST /api/admin/hermes-channels/apply`).
- Re-run after adding a profile, changing a group, toggling `apply_enabled`/`human_gate`, or moving the checkout.

---

## Post-deploy demo (paste after Daily Brief lands)

```text
Show me Daily Brief end to end for user richa in this WhatsApp group.

1. cd "${JOBWRIGHT_REPO}"
2. ./scripts/install_hermes_scripts.sh && ./scripts/install_skills.sh
3. Confirm ~/.hermes/scripts/jobwright_brief.sh exists
4. Follow docs/agents/hermes-setup.md: register a single jobwright-brief-richa at 6:00 daily (deliver local)
5. Delete any job-apply-*, jobwright-send-*, or jobwright-check-* crons for richa
6. Update this group's channel_overrides system_prompt (see docs/agents/whatsapp-group-jobwright.md). Bind cursor-agent. Restart gateway if needed.
7. jobwright --user richa doctor && jobwright --user richa status
8. Trigger now: JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_brief.sh
9. When it finishes, the brief sends ONE WhatsApp list of new jobs with dashboard deep links. Confirm it landed here.
10. Report: cron name, next run time, job count, notify result, failures.

Also confirm you know: resolve sender→richa, file uploads to users/richa/ with backup, continuous improvement in hermes-operator-guide.md.
```

---

## Optional: legacy single-user crons

**Only** if `jobwright users list` is **empty** and data lives in `~/.jobwright`.

**If registry users exist (e.g. `richa`), do NOT create legacy crons** (`jobwright-brief` without `-<user_id>`, or old `job-apply-*`). They duplicate digests.

Legacy example (empty registry only):

```bash
hermes cron create "0 6 * * *" \
  --name jobwright-brief \
  --script jobwright_brief.sh \
  --no-agent \
  --deliver local \
  --workdir "${JOBWRIGHT_REPO}"
```

---

## Mac mini notes

- Cron hard timeout: **300s** — brief script detaches long pipeline (by design).
- Gateway: `launchctl list | grep ai.hermes.gateway`
- Logs: `~/.hermes/logs/gateway.log`
- Optional `terminal.cwd` in `~/.hermes/config.yaml` → `${JOBWRIGHT_REPO}`

## Skill location

Thin loader: `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/` (see [install-hermes-skill.md](install-hermes-skill.md)).

Canonical docs: `${JOBWRIGHT_REPO}/AGENTS.md` and this folder.
