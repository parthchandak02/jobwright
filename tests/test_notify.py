"""Tests for the simplified WhatsApp daily-notify feature."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jobwright import notify
from jobwright.database import (
    close_connection,
    get_unnotified_prepare_jobs,
    init_db,
    job_id_for_url,
    mark_whatsapp_notified,
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


def _insert_job(conn: sqlite3.Connection, url: str, **cols) -> None:
    defaults = {
        "url": url,
        "title": "Chief of Staff",
        "site": "indeed",
        "company": "Acme",
        "location": "San Francisco, CA",
        "salary": "$150k",
        "fit_score": 8,
        "discovered_at": "2026-01-01T00:00:00+00:00",
        "funnel_stage": "prepare",
    }
    defaults.update(cols)
    keys = ", ".join(defaults)
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


def test_build_notification_includes_deep_link():
    url = "https://example.com/job-a"
    jobs = [
        {
            "url": url,
            "title": "Ops Lead",
            "company": "Acme",
            "location": "Remote",
            "fit_score": 9,
        }
    ]
    msg = notify.build_notification(jobs, "https://jobwright.parthchandak.info/")
    assert "1 new job ready to review:" in msg
    assert "Ops Lead @ Acme" in msg
    assert "Remote \u00b7 score 9" in msg
    assert f"https://jobwright.parthchandak.info/jobs/{job_id_for_url(url)}" in msg


def test_get_unnotified_prepare_jobs_filters_stage_and_null(db: sqlite3.Connection):
    _insert_job(db, "https://example.com/prepare-new", fit_score=9)
    _insert_job(db, "https://example.com/backlog", funnel_stage="backlog")
    _insert_job(
        db,
        "https://example.com/prepare-done",
        fit_score=7,
        whatsapp_notified_at="2026-01-02T00:00:00+00:00",
    )

    jobs = get_unnotified_prepare_jobs(db)
    urls = [j["url"] for j in jobs]
    assert urls == ["https://example.com/prepare-new"]
    assert jobs[0]["fit_score"] == 9


def test_get_unnotified_prepare_jobs_prefers_user_score(db: sqlite3.Connection):
    _insert_job(db, "https://example.com/j1", fit_score=5, user_fit_score=9)
    jobs = get_unnotified_prepare_jobs(db)
    assert jobs[0]["fit_score"] == 9


def test_mark_whatsapp_notified_stamps_and_is_idempotent(db: sqlite3.Connection):
    url = "https://example.com/prepare-new"
    _insert_job(db, url)

    first = mark_whatsapp_notified([url], db)
    assert first == 1
    stamp = db.execute(
        "SELECT whatsapp_notified_at FROM jobs WHERE url = ?", (url,)
    ).fetchone()[0]
    assert stamp is not None

    second = mark_whatsapp_notified([url], db)
    assert second == 0


def test_run_notify_no_prepare_jobs_skips(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("hermes should not be called when there is nothing to send")

    monkeypatch.setattr(notify, "send_via_hermes", _boom)
    result = notify.run_notify()
    assert result == {"sent": 0, "skipped": True, "reason": "no new prepare jobs", "jobs": []}


def test_run_notify_dry_run_does_not_mark(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    url = "https://example.com/prepare-new"
    _insert_job(db, url)

    def _boom(*_args, **_kwargs):
        raise AssertionError("dry_run must not send")

    monkeypatch.setattr(notify, "send_via_hermes", _boom)
    result = notify.run_notify(dry_run=True)

    assert result["skipped"] is False
    assert result["dry_run"] is True
    assert "message" in result
    assert result["jobs"][0]["job_id"] == job_id_for_url(url)

    stamp = db.execute(
        "SELECT whatsapp_notified_at FROM jobs WHERE url = ?", (url,)
    ).fetchone()[0]
    assert stamp is None


def test_run_notify_sends_and_marks(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    url = "https://example.com/prepare-new"
    _insert_job(db, url)

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send_via_hermes", lambda msg, target: sent.append((msg, target)))
    monkeypatch.setattr(notify, "get_active_user_id", lambda: "richa")
    monkeypatch.setattr(
        notify, "get_user", lambda _uid: type("U", (), {"whatsapp_target": "whatsapp:123@g.us"})()
    )

    result = notify.run_notify()
    assert result["sent"] == 1
    assert len(sent) == 1
    assert sent[0][1] == "whatsapp:123@g.us"

    stamp = db.execute(
        "SELECT whatsapp_notified_at FROM jobs WHERE url = ?", (url,)
    ).fetchone()[0]
    assert stamp is not None


def test_run_notify_missing_target_raises(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    _insert_job(db, "https://example.com/prepare-new")
    monkeypatch.setattr(notify, "send_via_hermes", lambda *_a, **_k: None)
    monkeypatch.setattr(notify, "get_active_user_id", lambda: "richa")
    monkeypatch.setattr(
        notify, "get_user", lambda _uid: type("U", (), {"whatsapp_target": ""})()
    )
    with pytest.raises(ValueError):
        notify.run_notify()
