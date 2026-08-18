"""Tests for company column persistence and schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def test_ensure_columns_adds_company_and_docx(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, ensure_columns, init_db

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    close_connection(db)

    # Simulate old schema without company / docx columns
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY,
            title TEXT,
            site TEXT,
            strategy TEXT,
            discovered_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    conn = init_db(db)
    added = ensure_columns(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "company" in cols
    assert "tailored_resume_docx_path" in cols
    assert "cover_letter_docx_path" in cols
    assert "company" in added or "company" in cols
    close_connection(db)


def test_store_jobspy_persists_company(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.discovery.jobspy import store_jobspy_results

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    # Minimal search config so exclude_companies works
    monkeypatch.setattr(
        config,
        "load_search_config",
        lambda: {"exclude_companies": [], "exclude_titles": [], "min_salary": 0},
    )
    close_connection(db)
    init_db(db)
    conn = get_connection(db)

    df = pd.DataFrame(
        [
            {
                "job_url": "https://example.com/jobs/1",
                "title": "Chief of Staff",
                "company": "Acme Impact",
                "location": "San Francisco, CA",
                "description": "A" * 250,
                "site": "linkedin",
                "is_remote": False,
                "min_amount": None,
                "max_amount": None,
                "interval": None,
                "currency": None,
                "job_url_direct": "https://example.com/apply/1",
            }
        ]
    )
    new, existing, skipped_known = store_jobspy_results(conn, df, "linkedin")
    assert new == 1
    assert existing == 0
    assert skipped_known == 0
    row = conn.execute(
        "SELECT company, title FROM jobs WHERE url = ?",
        ("https://example.com/jobs/1",),
    ).fetchone()
    assert row["company"] == "Acme Impact"
    assert row["title"] == "Chief of Staff"

    # Second pass with known_urls should skip filter work and count as existing
    new2, existing2, skipped2 = store_jobspy_results(
        conn, df, "linkedin", known_urls={"https://example.com/jobs/1"},
    )
    assert new2 == 0
    assert existing2 == 1
    assert skipped2 == 1
    close_connection(db)
