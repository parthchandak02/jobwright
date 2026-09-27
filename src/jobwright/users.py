"""Multi-profile user registry.

Registry file: <repo>/users/users.yaml
Per-user data: <repo>/users/<user_id>/  (full JOBWRIGHT_DIR)
Override: JOBWRIGHT_USERS_ROOT
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
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

DEFAULT_FOLLOWUP_DAYS = 10

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
    # Human gate: when true, the default daily-brief pipeline stops before
    # tailor/cover/pdf/docx and notify sends a review-first list; materials
    # are generated on demand after the user approves a job.
    human_gate: bool = False
    # Notify cap: show the top N jobs by fit score per brief. 0 = uncapped
    # (legacy behavior: send every prepare-stage job).
    brief_top_n: int = 10
    # Optional overrides; empty = use default path under USERS_ROOT
    data_dir: str = ""
    # Cloudflare Access login emails that may open this profile.
    emails: list[str] = field(default_factory=list)
    # Sunday WhatsApp recap (jobwright summary); false opts out.
    weekly_summary: bool = True
    # Applied jobs with no stage change for this many days are "follow-up due".
    followup_days: int = DEFAULT_FOLLOWUP_DAYS

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
    """Atomically rewrite users.yaml (temp file + rename, owner-only)."""
    USERS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        USERS_ROOT.chmod(0o700)
    except OSError:
        pass
    text = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    fd, tmp = tempfile.mkstemp(prefix=".users.", suffix=".yaml", dir=str(USERS_ROOT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, REGISTRY_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def list_admin_emails() -> list[str]:
    """Registry ``admins`` plus JOBWRIGHT_ADMIN_EMAILS (comma-separated)."""
    data = load_registry()
    emails = [normalize_email(e) for e in (data.get("admins") or []) if normalize_email(e)]
    for raw in os.environ.get("JOBWRIGHT_ADMIN_EMAILS", "").split(","):
        e = normalize_email(raw)
        if e and e not in emails:
            emails.append(e)
    return emails


def is_admin_email(email: str | None) -> bool:
    e = normalize_email(email)
    return bool(e) and e in list_admin_emails()


def set_admin_emails(emails: list[str]) -> list[str]:
    data = load_registry()
    cleaned: list[str] = []
    for raw in emails:
        e = normalize_email(raw)
        if e and e not in cleaned:
            cleaned.append(e)
    data["admins"] = cleaned
    save_registry(data)
    return cleaned


def users_for_email(email: str | None) -> list[UserRecord]:
    """Profiles whose ``emails`` list contains this login email."""
    e = normalize_email(email)
    if not e:
        return []
    return [u for u in list_users() if e in {normalize_email(x) for x in u.emails}]


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
        human_gate=bool(raw.get("human_gate", False)),
        brief_top_n=int(raw.get("brief_top_n", 0)),
        data_dir=str(raw.get("data_dir") or ""),
        emails=[normalize_email(e) for e in (raw.get("emails") or []) if normalize_email(e)],
        weekly_summary=bool(raw.get("weekly_summary", True)),
        followup_days=_positive_int(raw.get("followup_days"), DEFAULT_FOLLOWUP_DAYS),
    )


def _positive_int(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def _to_dict(user: UserRecord, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize a user, keeping unknown keys from ``base`` (e.g. jev_hybrid)."""
    d = dict(base or {})
    d.update(asdict(user))
    for key in ("data_dir", "notes", "emails"):
        if not d.get(key):
            d.pop(key, None)
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
    human_gate: bool = False,
    brief_top_n: int = 0,
    emails: list[str] | None = None,
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
        human_gate=human_gate,
        brief_top_n=brief_top_n,
        emails=[normalize_email(e) for e in (emails or []) if normalize_email(e)],
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
        "human_gate", "brief_top_n", "emails", "weekly_summary", "followup_days",
    }
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Cannot update field '{key}'")
        if key == "emails":
            value = [normalize_email(e) for e in (value or []) if normalize_email(e)]
        if key == "followup_days":
            value = int(value)
            if not 1 <= value <= 90:
                raise ValueError("followup_days must be between 1 and 90")
        setattr(user, key, value)
    data = load_registry()
    data["users"] = [
        _to_dict(user, u) if u.get("user_id") == user_id else u
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


DEFAULT_BRIEF_TOP_N = 0  # uncapped legacy default; cap only when explicitly configured (richa: 10)


def get_human_gate(user_id: str | None = None) -> bool:
    """Return whether the default brief pipeline is human-gated for a user.

    When True, the daily brief stops before material generation (tailor/cover/
    pdf/docx) and notify sends a review-first list; materials are produced on
    demand after the user approves. Defaults to False for legacy single-user
    and for any unknown user id.
    """
    if not user_id:
        return False
    user = get_user(user_id)
    if user is None:
        return False
    return bool(user.human_gate)


def get_brief_top_n(user_id: str | None = None) -> int:
    """Return the per-brief notify cap (top N jobs by fit score) for a user.

    0 means uncapped (legacy behavior — send every prepare-stage job).
    Defaults to 10 for legacy single-user and unknown user ids.
    """
    if not user_id:
        return DEFAULT_BRIEF_TOP_N
    user = get_user(user_id)
    if user is None:
        return DEFAULT_BRIEF_TOP_N
    return max(int(user.brief_top_n), 0)


def get_followup_days(user_id: str | None = None) -> int:
    """Days in Applied with no stage change before a follow-up is due."""
    user = get_user(user_id) if user_id else None
    return user.followup_days if user else DEFAULT_FOLLOWUP_DAYS
