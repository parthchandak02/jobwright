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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from jobwright.web.bootstrap import bootstrap_dashboard_user
from jobwright.web.routers import (
    board_router,
    connections_router,
    jobs_router,
    materials_router,
    notify_router,
    runs_router,
    settings_router,
    system_router,
)
from jobwright.web.session import DashboardUserMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    user_id = bootstrap_dashboard_user()
    _app.state.dashboard_user = user_id
    yield


app = FastAPI(title="jobwright Dashboard", version="0.5.0", lifespan=lifespan)

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
app.include_router(board_router)
# Specific /jobs/{url}/… routes must register before the greedy /jobs/{url:path} catch-all.
app.include_router(materials_router)
app.include_router(connections_router)
app.include_router(jobs_router)
app.include_router(notify_router)
app.include_router(runs_router)
app.include_router(settings_router)

_static_dir = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "dist"


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    if _static_dir.exists():
        candidate = _static_dir / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
    raise HTTPException(
        status_code=404,
        detail="Frontend not built. Run: cd frontend && pnpm build",
    )
