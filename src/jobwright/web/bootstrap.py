"""Activate dashboard user and initialize DB/paths."""

from __future__ import annotations

import os

from jobwright.config import ensure_dirs, load_env, set_active_user
from jobwright.database import init_db


def bootstrap_dashboard_user() -> str:
    """Set active user from JOBWRIGHT_DASHBOARD_USER (default: richa)."""
    user_id = os.environ.get("JOBWRIGHT_DASHBOARD_USER", "richa").strip() or "richa"
    set_active_user(user_id)
    load_env()
    ensure_dirs()
    init_db()
    return user_id
