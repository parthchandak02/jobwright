"""Cross-board duplicate detection.

The same posting shows up under different URLs (LinkedIn + Indeed + a repost
with a fresh id). URL keys cannot catch that, so every job gets a normalized
``dedupe_key`` (company | title | place). A newly discovered job whose key
matches an existing job, or a job removed in the last ``window_days``, is
tombstoned as a duplicate before it costs an enrich/score call.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from jobwright.database import tombstone_jobs

log = logging.getLogger(__name__)

_COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
    "company", "plc", "lp", "llp", "pbc", "the", "group", "holdings",
}
# Work-arrangement words only; role-distinguishing text (e.g. "(Education)")
# is kept so two different openings at one company never collapse.
_TITLE_NOISE = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|onsite|full[- ]?time|part[- ]?time|"
    r"contract|temporary|temp|usa|united states)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _squash(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def normalize_company(company: str | None) -> str:
    words = [w for w in _squash(company or "").split() if w not in _COMPANY_SUFFIXES]
    return " ".join(words)


def normalize_title(title: str | None) -> str:
    cleaned = _TITLE_NOISE.sub(" ", title or "")
    return " ".join(_squash(cleaned).split())


def normalize_place(location: str | None) -> str:
    loc = (location or "").lower()
    if not loc.strip() or re.fullmatch(r"\W*remote\W*", loc) or loc.startswith("remote"):
        return "remote"
    first = loc.split(",")[0]
    return " ".join(_squash(first).split())


def dedupe_key(title: str | None, company: str | None, location: str | None) -> str | None:
    """Stable duplicate key, or None when there is not enough signal."""
    c = normalize_company(company)
    t = normalize_title(title)
    if not c or not t:
        return None
    return f"{c}|{t}|{normalize_place(location)}"


def dedupe_new_jobs(conn: sqlite3.Connection, *, window_days: int = 45) -> dict[str, int]:
    """Key every unkeyed job and tombstone duplicates of existing/removed jobs."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT url, title, company, location, source, board_updated_by, discovered_at "
        "FROM jobs WHERE dedupe_key IS NULL ORDER BY discovered_at, rowid"
    ).fetchall()
    if not rows:
        return {"keyed": 0, "duplicates": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    duplicates: list[tuple[str, str]] = []
    keyed = 0
    for row in rows:
        key = dedupe_key(row["title"], row["company"], row["location"])
        if key is None:
            conn.execute("UPDATE jobs SET dedupe_key = '' WHERE url = ?", (row["url"],))
            continue
        protected = (row["source"] or "") == "manual" or (row["board_updated_by"] or "") == "human"
        if not protected:
            original = conn.execute(
                "SELECT url FROM jobs WHERE dedupe_key = ? AND url != ? LIMIT 1",
                (key, row["url"]),
            ).fetchone()
            if original is not None:
                duplicates.append((row["url"], f"duplicate:{original[0]}"))
                continue
            removed = conn.execute(
                "SELECT url, reason FROM job_tombstones WHERE dedupe_key = ? AND removed_at >= ? "
                "AND url != ? LIMIT 1",
                (key, cutoff, row["url"]),
            ).fetchone()
            if removed is not None:
                duplicates.append((row["url"], f"repost_of_removed:{removed[0]}"))
                continue
        conn.execute("UPDATE jobs SET dedupe_key = ? WHERE url = ?", (key, row["url"]))
        keyed += 1
    conn.commit()
    for url, _reason in duplicates:
        row = next(r for r in rows if r["url"] == url)
        conn.execute(
            "UPDATE jobs SET dedupe_key = ? WHERE url = ?",
            (dedupe_key(row["title"], row["company"], row["location"]), url),
        )
    removed_n = tombstone_jobs(conn, duplicates)
    if removed_n:
        log.info("Dedupe: %d duplicate postings removed (%d keyed)", removed_n, keyed)
    return {"keyed": keyed, "duplicates": removed_n}
