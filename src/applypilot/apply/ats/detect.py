"""Detect ATS platform from application URL."""

from __future__ import annotations

import re

_ATS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(
        r"(?:job-boards|boards)(?:\.[a-z]{2})?\.greenhouse\.io|greenhouse\.io/|grnh\.se/",
        re.I,
    )),
    ("lever", re.compile(r"jobs\.lever\.co|lever\.co/(?:company|posting)", re.I)),
    ("workday", re.compile(r"myworkdayjobs\.com|myworkdaysite\.com|workday\.com", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com|ashbyhq\.com", re.I)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com|smartrecruiters\.com", re.I)),
    ("icims", re.compile(r"icims\.com", re.I)),
]


def detect_ats(url: str | None) -> str | None:
    """Return ats id (greenhouse, lever, workday, ashby, etc.) or None."""
    if not url:
        return None
    for ats_id, pattern in _ATS_PATTERNS:
        if pattern.search(url):
            return ats_id
    return None
