"""Bulk move / close from the table selection (``POST /api/jobs/bulk``)."""

from __future__ import annotations

import pytest

from jobwright.database import get_connection, insert_manual_job, job_id_for_url

pytest.importorskip("fastapi")

import test_web_board as _board  # noqa: E402
import test_web_multiuser as _multi  # noqa: E402

api_client = _board.api_client
api_env = _multi.api_env


def _add(slug: str, stage: str = "backlog", score: int | None = 6) -> str:
    url = f"https://example.com/bulk-{slug}"
    insert_manual_job(url, title=f"Role {slug}", company="ExampleCo", funnel_stage=stage)
    conn = get_connection()
    conn.execute("UPDATE jobs SET fit_score = ?, board_updated_by = 'agent' WHERE url = ?", (score, url))
    conn.commit()
    return job_id_for_url(url)


def _row(job_id: str):
    return get_connection().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()


def _labels(job_id: str) -> list:
    return get_connection().execute(
        "SELECT source, verdict, label_score, reasons FROM score_labels WHERE job_id = ? ORDER BY id", (job_id,)
    ).fetchall()


def test_bulk_move_matches_single_move(api_client):
    a, b = _add("a"), _add("b")
    res = api_client.post("/api/jobs/bulk", json={"job_ids": [a, b], "action": "move", "stage": "applied"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] == 2 and body["to_stage"] == "applied"
    assert [r["from_stage"] for r in body["results"]] == ["backlog", "backlog"]
    assert {c["job_id"] for c in body["jobs"]} == {a, b}
    assert all(c["funnel_stage"] == "applied" for c in body["jobs"])
    for jid in (a, b):
        row = _row(jid)
        # Same as a hand move: the human now owns the card and the apply stamps are set.
        assert row["board_updated_by"] == "human"
        assert row["applied_at"] and row["applied_manually"] == 1
        hist = get_connection().execute(
            "SELECT from_stage, to_stage, actor FROM stage_history WHERE job_url = ?", (row["url"],)
        ).fetchall()
        assert [tuple(h) for h in hist][-1] == ("backlog", "applied", "human")


def test_bulk_close_records_not_for_me_labels(api_client):
    a, b = _add("a"), _add("b")
    applied = _add("c", stage="applied")
    conn = get_connection()
    conn.execute("UPDATE jobs SET applied_at = '2026-10-01T00:00:00+00:00' WHERE job_id = ?", (applied,))
    conn.commit()
    res = api_client.post(
        "/api/jobs/bulk",
        json={"job_ids": [a, b, applied], "action": "close", "reasons": ["Too senior"], "note": ""},
    )
    assert res.status_code == 200, res.text
    results = {r["job_id"]: r for r in res.json()["results"]}
    assert results[a]["labeled"] and results[b]["labeled"]
    # Applied jobs are never labeled "not for me" (same rule as the single flow).
    assert not results[applied]["labeled"]
    for jid in (a, b):
        row = _row(jid)
        assert row["funnel_stage"] == "closed" and row["outcome"] == "not_interested"
        assert row["close_reason"] == "Too senior" and row["user_fit_score"] == 2
        assert [tuple(r)[:3] for r in _labels(jid)] == [("bulk_dismiss", "not_relevant", 2)]
    assert _labels(applied) == []


def test_bulk_close_skips_label_for_rated_jobs(api_client):
    a = _add("a")
    api_client.patch(f"/api/jobs/{a}", json={"user_fit_score": 7, "user_score_reasons": ["good team"]})
    res = api_client.post("/api/jobs/bulk", json={"job_ids": [a], "action": "close", "reasons": ["Too senior"]})
    assert res.json()["results"][0]["labeled"] is False
    assert [r["source"] for r in _labels(a)] == ["dashboard"]


def test_bulk_unknown_ids_are_reported_not_fatal(api_client):
    a = _add("a")
    res = api_client.post(
        "/api/jobs/bulk",
        json={"job_ids": ["ffffffffffff", a, a, "https://example.com/nope"], "action": "move", "stage": "prepare"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] == 1
    bad = [r for r in body["results"] if not r["ok"]]
    assert [r["error"] for r in bad] == ["not_found", "not_found"]
    assert _row(a)["funnel_stage"] == "prepare"


def test_bulk_validation(api_client):
    a = _add("a")
    post = api_client.post
    assert post("/api/jobs/bulk", json={"job_ids": [], "action": "move", "stage": "prepare"}).status_code == 400
    assert post("/api/jobs/bulk", json={"job_ids": [a], "action": "move"}).status_code == 400
    assert post("/api/jobs/bulk", json={"job_ids": [a], "action": "move", "stage": "nope"}).status_code == 400
    assert post("/api/jobs/bulk", json={"job_ids": [a], "action": "move", "stage": "closed"}).status_code == 400
    assert post("/api/jobs/bulk", json={"job_ids": [a], "action": "close", "outcome": "nope"}).status_code == 400
    assert post("/api/jobs/bulk", json={"job_ids": [a], "action": "delete"}).status_code == 422
    too_many = ["ffffffffffff"] * 501
    res = post("/api/jobs/bulk", json={"job_ids": too_many, "action": "move", "stage": "prepare"})
    assert res.status_code == 400 and "500" in res.json()["detail"]
    assert _row(a)["funnel_stage"] == "backlog"


def test_bulk_is_one_transaction(api_client, monkeypatch):
    import jobwright.web.routers.board as board_mod

    a, b = _add("a"), _add("b")
    real = board_mod._apply_move
    calls = {"n": 0}

    def flaky(conn, url, body, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(conn, url, body, **kw)

    monkeypatch.setattr(board_mod, "_apply_move", flaky)
    with pytest.raises(RuntimeError):
        api_client.post("/api/jobs/bulk", json={"job_ids": [a, b], "action": "move", "stage": "prepare"})
    # The first job's move was rolled back with the failed second one.
    assert _row(a)["funnel_stage"] == "backlog" and _row(b)["funnel_stage"] == "backlog"
    assert get_connection().execute("SELECT COUNT(*) FROM stage_history WHERE to_stage = 'prepare'").fetchone()[0] == 0


def test_bulk_undo_restores_stage_and_clears_dismiss_label(api_client):
    a, b = _add("a"), _add("b", stage="prepare")
    res = api_client.post("/api/jobs/bulk", json={"job_ids": [a, b], "action": "close", "reasons": ["Pay too low"]})
    results = res.json()["results"]
    # Undo: one bulk move per original lane, clearing the labels close recorded.
    by_stage: dict[str, list[str]] = {}
    for r in results:
        by_stage.setdefault(r["from_stage"], []).append(r["job_id"])
    for stage, ids in by_stage.items():
        res = api_client.post(
            "/api/jobs/bulk",
            json={"job_ids": ids, "action": "move", "stage": stage, "clear_dismiss_labels": True},
        )
        assert res.status_code == 200, res.text
        assert all(r["label_cleared"] for r in res.json()["results"])
    assert _row(a)["funnel_stage"] == "backlog" and _row(b)["funnel_stage"] == "prepare"
    for jid in (a, b):
        row = _row(jid)
        assert row["outcome"] is None and row["user_fit_score"] is None
        # Append-only: the dismiss label stays in history with a "cleared" marker after it.
        assert [r["verdict"] for r in _labels(jid)] == ["not_relevant", "cleared"]


def test_bulk_undo_keeps_hand_ratings(api_client):
    a = _add("a")
    api_client.patch(f"/api/jobs/{a}", json={"user_fit_score": 3, "user_score_reasons": ["too senior"]})
    api_client.post("/api/jobs/bulk", json={"job_ids": [a], "action": "close", "reasons": ["x"]})
    res = api_client.post(
        "/api/jobs/bulk", json={"job_ids": [a], "action": "move", "stage": "backlog", "clear_dismiss_labels": True}
    )
    assert res.json()["results"][0]["label_cleared"] is False
    assert _row(a)["user_fit_score"] == 3


def test_bulk_only_touches_the_active_profile(api_env):
    client, h, _ = api_env
    ann, bo = h("ann@example.com"), h("bo@example.com")
    client.post("/api/onboarding/profile", json={"name": "Ann"}, headers=ann)
    client.cookies.set("jobwright_user", "ann")
    job_id = client.post(
        "/api/jobs", json={"url": "https://example.com/ann-job", "title": "PM", "company": "Co"}, headers=ann
    ).json()["job_id"]
    client.cookies.clear()
    client.post("/api/onboarding/profile", json={"name": "Bo"}, headers=bo)
    client.cookies.set("jobwright_user", "bo")
    res = client.post("/api/jobs/bulk", json={"job_ids": [job_id], "action": "close"}, headers=bo)
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 0 and res.json()["results"][0]["error"] == "not_found"
    # Bo cannot pick Ann's profile either.
    client.cookies.set("jobwright_user", "ann")
    res = client.post("/api/jobs/bulk", json={"job_ids": [job_id], "action": "close"}, headers=bo)
    assert res.status_code in (200, 403)
    if res.status_code == 200:
        assert res.json()["updated"] == 0
    client.cookies.set("jobwright_user", "ann")
    card = client.get(f"/api/jobs/{job_id}", headers=ann).json()
    assert card["funnel_stage"] == "backlog"
