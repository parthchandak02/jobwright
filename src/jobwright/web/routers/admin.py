"""Admin: profiles, logins, operator alerts, watchdog."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import cf_access, config
from jobwright.users import (
    describe_cron_schedule,
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
                "schedule": u.schedule, "schedule_label": describe_cron_schedule(u.schedule),
                "human_gate": u.human_gate, "brief_top_n": u.brief_top_n,
                "apply_enabled": u.apply_enabled, "cron": brief_cron_name(u.user_id), **_user_health(u),
            }
            for u in list_users()
        ],
    }


def _user_usage(user, days: int) -> dict[str, Any]:
    """Token use and estimated cost from one profile's llm_usage (read-only)."""
    import sqlite3

    from jobwright.llm import estimate_cost

    out: dict[str, Any] = {
        "user_id": user.user_id, "name": user.name or user.user_id, "calls": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": None, "error": None,
    }
    db = user.resolve_data_dir() / "jobwright.db"
    if not db.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            rows = conn.execute(
                "SELECT model, SUM(prompt_tokens), SUM(completion_tokens), SUM(cost_usd), COUNT(cost_usd), COUNT(*) "
                "FROM llm_usage WHERE at >= ? GROUP BY model",
                ((datetime.now(UTC) - timedelta(days=days)).isoformat(),),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        out["error"] = "no usage table" if "no such table" in str(exc) else str(exc)
        return out
    cost: float | None = None
    for model, prompt, completion, stored, priced_rows, n in rows:
        prompt, completion = int(prompt or 0), int(completion or 0)
        out["calls"] += int(n)
        out["prompt_tokens"] += prompt
        out["completion_tokens"] += completion
        estimate = estimate_cost(model or "", prompt, completion) if priced_rows != n else None
        value = estimate if estimate is not None else stored
        if value is not None:
            cost = (cost or 0.0) + float(value)
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    out["cost_usd"] = round(cost, 4) if cost is not None else None
    return out


@router.get("/costs")
def costs(request: Request, days: int = 30) -> dict:
    require_admin(request)
    days = max(1, min(days, 365))
    rows = [_user_usage(u, days) for u in list_users()]
    priced = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    total = {
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "completion_tokens": sum(r["completion_tokens"] for r in rows),
        "total_tokens": sum(r["total_tokens"] for r in rows),
        "calls": sum(r["calls"] for r in rows),
        "cost_usd": round(sum(priced), 4) if priced else None,
    }
    return {"days": days, "users": rows, "total": total}


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
    access = cf_access.auto_sync() if "emails" in fields else None
    return {"ok": True, "user_id": user.user_id, "emails": user.emails, "access_sync": access}


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

    access = None
    if body.admins is not None:
        admins = [a for a in body.admins if a.strip()]
        if identity.email and identity.email not in [a.lower().strip() for a in admins]:
            raise HTTPException(400, "You cannot remove your own admin access.")
        set_admin_emails(admins)
        access = cf_access.auto_sync()
    if body.ops_target is not None:
        set_ops_target(body.ops_target)
    return {"admins": list_admin_emails(), "ops_target": ops_target(), "access_sync": access}


@router.get("/access")
def access_status(request: Request) -> dict:
    require_admin(request)
    return cf_access.status()


@router.post("/access/sync")
def access_sync(request: Request) -> dict:
    require_admin(request)
    if not cf_access.is_configured():
        raise HTTPException(400, "CLOUDFLARE_API_TOKEN is not set.")
    try:
        return cf_access.apply_sync()
    except cf_access.CFAccessError as exc:
        raise HTTPException(502, str(exc)) from exc


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


def _channels(prune: bool = False, write: bool = False) -> dict:
    from jobwright import hermes_channels

    try:
        if write:
            return hermes_channels.apply(prune=prune)
        return hermes_channels.plan(prune=prune).as_dict()
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Hermes config not found: {exc.filename}") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"Could not read the Hermes config: {exc}") from exc


@router.get("/hermes-channels")
def hermes_channels_plan(request: Request) -> dict:
    require_admin(request)
    return _channels()


class HermesChannelsApply(BaseModel):
    prune: bool = False


@router.post("/hermes-channels/apply")
def hermes_channels_apply(request: Request, body: HermesChannelsApply | None = None) -> dict:
    require_admin(request)
    return _channels(prune=bool(body and body.prune), write=True)
