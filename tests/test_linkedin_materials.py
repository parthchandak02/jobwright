"""LinkedIn: full brief materials OK; live apply still blocked."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def linkedin_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "NETWORK_DIR", tmp_path / "network")
    monkeypatch.setattr(config, "is_manual_ats", lambda url: False)
    close_connection(db)
    init_db(db)
    conn = get_connection(db)

    resume = tmp_path / "resume.txt"
    resume.write_text("Jane Doe\nChief of Staff\n", encoding="utf-8")
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"PK\x03\x04fake")
    li_url = "https://www.linkedin.com/jobs/view/1234567890"
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, site, company, fit_score, full_description,
            tailored_resume_path, tailored_resume_docx_path, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            li_url,
            "Chief of Staff",
            "linkedin",
            "Acme",
            9,
            "Lead ops and strategy at Acme.",
            str(resume),
            str(docx),
            "2026-01-01",
        ),
    )
    # Untailored LinkedIn row for pending_tailor / portfolio / cover selection.
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, site, company, fit_score, full_description, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://www.linkedin.com/jobs/view/999",
            "Chief of Staff Ops",
            "linkedin",
            "Acme",
            8,
            "Ops role needing a CoS.",
            "2026-01-01",
        ),
    )
    conn.commit()
    yield conn, db, li_url, resume
    close_connection(db)


def test_load_apply_blocked_includes_linkedin():
    from jobwright.config import load_apply_blocked, load_blocked_sites

    apply_sites, apply_patterns = load_apply_blocked()
    assert "linkedin" in apply_sites
    assert any("linkedin.com/jobs" in p for p in apply_patterns)

    disc_sites, disc_patterns = load_blocked_sites()
    assert "linkedin" not in disc_sites
    assert not any("linkedin.com" in p for p in disc_patterns)


def test_linkedin_in_pending_tailor_and_portfolio_and_cover(linkedin_db):
    from jobwright.database import get_jobs_by_stage
    from jobwright.scoring import cover_letter, portfolio

    conn, _db, _li_url, _resume = linkedin_db
    pending = get_jobs_by_stage(conn=conn, stage="pending_tailor", min_score=7, limit=10)
    urls = {j["url"] for j in pending}
    assert "https://www.linkedin.com/jobs/view/999" in urls

    # Portfolio SELECT (mirror production query without LLM)
    rows = conn.execute(
        """
        SELECT url FROM jobs
        WHERE fit_score >= ?
          AND full_description IS NOT NULL
          AND portfolio_project_ids IS NULL
        ORDER BY fit_score DESC
        """,
        (7,),
    ).fetchall()
    assert any("linkedin.com" in r[0] for r in rows)

    # Cover SELECT shape from cover_letter.run_cover_letters
    cover_rows = conn.execute(
        """
        SELECT url FROM jobs
        WHERE fit_score >= ? AND tailored_resume_path IS NOT NULL
          AND full_description IS NOT NULL
          AND (cover_letter_path IS NULL OR cover_letter_path = '')
        """,
        (7,),
    ).fetchall()
    assert any("linkedin.com/jobs/view/1234567890" in r[0] for r in cover_rows)

    # Sanity: modules still import after filter removal
    assert hasattr(portfolio, "run_portfolio_selection")
    assert hasattr(cover_letter, "run_cover_letters")


def test_list_ready_includes_linkedin(linkedin_db, monkeypatch):
    from jobwright.apply.launcher import list_ready_jobs
    import jobwright.config as config

    _conn, _db, li_url, _resume = linkedin_db
    monkeypatch.setattr(config, "load_blocked_sites", lambda: (set(), []))
    # Keep real apply_blocked - LinkedIn must still surface for materials/connect.

    ready = list_ready_jobs(min_score=7, limit=5)
    assert any(j["url"] == li_url for j in ready)


def test_apply_queue_excludes_linkedin(linkedin_db, monkeypatch):
    from jobwright.apply import launcher
    import jobwright.config as config

    _conn, _db, li_url, _resume = linkedin_db
    monkeypatch.setattr(config, "load_blocked_sites", lambda: (set(), []))

    where, params = launcher._ready_jobs_query(
        7, config.DEFAULTS["max_apply_attempts"], include_apply_blocked=True
    )
    conn = _conn
    rows = conn.execute(f"SELECT url, site FROM jobs WHERE {where}", params).fetchall()
    assert not any("linkedin" in (r["site"] or "").lower() for r in rows)
    assert not any("linkedin.com" in (r["url"] or "") for r in rows)

    claimed = launcher.acquire_job(min_score=7)
    assert claimed is None

    claimed_target = launcher.acquire_job(target_url=li_url, min_score=7)
    assert claimed_target is None
