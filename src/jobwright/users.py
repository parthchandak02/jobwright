"""Multi-profile user registry.

Registry file: <repo>/users/users.yaml
Per-user data: <repo>/users/<user_id>/  (full JOBWRIGHT_DIR)
Override: JOBWRIGHT_USERS_ROOT
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _default_users_root() -> Path:
    override = os.environ.get("JOBWRIGHT_USERS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "users"


USERS_ROOT = _default_users_root()
REGISTRY_PATH = USERS_ROOT / "users.yaml"

_USER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def describe_cron_schedule(expr: str) -> str:
    """Turn a 5-field cron into a short label, or return the expression as-is."""
    parts = (expr or "").split()
    if len(parts) != 5:
        return expr or ""
    minute, hour, dom, month, dow = parts
    clock = _cron_clock(minute, hour)
    if not clock or dom != "*" or month != "*":
        return expr
    if dow == "*":
        return f"Every day at {clock}"
    if dow in {"1-5", "MON-FRI", "mon-fri"}:
        return f"Weekdays at {clock}"
    return expr


def host_timezone_name() -> str:
    """Abbreviation for the machine that runs Hermes cron (e.g. PDT)."""
    return datetime.now().astimezone().tzname() or "local time"


def _cron_clock(minute: str, hour: str) -> str | None:
    if not minute.isdigit() or not hour.isdigit():
        return None
    h, m = int(hour), int(minute)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def apply_clock_to_cron(expr: str, hour: int, minute: int) -> str:
    """Set hour/minute on a 5-field cron; keep day-of-week and other fields."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Time must be a valid hour and minute.")
    parts = (expr or "").split()
    if len(parts) != 5:
        return f"{minute} {hour} * * *"
    parts[0] = str(minute)
    parts[1] = str(hour)
    return " ".join(parts)


def validate_brief_schedule(expr: str) -> str:
    """Require a 5-field cron with a fixed clock time (dashboard time picker)."""
    parts = (expr or "").split()
    if len(parts) != 5:
        raise ValueError("Schedule must be a 5-field cron expression.")
    if not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError("Schedule hour and minute must be fixed numbers.")
    hour, minute = int(parts[1]), int(parts[0])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Schedule time is out of range.")
    return " ".join(parts)


@dataclass
class UserRecord:
    user_id: str
    name: str = ""
    whatsapp_target: str = ""
    apply_enabled: bool = False
    schedule: str = "0 6 * * *"  # daily brief at 6:00 (all days)
    digest_schedule: str = "30 6 * * *"  # WhatsApp send at 6:30
    notes: str = ""
    # Optional overrides; empty = use default path under USERS_ROOT
    data_dir: str = ""

    def resolve_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).expanduser()
        return USERS_ROOT / self.user_id


def _empty_registry() -> dict[str, Any]:
    return {"users": []}


def load_registry() -> dict[str, Any]:
    """Load users.yaml; return empty registry if missing."""
    if not REGISTRY_PATH.exists():
        return _empty_registry()
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if "users" not in data or not isinstance(data["users"], list):
        data["users"] = []
    return data


def save_registry(data: dict[str, Any]) -> None:
    USERS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        USERS_ROOT.chmod(0o700)
    except OSError:
        pass
    REGISTRY_PATH.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    try:
        REGISTRY_PATH.chmod(0o600)
    except OSError:
        pass


def list_users() -> list[UserRecord]:
    data = load_registry()
    out: list[UserRecord] = []
    for raw in data.get("users", []):
        if not isinstance(raw, dict) or not raw.get("user_id"):
            continue
        out.append(_from_dict(raw))
    return out


def get_user(user_id: str) -> UserRecord | None:
    for u in list_users():
        if u.user_id == user_id:
            return u
    return None


def _normalize_whatsapp_target(target: str) -> str:
    """Normalize whatsapp deliver targets for comparison."""
    t = (target or "").strip().lower()
    if not t:
        return ""
    if not t.startswith("whatsapp:"):
        t = f"whatsapp:{t}"
    return t


