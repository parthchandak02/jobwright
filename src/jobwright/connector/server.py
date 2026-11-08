"""The ``/mcp`` endpoint: bearer auth, one profile per call, MCP streamable HTTP.

Stateless transport with JSON responses (like the Tandem and Wedding Looks
connectors): no MCP session survives a request, so a restart loses nothing.
The session manager is created fresh for every app lifespan
(``connector_lifespan``) because the SDK runs one only once.

Also here: ``/mcp/files/<token>`` (short-lived signed downloads of tailored
materials) and ``/mcp/icon.png``. Everything under ``/mcp`` is public at the
Cloudflare edge (Access bypass) and protected here instead.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import pathlib
from typing import AsyncIterator

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from jobwright import config
from jobwright.connector import store
from jobwright.connector.oauth import RateLimiter, resource_metadata_url

log = logging.getLogger(__name__)

current_principal: contextvars.ContextVar[store.Principal | None] = contextvars.ContextVar(
    "jobwright_connector_principal", default=None)

CALL_LIMIT = RateLimiter(240, 300)  # per connection (grant): 240 requests in 5 minutes
MAX_BODY_BYTES = 6 * 1024 * 1024  # a 3 MB PNG as base64 plus fields
_manager = None
_ICON = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "public" / "icon-512.png"

files_router = APIRouter(include_in_schema=False)


def enabled() -> bool:
    if os.environ.get("JOBWRIGHT_CONNECTOR", "on").strip().lower() in ("0", "off", "false", "no"):
        return False
    try:
        import mcp.server.mcpserver  # noqa: F401
    except ImportError:
        return False
    return True


@contextlib.asynccontextmanager
async def connector_lifespan() -> AsyncIterator[None]:
    """Run the MCP session manager for the app's lifetime (no-op when the connector is off)."""
    global _manager
    if not enabled():
        yield
        return
    from jobwright.connector.tools import build_server

    server = build_server()
    server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=MAX_BODY_BYTES,
                               transport_security=transport_security())
    manager = server.session_manager
    async with manager.run():
        _manager = manager
        try:
            yield
        finally:
            _manager = None


def transport_security():
    """Host / Origin checks (DNS rebinding): our public host and this machine only."""
    from urllib.parse import urlsplit

    from mcp.server.transport_security import TransportSecuritySettings

    from jobwright.connector.oauth import base_url

    public = urlsplit(base_url())
    extra = [h.strip() for h in os.environ.get("JOBWRIGHT_CONNECTOR_HOSTS", "").split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[public.netloc, "127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", *extra],
        allowed_origins=[f"{public.scheme}://{public.netloc}", "https://claude.ai", "https://claude.com"],
    )


async def _send_json(send, status: int, payload: dict, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"), *(headers or [])]})
    await send({"type": "http.response.body", "body": body})


def _bearer(scope) -> str:
    for key, value in scope.get("headers") or []:
        if key == b"authorization":
            raw = value.decode("latin-1").strip()
            if raw[:7].lower() == "bearer ":
                return raw[7:].strip()
    return ""


class MCPEndpoint:
    """ASGI app for ``/mcp``: verify the token, bind the profile, hand over to the SDK."""

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return
        token = _bearer(scope)
        principal = await anyio.to_thread.run_sync(store.verify_access, token) if token else None
        if principal is None:
            challenge = f'Bearer resource_metadata="{resource_metadata_url()}", scope="{" ".join(store.SCOPES)}"'
            if token:
                challenge += ', error="invalid_token"'
            await _send_json(send, 401, {"error": "unauthorized",
                                         "error_description": "Connect jobwright in Claude to sign in."},
                             [(b"www-authenticate", challenge.encode())])
            return
        if not CALL_LIMIT.hit(principal.grant_id):
            await _send_json(send, 429, {"error": "rate_limited", "error_description": "Too many calls; slow down."},
                             [(b"retry-after", b"60")])
            return
        manager = _manager
        if manager is None:
            await _send_json(send, 503, {"error": "unavailable", "error_description": "The connector is off."})
            return
        reset = current_principal.set(principal)
        try:
            with config.user_context(principal.user_id):
                await manager.handle_request(scope, receive, send)
        finally:
            current_principal.reset(reset)


mcp_endpoint = MCPEndpoint()


@files_router.get("/mcp/files/{token}")
def download(token: str) -> FileResponse:
    """A tailored resume / cover letter by short-lived link (15 minutes, the person's own files only)."""
    row = store.resolve_download(token)
    if row is None:
        raise HTTPException(404, "This link has expired. Ask Claude for a fresh one.")
    from jobwright.users import get_user

    user = get_user(row["user_id"])
    if user is None:
        raise HTTPException(404, "Not found")
    with config.user_context(user.user_id):
        roots = [pathlib.Path(config.TAILORED_DIR).resolve(), pathlib.Path(config.COVER_LETTER_DIR).resolve(),
                 pathlib.Path(config.RESUME_DIR).resolve()]
    path = pathlib.Path(row["path"]).resolve()
    if not any(path.is_relative_to(r) for r in roots) or path.suffix.lower() not in (".pdf", ".docx") \
            or not path.is_file():
        raise HTTPException(404, "Not found")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(str(path), filename=row["filename"], media_type=media,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@files_router.get("/mcp/icon.png")
def icon() -> FileResponse:
    if not _ICON.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(str(_ICON), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
