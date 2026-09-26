"""Per-request identity and active profile for the dashboard API.

Every /api request is authenticated (see auth.py), then bound to exactly one
profile via config.user_context() for its whole lifetime (including threadpool
handlers and streaming bodies). Non-admins can only open profiles whose
``emails`` include their login; admins can open any profile. The chosen profile
is remembered in the ``jobwright_user`` cookie.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request

from jobwright import config
from jobwright.users import UserRecord, get_user, list_users, users_for_email
from jobwright.web.auth import AuthError, Identity, identify

log = logging.getLogger(__name__)

COOKIE_NAME = "jobwright_user"

# Endpoints that work without an active profile (identity only).
PROFILE_OPTIONAL_PREFIXES = (
    "/api/health",
    "/api/me",
    "/api/session",
    "/api/onboarding",
    "/api/admin",
)

_init_lock = threading.Lock()
_initialized_dbs: set[str] = set()


def allowed_users(identity: Identity) -> list[UserRecord]:
    if identity.is_admin:
        return list_users()
    return users_for_email(identity.email)


def can_open(identity: Identity, user_id: str) -> bool:
    return any(u.user_id == user_id for u in allowed_users(identity))


def pick_active_user(identity: Identity, cookie_user: str | None) -> str | None:
    allowed = allowed_users(identity)
    ids = [u.user_id for u in allowed]
    if cookie_user and cookie_user in ids:
        return cookie_user
    if identity.is_admin and identity.email:
        own = [u.user_id for u in users_for_email(identity.email)]
        if own:
            return own[0]
    fallback = os.environ.get("JOBWRIGHT_DASHBOARD_USER", "").strip()
    if fallback and fallback in ids:
        return fallback
    return ids[0] if ids else None


def _ensure_user_storage() -> None:
    """Create dirs + schema once per DB per process (not on every request)."""
    from jobwright.database import init_db

    db_key = str(config.DB_PATH)
    if db_key in _initialized_dbs:
        return
    with _init_lock:
        if db_key in _initialized_dbs:
            return
        config.ensure_dirs()
        init_db()
        _initialized_dbs.add(db_key)


def forget_initialized(db_path: str | None = None) -> None:
    with _init_lock:
        if db_path is None:
            _initialized_dbs.clear()
        else:
            _initialized_dbs.discard(db_path)


def _cookies_from_scope(scope) -> dict[str, str]:
    raw = ""
    for key, value in scope.get("headers") or []:
        if key == b"cookie":
            raw = value.decode("latin-1")
            break
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:  # noqa: BLE001 - malformed cookie header
        return {}
    return {k: m.value for k, m in jar.items()}


def _headers_from_scope(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class DashboardUserMiddleware:
    """Pure ASGI middleware: authenticate, then bind the active profile."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api"):
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path == "/api/health":
            await self.app(scope, receive, send)
            return

        headers = _headers_from_scope(scope)
        cookies = _cookies_from_scope(scope)
        try:
            identity = identify(headers, cookies)
        except AuthError as exc:
            await _send_json(send, exc.status, {"detail": str(exc), "code": "unauthenticated"})
            return

        user_id = pick_active_user(identity, cookies.get(COOKIE_NAME))
        state = scope.setdefault("state", {})
        state["identity"] = identity
        state["active_user"] = user_id

        if user_id is None:
            if path.startswith(PROFILE_OPTIONAL_PREFIXES):
                await self.app(scope, receive, send)
                return
            await _send_json(
                send,
                403,
                {"detail": "No profile for this login yet.", "code": "no_profile", "email": identity.email},
            )
            return

        with config.user_context(user_id):
            _ensure_user_storage()
            await self.app(scope, receive, send)


def get_identity(request: Request) -> Identity:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(401, "Not authenticated")
    return identity


def current_user_id(request: Request) -> str:
    """Active profile for this request (bound by the middleware)."""
    user_id = getattr(request.state, "active_user", None)
    if not user_id or get_user(user_id) is None:
        raise HTTPException(403, detail={"code": "no_profile", "detail": "No active profile."})
    return user_id


def require_admin(request: Request) -> Identity:
    identity = get_identity(request)
    if not identity.is_admin:
        raise HTTPException(403, "Admin only")
    return identity


def resolve_dashboard_user(request: Request | None = None) -> str:
    """Back-compat alias used by routers: the request's active profile."""
    if request is None:
        user_id = config.get_active_user_id()
        if not user_id:
            raise HTTPException(403, detail={"code": "no_profile", "detail": "No active profile."})
        return user_id
    return current_user_id(request)
