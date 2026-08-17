# Hermes setup for jobwright (agent playbook)

**Audience:** Hermes agent on the Mac mini (WhatsApp or CLI). **Humans:** paste the block below to WhatsApp Hermes to register crons.

Hermes should **create and manage crons** via `hermes cron` (not ask the human to run `setup_hermes_cron.sh`). Scripts are shell-only (`--no-agent`); zero LLM tokens per tick.

---

## Paste to WhatsApp Hermes (one message)

```text
Set up jobwright Hermes crons on this machine.

1. Read JOBWRIGHT_REPO from ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO (or ask me for the clone path).
2. Follow the playbook: ${JOBWRIGHT_REPO}/docs/agents/hermes-setup.md — sections "Prerequisites" through "Register crons".
3. Use jobwright users list for registry users, schedules, and whatsapp_target.
4. Before creating each cron, check hermes cron list for an existing job with the same Name; edit if found, create only if missing.
5. Report back: cron names, schedules, deliver targets, and next run times.
```

Replace `${JOBWRIGHT_REPO}` with your actual path if the skill file is missing, e.g. `/Volumes/ExternalSSD/Projects/jobwright`.

---

## Prerequisites (Hermes runs these)

```bash
export JOBWRIGHT_REPO="$(cat ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO 2>/dev/null || echo '/Volumes/ExternalSSD/Projects/jobwright')"
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"
cd "${JOBWRIGHT_REPO}"

# Thin skill + Hermes scripts (safe to re-run)
./scripts/install_skills.sh
./scripts/install_hermes_scripts.sh

# Verify
test -f ~/.hermes/scripts/job_apply_morning.sh && echo "scripts OK"
jobwright users list
```

Read full agent context: `${JOBWRIGHT_REPO}/AGENTS.md` and `${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md`.

---

## Cron design (do not change without user approval)

| Cron name | Script | Mode | Purpose |
|-----------|--------|------|---------|
| `job-apply-morning-<user_id>` | `wrap_job-apply-morning-<user_id>.sh` | `--no-agent` | Prep pipeline stages 1-5 (detached) |
| `job-apply-digest-<user_id>` | `wrap_job-apply-digest-<user_id>.sh` | `--no-agent` | WhatsApp digest delivery |
| `job-apply-watchdog-<user_id>` | `wrap_job-apply-watchdog-<user_id>.sh` | `--no-agent` | Stuck pipeline / delivery check |

**Never** register `job-apply-discover` or `job-apply-submit` (deprecated).

**Never** use agent mode for these jobs. Always `--no-agent` + `--script`.

Schedules and deliver targets come from `users/users.yaml` per user (`schedule`, `digest_schedule`, `whatsapp_target`). Default if missing:

- morning: `0 */3 * * 1-5` (every 3h weekdays)
- digest: `15 */3 * * 1-5` (15 min after morning tick)
- watchdog: `0 11 * * 1-5`

---

## Step 1: Create per-user wrapper scripts

For each registry user `<id>`, write `~/.hermes/scripts/wrap_job-apply-morning-<id>.sh` (and digest/watchdog variants) that export user env then exec the real script:

```bash
USER_ID=richa   # example
REPO="${JOBWRIGHT_REPO}"
USERS_ROOT="${JOBWRIGHT_USERS_ROOT}"

for kind in morning digest watchdog; do
  cat > "${HOME}/.hermes/scripts/wrap_job-apply-${kind}-${USER_ID}.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export JOBWRIGHT_USER="${USER_ID}"
export JOBWRIGHT_USERS_ROOT="${USERS_ROOT}"
export JOBWRIGHT_DIR="${USERS_ROOT}/${USER_ID}"
export JOBWRIGHT_REPO="${REPO}"
export PATH="\${HOME}/.local/bin:\${PATH}"
exec bash "\${HOME}/.hermes/scripts/job_apply_${kind}.sh"
EOF
  chmod 755 "${HOME}/.hermes/scripts/wrap_job-apply-${kind}-${USER_ID}.sh"
done
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

- `whatsapp_target`: `whatsapp:120363427224277278@g.us`
- `schedule`: `0 */3 * * 1-5`
- `digest_schedule`: `15 */3 * * 1-5`

```bash
REPO="${JOBWRIGHT_REPO}"
DELIVER="whatsapp:120363427224277278@g.us"
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

upsert_cron "job-apply-morning-${UID}" "0 */3 * * 1-5" "wrap_job-apply-morning-${UID}.sh"
upsert_cron "job-apply-digest-${UID}" "15 */3 * * 1-5" "wrap_job-apply-digest-${UID}.sh"
upsert_cron "job-apply-watchdog-${UID}" "0 11 * * 1-5" "wrap_job-apply-watchdog-${UID}.sh"
```

Repeat for every user in the registry.

---

## Step 4: Verify

```bash
hermes cron list | grep -A6 'job-apply'
jobwright --user richa doctor
```

Confirm exactly **one** cron per name. Report next run times to the user on WhatsApp.

---

## LLM vs no_agent

| Surface | Mode |
|---------|------|
| Cron ticks (morning, digest, watchdog) | `--no-agent` (script stdout → WhatsApp) |
| WhatsApp chat (CONFIRM APPLY, status, find jobs now) | Hermes agent + skill `pp-job-apply` / `jobwright` + terminal |

Inbound WhatsApp routing: [whatsapp-routing.md](whatsapp-routing.md).

---

## Env and API keys

Cron wrappers source `${JOBWRIGHT_REPO}/.env` automatically inside `job_apply_*.sh`. Do not put API keys in cron definitions.

---

## After repo updates

```bash
cd "${JOBWRIGHT_REPO}"
./scripts/install_hermes_scripts.sh   # if shell scripts changed
./scripts/install_skills.sh           # only if templates/hermes-skill/SKILL.md changed
```

Re-run cron registration (Step 3) only if schedules, deliver targets, or user list changed. Use **edit** when the cron name already exists.

---

## Optional: legacy single-user crons

Only if `jobwright users list` is **empty** and data lives in `~/.jobwright/`:

```bash
hermes cron create "0 5 * * 1-5" \
  --name job-apply-morning \
  --script job_apply_morning.sh \
  --no-agent \
  --deliver "whatsapp:..." \
  --workdir "${JOBWRIGHT_REPO}"
```

Do not create legacy crons when registry users exist (duplicates digests).

---

## Mac mini notes

- Cron hard timeout: **300s** — morning script detaches long pipeline (by design).
- Gateway: `launchctl list | grep ai.hermes.gateway`
- Logs: `~/.hermes/logs/gateway.log`
- Optional `terminal.cwd` in `~/.hermes/config.yaml` → `${JOBWRIGHT_REPO}`

## Skill location

Thin loader: `~/.hermes/skills/autonomous-ai-agents/pp-job-apply/` (see [install-hermes-skill.md](install-hermes-skill.md)).

Canonical docs: `${JOBWRIGHT_REPO}/AGENTS.md` and this folder.
