"""Tests for manual per-job connections."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobwright.network.manual_connections import (
    add_manual_contact,
    get_manual_contacts,
    normalize_linkedin_url,
    remove_manual_contact,
    search_connections_csv,
)


def test_normalize_linkedin_url():
    assert (
        normalize_linkedin_url("linkedin.com/in/jane-doe")
        == "https://linkedin.com/in/jane-doe"
    )
    with pytest.raises(ValueError):
        normalize_linkedin_url("https://example.com/not-linkedin")


def test_manual_contact_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    network = tmp_path / "network"
    network.mkdir()
    monkeypatch.setattr("jobwright.network.manual_connections.config.NETWORK_DIR", network)

    job_url = "https://example.com/job"
    contact = add_manual_contact(
        job_url,
        {
            "first_name": "Jane",
            "last_name": "Doe",
            "company": "Acme",
            "position": "PM",
            "url": "https://www.linkedin.com/in/jane-doe",
        },
    )
    assert contact["id"]
    assert get_manual_contacts(job_url)[0]["first_name"] == "Jane"

    assert remove_manual_contact(job_url, contact["id"]) is True
    assert get_manual_contacts(job_url) == []


def test_search_connections_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    csv_path = tmp_path / "connections.csv"
    csv_path.write_text(
        "First Name,Last Name,Company,Position,URL\n"
        "Alice,Smith,Acme,Engineer,https://linkedin.com/in/alice\n"
        "Bob,Jones,Beta,Designer,https://linkedin.com/in/bob\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobwright.network.manual_connections.config.CONNECTIONS_PATH",
        csv_path,
    )

    results = search_connections_csv("ali")
    assert len(results) == 1
    assert results[0]["first_name"] == "Alice"

    assert search_connections_csv("a") == []
