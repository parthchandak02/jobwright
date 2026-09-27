"""WhatsApp chat picker and test message."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import config
from jobwright.web.session import current_user_id, get_identity

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _profile_phone() -> str:
    try:
        return (json.loads(config.PROFILE_PATH.read_text(encoding="utf-8")).get("personal") or {}).get("phone") or ""
    except (OSError, ValueError):
        return ""


@router.get("/chats")
def chats(request: Request, phone: str = "") -> dict:
    from jobwright.whatsapp import list_chats

    current_user_id(request)
    if not get_identity(request).is_admin:
        raise HTTPException(403, "Only an admin can choose WhatsApp chats.")
    return list_chats(for_phone=phone or _profile_phone(), show_all=True)


class TestBody(BaseModel):
    target: str = ""


@router.post("/test")
def test_message(body: TestBody, request: Request) -> dict:
    from jobwright.users import _normalize_whatsapp_target, get_user
    from jobwright.whatsapp import send_test

    uid = current_user_id(request)
    user = get_user(uid)
    own = _normalize_whatsapp_target(user.whatsapp_target if user else "")
    if get_identity(request).is_admin:
        target = _normalize_whatsapp_target(body.target) if body.target else own
    else:
        target = own
    if not target.startswith("whatsapp:") or len(target) < 14:
        raise HTTPException(400, "No WhatsApp chat is connected yet.")
    try:
        send_test(target, (user.name if user else "").split(" ")[0])
    except RuntimeError as exc:
        raise HTTPException(502, f"WhatsApp send failed: {exc}") from exc
    return {"ok": True, "target": target}
