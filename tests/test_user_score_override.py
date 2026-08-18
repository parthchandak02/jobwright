"""Tests for user score overrides and scorer calibration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db
from jobwright.scoring.scorer import _load_score_calibration
from jobwright.web.routers.board import _effective_fit_score, _row_to_card


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("jobwright.config.DB_PATH", db_path)
    monkeypatch.setattr("jobwright.config.APP_DIR", tmp_path)
    close_connection(db_path)
    conn = init_db(db_path)
    yield conn
    close_connection(db_path)


def _insert_job(conn: sqlite3.Connection, **cols) -> None:
    defaults = {
        "url": "https://example.com/job",
        "title": "Chief of Staff",
        "site": "indeed",
        "company": "Acme",
        "fit_score": 6,
        "score_reasoning": "ops, strategy\nModerate match for target role.",
        "discovered_at": "2026-01-01T00:00:00+00:00",
        "funnel_stage": "backlog",
    }
    defaults.update(cols)
    keys = ", ".join(defaults)
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


def test_effective_fit_score_prefers_user_override():
    row = {
        "fit_score": 6,
        "user_fit_score": 9,
    }
    assert _effective_fit_score(row) == 9


def test_row_to_card_material_chips_require_generated_files(
    db: sqlite3.Connection, tmp_path: Path
):
    resume = tmp_path / "tailored.md"
    resume.write_text("# Tailored", encoding="utf-8")
    cover = tmp_path / "cover.md"
    cover.write_text("Dear hiring manager", encoding="utf-8")

    _insert_job(
        db,
        url="https://example.com/stale",
        tailored_resume_path=str(tmp_path / "missing.md"),
        cover_letter_path=str(tmp_path / "missing_cl.md"),
    )
    stale = _row_to_card(
        db.execute("SELECT * FROM jobs WHERE url = ?", ("https://example.com/stale",)).fetchone()
    )
    assert stale["has_resume"] is False
    assert stale["has_cover"] is False

    _insert_job(
        db,
        url="https://example.com/resume-only",
        tailored_resume_path=str(resume),
    )
    resume_only = _row_to_card(
        db.execute(
            "SELECT * FROM jobs WHERE url = ?", ("https://example.com/resume-only",)
        ).fetchone()
    )
    assert resume_only["has_resume"] is True
    assert resume_only["has_cover"] is False

    _insert_job(
        db,
        url="https://example.com/both",
        tailored_resume_path=str(resume),
        cover_letter_path=str(cover),
    )
    both = _row_to_card(
        db.execute("SELECT * FROM jobs WHERE url = ?", ("https://example.com/both",)).fetchone()
    )
    assert both["has_resume"] is True
    assert both["has_cover"] is True


def test_row_to_card_marks_user_modified(db: sqlite3.Connection):
    _insert_job(
        db,
        user_fit_score=8,
        user_score_rationale="Strong ops fit despite junior title",
        user_score_at="2026-02-01T00:00:00+00:00",
    )
    row = db.execute("SELECT * FROM jobs WHERE url = ?", ("https://example.com/job",)).fetchone()
    card = _row_to_card(row)
    assert card["fit_score"] == 8
    assert card["ai_fit_score"] == 6
    assert card["score_user_modified"] is True
    assert "Strong ops fit" in card["user_score_rationale"]


def test_load_score_calibration_formats_examples(db: sqlite3.Connection):
    _insert_job(
        db,
        user_fit_score=9,
        user_score_rationale="Perfect CoS match for my background",
        user_score_at="2026-02-01T00:00:00+00:00",
    )
    text = _load_score_calibration(db)
    assert "HUMAN SCORE CALIBRATION" in text
    assert "human corrected to 9" in text
    assert "Perfect CoS match" in text


def test_patch_job_user_score_requires_rationale(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    from fastapi import HTTPException

    from jobwright.web.routers.board import PatchBody, patch_job

    _insert_job(db)
    monkeypatch.setattr("jobwright.web.routers.board.get_connection", lambda: db)

    with pytest.raises(HTTPException) as exc:
        patch_job("https://example.com/job", PatchBody(user_fit_score=8))
    assert exc.value.status_code == 400

    updated = patch_job(
        "https://example.com/job",
        PatchBody(user_fit_score=8, user_score_rationale="Underscored — direct CoS experience"),
    )
    assert updated["fit_score"] == 8
    assert updated["score_user_modified"] is True
    assert updated["ai_fit_score"] == 6


def test_patch_job_clear_user_score(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    from jobwright.web.routers.board import PatchBody, patch_job

    _insert_job(
        db,
        user_fit_score=9,
        user_score_rationale="Too high before",
        user_score_at="2026-02-01T00:00:00+00:00",
    )
    monkeypatch.setattr("jobwright.web.routers.board.get_connection", lambda: db)

    updated = patch_job("https://example.com/job", PatchBody(clear_user_score=True))
    assert updated["fit_score"] == 6
    assert updated["score_user_modified"] is False
