"""Dashboard identity: Cloudflare Access JWT (prod) or trusted local dev.

Modes (``JOBWRIGHT_AUTH_MODE``):
  cloudflare  Verify ``Cf-Access-Jwt-Assertion`` (or the ``CF_Authorization``
              cookie) against the team's JWKS, audience and issuer. Required
              whenever the API is reachable through the tunnel.
  dev         Trust the local caller (``JOBWRIGHT_DEV_EMAIL`` or anonymous
              admin). Refuses any request that arrived through Cloudflare, so a
              misconfigured prod API fails closed instead of open.

Default: ``cloudflare`` when ``JOBWRIGHT_CF_TEAM_DOMAIN`` is set, else ``dev``.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

from jobwright.users import is_admin_email, normalize_email

log = logging.getLogger(__name__)

CF_JWT_HEADER = "cf-access-jwt-assertion"
CF_JWT_COOKIE = "CF_Authorization"
_CF_EDGE_HEADERS = ("cf-ray", "cf-connecting-ip", CF_JWT_HEADER)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Identity:
    email: str
    is_admin: bool
    mode: str


def auth_mode() -> str:
    mode = os.environ.get("JOBWRIGHT_AUTH_MODE", "").strip().lower()
    if mode in ("cloudflare", "dev"):
        return mode
    return "cloudflare" if os.environ.get("JOBWRIGHT_CF_TEAM_DOMAIN", "").strip() else "dev"


def _team_domain() -> str:
    raw = os.environ.get("JOBWRIGHT_CF_TEAM_DOMAIN", "").strip()
    return raw.removeprefix("https://").rstrip("/")


_jwks_lock = threading.Lock()
_jwks_clients: dict[str, object] = {}


def _jwks_client(team: str):
    import jwt

    with _jwks_lock:
        client = _jwks_clients.get(team)
        if client is None:
            client = jwt.PyJWKClient(
                f"https://{team}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600
            )
            _jwks_clients[team] = client
        return client


def verify_cloudflare_token(token: str) -> str:
    """Return the verified email claim or raise AuthError."""
    import jwt

    team = _team_domain()
    audiences = [a.strip() for a in os.environ.get("JOBWRIGHT_CF_AUD", "").split(",") if a.strip()]
    if not team or not audiences:
        raise AuthError("Server auth misconfigured: set JOBWRIGHT_CF_TEAM_DOMAIN and JOBWRIGHT_CF_AUD", 503)
    try:
        signing_key = _jwks_client(team).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=f"https://{team}",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid Cloudflare Access token: {exc}") from exc
    email = normalize_email(claims.get("email"))
    if not email:
        raise AuthError("Cloudflare Access token has no email claim")
    return email


def identify(headers: dict[str, str], cookies: dict[str, str]) -> Identity:
    """Resolve the caller. ``headers`` keys must be lower-case."""
    mode = auth_mode()
    if mode == "cloudflare":
        token = headers.get(CF_JWT_HEADER) or cookies.get(CF_JWT_COOKIE) or ""
        if not token:
            raise AuthError("Missing Cloudflare Access token")
        email = verify_cloudflare_token(token)
        return Identity(email=email, is_admin=is_admin_email(email), mode=mode)

    if any(h in headers for h in _CF_EDGE_HEADERS):
        raise AuthError(
            "Request came through Cloudflare but the API runs in dev auth mode; "
            "set JOBWRIGHT_AUTH_MODE=cloudflare",
            503,
        )
    email = normalize_email(os.environ.get("JOBWRIGHT_DEV_EMAIL", ""))
    if email:
        return Identity(email=email, is_admin=is_admin_email(email), mode=mode)
    return Identity(email="", is_admin=True, mode=mode)
