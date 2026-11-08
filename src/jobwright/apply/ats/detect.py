"""Detect the ATS (applicant tracking system) family from an application URL.

``detect_ats`` returns the family id or None when the URL is on no known ATS
(callers chain ``detect_ats(a) or detect_ats(b)``). ``ats_family`` is the same
but answers ``"other"`` for any other non-empty URL, which is what the
``jobs.application_ats`` column stores.

Matching is on the host (plus the path for a couple of shared hosts), never on
the query string, so an aggregator URL that merely carries an encoded ATS link
in a parameter is not mistaken for the ATS itself.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# (family, host regex, optional path regex). First match wins.
_ATS_PATTERNS: list[tuple[str, re.Pattern[str], re.Pattern[str] | None]] = [
    ("greenhouse", re.compile(r"(?:^|\.)(?:job-boards|boards)(?:\.[a-z]{2})?\.greenhouse\.io$|(?:^|\.)grnh\.se$"),
     None),
    ("greenhouse", re.compile(r"(?:^|\.)greenhouse\.io$"), re.compile(r"/(?:embed/)?job_app|/jobs/\d+", re.I)),
    ("lever", re.compile(r"(?:^|\.)jobs(?:\.eu)?\.lever\.co$"), None),
    ("ashby", re.compile(r"(?:^|\.)ashbyhq\.com$"), None),
    ("workday", re.compile(r"(?:^|\.)(?:myworkdayjobs|myworkdaysite|workday)\.com$"), None),
    ("icims", re.compile(r"(?:^|\.)icims\.com$"), None),
    ("smartrecruiters", re.compile(r"(?:^|\.)smartrecruiters\.com$"), None),
    ("jobvite", re.compile(r"(?:^|\.)jobvite\.com$"), None),
    ("bamboohr", re.compile(r"(?:^|\.)bamboohr\.com$"), None),
    ("workable", re.compile(r"(?:^|\.)workable\.com$"), None),
    ("rippling", re.compile(r"(?:^|\.)ats\.rippling\.com$"), None),
    ("rippling", re.compile(r"(?:^|\.)rippling\.com$"), re.compile(r"/jobs?(?:/|$)", re.I)),
    ("successfactors", re.compile(r"(?:^|\.)(?:successfactors|sapsf)\.(?:com|eu)$"), None),
    ("adp", re.compile(r"(?:^|\.)(?:workforcenow|recruiting|myjobs)\.adp\.com$"), None),
    ("applytojob", re.compile(r"(?:^|\.)(?:applytojob|jazzhr)\.com$"), None),
    ("breezy", re.compile(r"(?:^|\.)breezy\.hr$"), None),
    ("taleo", re.compile(r"(?:^|\.)taleo\.net$"), None),
    ("dayforce", re.compile(r"(?:^|\.)dayforcehcm\.com$"), None),
]

ATS_FAMILIES: tuple[str, ...] = (*dict.fromkeys(f for f, _, _ in _ATS_PATTERNS), "other")


def _host_path(url: str) -> tuple[str, str]:
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return "", ""
    return host, parsed.path or "/"


def detect_ats(url: str | None) -> str | None:
    """ATS family id (greenhouse, lever, ashby, workday, ...) or None."""
    if not url:
        return None
    host, path = _host_path(url)
    if not host:
        return None
    for family, host_re, path_re in _ATS_PATTERNS:
        if host_re.search(host) and (path_re is None or path_re.search(path)):
            return family
    return None


def ats_family(url: str | None) -> str | None:
    """Like detect_ats, but ``"other"`` for a URL on no known ATS (None when empty)."""
    if not url or not url.strip():
        return None
    return detect_ats(url) or "other"
