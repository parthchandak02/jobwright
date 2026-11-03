"""Hand-made card order within a board lane (``board_position``)."""

from __future__ import annotations

import pytest

from jobwright.database import advance_funnel, ensure_columns, get_connection, insert_manual_job, job_id_for_url
pytest.importorskip("fastapi")

import test_web_board as _board  # noqa: E402

api_client = _board.api_client


def _add(slug: str, score: int | None, stage: str = "backlog") -> str:
    url = f"https://example.com/order-{slug}"
    insert_manual_job(url, title=f"Role {slug}", company="ExampleCo", funnel_stage=stage)
    conn = get_connection()
    conn.execute("UPDATE jobs SET fit_score = ? WHERE url = ?", (score, url))
    conn.commit()
    return job_id_for_url(url)


def _lane(client, stage: str) -> list[str]:
    board = client.get("/api/board").json()
    return [c["job_id"] for c in board["columns"][stage] if c["company"] == "ExampleCo"]


def test_column_is_added_by_migration(api_client):
    cols = {r[1] for r in get_connection().execute("PRAGMA table_info(jobs)").fetchall()}
    assert "board_position" in cols
    assert ensure_columns() == []


def test_default_order_unchanged_without_positions(api_client):
    a, b, c = _add("a", 9), _add("b", 5), _add("c", 7)
    assert _lane(api_client, "backlog") == [a, c, b]
    card = api_client.get("/api/board").json()["columns"]["backlog"][0]
    assert "board_position" in card


def test_reorder_persists_and_survives_refresh(api_client):
    a, b, c = _add("a", 9), _add("b", 5), _add("c", 7)
    r = api_client.post("/api/board/reorder", json={"stage": "backlog", "job_ids": [b, a, c]})
    assert r.status_code == 200
    assert _lane(api_client, "backlog") == [b, a, c]
    # A score change does not undo the hand order.
    conn = get_connection()
    conn.execute("UPDATE jobs SET fit_score = 1 WHERE job_id = ?", (b,))
    conn.commit()
    assert _lane(api_client, "backlog") == [b, a, c]


def test_reorder_keeps_unlisted_cards_and_ignores_strangers(api_client):
    a, b, c = _add("a", 9), _add("b", 5), _add("c", 7)
    other = _add("x", 8, stage="prepare")
    r = api_client.post(
        "/api/board/reorder",
        json={"stage": "backlog", "job_ids": [c, other, "ffffffffffff", c]},
    )
    assert r.status_code == 200
    assert _lane(api_client, "backlog") == [c, a, b]
    assert _lane(api_client, "prepare") == [other]


def test_new_unplaced_cards_land_on_top(api_client):
    a, b = _add("a", 9), _add("b", 5)
    api_client.post("/api/board/reorder", json={"stage": "backlog", "job_ids": [b, a]})
    fresh = _add("new", 3)
    assert _lane(api_client, "backlog") == [fresh, b, a]


def test_reorder_does_not_take_card_from_agent(api_client):
    a, b = _add("a", 9), _add("b", 5)
    conn = get_connection()
    conn.execute("UPDATE jobs SET board_updated_by = 'agent' WHERE job_id IN (?, ?)", (a, b))
    conn.commit()
    api_client.post("/api/board/reorder", json={"stage": "backlog", "job_ids": [b, a]})
    rows = conn.execute(
        "SELECT board_updated_by FROM jobs WHERE job_id IN (?, ?)", (a, b)
    ).fetchall()
    assert {r[0] for r in rows} == {"agent"}


def test_move_with_position_places_card(api_client):
    p1, p2 = _add("p1", 9, "prepare"), _add("p2", 8, "prepare")
    mover = _add("m", 4)
    r = api_client.post(f"/api/jobs/{mover}/move", json={"to_stage": "prepare", "position": 1})
    assert r.status_code == 200
    assert r.json()["job"]["board_position"] == 1
    assert _lane(api_client, "prepare") == [p1, mover, p2]
    # Same-lane move with a position is a reorder.
    api_client.post(f"/api/jobs/{mover}/move", json={"to_stage": "prepare", "position": 0})
    assert _lane(api_client, "prepare") == [mover, p1, p2]
    # Out-of-range positions clamp to the end.
    api_client.post(f"/api/jobs/{mover}/move", json={"to_stage": "prepare", "position": 99})
    assert _lane(api_client, "prepare") == [p1, p2, mover]


def test_lane_change_clears_stale_position(api_client):
    a, b = _add("a", 9), _add("b", 5)
    api_client.post("/api/board/reorder", json={"stage": "backlog", "job_ids": [b, a]})
    url = get_connection().execute("SELECT url FROM jobs WHERE job_id = ?", (b,)).fetchone()[0]
    advance_funnel(url, "prepare", "agent")
    pos = get_connection().execute("SELECT board_position FROM jobs WHERE job_id = ?", (b,)).fetchone()[0]
    assert pos is None
    # A move without a position puts the card on top of the target lane.
    placed = _add("p", 9, "prepare")
    api_client.post("/api/board/reorder", json={"stage": "prepare", "job_ids": [placed, b]})
    api_client.post(f"/api/jobs/{a}/move", json={"to_stage": "prepare"})
    assert _lane(api_client, "prepare")[0] == a


def test_closed_lane_order_and_counts(api_client):
    a, b = _add("a", 9), _add("b", 5)
    for key in (a, b):
        assert api_client.post(
            f"/api/jobs/{key}/move", json={"to_stage": "closed", "outcome": "withdrawn", "position": 0}
        ).status_code == 200
    assert _lane(api_client, "closed") == [b, a]
    api_client.post("/api/board/reorder", json={"stage": "closed", "job_ids": [a, b]})
    assert _lane(api_client, "closed") == [a, b]
    board = api_client.get("/api/board").json()
    assert board["stage_counts"]["closed"] == board["closed_total"] == 2
    assert board["stage_counts"]["backlog"] == len(board["columns"]["backlog"])


def test_reorder_rejects_unknown_stage(api_client):
    r = api_client.post("/api/board/reorder", json={"stage": "nope", "job_ids": []})
    assert r.status_code == 400


@pytest.mark.parametrize("stage", ["backlog", "applied"])
def test_reorder_empty_lane_is_ok(api_client, stage):
    r = api_client.post("/api/board/reorder", json={"stage": stage, "job_ids": []})
    assert r.status_code == 200
