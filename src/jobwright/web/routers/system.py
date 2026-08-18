"""Health, profile, and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from jobwright import __version__
from jobwright import config
from jobwright.database import FUNNEL_STAGES, get_connection, get_stats
from jobwright.users import get_user, list_users
from jobwright.web.session import (
    COOKIE_NAME,
    activate_user,
    default_dashboard_user,
    resolve_dashboard_user,
)

router = APIRouter(prefix="/api", tags=["system"])


def _profile_payload(user_id: str) -> dict:
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


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@router.get("/profile")
def profile(request: Request) -> dict:
    user_id = resolve_dashboard_user(request)
    return _profile_payload(user_id)


@router.get("/users")
def users_list() -> dict:
    users = [{"user_id": u.user_id, "name": u.name or u.user_id} for u in list_users()]
    return {"users": users, "default": default_dashboard_user()}


class SessionBody(BaseModel):
    user_id: str


@router.post("/session")
def set_session(body: SessionBody, response: Response) -> dict:
    user_id = body.user_id.strip()
    try:
        activate_user(user_id)
    except (ValueError, SystemExit) as exc:
        raise HTTPException(400, str(exc)) from exc

    response.set_cookie(
        key=COOKIE_NAME,
        value=user_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
        path="/",
    )
    return _profile_payload(user_id)
