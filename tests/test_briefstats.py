"""Tests for the D4 scoreboard (brief_items recording + briefstats precision math)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jobwright import briefstats
from jobwright.briefstats import briefstats as compute_briefstats
from jobwright.briefstats import record_brief_items
from jobwright.database import close_connection, init_db
from jobwright.users import get_brief_top_n, get_human_gate


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("jobwright.config.DB_PATH", db_path)
    monkeypatch.setattr("jobwright.config.APP_DIR", tmp_path)
    close_connection(db_path)
    conn = init_db(db_path)
    yield conn
    close_connection(db_path)


def _insert_job(conn: sqlite3.Connection, url: str, **cols) -> None:
    defaults = {
        "url": url,
        "title": "Role",
        "site": "indeed",
        "company": "Acme",
        "location": "Remote",
        "fit_score": 8,
        "discovered_at": "2026-01-01T00:00:00+00:00",
        "funnel_stage": "prepare",
    }
    defaults.update(cols)
    keys = ", ".join(defaults)
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


def _candidate(url: str, score: int) -> dict:
    return {"url": url, "title": "Role", "company": "Acme",
            "location": "Remote", "fit_score": score}


def test_get_human_gate_and_top_n_defaults():
    # Unknown / legacy single-user -> gate off, cap 10.
    assert get_human_gate(None) is False
    assert get_human_gate("nobody") is False
    assert get_brief_top_n(None) == 0  # uncapped legacy default
    assert get_brief_top_n("nobody") == 0


def test_record_brief_items_then_briefstats_math(db: sqlite3.Connection):
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    urls = [f"https://example.com/job-{c}" for c in "abcd"]
    jobs = [_candidate(u, 9 - i) for i, u in enumerate(urls)]
    # Brief 1 (yesterday): show all 4 (top-4 here = all under cap 10).
    record_brief_items(jobs, urls, brief_date=yesterday, conn=db)
    # Post-brief funnel outcomes for the shown items.
    _insert_job(db, urls[0], funnel_stage="applied")
    _insert_job(db, urls[1], funnel_stage="in_progress")
    _insert_job(db, urls[2], funnel_stage="closed")
    _insert_job(db, urls[3], funnel_stage="backlog")

    # Brief 2 (today): 2 candidates, show only 1 (cap effect), 1 not shown.
    u5, u6 = "https://example.com/job-e", "https://example.com/job-f"
    jobs2 = [_candidate(u5, 9), _candidate(u6, 8)]
    record_brief_items(jobs2, [u5], brief_date=today, conn=db)
    _insert_job(db, u5, funnel_stage="applied")
    _insert_job(db, u6, funnel_stage="prepare")

    stats = compute_briefstats(user="richa", days=14, conn=db)
    assert len(stats) == 2
    by_date = {s["brief_date"]: s for s in stats}

    b1 = by_date[yesterday]
    assert b1["shown"] == 4
    assert b1["applied"] == 1
    assert b1["in_progress"] == 1
    assert b1["closed"] == 1
    assert b1["untouched"] == 1
    assert b1["advanced"] == 2
    assert b1["precision"] == pytest.approx(0.5)

    b2 = by_date[today]
    assert b2["shown"] == 1
    assert b2["recorded"] == 2  # both candidates recorded, only 1 shown
    assert b2["applied"] == 1
    assert b2["advanced"] == 1
    assert b2["precision"] == pytest.approx(1.0)
    assert b2["user"] == "richa"


def test_briefstats_filters_old_briefs_and_empty(db: sqlite3.Connection):
    old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    url = "https://example.com/old-job"
    record_brief_items([_candidate(url, 8)], [url], brief_date=old, conn=db)
    _insert_job(db, url, funnel_stage="applied")

    # Outside the 14-day window -> dropped entirely.
    stats = compute_briefstats(user="richa", days=14, conn=db)
    assert stats == []

    # A brief wholly outside the window (recorded here) plus a fresh tuple for
    # a brief with no items should never be produced.
    assert briefstats.ensure_brief_items(db) is None


def test_briefstats_untouched_when_job_row_missing(db: sqlite3.Connection):
    today = datetime.now().strftime("%Y-%m-%d")
    # Recorded in brief_items but no matching jobs row (e.g. job pruned).
    url = "https://example.com/missing-row"
    record_brief_items([_candidate(url, 8)], [url], brief_date=today, conn=db)

    stats = compute_briefstats(user="richa", days=14, conn=db)
    assert len(stats) == 1
    b = stats[0]
    assert b["shown"] == 1
    assert b["untouched"] == 1
    assert b["advanced"] == 0
    assert b["precision"] == pytest.approx(0.0)