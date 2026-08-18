"""Kanban board endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobwright.database import (
    CLOSED_OUTCOMES,
    FUNNEL_STAGES,
    advance_funnel,
    get_connection,
)

router = APIRouter(prefix="/api", tags=["board"])


def _derive_work_model(location: str | None, description: str | None = None) -> str | None:
    text = " ".join(part for part in (location, description) if part).lower()
    if "hybrid" in text:
        return "hybrid"
    if "remote" in text or "work from home" in text or "wfh" in text:
        return "remote"
    if location:
        return "onsite"
    return None


def _row_to_card(row) -> dict:
    d = dict(row)
    reasoning = (d.get("score_reasoning") or "").split("\n", 1)
    return {
        "url": d.get("url"),
        "title": d.get("title"),
        "company": d.get("company") or d.get("site"),
        "site": d.get("site"),
        "location": d.get("location"),
        "salary": d.get("salary"),
        "work_model": _derive_work_model(d.get("location")),
        "fit_score": d.get("fit_score"),
        "keywords": reasoning[0][:120] if reasoning else "",
        "reasoning": reasoning[1][:240] if len(reasoning) > 1 else "",
        "funnel_stage": d.get("funnel_stage") or "backlog",
        "outcome": d.get("outcome"),
        "source": d.get("source") or "discovered",
        "applied_manually": bool(d.get("applied_manually")),
        "applied_at": d.get("applied_at"),
        "first_response_at": d.get("first_response_at"),
        "follow_up_at": d.get("follow_up_at"),
        "notes": d.get("notes"),
        "board_updated_by": d.get("board_updated_by"),
        "board_updated_at": d.get("board_updated_at"),
        "has_resume": bool(d.get("tailored_resume_path") or d.get("tailored_resume_docx_path")),
        "has_cover": bool(d.get("cover_letter_path") or d.get("cover_letter_docx_path")),
        "application_url": d.get("application_url") or d.get("url"),
        "discovered_at": d.get("discovered_at"),
        "apply_status": d.get("apply_status"),
    }


@router.get("/board")
def get_board() -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY fit_score DESC NULLS LAST, discovered_at DESC"
    ).fetchall()
    columns = {stage: [] for stage in FUNNEL_STAGES}
    for row in rows:
        card = _row_to_card(row)
        stage = card["funnel_stage"] if card["funnel_stage"] in columns else "backlog"
        columns[stage].append(card)
    return {
        "stages": list(FUNNEL_STAGES),
        "columns": columns,
        "total": sum(len(v) for v in columns.values()),
    }


class MoveBody(BaseModel):
    to_stage: str
    note: str | None = None
    outcome: str | None = None


@router.post("/jobs/{url:path}/move")
def move_job(url: str, body: MoveBody) -> dict:
    url = unquote(url)
    if body.to_stage not in FUNNEL_STAGES:
        raise HTTPException(400, f"Invalid stage: {body.to_stage}")
    if body.outcome is not None and body.outcome not in CLOSED_OUTCOMES:
        raise HTTPException(400, f"Invalid outcome: {body.outcome}")
    if body.to_stage == "closed" and not body.outcome:
        raise HTTPException(400, "outcome required when closing a job")

    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    if not exists:
        raise HTTPException(404, "Job not found")

    applied_manually = True if body.to_stage == "applied" else None
    try:
        from_stage = advance_funnel(
            url,
            body.to_stage,
            "human",
            note=body.note,
            outcome=body.outcome if body.to_stage == "closed" else None,
            applied_manually=applied_manually,
            conn=conn,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if body.to_stage == "applied":
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET applied_at = COALESCE(applied_at, ?), "
            "apply_status = COALESCE(apply_status, 'applied') WHERE url = ?",
            (now, url),
        )
    conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return {"from_stage": from_stage, "job": _row_to_card(row)}


class PatchBody(BaseModel):
    notes: str | None = None
    follow_up_at: str | None = None
    outcome: str | None = None
    title: str | None = None
    company: str | None = None


@router.patch("/jobs/{url:path}")
def patch_job(url: str, body: PatchBody) -> dict:
    url = unquote(url)
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")

    sets: list[str] = []
    params: list = []
    if body.notes is not None:
        sets.append("notes = ?")
        params.append(body.notes)
    if body.follow_up_at is not None:
        sets.append("follow_up_at = ?")
        params.append(body.follow_up_at or None)
    if body.outcome is not None:
        if body.outcome and body.outcome not in CLOSED_OUTCOMES:
            raise HTTPException(400, f"Invalid outcome: {body.outcome}")
        sets.append("outcome = ?")
        params.append(body.outcome or None)
    if body.title is not None:
        sets.append("title = ?")
        params.append(body.title)
    if body.company is not None:
        sets.append("company = ?")
        params.append(body.company)

    if sets:
        now = datetime.now(timezone.utc).isoformat()
        sets.extend(["board_updated_by = ?", "board_updated_at = ?"])
        params.extend(["human", now, url])
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE url = ?", params)
        conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


@router.post("/jobs/{url:path}/response")
def mark_response(url: str) -> dict:
    """Stamp first_response_at (got a reply) without changing lane."""
    url = unquote(url)
    conn = get_connection()
    row = conn.execute("SELECT first_response_at FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    now = datetime.now(timezone.utc).isoformat()
    if not row["first_response_at"]:
        conn.execute(
            "UPDATE jobs SET first_response_at = ?, board_updated_by = 'human', "
            "board_updated_at = ? WHERE url = ?",
            (now, now, url),
        )
        conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


@router.delete("/jobs/{url:path}/response")
def clear_response(url: str) -> dict:
    url = unquote(url)
    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    if not exists:
        raise HTTPException(404, "Job not found")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE jobs SET first_response_at = NULL, board_updated_by = 'human', "
        "board_updated_at = ? WHERE url = ?",
        (now, url),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


@router.get("/jobs/{url:path}/history")
def stage_history(url: str) -> dict:
    url = unquote(url)
    conn = get_connection()
    rows = conn.execute(
        "SELECT from_stage, to_stage, actor, at, note FROM stage_history "
        "WHERE job_url = ? ORDER BY at ASC, id ASC",
        (url,),
    ).fetchall()
    return {"url": url, "history": [dict(r) for r in rows]}
