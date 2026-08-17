"""Tests for ATS detection, Greenhouse schema helpers, and parser."""

from unittest.mock import MagicMock, patch

from applypilot.apply.ats.detect import detect_ats
from applypilot.apply.ats.greenhouse import (
    parse_greenhouse_url,
    summarize_schema_for_prompt,
    validate_schema_against_profile,
)
from applypilot.apply.providers.base import parse_result_output
from applypilot.config import load_location_filters


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

        from applypilot.apply.ats.greenhouse import fetch_greenhouse_schema

        schema = fetch_greenhouse_schema("stripe", "12345")
        assert schema["title"] == "Test Role"
