"""Settings → Claude: the connector address, connected Claude apps (revoke), and who applies.

Acts on the request's active profile only. ``apply_via`` can be switched
between ``connector`` and ``off`` by the person; only admins may hand a
profile to the server runner (``server``).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright.connector import store
from jobwright.connector.oauth import resource_url
from jobwright.connector.server import enabled
from jobwright.users import get_user, update_user
from jobwright.web.session import current_user_id, get_identity
from jobwright.web.txguard import TxGuardRoute

router = APIRouter(prefix="/api/connector", tags=["connector"], route_class=TxGuardRoute)


class ConnectorSettings(BaseModel):
    apply_via: Literal["connector", "server", "off"]


def _state(user_id: str, request: Request) -> dict:
    user = get_user(user_id)
    return {
        "enabled": enabled(),
        "url": resource_url(),
        "apply_via": user.apply_via if user else "off",
        "apply_enabled": bool(user and user.apply_enabled),
        "can_choose_server": get_identity(request).is_admin,
        "scopes": [{"scope": s, "label": store.SCOPE_LABELS[s]} for s in store.SCOPES],
        "clients": store.list_grants(user_id),
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
    update_user(user_id, apply_via=body.apply_via)
    return _state(user_id, request)
