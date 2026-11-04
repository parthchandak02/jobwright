"""Daily-list candidates are ordered by similarity to the person's past applications."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db
from jobwright.scoring.applied_similarity import rank_like_applied


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("jobwright.config.DB_PATH", db_path)
    monkeypatch.setattr("jobwright.config.APP_DIR", tmp_path)
    close_connection(db_path)
    conn = init_db(db_path)
    yield conn
    close_connection(db_path)


def _job(conn: sqlite3.Connection, url: str, title: str, company: str, desc: str, **cols) -> dict:
    row = {"url": url, "title": title, "company": company, "full_description": desc,
           "site": "indeed", "fit_score": 9, "funnel_stage": "backlog",
           "discovered_at": "2026-11-01T00:00:00+00:00", **cols}
    keys = ", ".join(row)
    conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))
    conn.commit()
    return {"url": url, "title": title, "company": company, "fit_score": 9}


FINANCE = "financial planning and analysis budgeting forecasting impact investing portfolio"


def _applied(conn, n: int = 5) -> None:
    for i in range(n):
        _job(conn, f"https://example.com/a{i}", "Impact Investment Associate", f"Fund {i}",
             FINANCE, funnel_stage="applied", applied_at="2026-10-01T00:00:00+00:00")


def test_candidates_like_applications_come_first(db):
    _applied(db)
    unlike = _job(db, "https://example.com/c1", "Warehouse Forklift Operator", "Sample Logistics",
                  "operate forklift loading dock shipping receiving")
    like = _job(db, "https://example.com/c2", "Impact Investing Analyst", "Example Capital",
                FINANCE + " due diligence")
    ranked = rank_like_applied(db, [unlike, like])
    assert [j["url"] for j in ranked] == [like["url"], unlike["url"]]
    assert ranked[0]["like_applied"] > ranked[1]["like_applied"]


def test_too_few_applications_keeps_original_order(db):
    _applied(db, n=4)
    a = _job(db, "https://example.com/c1", "Forklift Operator", "Sample Logistics", "forklift")
    b = _job(db, "https://example.com/c2", "Impact Investing Analyst", "Example Capital", FINANCE)
    assert rank_like_applied(db, [a, b]) == [a, b]


def test_stage_history_counts_as_applied_and_nothing_is_dropped(db):
    for i in range(5):
        _job(db, f"https://example.com/h{i}", "Impact Investment Associate", f"Fund {i}", FINANCE,
             funnel_stage="closed")
        db.execute("INSERT INTO stage_history (job_url, from_stage, to_stage, at, actor) "
                   "VALUES (?, 'prepare', 'applied', '2026-10-01', 'human')", (f"https://example.com/h{i}",))
    db.commit()
    jobs = [_job(db, f"https://example.com/c{i}", t, "Example Org", d) for i, (t, d) in
            enumerate([("Forklift Operator", "forklift"), ("Impact Investing Analyst", FINANCE)])]
    ranked = rank_like_applied(db, jobs)
    assert len(ranked) == 2 and ranked[0]["title"] == "Impact Investing Analyst"


def test_can_be_switched_off(db, monkeypatch):
    _applied(db)
    a = _job(db, "https://example.com/c1", "Forklift Operator", "Sample Logistics", "forklift")
    b = _job(db, "https://example.com/c2", "Impact Investing Analyst", "Example Capital", FINANCE)
    monkeypatch.setenv("JOBWRIGHT_RANK_LIKE_APPLIED", "0")
    assert rank_like_applied(db, [a, b]) == [a, b]
