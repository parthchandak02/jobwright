"""WhatsApp daily-notify endpoints for the active dashboard user."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from jobwright import notify
from jobwright.web.txguard import TxGuardRoute

router = APIRouter(prefix="/api/notify", tags=["notify"], route_class=TxGuardRoute)


@router.post("")
def send_notify(dry_run: bool = False) -> dict:
    """Send (or preview) the WhatsApp digest for newly prepared jobs (an explicit send ignores a paused search)."""
    try:
        return notify.run_notify(dry_run=dry_run, respect_pause=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/preview")
def preview_notify() -> dict:
    """Build the message without sending or marking jobs."""
    return notify.run_notify(dry_run=True, respect_pause=False)
