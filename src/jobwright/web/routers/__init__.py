"""API routers for the jobwright dashboard."""

from jobwright.web.routers.board import router as board_router
from jobwright.web.routers.connections import router as connections_router
from jobwright.web.routers.digest import router as digest_router
from jobwright.web.routers.jobs import router as jobs_router
from jobwright.web.routers.materials import router as materials_router
from jobwright.web.routers.runs import router as runs_router
from jobwright.web.routers.system import router as system_router

__all__ = [
    "board_router",
    "connections_router",
    "digest_router",
    "jobs_router",
    "materials_router",
    "runs_router",
    "system_router",
]
