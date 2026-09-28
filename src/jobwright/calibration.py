"""Optional "rate a few jobs" step after setup: pick scored jobs that teach the scorer most.

Ratings go through the normal label route (``PATCH /api/jobs/{id}`` → ``labels.record_label``),
so they become ``score_labels`` and retrieved examples on the next scoring run.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from jobwright.database import get_connection, job_id_for_url
from jobwright.enrichment.detail import _is_permanent_failure

TARGET = 10
READY_AT = 10
_REASON_CHARS = 160
_BAND_CYCLE = ("mid", "high", "mid", "low")


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _band(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "mid"
    return "low"


def _short_reason(row: dict) -> str:
    text = (row.get("score_reasoning") or "").strip()
    if not row.get("score_gates") and "\n" in text:
        text = text.split("\n", 1)[1].strip()
    text = " ".join(text.split())
    if len(text) <= _REASON_CHARS:
        return text
    cut = text[:_REASON_CHARS]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…"


def _labeled_urls(conn: sqlite3.Connection) -> set[str]:
    latest: dict[str, str] = {}
    for url, verdict in conn.execute("SELECT job_url, verdict FROM score_labels ORDER BY created_at, id"):
        latest[url] = verdict
    return {u for u, v in latest.items() if v != "cleared"}


def rated_count(conn: sqlite3.Connection | None = None) -> int:
    conn = conn or get_connection()
    return len(_labeled_urls(conn))


def _candidates(conn: sqlite3.Connection, exclude: set[str]) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT url, title, company, site, location, fit_score, score_reasoning, score_gates, detail_error, "
        "dedupe_key, discovered_at FROM jobs WHERE fit_score IS NOT NULL AND user_fit_score IS NULL "
        "AND COALESCE(funnel_stage, 'backlog') != 'closed' ORDER BY discovered_at DESC"
    ).fetchall()
    return [
        dict(r) for r in rows
        if r["url"] not in exclude and (r["title"] or "").strip() and not _is_permanent_failure(r["detail_error"])
    ]


def _band_order(band: str, row: dict) -> tuple:
    score = int(row["fit_score"])
    if band == "mid":
        return (abs(score - 6), -score)
    return (-score,)


def select_jobs(rows: list[dict], limit: int = TARGET) -> list[dict]:
    """Mix high, borderline and low scores (borderline twice as often), one per company and title."""
    bands: dict[str, list[dict]] = {"high": [], "mid": [], "low": []}
    for r in rows:
        bands[_band(int(r["fit_score"]))].append(r)
    for band, items in bands.items():
        items.sort(key=lambda r, b=band: _band_order(b, r))

    picked: list[dict] = []
    seen_keys: set[str] = set()
    seen_companies: set[str] = set()
    seen_titles: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    def take(band: str, strict: bool) -> bool:
        for i, r in enumerate(bands[band]):
            company = _norm(r["company"] or r["site"])
            title = _norm(r["title"])
            key = r.get("dedupe_key") or f"{company}|{title}"
            if key in seen_keys or (company, title) in seen_pairs:
                continue
            if strict and (company in seen_companies or title in seen_titles):
                continue
            bands[band].pop(i)
            picked.append(r)
            seen_keys.add(key)
            seen_companies.add(company)
            seen_titles.add(title)
            seen_pairs.add((company, title))
            return True
        return False

    for strict in (True, False):
        stalled = 0
        i = 0
        while len(picked) < limit and stalled < len(_BAND_CYCLE):
            band = _BAND_CYCLE[i % len(_BAND_CYCLE)]
            i += 1
            if take(band, strict):
                stalled = 0
            else:
                stalled += 1
        if len(picked) >= limit:
            break
    return picked


def calibration(conn: sqlite3.Connection | None = None, target: int = TARGET) -> dict[str, Any]:
    conn = conn or get_connection()
    labeled = _labeled_urls(conn)
    scored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL AND COALESCE(funnel_stage, 'backlog') != 'closed'"
    ).fetchone()[0]
    rated = len(labeled)
    remaining = max(0, target - rated)
    picked = select_jobs(_candidates(conn, labeled), remaining) if remaining else []
    return {
        "ready": scored >= READY_AT,
        "scored_count": int(scored),
        "rated_count": rated,
        "target": target,
        "jobs": [
            {
                "job_id": job_id_for_url(r["url"]),
                "url": r["url"],
                "title": r["title"],
                "company": r["company"] or r["site"],
                "location": r["location"],
                "fit_score": int(r["fit_score"]),
                "reason": _short_reason(r),
            }
            for r in picked
        ],
    }