def find_user_by_whatsapp(target: str) -> UserRecord | None:
    """Match a Hermes/WhatsApp deliver target to a registry user."""
    needle = _normalize_whatsapp_target(target)
    if not needle:
        return None
    bare = needle.removeprefix("whatsapp:")
    for u in list_users():
        wt = _normalize_whatsapp_target(u.whatsapp_target)
        if not wt:
            continue
        if wt == needle or wt.removeprefix("whatsapp:") == bare:
            return u
    return None


def _from_dict(raw: dict[str, Any]) -> UserRecord:
    return UserRecord(
        user_id=str(raw["user_id"]),
        name=str(raw.get("name") or ""),
        whatsapp_target=str(raw.get("whatsapp_target") or ""),
        apply_enabled=bool(raw.get("apply_enabled", False)),
        schedule=str(raw.get("schedule") or "0 */3 * * 1-5"),
        digest_schedule=str(raw.get("digest_schedule") or "15 */3 * * 1-5"),
        notes=str(raw.get("notes") or ""),
        data_dir=str(raw.get("data_dir") or ""),
    )


def _to_dict(user: UserRecord) -> dict[str, Any]:
    d = asdict(user)
    # Omit empty data_dir for cleaner YAML
    if not d.get("data_dir"):
        d.pop("data_dir", None)
    if not d.get("notes"):
        d.pop("notes", None)
    return d


def validate_user_id(user_id: str) -> None:
    if not _USER_ID_RE.match(user_id):
        raise ValueError(
            f"Invalid user_id '{user_id}'. Use 2-32 chars: lowercase letter, "
            "then letters/digits/hyphen/underscore (e.g. richa)."
        )


def add_user(
    user_id: str,
    name: str = "",
    whatsapp_target: str = "",
    apply_enabled: bool = False,
    schedule: str = "0 */3 * * 1-5",
    digest_schedule: str = "15 */3 * * 1-5",
    notes: str = "",
) -> UserRecord:
    """Register a user and create their data directory skeleton."""
    validate_user_id(user_id)
    if get_user(user_id) is not None:
        raise ValueError(f"User '{user_id}' already exists.")

    user = UserRecord(
        user_id=user_id,
        name=name or user_id,
        whatsapp_target=whatsapp_target,
        apply_enabled=apply_enabled,
        schedule=schedule,
        digest_schedule=digest_schedule,
        notes=notes,
    )
    data_dir = user.resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        data_dir.chmod(0o700)
    except OSError:
        pass

    for sub in ("tailored_resumes", "cover_letters", "logs", "chrome-workers", "apply-workers",
                "resume", "cover-letter", "cover-letter/examples", "references", "references/inbox"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    # No per-user .env: API keys are global (see config.global_env_path).
    # Per-user data dirs hold only profile/resume/searches/db and generated output.

    data = load_registry()
    data["users"].append(_to_dict(user))
    save_registry(data)
    return user


def remove_user(user_id: str, delete_data: bool = False) -> UserRecord:
    user = get_user(user_id)
    if user is None:
        raise ValueError(f"User '{user_id}' not found.")
    data = load_registry()
    data["users"] = [u for u in data["users"] if u.get("user_id") != user_id]
    save_registry(data)
    if delete_data:
        import shutil
        data_dir = user.resolve_data_dir()
        if data_dir.exists() and data_dir != Path.home() / ".jobwright":
            shutil.rmtree(data_dir)
    return user


def update_user(user_id: str, **fields: Any) -> UserRecord:
    user = get_user(user_id)
    if user is None:
        raise ValueError(f"User '{user_id}' not found.")
    allowed = {
        "name", "whatsapp_target", "apply_enabled", "schedule",
        "digest_schedule", "notes", "data_dir",
    }
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Cannot update field '{key}'")
        setattr(user, key, value)
    data = load_registry()
    data["users"] = [
        _to_dict(user) if u.get("user_id") == user_id else u
        for u in data["users"]
    ]
    save_registry(data)
    return user


def is_apply_enabled(user_id: str | None = None) -> bool:
    """Return whether live apply is enabled for a registry user.

    If user_id is None (legacy single-user ~/.jobwright), apply is allowed
    (backward compatible — gated only by APPLY_CONFIRMED).
    """
    if not user_id:
        return True
    user = get_user(user_id)
    if user is None:
        return False
    return bool(user.apply_enabled)
