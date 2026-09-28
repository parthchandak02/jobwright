"""Admin: profiles, logins, operator alerts, watchdog."""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import cf_access, config
from jobwright.users import (
    _normalize_whatsapp_target,
    apply_clock_to_cron,
    describe_cron_schedule,
    find_user_by_whatsapp,
    get_user,
    list_admin_emails,
    list_users,
    remove_user,
    set_admin_emails,
    update_user,
    validate_brief_schedule,
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


def _usage_rows(conn, days: int) -> list:
    return conn.execute(
        "SELECT model, SUM(prompt_tokens), SUM(completion_tokens), SUM(cost_usd), COUNT(cost_usd), COUNT(*), "
        "SUM(COALESCE(cached_tokens, 0)) "
        "FROM llm_usage WHERE at >= ? GROUP BY model",
        ((datetime.now(UTC) - timedelta(days=days)).isoformat(),),
    ).fetchall()


def _sum_usage(out: dict[str, Any], rows: list) -> dict[str, Any]:
    from jobwright.llm import estimate_cost

    cost: float | None = None
    for model, prompt, completion, stored, priced_rows, n, cached in rows:
        prompt, completion = int(prompt or 0), int(completion or 0)
        out["calls"] += int(n)
        out["prompt_tokens"] += prompt
        out["completion_tokens"] += completion
        estimate = estimate_cost(model or "", prompt, completion, int(cached or 0))
        value = estimate if estimate is not None else stored
        if value is not None:
            cost = (cost or 0.0) + float(value)
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    out["cost_usd"] = round(cost, 4) if cost is not None else None
    return out


def _empty_usage(user) -> dict[str, Any]:
    return {
        "user_id": user.user_id, "name": user.name or user.user_id, "calls": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": None, "error": None,
    }


def _open_ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _user_usage(user, days: int) -> dict[str, Any]:
    """Token use and estimated cost from one profile's llm_usage (read-only)."""
    out = _empty_usage(user)
    db = user.resolve_data_dir() / "jobwright.db"
    if not db.exists():
        return out
    try:
        conn = _open_ro(db)
        try:
            rows = _usage_rows(conn, days)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        out["error"] = "no usage table" if "no such table" in str(exc) else str(exc)
        return out
    return _sum_usage(out, rows)


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


OVERVIEW_TIMEOUT = 6.0
_BRIEF_STATUS_PREFIX = "BRIEF_STATUS_"


def _system_sources() -> dict[str, Any]:
    from jobwright import hermes_channels, whatsapp
    from jobwright.hermes_cron import _run_hermes

    def chats() -> dict[str, dict]:
        return {c["target"]: c for c in whatsapp.list_chats(show_all=True).get("chats") or []}

    def cron_listing() -> str | None:
        res = _run_hermes(["cron", "list"])
        return None if res.get("error") else res.get("stdout", "")

    jobs = {
        "bridge": whatsapp.bridge_status,
        "access": cf_access.status,
        "hermes": lambda: hermes_channels.plan().as_dict(),
        "chats": chats,
        "cron": cron_listing,
    }
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs))
    futures = {key: pool.submit(fn) for key, fn in jobs.items()}
    pool.shutdown(wait=False)
    deadline = time.monotonic() + OVERVIEW_TIMEOUT
    out: dict[str, Any] = {}
    for key, fut in futures.items():
        try:
            out[key] = fut.result(timeout=max(0.0, deadline - time.monotonic()))
        except concurrent.futures.TimeoutError:
            out[key] = TimeoutError(f"{key} timed out")
        except Exception as exc:  # noqa: BLE001
            out[key] = exc
    return out


def _access_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Exception):
        return {"configured": None, "in_sync": None, "add": [], "remove": [], "error": str(value)}
    return {
        "configured": value.get("configured"), "in_sync": value.get("in_sync"),
        "add": value.get("add") or [], "remove": value.get("remove") or [], "error": value.get("error"),
    }


