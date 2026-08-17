"""Multi-profile user registry.

Registry file: ~/.applypilot-users/users.yaml
Per-user data: ~/.applypilot-users/<user_id>/  (full APPLYPILOT_DIR)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

USERS_ROOT = Path.home() / ".applypilot-users"
REGISTRY_PATH = USERS_ROOT / "users.yaml"

_USER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


@dataclass
class UserRecord:
    user_id: str
    name: str = ""
    whatsapp_target: str = ""
    apply_enabled: bool = False
    schedule: str = "0 */3 * * 1-5"  # every 3 hours weekdays (near-real-time)
    digest_schedule: str = "15 */3 * * 1-5"
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
    copy_env_from: Path | None = None,
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

    for sub in ("tailored_resumes", "cover_letters", "logs", "chrome-workers", "apply-workers"):
        (data_dir / sub).mkdir(exist_ok=True)

    # Seed .env: prefer explicit copy_env_from; otherwise create a find-only stub
    # (do NOT silently copy API keys from ~/.applypilot — that duplicates secrets).
    env_path = data_dir / ".env"
    if not env_path.exists():
        if copy_env_from and Path(copy_env_from).exists():
            env_path.write_text(
                Path(copy_env_from).read_text(encoding="utf-8"), encoding="utf-8"
            )
        else:
            env_path.write_text(
                "# ApplyPilot per-user env (find-only by default)\n"
                "# Copy GEMINI_API_KEY from your shared vault, or:\n"
                "#   applypilot users add ... --copy-env ~/.applypilot/.env\n"
                "# For live apply also need CURSOR_API_KEY (+ CapSolver optional).\n"
                "LLM_MODEL=gemini-2.5-flash\n"
                "APPLY_DRY_RUN=true\n"
                "AGENT_PROVIDER=cursor-sdk\n",
                encoding="utf-8",
            )
        try:
            env_path.chmod(0o600)
        except OSError:
            pass

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
        if data_dir.exists() and data_dir != Path.home() / ".applypilot":
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

    If user_id is None (legacy single-user ~/.applypilot), apply is allowed
    (backward compatible — gated only by APPLY_CONFIRMED).
    """
    if not user_id:
        return True
    user = get_user(user_id)
    if user is None:
        return False
    return bool(user.apply_enabled)
