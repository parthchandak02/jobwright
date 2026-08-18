"""Tests for sponsorship status derivation."""

from jobwright.enrichment.sponsorship import (
    classify_sponsorship,
    derive_sponsorship_status,
)


def test_sponsorship_not_found_when_missing():
    assert derive_sponsorship_status(None) == "not_found"
    assert derive_sponsorship_status("") == "not_found"
    assert derive_sponsorship_status("Great role with executive sponsor relationships.") == "not_found"


def test_sponsorship_not_required():
    assert (
        derive_sponsorship_status("Must be authorized to work without sponsorship.")
        == "not_required"
    )
    assert (
        derive_sponsorship_status("This position is not eligible for Visa sponsorship.")
        == "not_required"
    )
    assert (
        derive_sponsorship_status(
            "This position is not eligible for Intel immigration sponsorship."
        )
        == "not_required"
    )
    assert (
        derive_sponsorship_status(
            "Employer work permit sponsorship is not available for this position."
        )
        == "not_required"
    )
    assert (
        derive_sponsorship_status("The Company is unable to provide sponsorship for workers.")
        == "not_required"
    )


def test_sponsorship_required():
    assert (
        derive_sponsorship_status("We offer visa sponsorship for qualified candidates.")
        == "required"
    )
    assert (
        derive_sponsorship_status("Visa sponsorship: We do sponsor visas!")
        == "required"
    )


def test_sponsorship_citizenship_or_green_card_is_ineligible():
    """US citizen / green card / permanent-resident requirements => not_required (ineligible)."""
    for text in (
        "Applicants must be a US citizen.",
        "US citizenship is required for this role.",
        "Open to US citizens or green card holders only.",
        "Candidates must be US citizens or permanent residents.",
        "Green card holders only.",
        "Must be a permanent resident to apply.",
    ):
        assert derive_sponsorship_status(text) == "not_required", text


def test_classify_falls_back_to_regex_when_llm_disabled():
    """With the LLM tier off, classify must equal the regex result (no network)."""
    cases = {
        None: "not_found",
        "": "not_found",
        "Great team, executive sponsor relationships.": "not_found",
        "We offer visa sponsorship for qualified candidates.": "required",
        "Must be authorized to work without sponsorship.": "not_required",
        "US citizenship is required.": "not_required",
    }
    for text, expected in cases.items():
        assert classify_sponsorship(text, use_llm=False) == expected, text


def test_classify_no_signal_skips_llm(monkeypatch):
    """No sponsorship/eligibility tokens => not_found without ever calling the LLM."""
    def _boom(_desc):
        raise AssertionError("LLM should not be called when there is no signal")

    monkeypatch.setattr(
        "jobwright.enrichment.sponsorship._classify_llm", _boom
    )
    assert classify_sponsorship("Own the roadmap and ship great products.") == "not_found"