def _hermes_summary(value: Any) -> tuple[dict[str, Any], dict[str, str]]:
    if isinstance(value, FileNotFoundError):
        return {"changed": False, "pending": 0, "error": f"Hermes config not found: {value.filename}"}, {}
    if isinstance(value, Exception):
        return {"changed": False, "pending": 0, "error": str(value)}, {}
    statuses = {e["user_id"]: e["status"] for e in value.get("entries") or []}
    statuses.update({s["user_id"]: "skipped" for s in value.get("skipped") or []})
    pending = len(value.get("add") or []) + len(value.get("update") or [])
    return {"changed": bool(value.get("changed")), "pending": pending, "error": None}, statuses


def _last_brief(data_dir: Path) -> dict[str, Any]:
    files = sorted(data_dir.glob(f"{_BRIEF_STATUS_PREFIX}*"))
    if not files:
        return {"at": None, "notified": None, "status": None}
    latest = files[-1]
    lines = [line.strip() for line in latest.read_text(encoding="utf-8").splitlines() if line.strip()]
    notify = next((line for line in reversed(lines) if line.startswith("notify_")), "")
    status, notified = None, None
    if notify.startswith("notify_sent"):
        status = "ok"
        parts = notify.split()
        notified = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    elif notify.startswith("notify_failed") or any(line.startswith("preflight_failed") for line in lines):
        status = "failed"
    elif notify.startswith("notify_skipped"):
        status, notified = "skipped", 0
    at = datetime.fromtimestamp(latest.stat().st_mtime).astimezone().isoformat()
    return {"at": at, "notified": notified, "status": status}


def _counts(conn: sqlite3.Connection, followup_days: int) -> dict[str, int]:
    from jobwright.followups import due_followups

    since = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    def one(sql: str, *args) -> int:
        return int(conn.execute(sql, args).fetchone()[0] or 0)

    return {
        "new_7d": one("SELECT COUNT(*) FROM jobs WHERE discovered_at >= ?", since),
        "sent_7d": one("SELECT COUNT(*) FROM jobs WHERE whatsapp_notified_at >= ?", since),
        "applied_total": one("SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"),
        "open": one("SELECT COUNT(*) FROM jobs WHERE COALESCE(funnel_stage, 'backlog') != 'closed'"),
        "followups_due": len(due_followups(conn, days=followup_days)),
    }


def _read_profile_strict() -> dict:
    path = Path(config.PROFILE_PATH)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"profile.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("profile.json is not a JSON object")
    return data


def _resolve_chat_name(target: str, chat: dict) -> str:
    jid = target.removeprefix("whatsapp:")
    name = str(chat.get("name") or "")
    if name and name != jid.split("@")[0]:
        return name
    try:
        from jobwright.whatsapp import chat_name

        return chat_name(target) or jid.split("@")[0]
    except Exception:  # noqa: BLE001
        return jid.split("@")[0]


def _profile_fields(user) -> dict[str, Any]:
    """Per-profile data read inside that profile's context (one read-only DB open)."""
    from jobwright.onboarding import onboarding_status
    from jobwright.ops import read_health
    from jobwright.scoring.criteria import load_criteria
    from jobwright.web.routers.quality import _recommendation, latest_eval_report

    out: dict[str, Any] = {}
    with config.user_context(user.user_id):
        steps = onboarding_status()["steps"]
        out["setup_complete"] = bool(steps.get("resume") and steps.get("profile"))
        health = read_health() or {}
        out["health"] = {"level": health.get("level"), "lines": list(health.get("lines") or [])}
        out["last_brief"] = _last_brief(Path(config.APP_DIR))
        out["notify_threshold"] = load_criteria(_read_profile_strict()).notify_threshold
        report = latest_eval_report()
        rec = _recommendation(report) if report else None
        out["recommended_threshold"] = rec.get("threshold") if rec else None
        db = Path(config.DB_PATH)
        if db.exists():
            conn = _open_ro(db)
            try:
                out["counts"] = _counts(conn, user.followup_days)
                usage = _sum_usage(_empty_usage(user), _usage_rows(conn, 30))
            finally:
                conn.close()
            out["cost_30d"] = {"tokens": usage["total_tokens"], "cost_usd": usage["cost_usd"]}
    return out


