"""New-profile onboarding (works before the login has any profile)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from jobwright import config
from jobwright.users import get_user, users_for_email
from jobwright.web.session import COOKIE_NAME, _ensure_user_storage, current_user_id, get_identity

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class CreateProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    user_id: str | None = Field(default=None, max_length=32)
    emails: list[str] | None = None  # admin only: create for someone else


@router.get("/status")
def status(request: Request) -> dict:
    from jobwright.onboarding import onboarding_status

    identity = get_identity(request)
    active = getattr(request.state, "active_user", None)
    if not active:
        return {"email": identity.email, "has_profile": False, "steps": {}, "complete": False}
    data = onboarding_status()
    return {"email": identity.email, "has_profile": True, **data}


@router.post("/profile")
def create_profile(body: CreateProfileBody, request: Request, response: Response) -> dict:
    """Create a profile bound to the caller's login (admins may bind other emails)."""
    from jobwright.onboarding import create_profile as _create

    identity = get_identity(request)
    if body.emails and not identity.is_admin:
        raise HTTPException(403, "Only an admin can create a profile for someone else.")
    if not identity.is_admin and users_for_email(identity.email):
        raise HTTPException(409, "You already have a profile.")
    if not identity.email and not identity.is_admin:
        raise HTTPException(400, "No login email.")
    email = identity.email
    try:
        uid = _create(name=body.name, email=email, user_id=body.user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.emails:
        from jobwright.users import update_user

        update_user(uid, emails=sorted({*body.emails, *( [email] if email else [])}))
    with config.user_context(uid):
        _ensure_user_storage()
    response.set_cookie(COOKIE_NAME, uid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365, path="/")
    return {"user_id": uid, "name": get_user(uid).name}


@router.post("/draft")
async def draft(
    request: Request,
    file: Annotated[UploadFile | None, File()] = None,
    target_roles: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    min_salary: Annotated[str, Form()] = "",
    avoid: Annotated[str, Form()] = "",
) -> dict:
    """Save the resume (if uploaded) and return an editable draft. Writes nothing else."""
    from starlette.concurrency import run_in_threadpool

    from jobwright.onboarding import draft_from_resume
    from jobwright.resume import load_resume_text

    current_user_id(request)
    if file is not None and file.filename:
        data = await file.read()
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "Upload your resume as a PDF.")
        pdf = config.RESUME_PDF_PATH
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(data)
        if config.RESUME_MD_PATH.exists():
            config.RESUME_MD_PATH.unlink()
    try:
        resume_text = await run_in_threadpool(load_resume_text)
    except FileNotFoundError as exc:
        raise HTTPException(400, "Upload your resume first.") from exc
    hints = {"target_roles": target_roles, "locations": locations, "min_salary": min_salary, "avoid": avoid}
    try:
        return await run_in_threadpool(draft_from_resume, resume_text, hints)
    except Exception as exc:  # noqa: BLE001 - surface LLM/provider problems to the user
        raise HTTPException(502, f"Could not draft your setup: {exc}") from exc


class ConfirmBody(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)
    criteria: dict[str, Any] | None = None
    searches: dict[str, Any] = Field(default_factory=dict)


@router.post("/confirm")
def confirm(body: ConfirmBody, request: Request) -> dict:
    from jobwright.onboarding import apply_draft, onboarding_status
    from jobwright.scoring.criteria import parse_criteria

    current_user_id(request)
    draft = body.model_dump()
    if draft.get("criteria"):
        draft["criteria"] = parse_criteria(draft["criteria"]).to_dict()
    for section in ("password", "eeo_voluntary"):
        draft["profile"].pop(section, None)
    apply_draft(draft)
    return onboarding_status()
