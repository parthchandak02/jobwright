"""Health and profile endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter

from jobwright import config
from jobwright import __version__
from jobwright.database import FUNNEL_STAGES, get_connection, get_stats
from jobwright.users import get_user

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@router.get("/profile")
def profile() -> dict:
    user_id = os.environ.get("JOBWRIGHT_DASHBOARD_USER", "richa")
    user = get_user(user_id)
    conn = get_connection()
    stats = get_stats(conn)
    stage_counts = {
        stage: conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE COALESCE(funnel_stage, 'backlog') = ?",
            (stage,),
        ).fetchone()[0]
        for stage in FUNNEL_STAGES
    }
    return {
        "user_id": user_id,
        "name": user.name if user else user_id,
        "apply_enabled": bool(user.apply_enabled) if user else False,
        "app_dir": str(config.APP_DIR),
        "stats": {
            "total": stats.get("total", 0),
            "scored": stats.get("scored", 0),
            "tailored": stats.get("tailored", 0),
            "applied": stats.get("applied", 0),
            "ready_to_apply": stats.get("ready_to_apply", 0),
        },
        "funnel_stages": list(FUNNEL_STAGES),
        "stage_counts": stage_counts,
        "source": "https://github.com/parthchandak02/jobwright",
    }
