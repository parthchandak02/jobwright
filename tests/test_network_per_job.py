"""Tests for per-job connection matching."""

from __future__ import annotations

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
