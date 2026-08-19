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


def _run_hermes(args: list[str]) -> dict:
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
