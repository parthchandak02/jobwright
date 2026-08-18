"""Tests for discovery location filtering (_location_ok / _pattern_matches)."""

from __future__ import annotations

from jobwright.discovery.jobspy import _location_ok, _pattern_matches

ACCEPT = ["San Francisco", "Bay Area", ", CA", "Remote", "United States", "US", "USA"]
REJECT = ["Calgary", "Toronto", "Canada", "India", "(ON)", "NYC only"]


def test_unknown_location_is_kept():
    assert _location_ok(None, ACCEPT, REJECT) is True
    assert _location_ok("", ACCEPT, REJECT) is True


def test_reject_wins_over_remote():
    # A Canadian remote posting must not slip through on the remote bypass.
    assert _location_ok("Calgary, AB (Remote)", ACCEPT, REJECT) is False
    assert _location_ok("Toronto, ON - Remote", ACCEPT, REJECT) is False
    assert _location_ok("Canada - Remote", ACCEPT, REJECT) is False


def test_plain_remote_is_accepted():
    assert _location_ok("Remote", ACCEPT, REJECT) is True
    assert _location_ok("Anywhere", ACCEPT, REJECT) is True


def test_bay_area_accepted():
    assert _location_ok("San Francisco, CA", ACCEPT, REJECT) is True
    assert _location_ok("San Jose, CA", ACCEPT, REJECT) is True  # matches ", CA"


def test_non_matching_us_city_rejected():
    # Austin is not in the accept list and must not false-match "US".
    assert _location_ok("Austin, TX", ACCEPT, REJECT) is False


def test_short_token_word_boundary():
    # "US" must not match "Australia" (substring "us"); must match a real "US".
    assert _pattern_matches("sydney, australia", "US") is False
    assert _pattern_matches("boston, us", "US") is True
    assert _location_ok("Sydney, Australia", ACCEPT, REJECT) is False
    assert _location_ok("Boston, US", ACCEPT, REJECT) is True


def test_ca_pattern_does_not_match_calgary_via_accept():
    # ", CA" is punctuated so substring-matched, but Calgary is rejected first.
    assert _location_ok("Calgary, CA", ACCEPT, REJECT) is False
