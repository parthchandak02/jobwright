"""Tests for Exa web research and per-job connect stage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest


def test_research_no_exa_key_returns_empty(monkeypatch):
    from jobwright.network.research import research_company_contacts

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    assert research_company_contacts("Acme", "Chief of Staff") == []


def test_research_http_error_returns_empty(monkeypatch):
    from jobwright.network import research

    monkeypatch.setenv("EXA_API_KEY", "exa-test")

    def boom(*_a, **_k):
        raise httpx.HTTPError("network down")

    monkeypatch.setattr(research.httpx, "post", boom)
    assert research.research_company_contacts("Acme", "PM") == []


def test_research_skips_linkedin_profiles(monkeypatch):
    from jobwright.network import research

    monkeypatch.setenv("EXA_API_KEY", "exa-test")
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": [
            {
                "title": "Pat Lee - Recruiter at Acme",
                "url": "https://www.linkedin.com/in/patlee",
                "text": "LinkedIn profile",
            },
            {
                "title": "Sam Ok - VP Ops at Acme",
                "url": "https://acme.com/team/sam",
                "text": "Public bio",
            },
        ]
    }
    monkeypatch.setattr(research.httpx, "post", lambda *a, **k: resp)
    out = research.research_company_contacts("Acme", "Ops", max_results=2)
    assert len(out) == 1
    assert "linkedin.com" not in out[0]["source_url"]
    assert "Sam" in out[0]["name"]


def test_run_per_job_connect_without_csv_or_exa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.network import per_job

    db = tmp_path / "jobs.db"
    network = tmp_path / "network"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "NETWORK_DIR", network)
    monkeypatch.setattr(config, "is_manual_ats", lambda url: False)
    monkeypatch.setattr(config, "load_blocked_sites", lambda: ([], []))
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    close_connection(db)
    init_db(db)
    conn = get_connection(db)
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, site, company, fit_score, tailored_resume_path,
            full_description, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job/1",
            "Chief of Staff",
            "indeed",
            "Acme",
            8,
            str(tmp_path / "resume.txt"),
            "Strategy ops role",
            "2026-01-01",
        ),
    )
    conn.commit()
    (tmp_path / "resume.txt").write_text("resume", encoding="utf-8")

    with patch("jobwright.network.per_job.load_connections_csv", side_effect=FileNotFoundError):
        result = per_job.run_per_job_connect(min_score=5, limit=5)

    assert result["status"] == "ok"
    assert result["jobs"] == 1
    latest = network / "job_contacts_latest.json"
    assert latest.exists()
    close_connection(db)


def test_digest_materials_lines_without_contacts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Digest still emits materials N lines when contacts file is absent."""
    import jobwright.config as config
    from jobwright.apply.launcher import write_morning_digest_and_manifest
    from jobwright.database import close_connection, get_connection, init_db

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "NETWORK_DIR", tmp_path / "network")
    monkeypatch.setattr(config, "is_manual_ats", lambda url: False)
    monkeypatch.setattr(config, "load_blocked_sites", lambda: ([], []))
    close_connection(db)
    init_db(db)
    conn = get_connection(db)
    resume = tmp_path / "resume.txt"
    resume.write_text("Jane\n", encoding="utf-8")
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"PK\x03\x04fake")
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, site, company, fit_score, tailored_resume_path,
            tailored_resume_docx_path, full_description, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job/9",
            "Chief of Staff",
            "indeed",
            "Acme",
            9,
            str(resume),
            str(docx),
            "Great role",
            "2026-01-01",
        ),
    )
    conn.commit()

    digest = tmp_path / "DIGEST"
    manifest = tmp_path / "MANIFEST"
    n = write_morning_digest_and_manifest(
        digest, manifest, min_score=5, limit=5, apply_enabled=False
    )
    assert n == 1
    text = digest.read_text(encoding="utf-8")
    assert "Materials: DOCX ready (reply materials 1)" in text
    assert "Connections:" not in text
    close_connection(db)
