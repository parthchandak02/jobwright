"""In-memory index of URLs already in the jobs DB.

Used by Workday discovery to skip detail HTTP fetches for known postings.
"""

from __future__ import annotations

import sqlite3


def load_known_urls(conn: sqlite3.Connection) -> set[str]:
    """Load url + application_url values, plus /job/ path suffixes for matching."""
    known: set[str] = set()
    rows = conn.execute("SELECT url, application_url FROM jobs").fetchall()
    for url, application_url in rows:
        for value in (url, application_url):
            if not value:
                continue
            known.add(value)
            # Workday externalPath is typically "/job/..." — index that suffix
            idx = value.find("/job/")
            if idx >= 0:
                known.add(value[idx:])
    return known


def job_url_known(employer: dict, external_path: str, known_urls: set[str]) -> bool:
    """Return True if this Workday posting is already in the DB."""
    if not external_path or not known_urls:
        return False
    if external_path in known_urls:
        return True
    site_id = employer.get("site_id", "")
    base = employer.get("base_url", "")
    if base and site_id:
        candidate = f"{base}/{site_id}{external_path}"
        if candidate in known_urls:
            return True
    return False
