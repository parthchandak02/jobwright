"""Job detail and manual add."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobwright.database import FUNNEL_STAGES, get_connection, insert_manual_job
from jobwright.web.routers.board import _derive_work_model, _row_to_card

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{url:path}")
def get_job(url: str) -> dict:
    url = unquote(url)
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    card = _row_to_card(row)
    d = dict(row)
    card["full_description"] = d.get("full_description") or d.get("description") or ""
    card["work_model"] = _derive_work_model(d.get("location"), card.get("full_description"))
    card["score_reasoning"] = d.get("score_reasoning") or ""
    card["tailored_resume_path"] = d.get("tailored_resume_path")
    card["tailored_resume_docx_path"] = d.get("tailored_resume_docx_path")
    card["cover_letter_path"] = d.get("cover_letter_path")
    card["cover_letter_docx_path"] = d.get("cover_letter_docx_path")
    card["portfolio_project_ids"] = d.get("portfolio_project_ids")
    card["apply_error"] = d.get("apply_error")
    return card


class ManualJobBody(BaseModel):
    url: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    application_url: str | None = None
    funnel_stage: str = "backlog"
    notes: str | None = None


@router.post("/jobs")
def create_manual_job(body: ManualJobBody) -> dict:
    if body.funnel_stage not in FUNNEL_STAGES:
        raise HTTPException(400, f"Invalid stage: {body.funnel_stage}")
    try:
        job = insert_manual_job(
            body.url,
            title=body.title,
            company=body.company,
            location=body.location,
            description=body.description,
            application_url=body.application_url,
            funnel_stage=body.funnel_stage,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _row_to_card(job)
