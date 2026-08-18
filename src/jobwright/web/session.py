"""Per-request dashboard user from cookie (fallback: JOBWRIGHT_DASHBOARD_USER)."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from jobwright.config import ensure_dirs, load_env, set_active_user
from jobwright.database import init_db
from jobwright.users import get_user

COOKIE_NAME = "jobwright_user"


def default_dashboard_user() -> str:
    return os.environ.get("JOBWRIGHT_DASHBOARD_USER", "richa").strip() or "richa"


def resolve_dashboard_user(request: Request | None = None) -> str:
    """Resolve active user from cookie, else env default."""
    if request is not None:
        raw = (request.cookies.get(COOKIE_NAME) or "").strip()
        if raw and get_user(raw) is not None:
            return raw
    return default_dashboard_user()


def activate_user(user_id: str) -> str:
    """Point config + DB at a registry user. Raises ValueError if unknown."""
    if get_user(user_id) is None:
        raise ValueError(f"Unknown user: {user_id}")
    set_active_user(user_id)
    load_env()
    ensure_dirs()
    init_db()
    return user_id


class DashboardUserMiddleware(BaseHTTPMiddleware):
    """Activate the dashboard user for each /api request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith("/api"):
            user_id = resolve_dashboard_user(request)
            try:
                activate_user(user_id)
            except (ValueError, SystemExit):
                activate_user(default_dashboard_user())
            request.state.dashboard_user = user_id
        return await call_next(request)
