"""Dashboard identity: Cloudflare Access JWT (prod) or trusted local dev.

Modes (``JOBWRIGHT_AUTH_MODE``):
  cloudflare  Verify ``Cf-Access-Jwt-Assertion`` (or the ``CF_Authorization``
              cookie) against the team's JWKS, audience and issuer. Required
              whenever the API is reachable through the tunnel.
  dev         Trust the local caller as ``JOBWRIGHT_DEV_EMAIL``; without it,
              only a loopback client (127.0.0.1 / ::1, no non-loopback
              forwarding headers) is treated as an anonymous admin. Refuses
              any request that arrived through Cloudflare, so a misconfigured
              prod API fails closed instead of open.

Default: ``cloudflare`` when ``JOBWRIGHT_CF_TEAM_DOMAIN`` is set, else ``dev``.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
from dataclasses import dataclass

from jobwright.users import is_admin_email, normalize_email

log = logging.getLogger(__name__)

CF_JWT_HEADER = "cf-access-jwt-assertion"
CF_JWT_COOKIE = "CF_Authorization"
_CF_EDGE_HEADERS = ("cf-ray", "cf-connecting-ip", CF_JWT_HEADER)
_FORWARDED_HEADERS = ("x-forwarded-for", "x-real-ip")
# Hostnames accepted as "this machine" besides loopback IPs (tests add theirs).
LOOPBACK_HOSTS: set[str] = {"localhost"}


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


def _is_loopback(host: str | None) -> bool:
    host = (host or "").strip().strip("[]")
    if not host:
        return False
    if host.lower() in LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


def _local_caller(headers: dict[str, str], client_host: str | None) -> bool:
    """True when the TCP peer is loopback and no hop says the request came from elsewhere."""
    if not _is_loopback(client_host):
        return False
    if "forwarded" in headers:
        return False
    for name in _FORWARDED_HEADERS:
        value = headers.get(name)
        if value is not None and not all(_is_loopback(h) for h in value.split(",")):
            return False
    return True


def identify(headers: dict[str, str], cookies: dict[str, str], client_host: str | None = None) -> Identity:
    """Resolve the caller. ``headers`` keys must be lower-case.

    ``client_host`` is the TCP peer (ASGI ``scope["client"][0]``); dev mode only
    grants anonymous admin to a loopback peer.
    """
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
    if not _local_caller(headers, client_host):
        raise AuthError(
            "Dev auth mode only trusts callers on this machine; set JOBWRIGHT_DEV_EMAIL "
            "or JOBWRIGHT_AUTH_MODE=cloudflare",
            401,
        )
    return Identity(email="", is_admin=True, mode=mode)
