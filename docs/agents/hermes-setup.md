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
5. Pause or remove any old job-apply-* crons for the same users (replaced by jobwright-brief/send/check).
6. Report back: cron names, schedules, deliver targets, and next run times.
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
| `jobwright-brief-<user_id>` | `wrap_jobwright-brief-<user_id>.sh` | `--no-agent` | Daily Brief: discover → cover → docx → connect (detached) |
| `jobwright-send-<user_id>` | `wrap_jobwright-send-<user_id>.sh` | `--no-agent` | WhatsApp digest delivery |
| `jobwright-check-<user_id>` | `wrap_jobwright-check-<user_id>.sh` | `--no-agent` | Stuck pipeline / delivery check |

**Never** register `job-apply-discover` or `job-apply-submit` (deprecated).

**Never** keep `job-apply-morning-*` / `job-apply-digest-*` / `job-apply-watchdog-*` alongside the new names (duplicates digests). Pause or delete them.

**Never** use agent mode for these jobs. Always `--no-agent` + `--script`.

Schedules and deliver targets come from `users/users.yaml` per user (`schedule`, `digest_schedule`, `whatsapp_target`). Default if missing:

- brief: `0 6 * * *` (6:00 AM every day)
- send: `30 6 * * *` (6:30 AM every day)
- check: `0 10 * * *` (10:00 AM every day)

---

## Step 1: Create per-user wrapper scripts

For each registry user `<id>`, write `~/.hermes/scripts/wrap_jobwright-brief-<id>.sh` (and send/check variants) that export user env then exec the real script:

```bash
USER_ID=richa   # example
REPO="${JOBWRIGHT_REPO}"
USERS_ROOT="${JOBWRIGHT_USERS_ROOT}"

for kind in brief send check; do
  cat > "${HOME}/.hermes/scripts/wrap_jobwright-${kind}-${USER_ID}.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export JOBWRIGHT_USER="${USER_ID}"
export JOBWRIGHT_USERS_ROOT="${USERS_ROOT}"
export JOBWRIGHT_DIR="${USERS_ROOT}/${USER_ID}"
export JOBWRIGHT_REPO="${REPO}"
export PATH="\${HOME}/.local/bin:\${PATH}"
exec bash "\${HOME}/.hermes/scripts/jobwright_${kind}.sh"
EOF
  chmod 755 "${HOME}/.hermes/scripts/wrap_jobwright-${kind}-${USER_ID}.sh"
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
- `schedule`: `0 6 * * *` (or whatever is in users.yaml)
- `digest_schedule`: `30 6 * * *`

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

upsert_cron "jobwright-brief-${UID}" "0 6 * * *" "wrap_jobwright-brief-${UID}.sh"
upsert_cron "jobwright-send-${UID}" "30 6 * * *" "wrap_jobwright-send-${UID}.sh"
upsert_cron "jobwright-check-${UID}" "0 10 * * *" "wrap_jobwright-check-${UID}.sh"
```

Repeat for every user in the registry. Pause any `job-apply-*` crons for the same user.

---

## Step 4: Verify

```bash
hermes cron list | grep -E 'jobwright-|job-apply-'
jobwright --user richa doctor
```

Confirm exactly **one** cron per new name. Report next run times to the user on WhatsApp.

---

## LLM vs no_agent

| Surface | Mode |
|---------|------|
| Cron ticks (brief, send, check) | `--no-agent` (script stdout → WhatsApp) |
| WhatsApp chat (CONFIRM APPLY, status, find jobs now, materials N) | Hermes agent + skill `pp-job-apply` / `jobwright` + terminal |

Inbound WhatsApp routing: [whatsapp-routing.md](whatsapp-routing.md).

---

## Env and API keys

Cron wrappers source `${JOBWRIGHT_REPO}/.env` automatically inside `jobwright_*.sh`. Do not put API keys in cron definitions.

Optional: `EXA_API_KEY` enables web research for per-job connections.

---

## After repo updates

```bash
cd "${JOBWRIGHT_REPO}"
./scripts/install_hermes_scripts.sh   # if shell scripts changed
./scripts/install_skills.sh           # only if templates/hermes-skill/SKILL.md changed
```

Re-run cron registration (Step 3) only if schedules, deliver targets, or user list changed. Use **edit** when the cron name already exists.

---

## Post-deploy demo (paste after Daily Brief lands)

```text
Show me Daily Brief end to end for user richa in this WhatsApp group.

1. cd /Volumes/ExternalSSD/Projects/jobwright
2. ./scripts/install_hermes_scripts.sh && ./scripts/install_skills.sh
3. Confirm ~/.hermes/scripts/jobwright_brief.sh exists
4. Follow docs/agents/hermes-setup.md: register jobwright-brief/send/check-richa at 6:00 / 6:30 / 10:00 daily
5. Delete any job-apply-* crons for richa
6. Update this group's channel_overrides system_prompt (see docs/agents/whatsapp-group-jobwright.md). Bind cursor-agent. Restart gateway if needed.
7. jobwright --user richa doctor && jobwright --user richa status
8. Trigger now: JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_brief.sh
9. When DIGEST is ready, post it here. I will reply materials 1 — send DOCX as documents.
10. Report: cron names, next run times, job count, DOCX paths, failures.

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
  --deliver "whatsapp:..." \
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