def _clock(schedule: str) -> tuple[int | None, int | None]:
    parts = (schedule or "").split()
    if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[1]), int(parts[0])
    return None, None


def _overview_row(user, sources: dict[str, Any], hermes_status: dict[str, str]) -> dict[str, Any]:
    from jobwright.hermes_cron import brief_cron_name, find_cron_id

    chats = sources.get("chats") if isinstance(sources.get("chats"), dict) else {}
    target = _normalize_whatsapp_target(user.whatsapp_target)
    chat = chats.get(target) or {}
    jid = target.removeprefix("whatsapp:")
    listing = sources.get("cron")
    hour, minute = _clock(user.schedule)
    row: dict[str, Any] = {
        "user_id": user.user_id, "name": user.name or user.user_id, "emails": user.emails,
        "setup_complete": False,
        "health": {"level": None, "lines": []},
        "last_brief": {"at": None, "notified": None, "status": None},
        "whatsapp": {
            "target": target or None,
            "name": _resolve_chat_name(target, chat) if target else None,
            "type": ("group" if jid.endswith("@g.us") else "dm") if target else None,
        },
        "schedule": user.schedule, "schedule_label": describe_cron_schedule(user.schedule),
        "hour": hour, "minute": minute,
        "notify_threshold": None, "recommended_threshold": None,
        "brief_top_n": user.brief_top_n, "human_gate": user.human_gate,
        "weekly_summary": user.weekly_summary, "followup_days": user.followup_days,
        "counts": {"new_7d": 0, "sent_7d": 0, "applied_total": 0, "open": 0, "followups_due": 0},
        "cost_30d": {"tokens": 0, "cost_usd": None},
        "hermes_status": hermes_status.get(user.user_id),
        "brief_cron": (find_cron_id(listing, brief_cron_name(user.user_id)) is not None)
        if isinstance(listing, str) else None,
        "error": None,
    }
    try:
        row.update(_profile_fields(user))
    except Exception as exc:  # noqa: BLE001
        message = f"could not read profile: {exc}"
        row["health"] = {"level": "fail", "lines": [message, *row["health"]["lines"]]}
        row["error"] = message
    return row


def _ops_target_name(target: str, chats: dict[str, dict]) -> str | None:
    if not target:
        return None
    normalized = _normalize_whatsapp_target(target)
    if chats.get(normalized, {}).get("name"):
        return chats[normalized]["name"]
    owner = find_user_by_whatsapp(normalized)
    if owner:
        return owner.name or owner.user_id
    return normalized.removeprefix("whatsapp:").split("@")[0]


@router.get("/overview")
def overview(request: Request) -> dict:
    require_admin(request)
    from jobwright.ops import ops_target

    sources = _system_sources()
    hermes, hermes_status = _hermes_summary(sources["hermes"])
    chats = sources["chats"] if isinstance(sources["chats"], dict) else {}
    target = ops_target()
    bridge = sources["bridge"]
    return {
        "bridge": bridge if isinstance(bridge, str) else "unreachable",
        "access": _access_summary(sources["access"]),
        "hermes": hermes,
        "settings": {"admins": list_admin_emails(), "ops_target": target,
                     "ops_target_name": _ops_target_name(target, chats)},
        "users": [_overview_row(u, sources, hermes_status) for u in list_users()],
    }


def _single_row(user_id: str) -> dict[str, Any]:
    user = get_user(user_id)
    assert user is not None
    sources = _system_sources()
    return _overview_row(user, sources, _hermes_summary(sources["hermes"])[1])


class AdminUserPatch(BaseModel):
    name: str | None = None
    emails: list[str] | None = None
    whatsapp_target: str | None = None
    schedule: str | None = None
    hour: int | None = None
    minute: int | None = None
    notify_threshold: int | None = None
    brief_top_n: int | None = None
    human_gate: bool | None = None
    weekly_summary: bool | None = None
    followup_days: int | None = None


