"""Automatic-apply surfaces: answer bank, human-in-the-loop requests, evidence, picks.

All routes act on the request's active profile only.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jobwright.apply import answers as answers_mod
from jobwright.apply import auto, evidence, hitl, safety
from jobwright.users import get_user
from jobwright.web.session import current_user_id, get_identity
from jobwright.web.txguard import TxGuardRoute

router = APIRouter(prefix="/api", tags=["apply"], route_class=TxGuardRoute)


class AnswersBody(BaseModel):
    answers: dict[str, Optional[str]] = Field(default_factory=dict)


class CustomAnswerBody(BaseModel):
    question: str
    value: str = ""


class ProvideBody(BaseModel):
    value: str = ""


def _who(request: Request) -> str:
    try:
        ident = get_identity(request)
        return f"dashboard:{ident.email}" if getattr(ident, "email", None) else "dashboard"
    except HTTPException:
        return "dashboard"


@router.get("/answers")
def get_answers(request: Request) -> dict:
    current_user_id(request)
    return answers_mod.load_answers().as_public_dict()


@router.put("/answers")
def put_answers(body: AnswersBody, request: Request) -> dict:
    current_user_id(request)
    try:
        bank = answers_mod.set_answers(body.answers, source="settings")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return bank.as_public_dict()


@router.put("/answers/custom")
def put_custom_answer(body: CustomAnswerBody, request: Request) -> dict:
    current_user_id(request)
    try:
        bank = answers_mod.set_custom_answer(body.question, body.value, source="settings")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return bank.as_public_dict()


@router.get("/apply/status")
def apply_status(request: Request) -> dict:
    user = get_user(current_user_id(request))
    return {
        "apply_enabled": bool(user and user.apply_enabled),
        "apply_mode": user.apply_mode if user else "veto",
        "apply_via": user.apply_via if user else "off",
        "apply_daily_cap": user.apply_daily_cap if user else 0,
        "apply_min_score": user.apply_min_score if user else 8,
        "apply_veto_minutes": user.apply_veto_minutes if user else 180,
        "apply_paused": bool(user and user.apply_paused),
        "apply_paused_reason": (user.apply_paused_reason if user else "") or "",
        "kill_switch": safety.kill_switch_on(),
        "submitted_today": safety.live_submissions_today(),
        "missing_answers": [s.key for s in answers_mod.load_answers().missing()],
    }


# --- human-in-the-loop -----------------------------------------------------


def _pending_or_404(pending_id: str) -> dict:
    row = hitl.get_pending(pending_id)
    if row is None:
        raise HTTPException(404, "No such request")
    return row


@router.get("/apply/pending")
def list_pending(request: Request, status: Optional[str] = "open") -> dict:
    current_user_id(request)
    return {"pending": hitl.list_pending(status or None)}


@router.get("/apply/pending/{pending_id}")
def get_pending(pending_id: str, request: Request) -> dict:
    current_user_id(request)
    hitl.expire_stale()
    row = _pending_or_404(pending_id)
    row["has_screenshot"] = hitl.live_screenshot_path(pending_id).is_file()
    return row


@router.post("/apply/pending/{pending_id}/provide")
def provide_pending(pending_id: str, body: ProvideBody, request: Request) -> dict:
    current_user_id(request)
    _pending_or_404(pending_id)
    try:
        return hitl.provide(pending_id, body.value, by=_who(request))
    except hitl.ProvideError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/apply/pending/{pending_id}/screenshot")
def pending_screenshot(pending_id: str, request: Request) -> FileResponse:
    current_user_id(request)
    row = _pending_or_404(pending_id)
    path = hitl.live_screenshot_path(row["id"])
    if not path.is_file():
        raise HTTPException(404, "No live screenshot")
    return FileResponse(str(path), media_type="image/png", headers={"Cache-Control": "no-store"})


# --- evidence ----------------------------------------------------------------


@router.get("/apply/submissions")
def list_submissions(request: Request, limit: int = 30) -> dict:
    current_user_id(request)
    return {"submissions": evidence.list_submissions(min(max(limit, 1), 200))}


@router.get("/apply/submissions/{submission_id}")
def get_submission(submission_id: int, request: Request) -> dict:
    current_user_id(request)
    row = evidence.get_submission(submission_id)
    if row is None:
        raise HTTPException(404, "No such submission")
    row["picks"] = auto.picks_for_job(row["job_url"])
    return row


@router.get("/apply/submissions/{submission_id}/screenshots/{name}")
def submission_screenshot(submission_id: int, name: str, request: Request) -> FileResponse:
    current_user_id(request)
    path = evidence.submission_file(submission_id, name)
    if path is None:
        raise HTTPException(404, "No such screenshot")
    return FileResponse(str(path), media_type="image/png")


# --- picks (veto window) -----------------------------------------------------


@router.get("/apply/picks")
def list_picks(request: Request, job: Optional[str] = None) -> dict:
    current_user_id(request)
    if job:
        from jobwright.web.jobkeys import resolve_job_key

        return {"picks": auto.picks_for_job(resolve_job_key(job))}
    return {"picks": auto.list_picks()}


@router.post("/apply/picks/{pick_id}/veto")
def veto_pick(pick_id: int, request: Request) -> dict:
    current_user_id(request)
    try:
        rows = auto.veto(pick_id, by=_who(request))
    except auto.VetoError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"picks": rows}
