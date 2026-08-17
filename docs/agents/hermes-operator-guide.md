# Hermes operator guide (jobwright end-to-end)

This is the **primary guide for Hermes agents** operating jobwright. Hermes loads the thin skill from `~/.hermes/skills/` (see [install-hermes-skill.md](install-hermes-skill.md)); this file lives in your clone at `docs/agents/`.

## Constants

```bash
export JOBWRIGHT_REPO="${JOBWRIGHT_REPO:-/Volumes/ExternalSSD/Projects/jobwright}"
export JOBWRIGHT_USERS_ROOT="${JOBWRIGHT_USERS_ROOT:-${JOBWRIGHT_REPO}/users}"
cd "${JOBWRIGHT_REPO}"
```

| What | Path |
|------|------|
| Repo | `${JOBWRIGHT_REPO}` |
| Registry | `${JOBWRIGHT_USERS_ROOT}/users.yaml` |
| User data | `${JOBWRIGHT_USERS_ROOT}/<user_id>/` |
| Hermes scripts | `~/.hermes/scripts/job_apply_*.sh` |
| Skill (this doc) | `${JOBWRIGHT_REPO}/docs/agents/hermes-operator-guide.md` |
| Human WhatsApp guide | `${JOBWRIGHT_REPO}/docs/agents/whatsapp-user-guide.md` |

## Per-user folder layout (canonical)

Each user lives at `users/<user_id>/`:

```
<user_id>/
├── profile.json              # prefs, tailor_mode, cover_letter_mode
├── searches.yaml             # job discovery filters
├── connections.csv           # LinkedIn export (1st-degree network)
├── resume/
│   ├── base.txt              # source resume for AI stages
│   └── base.pdf              # formatted resume (optional)
├── cover-letter/
│   ├── template.txt          # cover letter skeleton
│   └── examples/             # real sent letters (.txt)
├── references/
│   └── inbox/                # UNSORTED uploads only — file into resume/ or cover-letter/
├── tailored_resumes/         # generated per job
├── cover_letters/            # generated per job
├── target_companies.yaml     # from `targets` command
├── jobwright.db
└── logs/
```

**Rule:** When a user uploads a file on WhatsApp, save to `references/inbox/` first, then **move** to the correct structured folder. Do not leave organized assets in `references/`.

Legacy symlinks `resume.txt` / `resume.pdf` at user root may exist; prefer `resume/base.*`.

## Step 0: Resolve WhatsApp sender → user

```bash
USER_ID="$(bash "${JOBWRIGHT_REPO}/scripts/resolve_user_from_whatsapp.sh" 'whatsapp:SENDER_JID')" \
  || { echo "Unknown sender"; exit 1; }
export JOBWRIGHT_USER="${USER_ID}"
export JOBWRIGHT_DIR="${JOBWRIGHT_USERS_ROOT}/${USER_ID}"
```

## End-to-end workflows

### A. Job discovery + digest (automatic + on demand)

| Trigger | Action |
|---------|--------|
| Cron (weekdays, ~every 3h) | `job_apply_morning.sh` → digest cron → WhatsApp |
| User: "find jobs now" | `JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/job_apply_morning.sh` |
| User: "job status" | `jobwright --user $USER_ID status` |

Pipeline stages: discover → enrich → score → portfolio → tailor → cover.

### B. Resume tailoring (per job)

```bash
jobwright --user $USER_ID run tailor --validation lenient
# or full pipeline:
jobwright --user $USER_ID run discover enrich score portfolio tailor cover -w 4 --min-score 5 --validation lenient
```

Output: `users/<id>/tailored_resumes/`

Check `profile.json` → `tailor_mode` (`keyword_swap` = same-length keyword edits when implemented).

### C. Cover letters (template + examples)

Input materials:

- `cover-letter/template.txt`
- `cover-letter/examples/*.txt`

```bash
jobwright --user $USER_ID run cover --validation lenient
```

Output: `users/<id>/cover_letters/`

When user sends new examples, save as `cover-letter/examples/<short-name>.txt`.

### D. LinkedIn network ranking (1st degree only)

Requires `connections.csv`. **No 2nd-degree support.**

```bash
jobwright --user $USER_ID network
```

Paste ranked digest to WhatsApp. Replace dummy CSV with user's LinkedIn export when provided.

### E. Target company list

```bash
jobwright --user $USER_ID targets
# optional: merge into searches
jobwright --user $USER_ID targets --merge-searches
```

### F. Live apply (opt-in only)

Only if `apply_enabled: true` in registry **and** user sends `CONFIRM APPLY`:

