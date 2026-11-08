"""FastAPI app for the jobwright Kanban dashboard.

Run:
    JOBWRIGHT_DASHBOARD_USER=richa uvicorn jobwright.web.app:app --host 127.0.0.1 --port 8002
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from jobwright import __version__
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from starlette.routing import Route

from jobwright.connector.oauth import router as connector_oauth_router
from jobwright.connector.server import connector_lifespan, files_router as connector_files_router, mcp_endpoint
from jobwright.web.bootstrap import bootstrap_dashboard
from jobwright.web.routers import (
    admin_router,
    apply_router,
    board_router,
    connections_router,
    connector_router,
    jobs_router,
    materials_router,
    notify_router,
    onboarding_router,
    quality_router,
    runs_router,
    settings_router,
    system_router,
    whatsapp_router,
)
from jobwright.web.session import DashboardUserMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    bootstrap_dashboard()
    async with connector_lifespan():
        yield


app = FastAPI(title="jobwright Dashboard", version=__version__, lifespan=lifespan)

_cors = os.environ.get(
    "JOBWRIGHT_CORS_ORIGINS",
    "http://127.0.0.1:5120,http://localhost:5120,"
    "http://127.0.0.1:8002,http://localhost:8002",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DashboardUserMiddleware)

app.include_router(system_router)
app.include_router(admin_router)
app.include_router(onboarding_router)
app.include_router(whatsapp_router)
app.include_router(board_router)
# Specific /jobs/{url}/… routes must register before the greedy /jobs/{url:path} catch-all.
app.include_router(quality_router)
app.include_router(materials_router)
app.include_router(connections_router)
app.include_router(jobs_router)
app.include_router(notify_router)
app.include_router(runs_router)
app.include_router(settings_router)
app.include_router(apply_router)
app.include_router(connector_router)

# Claude connector (docs/agents/claude-connector.md): OAuth + /mcp. These paths are outside /api, so the
# dashboard middleware leaves them alone; each authenticates itself (Access JWT on /oauth/authorize, bearer
# tokens on /mcp). Registered before the SPA fallback below.
app.include_router(connector_oauth_router)
app.include_router(connector_files_router)
for _path in ("/mcp", "/mcp/"):
    app.router.routes.append(Route(_path, endpoint=mcp_endpoint, methods=["GET", "POST", "DELETE"]))

_static_dir = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "dist"

# index.html (and other unhashed files) must be revalidated so a refresh after a deploy loads the new
# bundle; Vite's content-hashed files under assets/ never change, so browsers may keep them for a year.
_NO_CACHE = {"Cache-Control": "no-cache"}
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _cache_headers(rel: pathlib.Path) -> dict[str, str]:
    return _IMMUTABLE if rel.parts and rel.parts[0] == "assets" else _NO_CACHE


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if _static_dir.exists():
        root = _static_dir.resolve()
        try:
            candidate = (root / full_path).resolve()
        except (OSError, RuntimeError):
            candidate = root
        if candidate != root and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(str(candidate), headers=_cache_headers(candidate.relative_to(root)))
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index), headers=_NO_CACHE)
    raise HTTPException(
        status_code=404,
        detail="Frontend not built. Run: cd frontend && pnpm build",
    )
