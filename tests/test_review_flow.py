"""Quick review (/review) answers and their undo, through the existing job routes.

The page has no endpoint of its own: it reads ``GET /api/board`` and answers with
``PATCH /api/jobs/{id}`` (rating -> label) plus ``POST /api/jobs/{id}/move``.
These tests pin the sequence it sends so every answer teaches the scorer exactly
once and Undo puts the job back as it was.
"""

from __future__ import annotations

import pytest

from jobwright.database import get_connection, insert_manual_job, job_id_for_url

pytest.importorskip("fastapi")

import test_web_board as _board  # noqa: E402

api_client = _board.api_client


def _add(slug: str, score: int = 8) -> str:
    url = f"https://example.com/review-{slug}"
    insert_manual_job(url, title=f"Role {slug}", company="ExampleCo", funnel_stage="backlog")
    conn = get_connection()
    conn.execute("UPDATE jobs SET fit_score = ? WHERE url = ?", (score, url))
    conn.commit()
    return job_id_for_url(url)


def _labels(job_id: str) -> list[tuple[int, str, str]]:
    rows = get_connection().execute(
        "SELECT label_score, verdict, source FROM score_labels WHERE job_id = ? ORDER BY id", (job_id,)
    ).fetchall()
    return [tuple(r) for r in rows]


def _job(client, job_id: str) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def test_interested_rates_up_and_moves_to_prepare_then_undo(api_client):
    jid = _add("yes")
    r = api_client.patch(f"/api/jobs/{jid}", json={"user_fit_score": 8, "user_score_reasons": [], "user_score_rationale": "Interested"})
    assert r.status_code == 200
    r = api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "prepare"})
    assert r.status_code == 200
    card = _job(api_client, jid)
    assert card["funnel_stage"] == "prepare"
    assert card["user_fit_score"] == 8
    assert _labels(jid) == [(8, "relevant", "dashboard")]

    # Undo: clear the rating, back to Backlog.
    assert api_client.patch(f"/api/jobs/{jid}", json={"clear_user_score": True, "close_reason": ""}).status_code == 200
    assert api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "backlog"}).status_code == 200
    card = _job(api_client, jid)
    assert card["funnel_stage"] == "backlog"
    assert card["user_fit_score"] is None
    assert [v for _, v, _ in _labels(jid)] == ["relevant", "cleared"]
    backlog = api_client.get("/api/board").json()["columns"]["backlog"]
    assert any(c["job_id"] == jid and c["user_fit_score"] is None for c in backlog)


def test_not_for_me_records_one_label_and_undo_reopens(api_client):
    jid = _add("no", score=6)
    reasons = ["Wrong location", "Pay too low"]
    r = api_client.patch(f"/api/jobs/{jid}", json={"user_fit_score": 2, "user_score_reasons": reasons, "user_score_rationale": ""})
    assert r.status_code == 200
    r = api_client.post(
        f"/api/jobs/{jid}/move",
        json={"to_stage": "closed", "outcome": "not_interested", "reasons": reasons},
    )
    assert r.status_code == 200
    card = _job(api_client, jid)
    assert card["funnel_stage"] == "closed"
    assert card["outcome"] == "not_interested"
    assert card["close_reason"] == "Wrong location, Pay too low"
    # The rating already labelled it, so the dismiss does not add a second label.
    assert _labels(jid) == [(2, "not_relevant", "dashboard")]

    assert api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "backlog"}).status_code == 200
    assert api_client.patch(f"/api/jobs/{jid}", json={"clear_user_score": True, "close_reason": ""}).status_code == 200
    card = _job(api_client, jid)
    assert card["funnel_stage"] == "backlog"
    assert card["outcome"] is None
    assert card["close_reason"] is None
    assert card["user_fit_score"] is None


def test_not_for_me_without_reason_still_labels(api_client):
    jid = _add("plain", score=5)
    r = api_client.patch(f"/api/jobs/{jid}", json={"user_fit_score": 2, "user_score_reasons": [], "user_score_rationale": "Not for me"})
    assert r.status_code == 200
    r = api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "closed", "outcome": "not_interested", "reasons": []})
    assert r.status_code == 200
    assert _labels(jid) == [(2, "not_relevant", "dashboard")]
    assert _job(api_client, jid)["close_reason"] is None
