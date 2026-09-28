"""Best-effort sync of the daily brief Hermes cron with users.yaml."""

from __future__ import annotations

import os
import re
import subprocess

_JOB_ID_RE = re.compile(r"^\s+([a-f0-9]{8,})\s+\[")
_NAME_RE = re.compile(r"Name:\s+(\S.*?)\s*$")


_LEGACY_CRON_SUFFIXES = ("send", "check")
_LEGACY_CRON_PREFIXES = ("job-apply-morning", "job-apply-digest", "job-apply-watchdog")


def brief_cron_name(user_id: str) -> str:
    return f"jobwright-brief-{user_id}"


def legacy_cron_names(user_id: str) -> list[str]:
    """Retired digest/send/check crons that false-alarm after the notify flow."""
    names = [f"jobwright-{suffix}-{user_id}" for suffix in _LEGACY_CRON_SUFFIXES]
    names.extend(f"{prefix}-{user_id}" for prefix in _LEGACY_CRON_PREFIXES)
    return names


def find_cron_id(listing: str, name: str) -> str | None:
    """Parse `hermes cron list` text for the job id with this Name."""
    current_id = None
    for line in listing.splitlines():
        id_match = _JOB_ID_RE.match(line)
        if id_match:
            current_id = id_match.group(1)
            continue
        name_match = _NAME_RE.search(line)
        if name_match and name_match.group(1) == name:
            return current_id
    return None


def sync_brief_cron(user_id: str, schedule: str, deliver: str) -> dict:
    """Edit the existing ``jobwright-brief-<user>`` cron. Does not create one.

    Also pauses retired send/check/digest crons for the same user when found.

    Returns ``synced``, ``cron_id``, ``name``, optional ``legacy_paused``, and optional ``error``.
    """
    name = brief_cron_name(user_id)
    listing = _run_hermes(["cron", "list"])
    if listing.get("error"):
        return {"synced": False, "name": name, "cron_id": None, "error": listing["error"]}

    stdout = listing.get("stdout") or ""
    legacy_paused = pause_legacy_crons(user_id, stdout)

    cron_id = find_cron_id(stdout, name)
    if not cron_id:
        return {
            "synced": False,
            "name": name,
            "cron_id": None,
            "legacy_paused": legacy_paused,
            "error": f"No Hermes cron named {name}. Register it with hermes-setup.md.",
        }

    edit = ["cron", "--accept-hooks", "edit", cron_id, "--schedule", schedule]
    if deliver.strip():
        edit.extend(["--deliver", deliver.strip()])
    result = _run_hermes(edit)
    if result.get("error"):
        return {
            "synced": False,
            "name": name,
            "cron_id": cron_id,
            "legacy_paused": legacy_paused,
            "error": result["error"],
        }
    return {
        "synced": True,
        "name": name,
        "cron_id": cron_id,
        "legacy_paused": legacy_paused,
        "error": None,
    }


def pause_legacy_crons(user_id: str, listing: str | None = None) -> list[str]:
    """Pause/delete retired digest/send/check crons for ``user_id`` when present."""
    if listing is None:
        result = _run_hermes(["cron", "list"])
        if result.get("error"):
            return []
        listing = result.get("stdout") or ""

    paused: list[str] = []
    for legacy_name in legacy_cron_names(user_id):
        cron_id = find_cron_id(listing, legacy_name)
        if not cron_id:
            continue
        for action in (["cron", "pause", cron_id], ["cron", "delete", cron_id]):
            proc = _run_hermes(action)
            if proc.get("error"):
                break
        paused.append(legacy_name)
    return paused


