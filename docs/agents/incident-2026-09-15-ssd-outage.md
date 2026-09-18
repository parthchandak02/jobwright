shell-init: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
chdir: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
shell-init: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
chdir: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
shell-init: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
chdir: error retrieving current directory: getcwd: cannot access parent directories: Interrupted system call
# Incident: jobwright.parthchandak.info Outage — SSD Disconnect / Tunnel Error 1033

- **Date:** 2026-09-15 (down); mitigated same day
- **Status:** Mitigated; root cause of the SSD disconnect **still open** (see "Open research" below)
- **Severity:** Production site outage for jobwright.parthchandak.info (Richa job search / Richa profile)

---

## What happened (timeline)

| Time (PDT) | Event |
|---|---|
| ~Sep 15 morning | `jobwright.parthchandak.info` went down. |
| 13:54 | Parth directed via WhatsApp: *"use cloudflared cli to help fix these issues Error 1033 Ray ID: a3ba86d1af92f0a"* — confirmed in `~/.hermes/logs/agent.log` (`2026-09-15 13:54:52,512`, session `20260817_150435_c3ac4e`). |
| 14:17 | Repo unreadable: `ls: /Volumes/ExternalSSD/Projects/jobwright: Interrupted system call` — confirmed in `~/.hermes/logs/agent.log` (line 3125). This is the documented SSD failure mode. |
| During outage | The jobwright API was brought up on a **temporary port 8002** as a workaround while the SSD was flaky. |
| After fix | Cloudflare Tunnel restored using the `cloudflared` CLI. Tunnel + API both taken over under **pm2** as `jobwright-tunnel` and `jobwright-api`. |
| Sep 16 21:51 | SSD still intermittent: `Interrupted system call` again on `/Volumes/ExternalSSD` — confirmed in `~/.hermes/logs/agent.log` (`2026-09-16 21:51:02,214`). **The underlying issue is not resolved.** |

## Root-cause chain

```
/Volumes/ExternalSSD volume drops/disconnects
  -> jobwright API (homed on that volume) loses its working tree / can't read
  -> API restarted on a TEMPORARY port 8002 (ad-hoc patch, not the configured port)
  -> Cloudflare Tunnel (jobwright.parthchandak.info) pointed at the expected port
     finds nothing / mis-routes -> Tunnel Error 1033 (No connection to origin)
     -> site down
  -> Mitigation: restored tunnel via cloudflared CLI; pinned API + tunnel under pm2
```

## What fixed it

1. `cloudflared` CLI used to re-establish the Tunnel connection for `jobwright.parthchandak.info`.
2. The jobwright API process and the tunnel are now **owned by pm2**:
   - `jobwright-api`
   - `jobwright-tunnel`
3. `pm2 save` was run so pm2 restores both on reboot — **re-check this after reboot; do not rely on it silently.**

## Permanent rules (binding)

1. **NO ad-hoc port changes.** Never move the jobwright API to a temp port (e.g. 8002) as a workaround. If a port is wrong, fix the config properly.
2. **pm2 owns the service processes.** `jobwright-api` and `jobwright-tunnel` must stay managed under pm2 so they survive crashes and reboots. Do not hand-run `cloudflared` or the API as a foreground process for day-to-day operation.
3. **Persist pm2 config for reboot:** run `pm2 save` after any pm2 process/ecosystem change (and verify with `pm2 list` that both processes carry `er` / a saved state).
4. **SSD health-check before touching the repo.** The volume throws intermittent I/O errors (`Interrupted system call`, `ls` hanging). Always read/browse the repo with **short timeouts** — the repo IS unreadable today (2026-09-17). Never run unbounded `ls`/`find`/`cat`/`git` against `/Volumes/ExternalSSD`.

## SSD health-check procedure (for agents)

Use **short-timeout, bounded** reads only. Example:

```bash
# the `timeout` command may not exist on macOS — use gtimeout (coreutils) or a python alarm/thread bound:
gtimeout 20 ls /Volumes/ExternalSSD/Projects/jobwright || echo "SSD HUNG"
gtimeout 20 cat /Volumes/ExternalSSD/Projects/jobwright/AGENTS.md || echo "SSD HUNG"
```

Rules when the SSD misbehaves:

1. Do **NOT** retry more than twice. A hang / `Interrupted system call` means the volume is wedged again — retrying wastes runs and can compound the outage.
2. If blocked, proceed via the **staging directory** workflow described in `RESTORE.md` / this repo's docs, never by "fixing" the volume on the live repo.
3. Record every SSD failure (timestamp + command + error) in the handoff doc so the disconnect pattern stays visible.
4. Never run `git` against the SSD repo while it is hanging.

## Open research (STILL UNRESOLVED)

Why `/Volumes/ExternalSSD` keeps disconnecting is **not documented**. On Sep 15 a `/goal` sub-agent launch was started to investigate "why the SSD keeps disconnecting (common Mac issue? resolutions?)" — **the results were never written into this repo, and the investigation is marked OPEN.** Parth explicitly asked to document the root cause.

Hand-off thread: see `docs/agents/handoff-2026-09-17.md` → open thread (a) "SSD disconnect root-cause research never documented".

---

### Sources / verification
- `~/.hermes/logs/agent.log` lines 2964 (Error 1033 msg, Sep 15 13:54), 3080/3125 (`Interrupted system call`, Sep 15 14:00/14:17), 6827 (`Interrupted system call`, Sep 16 21:51).
- WhatsApp chat `120363427224277278@g.us` (Sep 15–17).
- Hermes session `20260817_150435_c3ac4e`.
- Details of the temp port 8002 and the pm2 process names are **reported from the incident session; the number-specific claims (port, process names) were not independently re-verified against live pm2 state** because the repo/SSD was unreadable at write time.