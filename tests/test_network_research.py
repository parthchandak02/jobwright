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


def test_looks_like_person_name():
    from jobwright.network.research import looks_like_person_name

    assert looks_like_person_name("Pat Lee")
    assert looks_like_person_name("Sam Ok")
    assert not looks_like_person_name("Programme Coordinator")
    assert not looks_like_person_name("Legal Manager")
    assert not looks_like_person_name("Community College Job Network")


def test_present_contact_drops_job_postings():
    from jobwright.network.research import present_contact

    junk = present_contact({
        "name": "Programme Coordinator",
        "role": "Programme Coordinator, Trustlaw-Thomson Reuters Foundation",
        "source_url": "https://thomsonreuters.wd5.myworkdayjobs.com/job/x",
        "note": "Public web result for Thomson Reuters",
        "source": "web",
    })
    assert junk is None

    keep = present_contact({
        "name": "Pat Lee",
        "role": "Recruiter at Acme",
        "source_url": "https://www.linkedin.com/in/pat-lee",
        "note": "Hiring contact",
        "source": "web",
    })
    assert keep is not None
    assert keep["url"] == "https://www.linkedin.com/in/pat-lee"
    assert keep["why"] == "Hiring contact"
    assert keep["position"] == "Recruiter at Acme"


def test_research_keeps_linkedin_skips_job_boards(monkeypatch):
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
                "title": "Programme Coordinator, Trustlaw-Thomson Reuters Foundation",
                "url": "https://thomsonreuters.wd5.myworkdayjobs.com/job/x",
                "text": "Job posting",
            },
            {
                "title": "Sam Ok - VP Ops at Acme",
                "url": "https://acme.com/team/sam",
                "text": "Public bio",
            },
        ]
    }
    monkeypatch.setattr(research.httpx, "post", lambda *a, **k: resp)
    out = research.research_company_contacts("Acme", "Ops", max_results=3)
    names = [c["name"] for c in out]
    assert "Pat Lee" in names
    assert "Sam Ok" in names
    assert "Programme Coordinator" not in names
    assert any("linkedin.com/in/" in (c.get("url") or "") for c in out)


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
