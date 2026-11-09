"""Settings → Claude: the connector address, connected Claude apps (revoke), and auto-apply.

Acts on the request's active profile only. The person turns auto-apply on or off
(``apply_via`` ``connector`` / ``off``) and chooses whether their Claude may press
Submit itself (``apply_enabled``; Parth's call 2026-11-09: each person decides). The
daily cap, minimum score and saved-answers-only rules still apply. Only admins may hand
a profile to the server runner (``server``).
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import hermes_cron
from jobwright.apply import answers as answers_mod
from jobwright.apply import safety
from jobwright.connector import store
from jobwright.connector.oauth import resource_url
from jobwright.connector.server import enabled
from jobwright.users import get_user, update_user
from jobwright.web.session import current_user_id, get_identity
from jobwright.web.txguard import TxGuardRoute

router = APIRouter(prefix="/api/connector", tags=["connector"], route_class=TxGuardRoute)


class ConnectorSettings(BaseModel):
    apply_via: Optional[Literal["connector", "server", "off"]] = None
    apply_enabled: Optional[bool] = None


def _state(user_id: str, request: Request) -> dict:
    user = get_user(user_id)
    veto = user.apply_veto_minutes if user else 180
    return {
        "enabled": enabled(),
        "url": resource_url(),
        "apply_via": user.apply_via if user else "off",
        "apply_enabled": bool(user and user.apply_enabled),
        "apply_min_score": user.apply_min_score if user else 8,
        "apply_daily_cap": user.apply_daily_cap if user else 2,
        "can_choose_server": get_identity(request).is_admin,
        "scopes": [{"scope": s, "label": store.SCOPE_LABELS[s]} for s in store.SCOPES],
        "clients": store.list_grants(user_id),
        # Setup guide: how many required application answers are still empty, whether applying is
        # stopped, and when the daily picks arrive (from the Hermes pick script, if one is installed).
        "missing_answers": len(answers_mod.load_answers().missing()),
        "apply_paused": bool(user and user.apply_paused) or safety.kill_switch_on(),
        "daily_pick": hermes_cron.apply_pick_schedule(user_id, veto),
    }


@router.get("")
def connector_status(request: Request) -> dict:
    return _state(current_user_id(request), request)


@router.delete("/clients/{grant_id}")
def revoke_client(grant_id: str, request: Request) -> dict:
    user_id = current_user_id(request)
    if not store.revoke_grant(grant_id, user_id=user_id, reason=f"revoked in Settings by {get_identity(request).email}"):
        raise HTTPException(404, "No such connected Claude")
    return _state(user_id, request)


@router.put("/settings")
def put_settings(body: ConnectorSettings, request: Request) -> dict:
    user_id = current_user_id(request)
    if body.apply_via == "server" and not get_identity(request).is_admin:
        raise HTTPException(403, "Only an admin can hand applications to the server runner")
    changes: dict = {}
    if body.apply_via is not None:
        changes["apply_via"] = body.apply_via
    if body.apply_enabled is not None:
        changes["apply_enabled"] = body.apply_enabled
    if not changes:
        raise HTTPException(400, "Nothing to change")
    update_user(user_id, **changes)
    return _state(user_id, request)