```bash
JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/job_apply_confirm.sh
JOBWRIGHT_USER=$USER_ID bash ~/.hermes/scripts/job_apply_on_confirm.sh
```

Never use `jobwright apply --live --url ...` for WhatsApp users.

## Onboarding a new user

```bash
cd "${JOBWRIGHT_REPO}"
jobwright users add <id> --name "Full Name" --whatsapp "whatsapp:..." --template nontech-bay-area
# Creates resume/, cover-letter/, references/inbox/ skeleton
# Write resume/base.txt, profile.json, searches.yaml
# Optional: connections.csv, cover-letter/template.txt, examples/
./scripts/install_hermes_scripts.sh
# Crons: Hermes agent registers via docs/agents/hermes-setup.md
jobwright --user <id> doctor
```

Apply stays OFF unless: `jobwright users set <id> --apply`

## File upload handling (WhatsApp)

| File type | Move to |
|-----------|---------|
| Resume PDF/DOC | Extract text → `resume/base.txt`; PDF → `resume/base.pdf` |
| Cover letter examples | `cover-letter/examples/<name>.txt` |
| Cover letter template | `cover-letter/template.txt` |
| LinkedIn Connections export | `connections.csv` (user root) |
| Unknown / misc | `references/inbox/` then ask user or infer |

After filing, confirm with user on WhatsApp.

## Repo access + improving jobwright (Cursor Agent)

Hermes has full terminal access on the Mac mini. Use it to **run jobwright** and **improve the repo** when users need features the pipeline lacks.

### Working directory

Always `cd "${JOBWRIGHT_REPO}"` before repo commands. Optional: set in `~/.hermes/config.yaml`:

```yaml
terminal:
  backend: local
  cwd: /Volumes/ExternalSSD/Projects/jobwright
```

### Run jobwright CLI

```bash
cd "${JOBWRIGHT_REPO}"
jobwright --user richa doctor
jobwright --user richa status
./bin/job-apply-pp-cli status --agent --user richa
```

### Invoke Cursor Agent to modify the repo

When a user need requires code changes (e.g. `keyword_swap` tailor, digest attachments, new filters):

```bash
cd "${JOBWRIGHT_REPO}"
agent -p --force "$(cat <<'EOF'
Context: jobwright repo at JOBWRIGHT_REPO. User richa needs keyword-only resume tailoring (same length, no new sentences).

Task: Implement tailor_mode keyword_swap in src/jobwright/scoring/tailor.py. Match existing code style. Add tests if straightforward.

Do not commit unless asked. Summarize changes when done.
EOF
)"
```

Rules for repo changes via Cursor Agent:

1. **Scope:** Fix the specific gap blocking the user; no drive-by refactors.
2. **Never commit** `users/` or `.env`.
3. **After code changes:** `./scripts/install_hermes_scripts.sh` if scripts changed; `./scripts/install_skills.sh` if `templates/hermes-skill/` changed.
4. **Verify:** `python3 -m pytest tests/` and `jobwright --user <id> doctor`.
5. **Tell the user** what changed and what to test on WhatsApp.

Alternative: Hermes can edit files directly with `read_file` / `patch` terminal tools for small fixes; use `agent -p` for multi-file features.

### Post-change sync checklist

```bash
cd "${JOBWRIGHT_REPO}"
./scripts/install_skills.sh          # if templates/hermes-skill/SKILL.md changed
./scripts/install_hermes_scripts.sh  # if scripts/*.sh changed
# Crons: Hermes agent — docs/agents/hermes-setup.md (edit existing, do not duplicate)
```

## Health checks

```bash
jobwright --user $USER_ID doctor
tail -50 "${JOBWRIGHT_DIR}/logs/morning_$(date +%Y%m%d).log"
hermes cron list | grep job-apply
test -f ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/SKILL.md && cat ~/.hermes/skills/autonomous-ai-agents/pp-job-apply/JOBWRIGHT_REPO && echo skill OK
```

## Safety (never break)

1. No auto-apply from cron
2. No LinkedIn job apply
3. Live apply only via CONFIRM APPLY + manifest
4. Registry `apply_enabled` defaults false
5. Never commit user data or secrets

## Example: Richa (user `richa`)

| She wants | Hermes does |
|-----------|-------------|
| Fresh jobs | Cron digest or "find jobs now" |
| Tailored resume | Pipeline tailor stage (check tailor_mode) |
| Cover letter | Ensure examples in `cover-letter/examples/`; run cover stage |
| Network help | `jobwright --user richa network` (needs real connections.csv) |
| Target companies | `jobwright --user richa targets` |
| Upload cover letter | Save to `cover-letter/examples/` |

WhatsApp group: `whatsapp:120363427224277278@g.us` (see registry).
