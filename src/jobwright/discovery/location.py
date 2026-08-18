"""Shared location accept/reject filtering for discovery sources."""

from __future__ import annotations

import re

# Remote markers accepted after reject patterns pass.
_REMOTE_MARKERS = ("remote", "anywhere", "work from home", "wfh", "distributed")

# Non-US remote junk that often slips past bare "remote" acceptance.
# Matched as substrings on the lowercased location (conservative, minimal).
_INTL_REMOTE_JUNK = (
    "emea",
    "apac",
    "latam",
    "europe only",
    "uk only",
    "india only",
    "canada only",
    "worldwide except",
    "outside the us",
    "outside the united states",
    "non-us",
    "non us",
)


def pattern_matches(loc: str, pattern: str) -> bool:
    """Match a location pattern against a lowercased location string.

    Short alphanumeric tokens (<= 3 chars, e.g. "US", "SF", "CA") are matched on
    word boundaries so "US" does not match "Australia" and "CA" does not match
    "Calgary". Longer or punctuated patterns (", CA", "San Francisco") use plain
    substring matching.
    """
    p = pattern.lower().strip()
    if not p:
        return False
    if len(p) <= 3 and p.isalnum():
        return re.search(rf"\b{re.escape(p)}\b", loc) is not None
    return p in loc


def location_ok(location: str | None, accept: list[str], reject: list[str]) -> bool:
    """Check if a job location passes the user's location filter.

    Remote jobs are accepted after reject patterns pass (avoids "Calgary Remote").
    Known international-remote junk is rejected even when marked remote.
    Non-remote jobs must match an accept pattern.
    """
    if not location:
        return True  # unknown location -- keep it, let scorer decide

    loc = location.lower()

    for r in reject:
        if pattern_matches(loc, r):
            return False

    if any(marker in loc for marker in _REMOTE_MARKERS):
        if any(junk in loc for junk in _INTL_REMOTE_JUNK):
            return False
        return True

    for a in accept:
        if pattern_matches(loc, a):
            return True

    return False
