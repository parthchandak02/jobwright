"""Kanban board endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright.web.jobkeys import resolve_job_key
from jobwright.database import (
    CLOSED_OUTCOMES,
    FUNNEL_STAGES,
    advance_funnel,
    get_connection,
    get_job_by_id,
    job_id_for_url,
)
from jobwright.enrichment.sponsorship import derive_sponsorship_status
from jobwright.scoring.materials_format import generated_material_exists

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


def _effective_fit_score(d: dict) -> int | None:
    user_score = d.get("user_fit_score")
    if user_score is not None:
        return int(user_score)
    ai_score = d.get("fit_score")
    return int(ai_score) if ai_score is not None else None


def _gates(d: dict) -> dict:
    try:
        return json.loads(d.get("score_gates") or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _duplicate_of(job_id: str | None) -> dict | None:
    if not job_id:
        return None
    row = get_connection().execute(
        "SELECT title, company FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    return {
        "job_id": job_id,
        "title": row["title"] if row else None,
        "company": row["company"] if row else None,
    }


def _followup_fields(d: dict, days: int | None) -> dict:
    from jobwright.followups import followup_state, last_stage_change, resolve_days

    empty = {"followup_due": False, "applied_days_ago": None, "followup_due_at": None}
    if (d.get("funnel_stage") or "backlog") != "applied":
        return empty
    last = d["last_stage_at"] if "last_stage_at" in d else last_stage_change(get_connection(), d.get("url"))
    return followup_state(d, last, resolve_days(days)) or empty


def _row_to_card(row, followup_days: int | None = None) -> dict:
    d = dict(row)
    gates = _gates(d)
    if gates:
        # v2 scores store plain reasoning (no legacy "keywords\n" prefix).
        reasoning = ["", d.get("score_reasoning") or ""]
    else:
        reasoning = (d.get("score_reasoning") or "").split("\n", 1)
    user_rationale = (d.get("user_score_rationale") or "").strip()
    url = d.get("url")
    from jobwright.enrichment.detail import _is_permanent_failure

    is_dead = _is_permanent_failure(d.get("detail_error"))
    return {
        "url": url,
        "job_id": job_id_for_url(url) if url else None,
        "whatsapp_notified_at": d.get("whatsapp_notified_at"),
        "title": d.get("title"),
        "company": d.get("company") or d.get("site"),
        "site": d.get("site"),
        "location": d.get("location"),
        "salary": d.get("salary"),
        "work_model": _derive_work_model(d.get("location")),
        "sponsorship_status": d.get("sponsorship_status")
        or derive_sponsorship_status(d.get("full_description") or d.get("description")),
        "fit_score": _effective_fit_score(d),
        "ai_fit_score": d.get("fit_score"),
        "user_fit_score": d.get("user_fit_score"),
        "user_score_rationale": user_rationale or None,
        "user_score_at": d.get("user_score_at"),
        "score_user_modified": d.get("user_fit_score") is not None,
        "keywords": reasoning[0][:120] if reasoning else "",
        "reasoning": reasoning[1][:600] if len(reasoning) > 1 else "",
        "score_confidence": d.get("score_confidence"),
        "score_tier": d.get("score_tier"),
        "score_model": d.get("score_model"),
        "dealbreakers": gates.get("dealbreakers") or [],
        "concerns": gates.get("concerns") or [],
        "score_caps": gates.get("caps") or [],
        "location_ok": gates.get("location_ok"),
        "seniority": gates.get("seniority"),
        "close_reason": d.get("close_reason"),
        "duplicate_of": _duplicate_of(d.get("duplicate_of")),
        "funnel_stage": d.get("funnel_stage") or "backlog",
        "outcome": d.get("outcome"),
        "is_dead": is_dead,
        "source": d.get("source") or "discovered",
        "applied_manually": bool(d.get("applied_manually")),
        "applied_at": d.get("applied_at"),
        "first_response_at": d.get("first_response_at"),
        "follow_up_at": d.get("follow_up_at"),
        "followed_up_at": d.get("followed_up_at"),
        **_followup_fields(d, followup_days),
        "notes": d.get("notes"),
        "board_updated_by": d.get("board_updated_by"),
        "board_updated_at": d.get("board_updated_at"),
        "has_resume": generated_material_exists(
            d.get("tailored_resume_path"), d.get("tailored_resume_docx_path")
        ),
        "has_cover": generated_material_exists(
            d.get("cover_letter_path"), d.get("cover_letter_docx_path")
        ),
        "application_url": d.get("application_url") or d.get("url"),
        "discovered_at": d.get("discovered_at"),
        "apply_status": d.get("apply_status"),
    }


CLOSED_ON_BOARD = 150


@router.get("/board")
def get_board() -> dict:
    """Every open job plus the most recently closed ones (closed history is long)."""
    from jobwright.followups import LAST_CHANGE_SQL, resolve_days

    conn = get_connection()
    days = resolve_days(None)
    rows = conn.execute(
        f"SELECT *, {LAST_CHANGE_SQL} AS last_stage_at FROM jobs "
        "WHERE COALESCE(funnel_stage, 'backlog') != 'closed' "
        "ORDER BY COALESCE(user_fit_score, fit_score) DESC NULLS LAST, discovered_at DESC"
    ).fetchall()
    closed = conn.execute(
        "SELECT * FROM jobs WHERE funnel_stage = 'closed' "
        "ORDER BY COALESCE(board_updated_at, discovered_at) DESC LIMIT ?",
        (CLOSED_ON_BOARD,),
    ).fetchall()
    closed_total = conn.execute("SELECT COUNT(*) FROM jobs WHERE funnel_stage = 'closed'").fetchone()[0]
    columns = {stage: [] for stage in FUNNEL_STAGES}
    for row in [*rows, *closed]:
        card = _row_to_card(row, days)
        stage = card["funnel_stage"] if card["funnel_stage"] in columns else "backlog"
        columns[stage].append(card)
    return {
        "stages": list(FUNNEL_STAGES),
        "columns": columns,
        "total": sum(len(v) for v in columns.values()),
        "closed_total": closed_total,
    }


@router.get("/jobs/by-id/{job_id}")
def get_job_by_short_id(job_id: str) -> dict:
    """Resolve a card by its deep-link short id (blake2b of the url)."""
    row = get_job_by_id(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return _row_to_card(row)


class MoveBody(BaseModel):
    to_stage: str
    note: str | None = None
    outcome: str | None = None
    close_reason: str | None = None
    reasons: list[str] | None = None


@router.post("/jobs/{url:path}/move")
def move_job(url: str, body: MoveBody) -> dict:
    url = resolve_job_key(url)
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
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE jobs SET applied_at = COALESCE(applied_at, ?), "
            "apply_status = COALESCE(apply_status, 'applied') WHERE url = ?",
            (now, url),
        )
    elif from_stage == "applied" and body.to_stage in ("backlog", "prepare"):
        # Human correcting an accidental "Applied": undo the apply stamps.
        conn.execute(
            "UPDATE jobs SET applied_at = NULL, applied_manually = 0, "
            "apply_status = CASE WHEN apply_status = 'applied' THEN NULL ELSE apply_status END WHERE url = ?",
            (url,),
        )
    if body.to_stage == "closed":
        reasons = [r.strip() for r in (body.reasons or []) if r and r.strip()]
        reason_text = (body.close_reason or "").strip() or ", ".join(reasons)
        if reason_text:
            conn.execute("UPDATE jobs SET close_reason = ? WHERE url = ?", (reason_text, url))
        row = conn.execute("SELECT applied_at, user_fit_score FROM jobs WHERE url = ?", (url,)).fetchone()
        never_applied = row["applied_at"] is None and from_stage in ("backlog", "prepare")
        if never_applied and row["user_fit_score"] is None and (reasons or reason_text) \
                and body.outcome == "not_interested":
            from jobwright.labels import record_label

            conn.commit()
            record_label(url, 2, rationale=reason_text, reasons=reasons, source="dismiss", conn=conn)
    conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return {"from_stage": from_stage, "job": _row_to_card(row)}


class PatchBody(BaseModel):
    notes: str | None = None
    follow_up_at: str | None = None
    outcome: str | None = None
    title: str | None = None
    company: str | None = None
    user_fit_score: int | None = None
    user_score_rationale: str | None = None
    user_score_reasons: list[str] | None = None
    clear_user_score: bool = False
    close_reason: str | None = None


@router.patch("/jobs/{url:path}")
def patch_job(url: str, body: PatchBody, request: Request = None) -> dict:  # type: ignore[assignment]
    url = resolve_job_key(url)
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
    if body.close_reason is not None:
        sets.append("close_reason = ?")
        params.append(body.close_reason.strip() or None)
    label_change = None
    if body.clear_user_score:
        label_change = ("clear", None, "", [])
    elif body.user_fit_score is not None:
        if not (1 <= body.user_fit_score <= 10):
            raise HTTPException(400, "user_fit_score must be between 1 and 10")
        rationale = (body.user_score_rationale or "").strip()
        reasons = [r for r in (body.user_score_reasons or []) if isinstance(r, str) and r.strip()]
        if not rationale and not reasons:
            raise HTTPException(400, "Add a reason (chip or note) when setting a score")
        label_change = ("set", body.user_fit_score, rationale, reasons)

    if sets:
        now = datetime.now(UTC).isoformat()
        sets.extend(["board_updated_by = ?", "board_updated_at = ?"])
        params.extend(["human", now, url])
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE url = ?", params)
        conn.commit()

    if label_change is not None:
        from jobwright.labels import clear_label, record_label

        kind, score, rationale, reasons = label_change
        actor = getattr(getattr(request, "state", None), "identity", None)
        actor_email = getattr(actor, "email", None) or None
        if kind == "clear":
            clear_label(url, actor=actor_email, conn=conn)
        else:
            text = rationale or ", ".join(reasons)
            record_label(url, score, rationale=text, reasons=reasons, source="dashboard", actor=actor_email, conn=conn)

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


@router.post("/jobs/{url:path}/response")
def mark_response(url: str) -> dict:
    """Stamp first_response_at (got a reply) without changing lane."""
    url = resolve_job_key(url)
    conn = get_connection()
    row = conn.execute("SELECT first_response_at FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    now = datetime.now(UTC).isoformat()
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
    url = resolve_job_key(url)
    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    if not exists:
        raise HTTPException(404, "Job not found")
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE jobs SET first_response_at = NULL, board_updated_by = 'human', "
        "board_updated_at = ? WHERE url = ?",
        (now, url),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


class FollowupBody(BaseModel):
    action: str


@router.post("/jobs/{url:path}/followup")
def followup(url: str, body: FollowupBody) -> dict:
    """"Followed up" snoozes the reminder; "No response" closes the job."""
    from jobwright.followups import record_followed_up, record_no_response

    url = resolve_job_key(url)
    conn = get_connection()
    row = conn.execute("SELECT funnel_stage FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    if row["funnel_stage"] != "applied":
        raise HTTPException(400, "Only applied jobs have follow-ups")
    if body.action == "followed_up":
        record_followed_up(url, conn=conn)
    elif body.action == "no_response":
        record_no_response(url, conn=conn)
    else:
        raise HTTPException(400, "action must be followed_up or no_response")
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)


@router.get("/jobs/{url:path}/history")
def stage_history(url: str) -> dict:
    url = resolve_job_key(url)
    conn = get_connection()
    rows = conn.execute(
        "SELECT from_stage, to_stage, actor, at, note FROM stage_history "
        "WHERE job_url = ? ORDER BY at ASC, id ASC",
        (url,),
    ).fetchall()
    return {"url": url, "history": [dict(r) for r in rows]}
