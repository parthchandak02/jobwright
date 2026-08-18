# WhatsApp group context (jobwright)

Use this when Parth asks whether Hermes has **everything needed for jobwright** in **this WhatsApp group**.

## This group

| Field | Value |
|-------|--------|
| WhatsApp target | `whatsapp:120363427224277278@g.us` |
| Registry user | `richa` (Richa Jatia) |
| `apply_enabled` | `false` (find-only until user opts in) |
| Repo | `/Volumes/ExternalSSD/Projects/jobwright` |
| User data | `/Volumes/ExternalSSD/Projects/jobwright/users/richa/` |

```bash
bash /Volumes/ExternalSSD/Projects/jobwright/scripts/resolve_user_from_whatsapp.sh 'whatsapp:120363427224277278@g.us'
# → richa
```

## Skills for this group

| Skill | Role |
|-------|------|
| **pp-job-apply** / **jobwright** | Primary operator loader |
| **hermes-cron-jobs** | Schedule/edit crons |
| **cursor-agent** | Repo fixes when users report bugs |

## Live `config.yaml` (whatsapp section)

Put the durable prompt below into `~/.hermes/config.yaml` (do not commit secrets). After edit: `hermes gateway restart`, then `/new` in the group.

```yaml
  channel_skill_bindings:
    - id: "120363427224277278@g.us"
      skills:
        - pp-job-apply
        - hermes-cron-jobs
        - cursor-agent
  channel_overrides:
    120363427224277278@g.us:
      system_prompt: |
        You are the Hermes operator for jobwright (user: richa).
        JOBWRIGHT_REPO=/Volumes/ExternalSSD/Projects/jobwright
        apply_enabled: false until opted in.

        Every turn: load pp-job-apply; resolve WhatsApp sender → user before profile commands.
        Daily Brief crons: jobwright-brief-richa, jobwright-send-richa, jobwright-check-richa
          (never job-apply-*). Scripts: ~/.hermes/scripts/jobwright_*.sh
        Attachments: copy → users/richa/references/inbox/ → file to resume/base.* or connections.csv
          (backup first). See docs/agents/whatsapp-routing.md.
        materials N → materials --json or jobwright_deliver_materials.sh N → send DOCX as WhatsApp documents.
        send digest → jobwright_send.sh stdout posted here. find jobs now → jobwright_brief.sh (detached).
        Brief LLM: JOBWRIGHT_LLM_MODEL=gpt-oss-120b (Fireworks). Validation: lenient. Never use BRIEF_SMOKE for daily cron.
        Code/bugs: reproduce with doctor/status/logs; fix via cursor-agent or small patches;
          never commit users/ or .env; re-run install_hermes_scripts.sh / install_skills.sh if needed.
        Docs: docs/agents/whatsapp-group-jobwright.md, hermes-operator-guide.md, whatsapp-routing.md
```

## Crons (shell-only, `--no-agent`)

| Name | Schedule | Script |
|------|----------|--------|
| `jobwright-brief-richa` | `0 6 * * *` | `wrap_jobwright-brief-richa.sh` |
| `jobwright-send-richa` | `30 6 * * *` | `wrap_jobwright-send-richa.sh` |
| `jobwright-check-richa` | `0 10 * * *` | `wrap_jobwright-check-richa.sh` |

Delete any `job-apply-*` crons if still present.

```bash
hermes cron list | grep -E 'jobwright-|job-apply-'
```

## Scripts

```bash
cd /Volumes/ExternalSSD/Projects/jobwright
./scripts/install_hermes_scripts.sh
```

Need: `jobwright_brief.sh`, `jobwright_send.sh`, `jobwright_check.sh`, `jobwright_send_materials.sh`, `jobwright_confirm.sh`, `jobwright_on_confirm.sh`, `run_daily_brief.sh`, `resolve_user_from_whatsapp.sh`.

## Inbound (this group)

| User says | Action |
|-----------|--------|
| `job status` | `jobwright --user richa status` |
| `verify brief` | `JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_verify.sh` |
| `find jobs now` | `JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_brief.sh` (~20–30 min; monitor `logs/brief_YYYYMMDD.log`) |
| `send digest` | `JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_send.sh` → post stdout here |
| `materials 1` | `jobwright_deliver_materials.sh 1` or materials JSON → send DOCX documents |
| resume / Connections.csv | File into `users/richa/` (backup first) |
| `CONFIRM APPLY` | Only if `apply_enabled`; confirm scripts |
| `bug: …` | Continuous improvement in operator guide |

## Paste to Hermes: end-to-end demo (high priority)

```text
Show me Daily Brief end to end for user richa in this WhatsApp group.

1. cd /Volumes/ExternalSSD/Projects/jobwright
2. ./scripts/install_hermes_scripts.sh && ./scripts/install_skills.sh
3. Confirm ~/.hermes/scripts/jobwright_brief.sh exists
4. Follow docs/agents/hermes-setup.md: register jobwright-brief/send/check-richa at 6:00 / 6:30 / 10:00 daily
5. Delete or pause any job-apply-* crons for richa
6. Update this group's channel_overrides system_prompt to the text in docs/agents/whatsapp-group-jobwright.md (Daily Brief names + cursor-agent binding). Restart gateway if needed.
7. jobwright --user richa doctor && jobwright --user richa status
8. Trigger now: JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_brief.sh
9. When DIGEST is ready, post it here (or wait for jobwright-send). Then I will reply materials 1 — send the DOCX files as documents.
10. Report: cron names, next run times, job count, DOCX paths, and anything that failed.

Also confirm you know: resolve sender→richa, file uploads go to users/richa/ with backup, and how to fix bugs via continuous improvement in hermes-operator-guide.md.
```

## Health check

```bash
export JOBWRIGHT_REPO=/Volumes/ExternalSSD/Projects/jobwright
jobwright --user richa doctor
jobwright --user richa status
test -f ~/.hermes/scripts/jobwright_brief.sh && echo scripts_OK
```
