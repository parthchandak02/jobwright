"""Tests for Kanban funnel_stage, advance_funnel, manual jobs, anti-clobber."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jobwright.database import (
    ANTI_CLOBBER_SQL,
    MANUAL_SOURCE_EXCLUSION_SQL,
    advance_funnel,
    close_connection,
    get_jobs_by_stage,
    init_db,
    insert_manual_job,
    maybe_agent_advance_to_prepare,
)


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("jobwright.config.DB_PATH", db_path)
    monkeypatch.setattr("jobwright.config.APP_DIR", tmp_path)
    close_connection(db_path)
    conn = init_db(db_path)
    yield conn
    close_connection(db_path)


def _insert_discovered(conn: sqlite3.Connection, url: str, **extra) -> None:
    cols = {
        "url": url,
        "title": "Engineer",
        "site": "indeed",
        "strategy": "jobspy",
        "discovered_at": "2026-01-01T00:00:00+00:00",
        "source": "discovered",
        "funnel_stage": "backlog",
        **extra,
    }
    keys = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({placeholders})", list(cols.values()))
    conn.commit()


def test_advance_funnel_writes_history(db: sqlite3.Connection):
    _insert_discovered(db, "https://example.com/1")
    from_stage = advance_funnel("https://example.com/1", "prepare", "agent", note="ready")
    assert from_stage == "backlog"
    row = db.execute(
        "SELECT funnel_stage, board_updated_by FROM jobs WHERE url = ?",
        ("https://example.com/1",),
    ).fetchone()
    assert row["funnel_stage"] == "prepare"
    assert row["board_updated_by"] == "agent"
    hist = db.execute(
        "SELECT from_stage, to_stage, actor, note FROM stage_history WHERE job_url = ?",
        ("https://example.com/1",),
    ).fetchall()
    assert any(h["to_stage"] == "prepare" and h["actor"] == "agent" for h in hist)


def test_agent_cannot_cross_handoff(db: sqlite3.Connection):
    _insert_discovered(db, "https://example.com/2")
    with pytest.raises(ValueError, match="cannot advance"):
        advance_funnel("https://example.com/2", "applied", "agent")


def test_human_move_to_applied(db: sqlite3.Connection):
    _insert_discovered(db, "https://example.com/3", tailored_resume_path="/tmp/r.txt")
    advance_funnel("https://example.com/3", "prepare", "agent")
    advance_funnel(
        "https://example.com/3", "applied", "human", applied_manually=True
    )
    row = db.execute(
        "SELECT funnel_stage, applied_manually, board_updated_by FROM jobs WHERE url = ?",
        ("https://example.com/3",),
    ).fetchone()
    assert row["funnel_stage"] == "applied"
    assert row["applied_manually"] == 1
    assert row["board_updated_by"] == "human"


def test_anti_clobber_skips_human_held(db: sqlite3.Connection):
    _insert_discovered(
        db,
        "https://example.com/human",
        full_description="desc",
        fit_score=8,
        board_updated_by="human",
        funnel_stage="backlog",
    )
    _insert_discovered(
        db,
        "https://example.com/agent",
        full_description="desc",
        fit_score=8,
        funnel_stage="backlog",
    )
    pending = get_jobs_by_stage(conn=db, stage="pending_tailor", min_score=7, limit=50)
    urls = {j["url"] for j in pending}
    assert "https://example.com/agent" in urls
    assert "https://example.com/human" not in urls


def test_anti_clobber_skips_post_handoff(db: sqlite3.Connection):
    _insert_discovered(
        db,
        "https://example.com/applied",
        full_description="desc",
        fit_score=9,
        funnel_stage="applied",
        board_updated_by="human",
    )
    pending = get_jobs_by_stage(conn=db, stage="pending_tailor", min_score=7, limit=50)
    assert all(j["url"] != "https://example.com/applied" for j in pending)


def test_insert_manual_job_isolated(db: sqlite3.Connection):
    job = insert_manual_job(
        "https://example.com/manual",
        title="PM",
        company="Acme",
        funnel_stage="applied",
        conn=db,
    )
    assert job["source"] == "manual"
    assert job["site"] == "manual"
    assert job["funnel_stage"] == "applied"
    assert job["board_updated_by"] == "human"

    # Manual jobs must not appear in pending_apply
    _insert_discovered(
        db,
        "https://example.com/ready",
        tailored_resume_path="/tmp/a.txt",
        application_url="https://example.com/ready",
        fit_score=8,
        funnel_stage="prepare",
    )
    pending = get_jobs_by_stage(conn=db, stage="pending_apply", limit=50)
    urls = {j["url"] for j in pending}
    assert "https://example.com/ready" in urls
    assert "https://example.com/manual" not in urls


def test_maybe_agent_advance_to_prepare(db: sqlite3.Connection):
    _insert_discovered(db, "https://example.com/prep")
    db.execute(
        "UPDATE jobs SET tailored_resume_path = ? WHERE url = ?",
        ("/tmp/r.txt", "https://example.com/prep"),
    )
    db.commit()
    assert maybe_agent_advance_to_prepare("https://example.com/prep", conn=db) is True
    row = db.execute(
        "SELECT funnel_stage FROM jobs WHERE url = ?",
        ("https://example.com/prep",),
    ).fetchone()
    assert row["funnel_stage"] == "prepare"
    # Human-held: no advance
    advance_funnel("https://example.com/prep", "applied", "human", conn=db)
    db.execute(
        "UPDATE jobs SET tailored_resume_path = ?, cover_letter_path = ? WHERE url = ?",
        ("/tmp/r.txt", "/tmp/c.txt", "https://example.com/prep"),
    )
    db.commit()
    assert maybe_agent_advance_to_prepare("https://example.com/prep", conn=db) is False


def test_backfill_from_timestamps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr("jobwright.config.DB_PATH", db_path)
    close_connection(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT, site TEXT, "
        "strategy TEXT, discovered_at TEXT, tailored_resume_path TEXT, applied_at TEXT)"
    )
    conn.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("https://ex/a", "A", "indeed", "jobspy", "2026-01-01", "/tmp/a.txt", None),
    )
    conn.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("https://ex/b", "B", "indeed", "jobspy", "2026-01-01", "/tmp/b.txt", "2026-01-02"),
    )
    conn.commit()
    conn.close()
    close_connection(db_path)
    conn = init_db(db_path)
    stages = {
        r["url"]: r["funnel_stage"]
        for r in conn.execute("SELECT url, funnel_stage FROM jobs").fetchall()
    }
    assert stages["https://ex/a"] == "prepare"
    assert stages["https://ex/b"] == "applied"
    hist_count = conn.execute("SELECT COUNT(*) FROM stage_history").fetchone()[0]
    assert hist_count >= 2
    close_connection(db_path)


def test_sql_fragments_present():
    assert "board_updated_by" in ANTI_CLOBBER_SQL
    assert "manual" in MANUAL_SOURCE_EXCLUSION_SQL
