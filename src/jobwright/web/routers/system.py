"""Health, profile, and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from jobwright import __version__, config
from jobwright.database import FUNNEL_STAGES, get_connection, get_stats
from jobwright.hermes_cron import brief_cron_installed, brief_cron_name, ensure_brief_cron
from jobwright.users import (
    DEFAULT_FOLLOWUP_DAYS,
    _normalize_whatsapp_target,
    describe_cron_schedule,
    get_user,
    host_timezone_name,
    update_user,
    validate_brief_schedule,
)
from jobwright.web.session import (
    COOKIE_NAME,
    allowed_users,
    can_open,
    current_user_id,
    get_identity,
)

router = APIRouter(prefix="/api", tags=["system"])


def _chat_name(target: str) -> str:
    if not target:
        return ""
    try:
        from jobwright.whatsapp import chat_name

        return chat_name(target)
    except Exception:  # noqa: BLE001
        return target.removeprefix("whatsapp:").split("@")[0]


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
    schedule = user.schedule if user else "0 6 * * *"
    return {
        "user_id": user_id,
        "name": user.name if user else user_id,
        "apply_enabled": bool(user.apply_enabled) if user else False,
        "schedule": schedule,
        "schedule_label": describe_cron_schedule(schedule),
        "timezone": host_timezone_name(),
        "whatsapp_target": user.whatsapp_target if user else "",
        "whatsapp_chat_name": _chat_name(user.whatsapp_target if user else ""),
        "weekly_summary": user.weekly_summary if user else True,
        "followup_days": user.followup_days if user else DEFAULT_FOLLOWUP_DAYS,
        "brief_cron_name": brief_cron_name(user_id),
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


@router.get("/me")
def me(request: Request) -> dict:
    """Who is logged in, which profiles they may open, and the active one."""
    identity = get_identity(request)
    profiles = [{"user_id": u.user_id, "name": u.name or u.user_id} for u in allowed_users(identity)]
    active = getattr(request.state, "active_user", None)
    setup_complete = None
    if active:
        from jobwright.onboarding import onboarding_status

        try:
            with config.user_context(active):
                setup_complete = bool(onboarding_status()["complete"])
        except Exception:  # noqa: BLE001
            setup_complete = None
    return {
        "email": identity.email,
        "is_admin": identity.is_admin,
        "auth_mode": identity.mode,
        "active_user": active,
        "setup_complete": setup_complete,
        "profiles": profiles,
        "can_create_profile": True,
    }


@router.get("/profile")
def profile(request: Request) -> dict:
    return _profile_payload(current_user_id(request))


@router.get("/users")
def users_list(request: Request) -> dict:
    identity = get_identity(request)
    users = [{"user_id": u.user_id, "name": u.name or u.user_id} for u in allowed_users(identity)]
    return {"users": users, "default": getattr(request.state, "active_user", None)}


class SessionBody(BaseModel):
    user_id: str


class ProfileUpdate(BaseModel):
    schedule: str | None = None
    whatsapp_target: str | None = None
    weekly_summary: bool | None = None
    followup_days: int | None = None


@router.put("/profile")
def update_profile(body: ProfileUpdate, request: Request) -> dict:
    """Save daily-brief schedule and WhatsApp target, then edit the Hermes cron."""
    user_id = current_user_id(request)
    before = get_user(user_id)

    fields: dict = {}
    if body.schedule is not None:
        try:
            fields["schedule"] = validate_brief_schedule(body.schedule.strip())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if body.whatsapp_target is not None:
        new_target = _normalize_whatsapp_target(body.whatsapp_target.strip())
        current = get_user(user_id)
        if new_target != (current.whatsapp_target if current else ""):
            if not get_identity(request).is_admin:
                raise HTTPException(403, "Only an admin can change the WhatsApp chat.")
            fields["whatsapp_target"] = new_target
    if body.weekly_summary is not None:
        fields["weekly_summary"] = body.weekly_summary
    if body.followup_days is not None:
        fields["followup_days"] = body.followup_days
    if not fields:
        raise HTTPException(400, "Nothing to update.")

    try:
        update_user(user_id, **fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    user = get_user(user_id)
    assert user is not None
    payload = _profile_payload(user_id)
    schedule_changed = "schedule" in fields and fields["schedule"] != (before.schedule if before else None)
    if schedule_changed or "whatsapp_target" in fields or ("schedule" in fields and not brief_cron_installed(user_id)):
        cron = ensure_brief_cron(user_id, user.schedule)
        if cron["ok"]:
            from jobwright.onboarding import is_set_up
            from jobwright.welcome import send_welcome_async

            if is_set_up(user_id):
                send_welcome_async(user_id)
        payload["cron_synced"] = cron["ok"]
        payload["cron_id"] = cron.get("cron_id")
        payload["cron_error"] = cron.get("error")
    return payload


@router.get("/status")
def status(request: Request) -> dict:
    """Health for the dashboard banner: last run, last ops report, bridge."""
    from jobwright.ops import read_health
    from jobwright.pipeline import read_run_summary
    from jobwright.whatsapp import bridge_status

    current_user_id(request)
    summary = read_run_summary()
    return {
        "last_run": {
            k: summary.get(k) for k in ("started_at", "finished_at", "ok", "errors", "stages_requested")
        } if summary else None,
        "health": read_health(),
        "whatsapp_bridge": bridge_status(),
    }


@router.post("/session")
def set_session(body: SessionBody, request: Request, response: Response) -> dict:
    """Switch the active profile (only to profiles this login may open)."""
    identity = get_identity(request)
    user_id = body.user_id.strip()
    if get_user(user_id) is None:
        raise HTTPException(404, f"Unknown profile: {user_id}")
    if not can_open(identity, user_id):
        raise HTTPException(403, "You do not have access to that profile.")

    response.set_cookie(
        key=COOKIE_NAME,
        value=user_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
        path="/",
    )
    with config.user_context(user_id):
        from jobwright.web.session import _ensure_user_storage

        _ensure_user_storage()
        return _profile_payload(user_id)
