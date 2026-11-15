"""Local dashboard for Cook shots: static build + readme_images fake API.

Usage:
  cd frontend && pnpm run build
  uv run --extra web --with pillow python scripts/cook_demo_server.py [--port 8831]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "frontend" / "dist"

# Load readme_images without executing main (large module, shared fixtures).
_spec = importlib.util.spec_from_file_location("readme_images", REPO / "scripts" / "readme_images.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

STATE = {"admin": True, "setup_complete": True}


def _json_response(body) -> tuple[bytes, str]:
    return json.dumps(body).encode(), "application/json"


def _static_file(path: str) -> Path | None:
    clean = path.lstrip("/") or "index.html"
    file = (DIST / clean).resolve()
    if file.is_file() and DIST in file.parents:
        return file
    spa = (DIST / "index.html").resolve()
    return spa if spa.is_file() else None


def handle(method: str, path: str, raw_body: bytes | None) -> tuple[int, bytes, str]:
    if path.startswith("/api/"):
        payload = None
        if method in ("POST", "PATCH", "PUT") and raw_body:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                payload = None
        body = _mod.api_response(method, path, STATE, payload)
        if body is None:
            return 404, b'{"detail":"demo"}', "application/json"
        data, ctype = _json_response(body)
        return 200, data, ctype
    file = _static_file(path)
    if not file:
        return 404, b"not found", "text/plain"
    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return 200, file.read_bytes(), mime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8831)
    args = parser.parse_args()
    if not (DIST / "index.html").is_file():
        print("frontend/dist missing: run `cd frontend && pnpm run build`", file=sys.stderr)
        return 1

    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Route
    import uvicorn

    async def catch_all(request: Request) -> Response:
        body = await request.body()
        status, content, ctype = handle(request.method, request.url.path, body or None)
        return Response(content=content, status_code=status, media_type=ctype)

    app = Starlette(
        routes=[
            Route("/{path:path}", catch_all, methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]),
            Route("/", catch_all, methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]),
        ]
    )
    host = "127.0.0.1"
    print(f"cook demo: http://{host}:{args.port}/ (fake API, fixture jobs)", flush=True)
    uvicorn.run(app, host=host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())