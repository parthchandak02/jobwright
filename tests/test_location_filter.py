"""Tests for discovery location filtering (shared location_ok / pattern_matches)."""

from __future__ import annotations

from jobwright.discovery import cleanup, jobspy, smartextract, workday
from jobwright.discovery.location import location_ok, pattern_matches

ACCEPT = ["San Francisco", "Bay Area", ", CA", "Remote", "United States", "US", "USA"]
REJECT = ["Calgary", "Toronto", "Canada", "India", "(ON)", "NYC only"]


def test_unknown_location_is_kept():
    assert location_ok(None, ACCEPT, REJECT) is True
    assert location_ok("", ACCEPT, REJECT) is True


def test_reject_wins_over_remote():
    # A Canadian remote posting must not slip through on the remote bypass.
    assert location_ok("Calgary, AB (Remote)", ACCEPT, REJECT) is False
    assert location_ok("Toronto, ON - Remote", ACCEPT, REJECT) is False
    assert location_ok("Canada - Remote", ACCEPT, REJECT) is False


def test_plain_remote_is_accepted():
    assert location_ok("Remote", ACCEPT, REJECT) is True
    assert location_ok("Anywhere", ACCEPT, REJECT) is True


def test_bay_area_accepted():
    assert location_ok("San Francisco, CA", ACCEPT, REJECT) is True
    assert location_ok("San Jose, CA", ACCEPT, REJECT) is True  # matches ", CA"


def test_non_matching_us_city_rejected():
    # Austin is not in the accept list and must not false-match "US".
    assert location_ok("Austin, TX", ACCEPT, REJECT) is False


def test_short_token_word_boundary():
    # "US" must not match "Australia" (substring "us"); must match a real "US".
    assert pattern_matches("sydney, australia", "US") is False
    assert pattern_matches("boston, us", "US") is True
    assert location_ok("Sydney, Australia", ACCEPT, REJECT) is False
    assert location_ok("Boston, US", ACCEPT, REJECT) is True


def test_ca_pattern_does_not_match_calgary_via_accept():
    # ", CA" is punctuated so substring-matched, but Calgary is rejected first.
    assert location_ok("Calgary, CA", ACCEPT, REJECT) is False


def test_intl_remote_junk_rejected():
    assert location_ok("Remote - EMEA", ACCEPT, REJECT) is False
    assert location_ok("Remote APAC", ACCEPT, REJECT) is False
    assert location_ok("Remote (India only)", ACCEPT, REJECT) is False
    assert location_ok("Remote - US", ACCEPT, REJECT) is True


def test_all_callers_use_shared_helper():
    """jobspy/workday/smartextract/cleanup must share the same location_ok."""
    assert jobspy._location_ok is location_ok
    assert workday._location_ok is location_ok
    assert smartextract._location_ok is location_ok
    assert cleanup._location_ok is location_ok
