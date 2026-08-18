"""Tests for Workday known-URL skip and early-stop pagination."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def workday_db(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, init_db

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    close_connection(db)
    conn = init_db(db)
    yield conn, db
    close_connection(db)


def test_load_known_urls_indexes_job_path(workday_db):
    from jobwright.discovery.known_urls import job_url_known, load_known_urls

    conn, _ = workday_db
    path = "/job/San-Francisco/Chief-of-Staff_R123"
    url = f"https://acme.wd5.myworkdayjobs.com/en-US/Careers{path}"
    conn.execute(
        "INSERT INTO jobs (url, title, application_url) VALUES (?, ?, ?)",
        (url, "Chief of Staff", url),
    )
    conn.commit()

    known = load_known_urls(conn)
    assert url in known
    assert path in known

    employer = {
        "name": "Acme",
        "base_url": "https://acme.wd5.myworkdayjobs.com",
        "site_id": "en-US/Careers",
        "tenant": "acme",
    }
    assert job_url_known(employer, path, known) is True
    assert job_url_known(employer, "/job/Other/Unknown_R999", known) is False


def test_process_one_skips_detail_fetch_for_known(workday_db, monkeypatch):
    from jobwright.discovery import workday as wd

    conn, _ = workday_db
    path = "/job/SF/CoS_R1"
    url = f"https://acme.wd5.myworkdayjobs.com/en-US/Careers{path}"
    conn.execute(
        "INSERT INTO jobs (url, title, application_url) VALUES (?, ?, ?)",
        (url, "Chief of Staff", url),
    )
    conn.commit()

    employer = {
        "name": "Acme",
        "base_url": "https://acme.wd5.myworkdayjobs.com",
        "site_id": "en-US/Careers",
        "tenant": "acme",
    }
    employers = {"acme": employer}
    known = {url, path}

    listing = {
        "title": "Chief of Staff",
        "location": "San Francisco, CA",
        "posted": "Posted Today",
        "external_path": path,
        "employer_key": "acme",
        "employer_name": "Acme",
    }

    with patch.object(wd, "search_employer", return_value=[listing]):
        with patch.object(wd, "workday_detail") as mock_detail:
            with patch.object(wd, "get_connection", return_value=conn):
                result = wd._process_one(
                    "acme", employers, "chief of staff",
                    True, ["San Francisco"], [], known,
                )

    mock_detail.assert_not_called()
    assert result["skipped_known"] == 1
    assert result["new"] == 0
    assert result["existing"] == 1


def test_search_employer_early_stops_on_consecutive_known(monkeypatch):
    from jobwright.discovery import workday as wd

    employer = {
        "name": "Acme",
        "base_url": "https://acme.wd5.myworkdayjobs.com",
        "site_id": "en-US/Careers",
        "tenant": "acme",
    }

    # First page: 10 known jobs in a row → early stop (no second page)
    postings = [
        {
            "title": f"Job {i}",
            "locationsText": "San Francisco, CA",
            "postedOn": "Posted Today",
            "externalPath": f"/job/SF/Known_{i}",
        }
        for i in range(10)
    ]
    known = {f"/job/SF/Known_{i}" for i in range(10)}

    call_count = {"n": 0}

    def fake_search(_emp, _text, limit=20, offset=0):
        call_count["n"] += 1
        if offset == 0:
            return {"total": 40, "jobPostings": postings}
        return {"total": 40, "jobPostings": [
            {
                "title": "Should not fetch",
                "locationsText": "San Francisco, CA",
                "postedOn": "Posted Today",
                "externalPath": "/job/SF/New_99",
            }
        ]}

    monkeypatch.setattr(wd, "workday_search", fake_search)

    jobs = wd.search_employer(
        "acme", employer, "chief of staff",
        location_filter=True,
        accept_locs=["San Francisco"],
        reject_locs=[],
        known_urls=known,
        early_stop=10,
    )

    assert call_count["n"] == 1  # did not paginate to offset 20
    assert len(jobs) == 10
    assert all(j["external_path"].startswith("/job/SF/Known_") for j in jobs)


def test_canada_employers_filtered_when_reject_includes_canada(monkeypatch):
    """Empty-location Canada banks must not leak when reject includes canada."""
    from jobwright.discovery import workday

    employers = {
        "rbc": {"name": "RBC"},
        "nvidia": {"name": "NVIDIA"},
        "salesforce": {"name": "Salesforce"},
    }
    monkeypatch.setattr(workday, "load_employers", lambda: employers)
    monkeypatch.setattr(
        workday.config,
        "load_search_config",
        lambda: {
            "queries": [{"query": "chief of staff", "tier": 1}],
            "location": {"reject": ["Canada", "Toronto"]},
        },
    )
    monkeypatch.setattr(
        workday,
        "_load_location_filter",
        lambda _cfg=None: ([], ["Canada", "Toronto"]),
    )
    monkeypatch.setattr(workday, "init_db", lambda: None)
    monkeypatch.setattr(workday, "get_connection", lambda: None)
    monkeypatch.setattr(workday, "load_known_urls", lambda _c: set())

    captured: dict = {}

    def capture_scrape(**kwargs):
        captured["employers"] = kwargs.get("employers")
        return {"found": 0, "new": 0, "existing": 0, "skipped_known": 0, "errors": 0}

    monkeypatch.setattr(workday, "scrape_employers", capture_scrape)
    out = workday.run_workday_discovery()
    assert "rbc" not in captured["employers"]
    assert "nvidia" in captured["employers"]
    assert out["queries"] == 1
