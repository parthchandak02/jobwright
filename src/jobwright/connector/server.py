"""The ``/mcp`` endpoint: bearer auth, one profile per call, MCP streamable HTTP.

Stateless transport with JSON responses (like the Tandem and Wedding Looks
connectors): no MCP session survives a request, so a restart loses nothing.
The session manager is created fresh for every app lifespan
(``connector_lifespan``) because the SDK runs one only once.

Also here: ``/mcp/files/<token>`` (short-lived signed downloads of tailored
materials) and ``/mcp/icon.png``. Everything under ``/mcp`` is public at the
Cloudflare edge (Access bypass) and protected here instead.

``/mcp/files`` answers any origin (``Access-Control-Allow-Origin: *``, never
with credentials): the person's Claude in Chrome fetches the file from inside
the employer's application page and puts it in the form's file input. The
random token is the only key; it lives 15 minutes, works a few times
(``store.DOWNLOAD_MAX_USES``) and reaches only that profile's generated files.
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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

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


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Expose-Headers": "Content-Disposition, Content-Type, Content-Length",
    "Access-Control-Max-Age": "600",
    "Cross-Origin-Resource-Policy": "cross-origin",
}
MEDIA_TYPES = {".pdf": "application/pdf",
               ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _not_found(detail: str = "Not found") -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=404, headers={**CORS_HEADERS, "Cache-Control": "no-store"})


class FilesPreflight:
    """Answer CORS preflights for ``/mcp/files/*`` from any origin, before the dashboard's CORS middleware
    (which only allows the dashboard's own origins) can refuse them. A plain GET needs no preflight; this
    covers pages whose fetch adds a header."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS" and scope["path"].startswith("/mcp/files/"):
            headers = [(k.lower().encode(), v.encode()) for k, v in CORS_HEADERS.items()]
            headers.append((b"access-control-allow-headers", b"*"))
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return
        await self.app(scope, receive, send)


# The popup the page snippet opens when the job site's security policy blocks fetch() to jobwright. It runs
# on jobwright's own origin, downloads the file (one use) and posts the bytes to the application page that
# opened it (only to the origin named in the address), then closes itself.
_RELAY_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>jobwright · attaching your file</title></head>
<body style="font:15px/1.5 system-ui,sans-serif;margin:24px;color:#1f2328;background:#fafaf9">
<p id="s">Attaching your file to the application…</p>
<script>
(async () => {
  const s = document.getElementById('s');
  const q = new URLSearchParams(location.hash.slice(1));
  const target = q.get('o'), key = q.get('k');
  const fileUrl = location.pathname.replace(/\\/relay$/, '');
  if (!window.opener || !target || !/^https?:\\/\\//.test(target)) {
    s.innerHTML = 'Open this from the application page. Or <a href="' + fileUrl + '">download the file</a>.';
    return;
  }
  const send = (msg, transfer) => window.opener.postMessage(Object.assign({ jw: 'jobwright-file', key }, msg), target, transfer || []);
  try {
    const r = await fetch(fileUrl, { credentials: 'omit' });
    if (!r.ok) throw new Error(r.status === 404 ? 'the link expired or was used up' : 'HTTP ' + r.status);
    const bytes = await r.arrayBuffer();
    send({ ok: true, type: r.headers.get('Content-Type'), bytes }, [bytes]);
    s.textContent = 'Done. This window closes itself.';
    setTimeout(() => window.close(), 700);
  } catch (e) {
    send({ ok: false, error: String(e.message || e) });
    s.textContent = 'Could not attach the file: ' + (e.message || e) + '. Ask Claude for a fresh link.';
  }
})();
</script></body></html>"""


@files_router.get("/mcp/files/{token}/relay", response_model=None)
def relay(token: str) -> HTMLResponse | JSONResponse:
    """Popup page that hands a file to the application page (see ``_RELAY_HTML``). Does not use up the link."""
    row = store.resolve_download(token, count=False)
    if row is None or row["uses"] >= store.DOWNLOAD_MAX_USES:
        return _not_found("This link has expired or was used up. Call get_application_packet for a fresh one.")
    return HTMLResponse(_RELAY_HTML, headers={
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; "
                                   "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
    })


@files_router.get("/mcp/files/{token}", response_model=None)
def download(token: str) -> FileResponse | JSONResponse:
    """A resume / cover letter by short-lived link (15 minutes, a few uses, the person's own files only)."""
    row = store.resolve_download(token)
    if row is None:
        return _not_found("This link has expired or was used up. Call get_application_packet for a fresh one.")
    from jobwright.users import get_user

    user = get_user(row["user_id"])
    if user is None:
        return _not_found()
    with config.user_context(user.user_id):
        roots = [pathlib.Path(config.TAILORED_DIR).resolve(), pathlib.Path(config.COVER_LETTER_DIR).resolve(),
                 pathlib.Path(config.RESUME_DIR).resolve()]
    path = pathlib.Path(row["path"]).resolve()
    media = MEDIA_TYPES.get(path.suffix.lower())
    if not any(path.is_relative_to(r) for r in roots) or media is None or not path.is_file():
        return _not_found()
    from urllib.parse import quote

    name = row["filename"] or path.name
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name)
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}'
    return FileResponse(str(path), media_type=media,
                        headers={**CORS_HEADERS, "Content-Disposition": disposition, "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})


@files_router.get("/mcp/icon.png")
def icon() -> FileResponse:
    if not _ICON.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(str(_ICON), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
