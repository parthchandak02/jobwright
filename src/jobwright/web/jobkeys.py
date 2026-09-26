"""Resolve the ``{url:path}`` segment of job routes.

The dashboard addresses jobs by their 12-hex ``job_id`` (safe in a URL path).
Full URLs are still accepted for older clients; those are unquoted once more
for back-compat with clients that double-encoded them.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from fastapi import HTTPException

from jobwright.database import get_connection, get_job_by_id

_JOB_ID = re.compile(r"^[0-9a-f]{12}$")


def resolve_job_key(key: str) -> str:
    if _JOB_ID.match(key or ""):
        row = get_job_by_id(key, get_connection())
        if row is None:
            raise HTTPException(404, "Job not found")
        return row["url"]
    return unquote(key)
