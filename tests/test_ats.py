"""Tests for ATS detection, Greenhouse schema helpers, and parser."""

from unittest.mock import MagicMock, patch

from jobwright.apply.ats.detect import detect_ats
from jobwright.apply.ats.greenhouse import (
    parse_greenhouse_url,
    summarize_schema_for_prompt,
    validate_schema_against_profile,
)
from jobwright.apply.providers.base import parse_result_output
from jobwright.config import load_location_filters


def test_detect_ats_platforms():
    assert detect_ats("https://job-boards.greenhouse.io/stripe/jobs/123") == "greenhouse"
    assert detect_ats("https://boards.eu.greenhouse.io/stripe/jobs/123") == "greenhouse"
    assert detect_ats("https://grnh.se/bu1x3kkt8us") == "greenhouse"
    assert detect_ats("https://adobe.wd5.myworkdayjobs.com/job/123") == "workday"
    assert detect_ats("https://jobs.lever.co/foodsmart/123") == "lever"


def test_parse_greenhouse_url_formats():
    assert parse_greenhouse_url("https://job-boards.greenhouse.io/stripe/jobs/12345") == ("stripe", "12345")
    assert parse_greenhouse_url("https://boards.eu.greenhouse.io/stripe/jobs/12345") == ("stripe", "12345")
    assert parse_greenhouse_url(
        "https://boards.greenhouse.io/embed/job_app?token=12345&for=stripe"
    ) == ("stripe", "12345")


def test_summarize_schema_filters_standard_fields():
    schema = {
        "questions": [
            {"label": "First Name", "required": True, "fields": [{"type": "input_text"}]},
            {
                "label": "Are you authorized to work in the US?",
                "required": True,
                "fields": [{
                    "type": "multi_value_single_select",
                    "values": [{"label": "Yes"}, {"label": "No"}],
                }],
            },
        ],
    }
    summary = summarize_schema_for_prompt(schema)
    assert "First Name" not in summary
    assert "Are you authorized" in summary
    assert "[Yes, No]" in summary


def test_validate_schema_against_profile():
    schema = {"questions": [{"label": "Email", "required": True}]}
    profile = {"personal": {"full_name": "Jane Doe", "email": "jane@example.com", "phone": "555"}}
    assert validate_schema_against_profile(schema, profile) == []


def test_dry_run_rejects_applied():
    assert parse_result_output("RESULT:APPLIED", dry_run=True) == "failed:dryrun_protocol_violation"
    assert parse_result_output("did not RESULT:APPLIED today", dry_run=True) == "failed:no_result_line"
    assert parse_result_output("RESULT:DRYRUN", dry_run=True) == "dryrun"
    assert parse_result_output("**RESULT:EXPIRED**", dry_run=True) == "expired"


def test_location_filters_nested_yaml():
    cfg = {"location": {"accept_patterns": ["Remote"], "reject_patterns": ["India"]}}
    accept, reject = load_location_filters(cfg)
    assert accept == ["Remote"]
    assert reject == ["India"]


def test_fetch_greenhouse_schema_mock():
    with patch("httpx.Client") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "Test Role", "questions": []}
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

        from jobwright.apply.ats.greenhouse import fetch_greenhouse_schema

        schema = fetch_greenhouse_schema("stripe", "12345")
        assert schema["title"] == "Test Role"


def test_detect_ats_every_family():
    from jobwright.apply.ats.detect import ats_family

    cases = {
        "https://boards.greenhouse.io/exampleorg/jobs/4001": "greenhouse",
        "https://job-boards.eu.greenhouse.io/exampleorg/jobs/4001": "greenhouse",
        "https://jobs.eu.lever.co/exampleorg/abc-123/apply": "lever",
        "https://jobs.ashbyhq.com/exampleorg/1f2e3d4c/application": "ashby",
        "https://exampleorg.wd1.myworkdayjobs.com/en-US/External/job/Remote/Analyst_R1": "workday",
        "https://careers-exampleorg.icims.com/jobs/1234/analyst/job": "icims",
        "https://jobs.smartrecruiters.com/ExampleOrg/7430000000000-analyst": "smartrecruiters",
        "https://jobs.jobvite.com/exampleorg/job/oAbc123": "jobvite",
        "https://exampleorg.bamboohr.com/careers/42": "bamboohr",
        "https://apply.workable.com/exampleorg/j/ABC123/": "workable",
        "https://ats.rippling.com/exampleorg/jobs/9b1c": "rippling",
        "https://career4.successfactors.com/sfcareer/jobreqcareer?jobId=1": "successfactors",
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=x": "adp",
        "https://exampleorg.applytojob.com/apply/AbC123/Analyst": "applytojob",
        "https://exampleorg.breezy.hr/p/abc123-analyst": "breezy",
        "https://exampleorg.taleo.net/careersection/2/jobdetail.ftl?job=1": "taleo",
        "https://jobs.dayforcehcm.com/en-US/exampleorg/CANDIDATEPORTAL/jobs/1": "dayforce",
    }
    for url, family in cases.items():
        assert detect_ats(url) == family, url
        assert ats_family(url) == family, url
    assert detect_ats("https://careers.example.org/jobs/1") is None
    assert ats_family("https://careers.example.org/jobs/1") == "other"
    assert ats_family("") is None
    # An aggregator URL carrying an encoded ATS link is not the ATS.
    assert detect_ats("https://agg.example.net/r?url=https%3A%2F%2Fjobs.lever.co%2Fx%2F1") is None
