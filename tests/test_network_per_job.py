"""Tests for per-job connection matching and digest materials."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def test_companies_match_fuzzy():
    from jobwright.network.per_job import companies_match

    assert companies_match("Acme Inc", "Acme")
    assert companies_match("OpenAI", "Open AI")
    assert not companies_match("Google", "Meta")


def test_filter_contacts_for_company():
    from jobwright.network.per_job import filter_contacts_for_company

    contacts = [
        {"first_name": "A", "last_name": "One", "company": "Acme Corp", "position": "PM"},
        {"first_name": "B", "last_name": "Two", "company": "Other Co", "position": "Eng"},
    ]
    matched = filter_contacts_for_company(contacts, "Acme")
    assert len(matched) == 1
    assert matched[0]["first_name"] == "A"


def test_rank_contacts_for_job_fallback_without_llm():
    from jobwright.network.per_job import rank_contacts_for_job

    contacts = [
        {
            "first_name": "Pat",
            "last_name": "Lee",
            "company": "Acme",
            "position": "Recruiter",
            "email": "",
            "url": "",
        }
    ]
    job = {"title": "Chief of Staff", "company": "Acme", "fit_score": 8, "url": "https://x"}

    with patch("jobwright.network.per_job.get_client", side_effect=RuntimeError("no llm")):
        ranked = rank_contacts_for_job(contacts, job, top_n=3)
    assert len(ranked) == 1
    assert ranked[0]["source"] == "csv"
    assert ranked[0]["first_name"] == "Pat"


def test_write_digest_includes_materials_and_connections(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.apply.launcher import write_morning_digest_and_manifest
    from jobwright.database import close_connection, get_connection, init_db

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "NETWORK_DIR", tmp_path / "network")
    monkeypatch.setattr(config, "is_manual_ats", lambda url: False)
    monkeypatch.setattr(
        config,
        "load_blocked_sites",
        lambda: ([], []),
    )
    close_connection(db)
    init_db(db)
    conn = get_connection(db)
    resume = tmp_path / "resume.txt"
    resume.write_text("Jane Doe\nTitle\n\nSUMMARY\nHello\n", encoding="utf-8")
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"PK\x03\x04fake")  # minimal zip-ish marker; existence only
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, site, company, fit_score, tailored_resume_path,
            tailored_resume_docx_path, full_description, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job/1",
            "Chief of Staff",
            "linkedin",
            "Acme",
            9,
            str(resume),
            str(docx),
            "Great role at Acme doing strategy",
            "2026-01-01",
        ),
    )
    conn.commit()

    network_dir = tmp_path / "network"
    network_dir.mkdir()
    (network_dir / "job_contacts_latest.json").write_text(
        json.dumps(
            {
                "jobs": {
                    "https://example.com/job/1": {
                        "csv_contacts": [
                            {
                                "first_name": "Pat",
                                "last_name": "Lee",
                                "position": "Recruiter",
                                "why": "Same company",
                            }
                        ],
                        "web_contacts": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    digest = tmp_path / "DIGEST_20260101"
    manifest = tmp_path / "APPLY_MANIFEST_20260101"
    n = write_morning_digest_and_manifest(
        digest, manifest, min_score=5, limit=5, apply_enabled=False, user_label="Richa"
    )
    assert n == 1
    text = digest.read_text(encoding="utf-8")
    assert "Daily Brief" in text
    assert "Acme" in text
    assert "Pat Lee" in text
    assert "materials 1" in text.lower()
    materials = tmp_path / "MATERIALS_MANIFEST_latest.json"
    assert materials.exists()
    data = json.loads(materials.read_text(encoding="utf-8"))
    assert data["jobs"][0]["resume_docx"] == str(docx)
    close_connection(db)