def _registry_fields(user, body: AdminUserPatch) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True, exclude={"hour", "minute", "schedule", "notify_threshold"})
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            raise ValueError("Name cannot be empty.")
    if "whatsapp_target" in fields:
        target = _normalize_whatsapp_target(fields["whatsapp_target"])
        if target and len(target) < 14:
            raise ValueError("WhatsApp chat id looks wrong.")
        fields["whatsapp_target"] = target
    if "brief_top_n" in fields and not 0 <= fields["brief_top_n"] <= 100:
        raise ValueError("brief_top_n must be between 0 (all) and 100.")
    if "followup_days" in fields and not 1 <= fields["followup_days"] <= 90:
        raise ValueError("followup_days must be between 1 and 90.")
    if (body.hour is None) != (body.minute is None):
        raise ValueError("Send hour and minute together.")
    if body.schedule is not None and body.hour is not None:
        raise ValueError("Send either schedule or hour+minute, not both.")
    if body.schedule is not None:
        fields["schedule"] = validate_brief_schedule(body.schedule.strip())
    elif body.hour is not None:
        fields["schedule"] = apply_clock_to_cron(user.schedule, body.hour, body.minute)
    if body.notify_threshold is not None and not 1 <= body.notify_threshold <= 10:
        raise ValueError("notify_threshold must be between 1 and 10.")
    return fields


def _store_notify_threshold(user_id: str, threshold: int) -> None:
    from jobwright.web.routers.quality import write_profile

    with config.user_context(user_id):
        if not Path(config.PROFILE_PATH).exists():
            raise ValueError("This profile has no profile.json yet (setup not finished).")
        profile = _read_profile_strict()
        criteria = profile.get("match_criteria")
        if not isinstance(criteria, dict):
            criteria = {}
        criteria["notify_threshold"] = threshold
        profile["match_criteria"] = criteria
        write_profile(profile)


def _is_set_up(user_id: str) -> bool:
    from jobwright.onboarding import onboarding_status

    try:
        with config.user_context(user_id):
            steps = onboarding_status()["steps"]
    except Exception:  # noqa: BLE001
        return False
    return bool(steps.get("resume") and steps.get("profile"))


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: AdminUserPatch, request: Request) -> dict:
    require_admin(request)
    from jobwright.hermes_cron import ensure_brief_cron

    user = get_user(user_id)
    if user is None:
        raise HTTPException(404, "Unknown profile")
    try:
        fields = _registry_fields(user, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not fields and body.notify_threshold is None:
        raise HTTPException(400, "Nothing to update")
    try:
        if body.notify_threshold is not None:
            _store_notify_threshold(user_id, body.notify_threshold)
        if fields:
            user = update_user(user_id, **fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    access = cf_access.auto_sync() if "emails" in fields else None
    cron = None
    if ("schedule" in fields or "whatsapp_target" in fields) and _is_set_up(user_id):
        cron = ensure_brief_cron(user_id, user.schedule)
        if cron.get("ok"):
            from jobwright.welcome import send_welcome_async

            send_welcome_async(user_id)
    return {"user": _single_row(user_id), "access_sync": access, "cron": cron,
            "ok": True, "user_id": user_id, "emails": user.emails}


@router.post("/users/{user_id}/test-message")
def user_test_message(user_id: str, request: Request) -> dict:
    require_admin(request)
    from jobwright.whatsapp import send_test

    user = get_user(user_id)
    if user is None:
        raise HTTPException(404, "Unknown profile")
    target = _normalize_whatsapp_target(user.whatsapp_target)
    if not target.startswith("whatsapp:") or len(target) < 14:
        raise HTTPException(400, "This person has no WhatsApp chat set.")
    try:
        send_test(target, (user.name or "").split(" ")[0])
    except RuntimeError as exc:
        raise HTTPException(502, f"WhatsApp send failed: {exc}") from exc
    return {"sent": True, "target": target}


@router.post("/users/{user_id}/run")
def user_run(user_id: str, request: Request) -> dict:
    require_admin(request)
    from jobwright.web.routers.runs import start_pipeline_run

    if get_user(user_id) is None:
        raise HTTPException(404, "Unknown profile")
    with config.user_context(user_id):
        return start_pipeline_run(user_id)


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