def hermes_dry_run() -> bool:
    """JOBWRIGHT_HERMES_DRY_RUN=1: never change real Hermes crons or send messages (sandboxes)."""
    return os.environ.get("JOBWRIGHT_HERMES_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _run_hermes(args: list[str]) -> dict:
    if hermes_dry_run() and args[:2] != ["cron", "list"]:
        import logging

        logging.getLogger(__name__).warning("HERMES DRY RUN: would run hermes %s", " ".join(args))
        return {"stdout": ""}
    env = os.environ.copy()
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    try:
        proc = subprocess.run(
            ["hermes", *args],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return {"error": "hermes CLI not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"error": "hermes cron timed out"}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return {"error": detail}
    return {"stdout": proc.stdout or ""}


# ---------------------------------------------------------------------------
# Create / update / remove (onboarding and admin, not just edits)
# ---------------------------------------------------------------------------

WATCHDOG_CRON_NAME = "jobwright-ops-watchdog"


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def _hermes_scripts_dir():
    from pathlib import Path

    return Path(os.path.expanduser(os.environ.get("JOBWRIGHT_HERMES_SCRIPTS_DIR") or "~/.hermes/scripts"))


def write_brief_wrapper(user_id: str) -> str:
    """Per-user wrapper Hermes runs; pins user, users root and repo. Returns its name."""
    from jobwright.users import USERS_ROOT, get_user

    if hermes_dry_run():
        return f"wrap_{brief_cron_name(user_id)}.sh"

    user = get_user(user_id)
    data_dir = user.resolve_data_dir() if user else USERS_ROOT / user_id
    name = f"wrap_{brief_cron_name(user_id)}.sh"
    path = _hermes_scripts_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        "# Generated by jobwright (hermes_cron.write_brief_wrapper). Do not hand-edit:\n"
        "# settings belong in users.yaml or the user's .env.\n"
        "set -euo pipefail\n"
        f'export JOBWRIGHT_USER="{user_id}"\n'
        f'export JOBWRIGHT_USERS_ROOT="{USERS_ROOT}"\n'
        f'export JOBWRIGHT_DIR="{data_dir}"\n'
        f'export JOBWRIGHT_REPO="{_repo_root()}"\n'
        'export PATH="${HOME}/.local/bin:${PATH}"\n'
        f'exec bash "{_repo_root()}/scripts/jobwright_brief.sh"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return name


def brief_cron_installed(user_id: str) -> bool:
    """Cheap check: the per-user wrapper exists (written whenever the brief cron is ensured)."""
    return (_hermes_scripts_dir() / f"wrap_{brief_cron_name(user_id)}.sh").exists()


def ensure_brief_cron(user_id: str, schedule: str) -> dict:
    """Create or update ``jobwright-brief-<user>`` (no-agent, silent delivery).

    The launcher prints nothing on success and the brief sends its own WhatsApp
    notice, so the cron delivers to ``local``: a bridge outage can no longer
    turn a successful run into a "failed delivery".
    """
    name = brief_cron_name(user_id)
    script = write_brief_wrapper(user_id)
    listing = _run_hermes(["cron", "list"])
    if listing.get("error"):
        return {"ok": False, "name": name, "error": listing["error"]}
    cron_id = find_cron_id(listing.get("stdout") or "", name)
    common = ["--script", script, "--no-agent", "--deliver", "local", "--workdir", str(_repo_root())]
    if cron_id:
        result = _run_hermes(["cron", "--accept-hooks", "edit", cron_id, "--schedule", schedule, *common])
    else:
        result = _run_hermes(["cron", "--accept-hooks", "create", schedule, "--name", name, *common])
    if result.get("error"):
        return {"ok": False, "name": name, "cron_id": cron_id, "error": result["error"]}
    if not cron_id:
        again = _run_hermes(["cron", "list"])
        cron_id = find_cron_id(again.get("stdout") or "", name)
    return {"ok": True, "name": name, "cron_id": cron_id, "created": cron_id is not None, "error": None}


def remove_brief_cron(user_id: str) -> dict:
    name = brief_cron_name(user_id)
    listing = _run_hermes(["cron", "list"])
    cron_id = find_cron_id(listing.get("stdout") or "", name)
    if not cron_id:
        return {"ok": True, "name": name, "removed": False}
    result = _run_hermes(["cron", "delete", cron_id])
    return {"ok": not result.get("error"), "name": name, "removed": not result.get("error"),
            "error": result.get("error")}


BACKUP_CRON_NAME = "jobwright-backup"


def _ensure_script_cron(name: str, script_name: str, body: str, schedule: str) -> dict:
    """Create/update a silent no-agent cron that runs a generated script."""
    if hermes_dry_run():
        _run_hermes(["cron", "create", schedule, "--name", name])
        return {"ok": True, "error": None, "cron_id": None, "dry_run": True}
    path = _hermes_scripts_dir() / script_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    listing = _run_hermes(["cron", "list"])
    if listing.get("error"):
        return {"ok": False, "error": listing["error"]}
    cron_id = find_cron_id(listing.get("stdout") or "", name)
    common = ["--script", script_name, "--no-agent", "--deliver", "local", "--workdir", str(_repo_root())]
    if cron_id:
        result = _run_hermes(["cron", "--accept-hooks", "edit", cron_id, "--schedule", schedule, *common])
    else:
        result = _run_hermes(["cron", "--accept-hooks", "create", schedule, "--name", name, *common])
    return {"ok": not result.get("error"), "error": result.get("error"), "cron_id": cron_id}


def ensure_backup_cron(schedule: str = "30 2 * * *", dest: str = "") -> dict:
    """Nightly `jobwright ops backup` (alerts the operator on failure)."""
    from jobwright.users import USERS_ROOT

    py = _repo_root() / ".venv" / "bin" / "python3"
    dest_env = f'export JOBWRIGHT_BACKUP_DIR="{dest}"\n' if dest else ""
    body = (
        "#!/usr/bin/env bash\n"
        "# Generated by jobwright (hermes_cron.ensure_backup_cron).\n"
        "set -euo pipefail\n"
        f'export JOBWRIGHT_USERS_ROOT="{USERS_ROOT}"\n'
        f"{dest_env}"
        f'export PYTHONPATH="{_repo_root()}/src"\n'
        'export PATH="${HOME}/.local/bin:${PATH}"\n'
        f'cd "{_repo_root()}"\n'
        f'"{py}" -m jobwright.cli ops backup >/dev/null 2>&1 || true\n'
    )
    return _ensure_script_cron(BACKUP_CRON_NAME, "jobwright_backup.sh", body, schedule)


def ensure_watchdog_cron(schedule: str = "30 8 * * *") -> dict:
    """Daily missed-run watchdog; alerts go out via jobwright ops (hermes send)."""
    script_name = "jobwright_ops_watchdog.sh"
    if hermes_dry_run():
        _run_hermes(["cron", "create", schedule, "--name", WATCHDOG_CRON_NAME])
        return {"ok": True, "error": None, "cron_id": None, "dry_run": True}
    path = _hermes_scripts_dir() / script_name
    path.parent.mkdir(parents=True, exist_ok=True)
    from jobwright.users import USERS_ROOT

    py = _repo_root() / ".venv" / "bin" / "python3"
    path.write_text(
        "#!/usr/bin/env bash\n"
        "# Generated by jobwright (hermes_cron.ensure_watchdog_cron).\n"
        "set -euo pipefail\n"
        f'export JOBWRIGHT_USERS_ROOT="{USERS_ROOT}"\n'
        f'export PYTHONPATH="{_repo_root()}/src"\n'
        'export PATH="${HOME}/.local/bin:${PATH}"\n'
        f'cd "{_repo_root()}"\n'
        f'"{py}" -m jobwright.cli ops watchdog >/dev/null 2>&1 || true\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    listing = _run_hermes(["cron", "list"])
    if listing.get("error"):
        return {"ok": False, "error": listing["error"]}
    cron_id = find_cron_id(listing.get("stdout") or "", WATCHDOG_CRON_NAME)
    common = ["--script", script_name, "--no-agent", "--deliver", "local", "--workdir", str(_repo_root())]
    if cron_id:
        result = _run_hermes(["cron", "--accept-hooks", "edit", cron_id, "--schedule", schedule, *common])
    else:
        result = _run_hermes(["cron", "--accept-hooks", "create", schedule, "--name", WATCHDOG_CRON_NAME, *common])
    return {"ok": not result.get("error"), "error": result.get("error"), "cron_id": cron_id}


WEEKLY_SUMMARY_CRON_NAME = "jobwright-weekly-summary"


def ensure_weekly_summary_cron(schedule: str = "0 18 * * 0") -> dict:
    """Sunday 18:00 `jobwright summary` for every profile (each may opt out in users.yaml)."""
    from jobwright.users import USERS_ROOT

    py = _repo_root() / ".venv" / "bin" / "python3"
    body = (
        "#!/usr/bin/env bash\n"
        "# Generated by jobwright (hermes_cron.ensure_weekly_summary_cron).\n"
        "set -euo pipefail\n"
        f'export JOBWRIGHT_USERS_ROOT="{USERS_ROOT}"\n'
        f'export PYTHONPATH="{_repo_root()}/src"\n'
        'export PATH="${HOME}/.local/bin:${PATH}"\n'
        "unset JOBWRIGHT_USER\n"
        f'cd "{_repo_root()}"\n'
        f'"{py}" -m jobwright.cli summary >/dev/null 2>&1 || true\n'
    )
    return _ensure_script_cron(WEEKLY_SUMMARY_CRON_NAME, "jobwright_weekly_summary.sh", body, schedule)
