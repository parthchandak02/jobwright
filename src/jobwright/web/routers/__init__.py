"""API routers for the jobwright dashboard."""

from jobwright.web.routers.admin import router as admin_router
from jobwright.web.routers.board import router as board_router
from jobwright.web.routers.connections import router as connections_router
from jobwright.web.routers.jobs import router as jobs_router
from jobwright.web.routers.materials import router as materials_router
from jobwright.web.routers.notify import router as notify_router
from jobwright.web.routers.onboarding import router as onboarding_router
from jobwright.web.routers.quality import router as quality_router
from jobwright.web.routers.runs import router as runs_router
from jobwright.web.routers.settings import router as settings_router
from jobwright.web.routers.system import router as system_router
from jobwright.web.routers.whatsapp import router as whatsapp_router

__all__ = [
    "admin_router",
    "onboarding_router",
    "quality_router",
    "whatsapp_router",
    "board_router",
    "connections_router",
    "jobs_router",
    "materials_router",
    "notify_router",
    "runs_router",
    "settings_router",
    "system_router",
]
