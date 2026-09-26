"""Admin: profiles, logins, operator alerts, watchdog."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import config
from jobwright.users import (
    get_user,
    list_admin_emails,
    list_users,
    remove_user,
    set_admin_emails,
    update_user,
)
from jobwright.web.session import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_health(user) -> dict[str, Any]:
    data_dir = user.resolve_data_dir()
    today = data_dir / f"BRIEF_STATUS_{datetime.now():%Y%m%d}"
    status = today.read_text(encoding="utf-8").splitlines() if today.exists() else []
    health = None
    try:
        health = json.loads((data_dir / "logs" / "ops_health.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"brief_today": status[-4:], "health": health}


@router.get("/users")
def users(request: Request) -> dict:
    require_admin(request)
    from jobwright.hermes_cron import brief_cron_name

    return {
        "users": [
            {
                "user_id": u.user_id, "name": u.name, "emails": u.emails, "whatsapp_target": u.whatsapp_target,
                "schedule": u.schedule, "human_gate": u.human_gate, "brief_top_n": u.brief_top_n,
                "apply_enabled": u.apply_enabled, "cron": brief_cron_name(u.user_id), **_user_health(u),
            }
            for u in list_users()
        ],
    }


class AdminUserPatch(BaseModel):
    name: str | None = None
    emails: list[str] | None = None
    human_gate: bool | None = None
    brief_top_n: int | None = None


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: AdminUserPatch, request: Request) -> dict:
    require_admin(request)
    if get_user(user_id) is None:
        raise HTTPException(404, "Unknown profile")
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "Nothing to update")
    user = update_user(user_id, **fields)
    return {"ok": True, "user_id": user.user_id, "emails": user.emails}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, delete_data: bool = False) -> dict:
    require_admin(request)
    from jobwright.hermes_cron import remove_brief_cron

    if get_user(user_id) is None:
        raise HTTPException(404, "Unknown profile")
    cron = remove_brief_cron(user_id)
    remove_user(user_id, delete_data=delete_data)
    return {"ok": True, "cron": cron, "data_deleted": delete_data}


class AdminSettings(BaseModel):
    admins: list[str] | None = None
    ops_target: str | None = None


@router.get("/settings")
def get_settings(request: Request) -> dict:
    require_admin(request)
    from jobwright.ops import ops_target

    return {"admins": list_admin_emails(), "ops_target": ops_target()}


@router.put("/settings")
def put_settings(body: AdminSettings, request: Request) -> dict:
    identity = require_admin(request)
    from jobwright.ops import ops_target, set_ops_target

    if body.admins is not None:
        admins = [a for a in body.admins if a.strip()]
        if identity.email and identity.email not in [a.lower().strip() for a in admins]:
            raise HTTPException(400, "You cannot remove your own admin access.")
        set_admin_emails(admins)
    if body.ops_target is not None:
        set_ops_target(body.ops_target)
    return {"admins": list_admin_emails(), "ops_target": ops_target()}


@router.post("/watchdog")
def ensure_watchdog(request: Request) -> dict:
    require_admin(request)
    from jobwright.hermes_cron import ensure_watchdog_cron

    return ensure_watchdog_cron()


@router.post("/ops-test")
def ops_test(request: Request) -> dict:
    require_admin(request)
    from jobwright.ops import Report, deliver

    rep = Report(user=config.get_active_user_id() or "admin", level="warn", lines=["test alert from the dashboard"])
    return {"result": deliver(rep, force=True)}
