"""Process-level setup for the dashboard API (no user is activated globally)."""

from __future__ import annotations

from jobwright import config
from jobwright.users import USERS_ROOT


def bootstrap_dashboard() -> None:
    """Load global env and park the process default away from any real user.

    Requests bind their own profile via config.user_context(); anything that
    escapes a request context sees an empty sentinel dir, never someone's data.
    """
    config.load_env()
    config.set_app_dir(USERS_ROOT / ".no-active-user")
    config._DEFAULT_STATE.ACTIVE_USER_ID = None
